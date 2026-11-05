#!/usr/bin/env python3
"""차트봇 실행기.

  python run.py render [--only 키]   샘플 데이터로 디자인만 확인 (네트워크/로그인 불필요)
  python run.py login                디시 로그인 창 열기 (1회)
  python run.py export-session       로그인 상태를 dc_session.json 으로 내보내기 (GitHub Actions 용)
  python run.py once                 지금 시점 차트를 수집 -> 렌더 -> (dry_run 이 아니면) 업로드
  python run.py loop                 5분 주기로 반복 (5분 차트는 매번, 나머지는 시간당 1회)
  옵션: --config config.toml  --headed
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from datetime import timedelta

from chartbot.dcinside import DcUploader, HumanCheckRequired, UploadFailed
from chartbot.fetch import SPECS, Fetcher, RateLimited, get_chart, resolve
from chartbot.direct import ensure_snapshot
from chartbot.samples import SampleFetcher, seed_sample_history
from chartbot.render import body_text, embed_images, png_scale, post_title, render_html, render_png

ROOT = Path(__file__).parent
KST = ZoneInfo("Asia/Seoul")
log = logging.getLogger("chartbot")


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        sys.exit(f"설정 파일이 없습니다: {p}  (config.example.toml 을 복사해서 만드세요)")
    cfg = tomllib.loads(p.read_text(encoding="utf-8"))
    # 환경변수로 덮어쓰기 (GitHub Actions 의 Variables/Secrets 용). 설정 파일에는 민감한 값을 두지 않는다.
    if os.environ.get("DC_GALLERY_ID"):
        cfg.setdefault("dc", {})["gallery_id"] = os.environ["DC_GALLERY_ID"]
    if "DC_HEADTEXT" in os.environ:  # 빈 값이면 말머리 선택 생략
        cfg.setdefault("dc", {})["headtext"] = os.environ["DC_HEADTEXT"].strip()
    if os.environ.get("DC_MINOR"):
        cfg.setdefault("dc", {})["minor"] = os.environ["DC_MINOR"].lower() == "true"
    if os.environ.get("DRY_RUN"):
        cfg["bot"]["dry_run"] = os.environ["DRY_RUN"].lower() != "false"
    return cfg


def make_uploader(cfg, headed):
    dc = cfg["dc"]
    state_file = None
    if os.environ.get("DC_STORAGE_STATE") or os.environ.get("DC_ID"):
        # 세션(쿠키) 파일 위치. out/ 은 실행 사이에 캐시되므로 한 번 로그인하면 이후 실행에서 재사용된다.
        out_dir = Path(cfg["bot"].get("out_dir", ROOT / "out"))
        out_dir.mkdir(parents=True, exist_ok=True)
        state_file = str(out_dir / ".dc_session.json")
        # 시크릿의 계정이 바뀌면 캐시에 남은 예전 계정의 로그인 상태는 버린다
        import hashlib

        who = hashlib.sha256((os.environ.get("DC_ID") or "state").strip().encode()).hexdigest()[:16]
        marker = out_dir / ".dc_session.who"
        if marker.exists() and marker.read_text().strip() != who:
            Path(state_file).unlink(missing_ok=True)
            log.info("로그인 계정이 바뀌어 저장된 로그인 상태를 지웠습니다")
        marker.write_text(who)
        if os.environ.get("DC_STORAGE_STATE") and not Path(state_file).exists():
            fd = os.open(state_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(os.environ["DC_STORAGE_STATE"])
    return DcUploader(storage_state=state_file, login_id=os.environ.get("DC_ID"), login_pw=os.environ.get("DC_PW"),
        anon_nick=os.environ.get("DC_ANON_NICK"), anon_pw=os.environ.get("DC_ANON_PW"),
        gallery_id=dc["gallery_id"], headtext=dc.get("headtext", "차트봇"), profile_dir=dc.get("profile_dir", "~/.chartbot/profile"),
        selectors=dc.get("selectors"), minor=dc.get("minor", True), headed=headed,
    )


def process(key, cfg, fetcher, uploader, state, out):
    spec = resolve(key)
    b = cfg["bot"]
    # 가이섬은 한국시간 기준이라, 서버 시계/타임존과 무관하게 KST 로 시각을 계산한다
    now = datetime.now(KST).replace(tzinfo=None)

    # 사람 확인 요구를 받은 뒤에는 일정 시간 게시(와 그를 위한 수집)를 쉰다
    paused = state.get("dc_pause_until")
    if not b.get("dry_run", True) and paused and now < datetime.fromisoformat(paused):
        log.info("디시 게시 일시중지 중 (%s 까지), 건너뜀", paused)
        return

    if spec.cadence == "hourly":
        # 시간당 1회: 정시 직후엔 가이섬 갱신 전일 수 있어 hourly_after_minute 이후에만 시도하고,
        # 이미 올린 시간대면 요청 자체를 하지 않는다.
        # (직접 수집 차트는 사이트가 이미 최신이라 기다릴 필요가 없다. 수동 실행/밀린 스케줄에서도 바로 올라가게 한다)
        if spec.source != "direct" and now.minute < int(b.get("hourly_after_minute", 5)):
            return
        if state.get(spec.key) == f"{now:%Y%m%d%H}00":
            return

    chart = get_chart(spec.key, now, fetcher, cache_dir=out / "cache")
    stamp = f"{chart.stamp:%Y%m%d%H%M}"
    if state.get(spec.key) == stamp:
        log.info("%s %s 이미 처리함, 건너뜀", spec.key, stamp)
        return

    images = embed_images(chart, fetcher, out / "cache", budget=int(b.get("image_budget", 30)), gap=float(b.get("image_gap", 1.0)),
                         size=400 if spec.layout == "table_users" else (None if spec.source == "direct" else 80))
    html = render_html(chart, images)
    png = out / f"{spec.key}_{stamp}.png"
    (out / f"{spec.key}_{stamp}.html").write_text(html, encoding="utf-8")
    render_png(html, png, png_scale(chart))
    title, body = post_title(chart), body_text(chart)
    if b.get("dry_run", True):
        log.info("[dry-run] 업로드 생략: %s -> %s", title, png)
    else:
        try:
            uploader.post(title, body, png, out)
        except HumanCheckRequired:
            state["dc_pause_until"] = (now + timedelta(hours=int(b.get("pause_hours_on_human_check", 6)))).isoformat()
            raise
        log.info("업로드 완료: %s", title)
    state[spec.key] = stamp
    for f in sorted(out.glob(f"{spec.key}_2*"))[:-6]:  # 오래된 산출물 정리 (최근 3회분 png+html 유지)
        f.unlink(missing_ok=True)


def collect_direct(cfg, fetcher, out):
    """직접 수집 차트가 하나라도 있는 플랫폼은 올릴 차트가 없는 주기에도 순위를 기록해 둔다 (그래프용 기록)."""
    now = datetime.now(KST).replace(tzinfo=None)
    for platform in dict.fromkeys(resolve(k).platform for k in cfg["bot"]["charts"] if resolve(k).source == "direct"):
        try:
            ensure_snapshot(platform, now, fetcher, out / "rank")
        except RateLimited:
            raise
        except Exception:
            log.exception("%s 순위 수집 실패", platform)


def run_cycle(cfg, fetcher, uploader, state, out):
    try:
        collect_direct(cfg, fetcher, out)
    except RateLimited as e:
        log.error("%s — 이번 주기를 중단합니다.", e)
        return
    for key in cfg["bot"]["charts"]:
        try:
            process(key, cfg, fetcher, uploader, state, out)
        except RateLimited as e:
            log.error("%s — 이번 주기의 나머지 요청을 중단합니다. 이 환경(IP)에서 가이섬 접근이 막혀 있을 수 있습니다.", e)
            break
        except UploadFailed:
            log.exception("%s 업로드 실패 — 이번 주기의 나머지 업로드를 중단합니다.", key)
            break
        except Exception:
            log.exception("%s 처리 실패 (다음 차트로 계속)", key)
    (out / "state.json").write_text(json.dumps(state), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render", "login", "export-session", "once", "loop"])
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    ap.add_argument("--headed", action="store_true", help="업로드 시 브라우저 창을 보이게")
    ap.add_argument("--only", help="render 에서 특정 차트 키만")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if a.cmd == "render":
        a_only = a.only
        out = ROOT / "out"
        out.mkdir(exist_ok=True)
        sf = SampleFetcher(ROOT / "samples")
        for key, spec in SPECS.items():
            if a_only and resolve(a_only).key != key:
                continue
            # 샘플 파일의 시각을 "지금"으로 보고 운영과 같은 경로(get_chart -> 이력 수집 -> 렌더)로 그린다
            if spec.source == "direct":
                sample_time = datetime(2026, 11, 5, 14, 35)
                sdir = out / "rank_sample"
                seed_sample_history(spec.platform, sample_time, sf, sdir / "rank")
                c = get_chart(key, sample_time, sf, cache_dir=sdir / "cache")
            else:
                sample_time = datetime.fromisoformat(json.loads((ROOT / "samples" / f"{spec.platform}-{spec.path}.json").read_text(encoding="utf-8"))["time"])
                c = get_chart(key, sample_time, sf, cache_dir=None)
            h = render_html(c)
            (out / f"{key}.html").write_text(h, encoding="utf-8")
            render_png(h, out / f"{key}.png", png_scale(c))
            print("생성:", out / f"{key}.png")
        return

    cfg = load_config(a.config)
    for k in cfg["bot"]["charts"]:
        resolve(k)  # 잘못된 키는 시작할 때 바로 알려준다
    out = Path(cfg["bot"].get("out_dir", ROOT / "out"))
    out.mkdir(parents=True, exist_ok=True)
    uploader = make_uploader(cfg, a.headed)

    if a.cmd == "login":
        uploader.login()
        return
    if a.cmd == "export-session":
        target = ROOT / "dc_session.json"
        uploader.export_session(str(target))
        print(f"저장했습니다: {target}\n이 파일의 내용 전체를 GitHub Secrets 의 DC_STORAGE_STATE 에 넣고, 파일은 지우세요 (비밀번호와 같은 값입니다).")
        return

    b = cfg["bot"]
    fetcher = Fetcher(user_agent=b.get("user_agent", "chartbot/1.0"), min_gap=b.get("min_request_gap", 3.0))
    sf = out / "state.json"
    state = json.loads(sf.read_text()) if sf.exists() else {}

    if a.cmd == "once":
        run_cycle(cfg, fetcher, uploader, state, out)
        return

    interval = int(b.get("interval_minutes", 5)) * 60
    delay = int(b.get("delay_seconds", 20))  # 정각 직후엔 사이트 갱신 전일 수 있어 약간 늦춰서 실행
    log.info("loop 시작: %d분 주기, 정각+%d초에 실행, dry_run=%s, 차트=%s", interval // 60, delay, b.get("dry_run", True), b["charts"])
    while True:
        now = time.time()
        nxt = (now // interval + 1) * interval + delay
        time.sleep(max(0, nxt - now))
        run_cycle(cfg, fetcher, uploader, state, out)


if __name__ == "__main__":
    main()
