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
import random
import time
import json
import logging
import os
import sys
import time
import tomllib
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from chartbot.dcinside import DcUploader, UploadFailed
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
    if os.environ.get("DC_KIND"):
        cfg.setdefault("dc", {})["kind"] = os.environ["DC_KIND"].strip()
    if os.environ.get("DC_MINOR"):
        cfg.setdefault("dc", {})["minor"] = os.environ["DC_MINOR"].lower() == "true"
    if os.environ.get("CHARTS", "").strip():
        cfg["bot"]["charts"] = [c.strip() for c in os.environ["CHARTS"].split(",") if c.strip()]
    if os.environ.get("CHART_FORCE", "").lower() == "true":
        cfg["bot"]["force"] = True
    if os.environ.get("MAX_POSTS", "").strip().isdigit():
        cfg["bot"]["max_posts"] = int(os.environ["MAX_POSTS"])
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
        kind=dc.get("kind"),
    )


_LAST_POST = [0.0]


def prepare(key, cfg, fetcher, out, state):
    """차트를 받아 이미지(PNG)와 제목·본문까지 만든다. 올리지는 않는다. 올릴 게 없으면 None."""
    spec = resolve(key)
    b = cfg["bot"]
    # 가이섬은 한국시간 기준이라, 서버 시계/타임존과 무관하게 KST 로 시각을 계산한다
    now = datetime.now(KST).replace(tzinfo=None)

    if spec.cadence == "hourly":
        # 1시간 단위 차트는 정시(02:00, 03:00 …)부터 hourly_window_minutes 분 안에서만 올린다.
        # 그 밖의 시각(예: 02:37)에 실행해도 올리지 않는다. (force 로 시험할 때만 예외)
        if not b.get("force") and now.minute >= int(b.get("hourly_window_minutes", 15)):
            log.info("%s 정시 창(%d분) 밖이라 건너뜀 (%s)", spec.key, int(b.get("hourly_window_minutes", 15)), f"{now:%H:%M}")
            return None
        # 시간당 1회: 정시 직후엔 가이섬 갱신 전일 수 있어 hourly_after_minute 이후에만 시도하고,
        # 이미 올린 시간대면 요청 자체를 하지 않는다.
        # (직접 수집 차트는 사이트가 이미 최신이라 기다릴 필요가 없다. 수동 실행/밀린 스케줄에서도 바로 올라가게 한다)
        if spec.source != "direct" and now.minute < int(b.get("hourly_after_minute", 5)):
            return None
        if state.get(spec.key) == f"{now:%Y%m%d%H}00":
            return None

    chart = get_chart(spec.key, now, fetcher, cache_dir=out / "cache")
    stamp = f"{chart.stamp:%Y%m%d%H%M}"
    if state.get(spec.key) == stamp:
        log.info("%s %s 이미 처리함, 건너뜀", spec.key, stamp)
        return None

    size = 400 if spec.layout == "table_users" else (None if spec.source == "direct" else 80)
    budget, gap = int(b.get("image_budget", 30)), float(b.get("image_gap", 1.0))
    images = embed_images(chart, fetcher, out / "cache", budget=budget, gap=gap, size=size)
    missing = [r for r in chart.rows if r.image and r.image not in images]
    if missing:   # 못 받은 앨범 이미지는 한 번 더 시도 (커버가 빠지지 않게)
        images = embed_images(chart, fetcher, out / "cache", budget=budget, gap=gap, size=size)
        missing = [r for r in chart.rows if r.image and r.image not in images]
        if missing:
            log.warning("%s 앨범 이미지 %d곡 못 받음: %s", spec.key, len(missing), ", ".join(f"{r.rank}위" for r in missing[:10]))
    html = render_html(chart, images)
    png = out / f"{spec.key}_{stamp}.png"
    (out / f"{spec.key}_{stamp}.html").write_text(html, encoding="utf-8")
    render_png(html, png, png_scale(chart))
    title, body = post_title(chart), body_text(chart)
    if b.get("dry_run", True):
        log.info("[dry-run] 업로드 생략: %s -> %s", title, png)
        return None
    return {"key": spec.key, "stamp": stamp, "title": title, "body": body, "png": png}


def publish(job, cfg, uploader, state, out):
    """준비된 글 하나를 올린다. 글 사이 간격은 앞 글이 시작된 시각 기준(post_gap_seconds)이라 업로드 시간이 간격에 포함된다."""
    b = cfg["bot"]
    _g = [float(x) for x in str(b.get("post_gap_seconds", "20-30")).split("-")]
    gap = random.uniform(_g[0], _g[-1])
    wait = _LAST_POST[0] + gap - time.monotonic()
    if _LAST_POST[0] and wait > 0:
        log.info("이전 글과 간격을 두기 위해 %.0f초 대기", wait)
        time.sleep(wait)
    _LAST_POST[0] = time.monotonic()
    uploader.post(job["title"], job["body"], job["png"], out)
    log.info("업로드 완료: %s (%s)", job["title"], f"{datetime.now(KST):%H:%M:%S}")
    state[job["key"]] = job["stamp"]
    for f in sorted(out.glob(f"{job['key']}_2*"))[:-6]:  # 오래된 산출물 정리 (최근 3회분 png+html 유지)
        f.unlink(missing_ok=True)


def _kst():
    return datetime.now(KST).replace(tzinfo=None)


