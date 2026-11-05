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
    gaisum_try(now)                              # 이용자수: 열려 있을 때만 저장됨
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
    last = log["tries"][-1] if log["tries"] else None
    if last and last["ok"] is False and (now - datetime.fromisoformat(last["time"])) < timedelta(hours=6):
        return
    if last and last["ok"] and (now - datetime.fromisoformat(last["time"])) < timedelta(minutes=50):
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


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    now = datetime.now(KST).replace(tzinfo=None)
    if mode == "auto": mode = "snap" if now.minute < 30 else "predict"
    print("모드", mode, now)
    (snap if mode == "snap" else predict)(now)
