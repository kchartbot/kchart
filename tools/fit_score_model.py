"""지금까지 모은 점수 표본으로 근사 모델을 맞추고 오차를 계산한다.
표본: 써클차트 글에서 옮겨 적은 값 + samples/ 의 가이섬 실측 파일."""
import json, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 써클차트 00:00 실시간 그래프 글 (1시간 단위, 0·1·7~23·0시)
G = {
    "With": [5.04218, 4.509, 5.17701, 5.84885, 5.30164, 4.61711, 3.94428, 3.58605, 3.74009, 3.73503, 3.61451, 3.66414, 3.79629, 4.35557, 4.45227, 4.37305, 4.57231, 4.43245, 4.60426, 4.612],
    "백화요란": [3.64365, 3.6, 3.46034, 3.52729, 3.48163, 3.256, 2.88437, 2.63776, 2.61792, 2.60792, 2.51816, 2.56686, 2.61716, 2.8818, 2.89482, 2.84072, 3.03156, 3.13503, 3.40113, 3.47],
    "LOVE ATTACK": [None, 2.697, 2.813, 2.699, 2.692, 2.715, 2.59971, 2.475, 2.47, 2.44338, 2.447, 2.52684, 2.55, 2.522, 2.718, 2.707, 2.5949, 2.70058, 2.7244, 2.742],
}
# 써클차트 00:35 멜론 5분 차트 글 (00:00~00:35, 5분 단위)
F = {
    "With": [4.6122, 8.534, 5.53446, 5.05966, 5.42105, 5.02044, 4.91715, 4.71615],
    "Finest Thing": [2.70569, 1.64879, 1.69005, 1.79236, 1.81724, 2.55311, 2.52363, 3.2143],
    "백화요란": [3.47017, 2.52498, 3.81619, 3.58045, 3.34085, 3.21918, 3.18056, 3.06492],
}


def columns(series):
    """시점마다 값을 큰 순서로 늘어놓은 목록."""
    n = max(len(v) for v in series.values())
    for i in range(n):
        vals = sorted((v[i] for v in series.values() if i < len(v) and v[i]), reverse=True)
        if len(vals) >= 2:
            yield vals


def sample_files():
    for name in ("melon-realtime-five.json", "melon-hot100-five.json", "melon-hot100-graph.json"):
        d = json.loads((ROOT / "samples" / name).read_text(encoding="utf-8"))
        rows = d["data"]
        n = len(rows[0]["values"])
        for i in range(n):
            vals = sorted((r["values"][i] for r in rows if r["values"][i]), reverse=True)
            if len(vals) >= 3:
                yield name, vals


def fit():
    obs = {2: [], 3: [], 4: [], 5: []}
    src = {2: {}, 3: {}}
    for tag, cols in (("써클 그래프", list(columns(G))), ("써클 5분", list(columns(F)))):
        for vals in cols:
            for k in obs:
                if len(vals) >= k:
                    obs[k].append(vals[k - 1] / vals[0])
                    if k in src:
                        src[k].setdefault(tag, []).append(vals[k - 1] / vals[0])
    for name, vals in sample_files():
        for k in obs:
            if len(vals) >= k:
                obs[k].append(vals[k - 1] / vals[0])
                if k in src:
                    src[k].setdefault(name, []).append(vals[k - 1] / vals[0])
    ratios = {k: st.median(v) for k, v in obs.items() if v}
    return ratios, obs, src


if __name__ == "__main__":
    r, obs, src = fit()
    print("순위별 비율(1위=1, 표본 전체 중앙값):", {k: round(v, 4) for k, v in r.items()})
    for k in obs:
        v = obs[k]
        err = [abs(x - r[k]) / x for x in v]
        print(f"  {k}위: 표본 {len(v)}개, 비율 범위 {min(v):.3f}~{max(v):.3f}, 평균오차 {st.mean(err)*100:.1f}% 최대 {max(err)*100:.1f}%")
    for k in (2, 3):
        print(f"  {k}위 표본별 중앙값:", {t: round(st.median(x), 3) for t, x in src[k].items()})
