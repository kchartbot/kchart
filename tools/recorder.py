"""기록 전용: 디시에 아무것도 올리지 않고 매시 멜론 순위와 우리가 계산한 점수·다음 순위 예측을 저장하고, 실제 결과와 비교해 통계를 쌓는다.

저장 위치: 저장소의 livedata 브랜치 (data/ 폴더). 실행: python tools/recorder.py [snap|predict|auto]
 - snap    : 정각 이후(분<30) 멜론 TOP100·HOT100 전체 순위를 저장 → 직전 예측과 비교해 stats.json 갱신 → 계산 점수 저장
 - predict : 50분쯤 다음 정각 TOP100 순위를 예측해 저장 (30·40·50분 3번 하는 써클과 달리 멜론은 정각에만 바뀌므로 한 번이면 충분)
"""
import json, sys, tempfile, statistics as st
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data"
KST = timezone(timedelta(hours=9))

# ── 점수 모델 (tools/hot_stats.py, rt_hot_compare.py 의 표본에서 얻은 값) ──
HOT_BY_RANK = {1: 7.0, 2: 5.615, 3: 4.126, 4: 3.987, 5: 3.678}      # 순위별 중앙값, 1위는 상한
# 시간대별 HOT100÷실시간 배율(백화요란 기준). 2~6시는 표본이 없어 밤 값(1.65)으로 가정
FACTOR = {7: 1.66, 8: 1.90, 9: 1.75, 10: 1.78, 11: 1.85, 12: 1.97, 13: 2.00, 14: 1.98, 15: 2.01, 16: 2.01,
          17: 2.00, 18: 2.00, 19: 2.00, 20: 1.94, 21: 1.88, 22: 1.72, 23: 1.72, 0: 1.66, 1: 1.65}
def factor(h): return FACTOR.get(h, 1.65)