def prewarm(cfg, fetcher, out, deadline):
    """정각 전에 미리: 직전 순위를 저장하고 앨범 이미지를 캐시에 받아 둔다 (정각엔 새로 받을 이미지를 줄이려고)."""
    b = cfg["bot"]
    for key in b["charts"]:
        left = (deadline - _kst()).total_seconds()
        if left <= 0:
            break
        try:
            spec = resolve(key)
            chart = get_chart(key, _kst(), fetcher, cache_dir=out / "cache")
            gap = float(b.get("image_gap", 1.0))
            budget = int(min(int(b.get("image_budget", 30)), max(0, left / max(gap, 0.5))))
            embed_images(chart, fetcher, out / "cache", budget=budget, gap=gap,
                         size=400 if spec.layout == "table_users" else (None if spec.source == "direct" else 80))
        except Exception:
            log.exception("%s 미리 준비 실패 (정각에 다시 시도)", key)


def wait_until(target):
    while True:
        left = (target - _kst()).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 5) if left > 5 else max(left, 0.02))


def precise_wait(cfg, fetcher, out):
    """정각 전에 시작한 실행: 이미지 등 준비를 끝내 두고 정각까지 기다린다. 이어서 run_cycle 이 첫 차트(TOP100)부터 올린다."""
    b = cfg["bot"]
    top = (b.get("charts") or [None])[0]
    now = _kst()
    lead = int(b.get("precise_lead_minutes", 12))
    if not top or b.get("force") or now.minute < 60 - lead:
        return
    target = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    log.info("정각(%s)에 맞춰 올리려고 준비합니다", f"{target:%H:%M}")
    prewarm(cfg, fetcher, out, target - timedelta(seconds=45))
    wait_until(target)
    # 정각 직후 사이트가 아직 직전 시간 순위를 보여 줄 수 있어, 직전 저장본과 같으면 몇 초씩 기다려 본다 (최대 90초)
    spec = resolve(top)
    if spec.source == "direct":
        from chartbot.direct import PARSERS, urls
        prev = None
        try:
            prev = json.loads((out / "rank" / f"{spec.platform}.json").read_text(encoding="utf-8"))["latest"]["rows"]
        except Exception:
            pass
        sig = lambda rows: [(r["sid"], r["rank"]) for r in rows]
        t0 = time.monotonic()
        while prev and time.monotonic() - t0 < 90:
            try:
                fetcher._last = 0.0
                cur = PARSERS[spec.platform](fetcher.get(urls(spec.platform, _kst())[0]))
            except Exception:
                break
            if sig(cur) != sig(prev):
                break
            log.info("%s 아직 갱신 전 (직전 순위와 동일) — 5초 뒤 다시 확인", top)
            time.sleep(5)
        fetcher._last = 0.0


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
    """준비 스레드가 차트를 차례로 만들어 두고(수집·이미지·렌더), 메인은 만들어진 것부터 간격을 두고 올린다.
    첫 글(TOP100)을 올리는 동안 나머지가 이미 준비되므로 글 사이 대기가 업로드 시간뿐이다."""
    import queue
    import threading
    b = cfg["bot"]
    limit = int(b.get("max_posts", 1))  # 한 번 실행에 올리는 글 수
    q, stop = queue.Queue(), threading.Event()

    def worker():
        try:
            for n, key in enumerate(b["charts"]):
                if stop.is_set():
                    break
                try:
                    job = prepare(key, cfg, fetcher, out, state)
                    if job:
                        q.put(job)
                except RateLimited as e:
                    log.error("%s — 이번 주기의 나머지 요청을 중단합니다. 이 환경(IP)에서 가이섬 접근이 막혀 있을 수 있습니다.", e)
                    break
                except Exception:
                    log.exception("%s 준비 실패 (다음 차트로 계속)", key)
                if n == 0:
                    try:
                        collect_direct(cfg, fetcher, out)   # 올리지 않는 플랫폼도 순위를 기록해 둔다 (그래프용)
                    except RateLimited as e:
                        log.error("%s — 이번 주기를 중단합니다.", e)
                        break
        finally:
            q.put(None)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    posted = 0
    while True:
        job = q.get()
        if job is None:
            break
        if stop.is_set():
            continue
        if posted >= limit:
            log.info("이번 실행의 게시 한도(%d개)에 도달, 나머지는 다음 실행에서 처리", limit)
            stop.set()
            continue
        try:
            publish(job, cfg, uploader, state, out)
            posted += 1
            (out / "state.json").write_text(json.dumps(state), encoding="utf-8")
        except UploadFailed:
            log.exception("%s 업로드 실패 — 이번 주기의 나머지 업로드를 중단합니다.", job["key"])
            stop.set()
        except Exception:
            log.exception("%s 처리 실패 (다음 차트로 계속)", job["key"])
    t.join(timeout=5)
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
    import chartbot.render as _render
    _render.RANK_STYLE = os.environ.get("RANK_STYLE") or b.get("rank_style", "classic")
    fetcher = Fetcher(user_agent=b.get("user_agent", "chartbot/1.0"), min_gap=b.get("min_request_gap", 3.0))
    sf = out / "state.json"
    state = json.loads(sf.read_text()) if sf.exists() else {}

    if a.cmd == "once":
        if b.get("precise_top", False):
            precise_wait(cfg, fetcher, out)
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