def fetch_rows(key, now):
    from chartbot.fetch import Fetcher
    from chartbot.direct import get_direct_chart
    f = Fetcher(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", min_gap=3.0)
    c = get_direct_chart(key, now, f, tempfile.mkdtemp())
    return [{"rank": r.rank, "previous": r.previous, "name": r.name, "artists": r.artists} for r in c.rows]


def hour_key(dt): return dt.strftime("%Y%m%d-%H00")
def song_key(r): return f"{r['name']}|{','.join(r['artists']) if isinstance(r['artists'], list) else r['artists']}"
def load(p, d=None):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return d
def save(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")


def predict_next(prev_rows, cur_rows):
    """직전 순위 → 지금 순위 흐름을 반만 더 이어 가는 단순 예측. 순위 변화가 없던 곡은 그대로 둔다."""
    pr = {song_key(r): r["rank"] for r in prev_rows or []}
    sc = []
    for r in cur_rows:
        k = song_key(r); p = pr.get(k, r["rank"])
        sc.append((r["rank"] - 0.5 * (p - r["rank"]), r["rank"], k, r))
    sc.sort(key=lambda x: (x[0], x[1]))
    return [{"rank": i + 1, "now": x[1], "name": x[3]["name"], "artists": x[3]["artists"]} for i, x in enumerate(sc)]


def score_ranks(a, b):
    """두 순위표(곡 키→순위) 비교: 평균 순위 오차, 상위 10곡 순서까지 맞은 개수, 상위 10곡 집합 일치 수."""
    common = [k for k in a if k in b]
    if not common: return None
    err = [abs(a[k] - b[k]) for k in common]
    top = lambda d: [k for k, _ in sorted(d.items(), key=lambda kv: kv[1])][:10]
    ta, tb = top(a), top(b)
    return {"곡수": len(common), "평균순위오차": round(st.mean(err), 3), "최대순위오차": max(err),
            "상위10순서일치": sum(1 for x, y in zip(ta, tb) if x == y), "상위10집합일치": len(set(ta) & set(tb))}


def snap(now):
    hk = hour_key(now.replace(minute=0))
    for key, d in (("melon_rank", "top100"), ("melonhot_rank", "hot100")):
        p = DATA / d / f"{hk}.json"
        if p.exists(): continue
        rows = fetch_rows(key, now)
        save(p, {"time": hk, "rows": rows})
    # 직전 예측과 비교
    t = load(DATA / "top100" / f"{hk}.json")
    pred = load(DATA / "predict" / f"{hk}.json")
    stats = load(DATA / "stats.json", {"records": []})
    if t and pred and not any(r["time"] == hk for r in stats["records"]):
        actual = {song_key(r): r["rank"] for r in t["rows"]}
        base = {k: v["now"] for k, v in ((song_key(x), x) for x in pred["predicted"])}      # 변화 없다고 본 경우
        mine = {song_key(x): x["rank"] for x in pred["predicted"]}
        stats["records"].append({"time": hk, "내 예측": score_ranks(mine, actual), "지금 순위 그대로": score_ranks(base, actual)})
        save(DATA / "stats.json", stats)
    # 계산 점수(HOT100 5곡 + 실시간 3곡) 저장
    h = load(DATA / "hot100" / f"{hk}.json")
    if h:
        top5 = h["rows"][:5]
        fac = factor(now.hour)
        hot = {r["name"]: HOT_BY_RANK[r["rank"]] for r in top5}
        save(DATA / "scores" / f"{hk}.json", {
            "time": hk, "HOT100": hot, "factor": fac,
            "실시간": {r["name"]: round(HOT_BY_RANK[r["rank"]] / fac, 3) for r in top5[:3]},
            "참고": "1위는 상한 7.0이라 실시간 1위 값은 하한(실제는 더 클 수 있음). 순위별 중앙값 모델."})


def gaisum_try(now):
    """가이섬 24시간 이용자수 차트를 하루 몇 번만 조심스럽게 시도한다. 막히면(429 등) 기록만 남기고 6시간 쉰다."""
    log = load(DATA / "gaisum_log.json", {"tries": []})
    if now.minute < 5 or (DATA / "users" / f"{hour_key(now.replace(minute=0))}.json").exists():
        return
    last = log["tries"][-1] if log["tries"] else None
    if last and last["ok"] is False and (now - datetime.fromisoformat(last["time"])) < timedelta(minutes=10):
        return
    rec = {"time": now.isoformat(timespec="seconds"), "ok": False, "msg": ""}
    try:
        from chartbot.fetch import Fetcher, get_chart
        f = Fetcher(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", min_gap=5.0, retries=0)
        c = get_chart("melon_24h_count", now, f, tempfile.mkdtemp())
        rows = [{"rank": r.rank, "name": r.name, "artists": r.artists, "count": getattr(r, "count", None),
                 "count1": getattr(r, "count1", None), "count2": getattr(r, "count2", None)} for r in c.rows]
        save(DATA / "users" / f"{hour_key(now.replace(minute=0))}.json", {"time": hour_key(now.replace(minute=0)), "rows": rows})
        rec.update(ok=True, msg=f"{len(rows)}곡")
    except Exception as e:                       # 막혀도 전체 기록은 계속 진행
        rec["msg"] = f"{type(e).__name__}: {str(e)[:120]}"
    log["tries"] = (log["tries"] + [rec])[-60:]
    save(DATA / "gaisum_log.json", log)


def predict(now):
    nxt = now.replace(minute=0) + timedelta(hours=1)
    cur = load(DATA / "top100" / f"{hour_key(now.replace(minute=0))}.json")
    if not cur: print("지금 정각 스냅이 없어 예측 건너뜀"); return
    prev = load(DATA / "top100" / f"{hour_key(now.replace(minute=0) - timedelta(hours=1))}.json")
    pr = predict_next(prev["rows"] if prev else None, cur["rows"])
    save(DATA / "predict" / f"{hour_key(nxt)}.json", {"time": hour_key(nxt), "based_on": cur["time"], "predicted": pr})


RAW = {
    "five": ("https://m2.melon.com/m6/chart/hour/five/graph.json", {"v": "4.0", "cpId": "IS40", "cpKey": "17LNM9"}),
    "fivetop": ("https://m.app.melon.com/chart/hourly/fiveChartGraph.json", {"cpId": "AS40", "cpKey": "14LNC3", "v": "4.0"}),
    "hourtop": ("https://m2.melon.com/chart/hourly/hourlyChartGraph.json", {"appVer": "5.0.4", "cpId": "IS40", "cpKey": "17LNM9", "resolution": "2", "v": "4.0"}),
    "hourgraph": ("https://m2.melon.com/m6/chart/hour/graph.json", {"v": "4.0", "cpId": "IS40", "cpKey": "17LNM9"}),
    "hot100": ("https://m2.melon.com/m6/chart/hot100/list.json", {"chartType": "D100", "cpId": "IS40", "cpKey": "17LNM9", "appVer": "6.22.1"}),
    "hourly": ("https://m.app.melon.com/chart/hourly/hourlyChartList.json", {"cpId": "AS40", "cpKey": "14LNM3", "v": "4.0", "resolution": "2", "appVer": "4.1.0.1", "osVersion": "11", "isRecom": "N", "pageSize": "100"}),
}
EVERY = {"five", "fivetop"}
REPORT = ("https://m2.melon.com/m6/chart/song/chartReport.json", {"cpId": "AS40", "cpKey": "14LNC3", "appVer": "6.2.0"})


def raw_get(url, params):
    import urllib.request, urllib.parse
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def report_lite(o, sid):
    r = (o or {}).get("response") or {}
    si = r.get("SONGINFO") or {}
    rc = r.get("RANKCHART") or {}
    labels = [x.get("XLABEL") for x in rc.get("XLABELS") or []]
    pred = None
    if "예측" in labels:
        i = labels.index("예측")
        pred = next((p.get("VALUE") for p in rc.get("PREDICTEDDATA") or [] if p.get("XINDEX") == i), None)
    v = ((r.get("LISTENERCHART") or {}).get("TITLE") or {}).get("VALUE")
    return {"id": sid, "name": si.get("SONGNAME"), "recent": r.get("RECENTTIME"), "rank": si.get("CURRANK"), "past": si.get("PASTRANK"),
            "listeners": int(v.replace(",", "")) if isinstance(v, str) and v.replace(",", "").isdigit() else None,
            "predicted": pred, "predict_text": (rc.get("TITLE") or {}).get("VALUE")}


def raw(now):
    import time
    stamp = now.strftime("%Y%m%d-%H%M")
    hourly = None
    for name, (url, params) in RAW.items():
        if name not in EVERY and now.minute >= 12 and any((DATA / "raw" / name).glob(f"{stamp[:11]}*.json")):
            continue
        try:
            o = raw_get(url, params)
            save(DATA / "raw" / name / f"{stamp}.json", o)
            if name == "hourly": hourly = o
        except Exception as e:
            print("raw 실패", name, type(e).__name__, str(e)[:100])
        time.sleep(2)
    if hourly is None:
        fs = sorted((DATA / "raw" / "hourly").glob("*.json"))
        hourly = load(fs[-1]) if fs else None
    ids = [str(x["SONGID"]) for x in ((hourly or {}).get("response") or {}).get("CHARTLIST", [])]
    n = 100 if now.minute % 10 < 5 else 0
    rows = []
    for k, sid in enumerate(ids[:n]):
        try:
            o = raw_get(REPORT[0], {**REPORT[1], "songId": sid})
            rows.append(report_lite(o, sid))
            if k < 5:
                save(DATA / "raw" / "report" / f"{stamp}-{sid}.json", o)
        except Exception as e:
            print("raw 실패 report", sid, type(e).__name__, str(e)[:100])
        time.sleep(1)
    if rows:
        save(DATA / "raw" / "reportlite" / f"{stamp}.json", {"stamp": stamp, "n": n, "rows": rows})


def derive():
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import derive as d
        d.run(DATA)
    except Exception as e:
        print("derive 실패", type(e).__name__, str(e)[:100])


def push():
    import subprocess
    live = str(DATA.parent)
    subprocess.run(["git", "-C", live, "add", "-A", "data"], check=False)
    if subprocess.run(["git", "-C", live, "diff", "--cached", "--quiet"]).returncode == 0:
        return
    subprocess.run(["git", "-C", live, "commit", "-qm", "기록 " + datetime.now(timezone.utc).strftime("%FT%TZ")], check=False)
    for _ in range(3):
        if subprocess.run(["git", "-C", live, "push", "-q", "origin", "livedata"]).returncode == 0:
            return
        subprocess.run(["git", "-C", live, "pull", "-q", "--rebase", "origin", "livedata"], check=False)


def cycle(now):
    (snap if now.minute < 30 else predict)(now)
    raw(now)
    derive()


def loop(minutes):
    import time
    end = datetime.now(KST) + timedelta(minutes=minutes)
    while True:
        now = datetime.now(KST).replace(tzinfo=None)
        try:
            cycle(now)
            push()
        except Exception as e:
            print("주기 실패", type(e).__name__, str(e)[:100])
        cur = datetime.now(KST)
        nxt = cur.replace(second=20, microsecond=0) + timedelta(minutes=(1 - cur.minute) % 5 or 5)
        if nxt >= end:
            break
        time.sleep(max(0, (nxt - cur).total_seconds()))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    now = datetime.now(KST).replace(tzinfo=None)
    if mode == "loop":
        loop(int(sys.argv[3]) if len(sys.argv) > 3 else 20)
        sys.exit(0)
    if mode == "auto": mode = "snap" if now.minute < 30 else "predict"
    print("모드", mode, now)
    if mode == "raw": raw(now)
    else:
        (snap if mode == "snap" else predict)(now)
        raw(now)
    derive()
