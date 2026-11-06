"""차트를 새 디자인의 HTML / PNG 로 렌더링하고, 게시글 본문 텍스트를 만든다.

레이아웃
  five / graph24  선 그래프 (상위 3곡, y축 점수 · x축 시각 · 하단 범례)
  table           단순 표 (순위 · 변동 · 곡)           2단 구성
  table_counts    이용자 수치 포함 표 (TOP100)         이용자 수치가 비어 있으면 table 로 대체
  table_users     24시간 이용자 수: 곡별 24시간 표를 나란히 (시간 · 순위 · T100 · 이용자수 · 증감)
"""
from __future__ import annotations

import base64
import hashlib
import html
import math
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

from .fetch import SOURCE_CREDIT, Chart, Fetcher
from .history import NIGHT

SPARK_W, SPARK_H, PAD = 240, 44, 6


# ───────────────────────── 공통 도우미 ─────────────────────────
def _fmt(v):
    return "-" if not v else f"{v:.5f}".rstrip("0").rstrip(".")


def _num(n):
    return "-" if n is None else f"{n:,}"


def _signed(n):
    if n is None or n == 0:
        return "–", "flat"
    return (f"▲ {n:,}", "up") if n > 0 else (f"▼ {abs(n):,}", "down")


def _rank_change(rank, prev):
    """순위 변동. previous 가 없거나 0 이면 신규 진입."""
    if not prev:
        return "NEW", "new"
    d = prev - rank
    if d > 0:
        return f"▲{d}", "up"
    if d < 0:
        return f"▼{-d}", "down"
    return "–", "flat"


def _art(r, images):
    img = images.get(r.image)
    return f'<img src="{img}" alt="">' if img else html.escape(r.name[:1] or "♪")


def _wd(dt):
    return "월화수목금토일"[dt.weekday()]


def embed_images(chart: Chart, fetcher: Fetcher, cache_dir: Path, budget: int = 30, gap: float = 1.0, size: int | None = 80) -> dict:
    """앨범 이미지를 받아 로컬에 캐시하고 data URI 로 돌려준다.

    CDN 부하를 줄이기 위해 (1) 한 번 받은 이미지는 다시 받지 않고, (2) 한 번 실행에서 새로 받는 장수를
    budget 으로 제한하며, (3) 요청 사이에 gap 초를 둔다. 못 받은 곡은 첫 글자 타일로 표시되고 다음 주기에 채워진다.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    out, fetched = {}, 0
    for url in dict.fromkeys(r.image for r in chart.rows if r.image):
        f = cache_dir / (hashlib.sha1(f"{url}|{size}".encode()).hexdigest() + ".bin")
        try:
            if not f.exists():
                if fetched >= budget:
                    continue
                if fetched:
                    time.sleep(gap)
                fetched += 1
                full = url if size is None else url + ("&" if "?" in url else "?") + f"size={size}"
                req = urllib.request.Request(full, headers={"User-Agent": fetcher.ua})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    f.write_bytes(resp.read())
            out[url] = "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
        except Exception:
            continue
    return out


def upgrade_covers(images: dict, rows, n: int = 3, size: int = 500, timeout: int = 10) -> int:
    """1~n위 앨범 커버를 더 큰 버전으로 바꿔 받는다 (멜론 이미지 주소의 /resize/120/ → /resize/500/). 못 받으면 원래 작은 이미지를 그대로 쓴다."""
    import re
    done = 0
    for r in rows[:n]:
        url = r.image or ""
        if not url or "/resize/" not in url:
            continue
        big = re.sub(r"/resize/\d+/", f"/resize/{size}/", url)
        if big == url:
            continue
        try:
            req = urllib.request.Request(big, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if len(data) > 5000:
                images[url] = "data:image/jpeg;base64," + base64.b64encode(data).decode()
                done += 1
        except Exception:
            continue
    return done


# ───────────────────────── 스타일 ─────────────────────────
CSS = """
:root{--bg:#ffffff;--card:#ffffff;--card2:#f5f3ee;--text:#1c2230;--muted:#8a8f9c;--rule:#e6e2d8;--line:#3f5bd0;
--up:#d6453d;--down:#2f6fd0;--accent:#a07c26;--ink:#141a2b}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--text);width:1080px;padding:44px 40px 30px;
font-family:'Pretendard','Noto Sans KR','Noto Sans CJK KR','Noto Sans CJK TC','Malgun Gothic',sans-serif}
header{display:flex;justify-content:space-between;align-items:flex-end;padding-bottom:18px;margin-bottom:22px;
border-bottom:1px solid var(--ink);position:relative}
header:after{content:"";position:absolute;left:0;bottom:-4px;width:64px;height:3px;background:var(--accent)}
h1{font-size:34px;font-weight:800;letter-spacing:-.02em;color:var(--ink)}
.sub{color:var(--muted);font-size:16px;margin-top:6px;letter-spacing:.01em}
.stamp{font-size:40px;font-weight:300;color:var(--ink);font-variant-numeric:tabular-nums;letter-spacing:.01em}
.stamp small{display:block;font-size:13px;font-weight:600;color:var(--accent);text-align:right;letter-spacing:.2em}
footer{display:flex;justify-content:space-between;gap:20px;color:var(--muted);font-size:13px;margin-top:22px;
padding-top:12px;border-top:1px solid var(--rule)}
.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--muted)}.new{color:var(--accent)}
.art{background:var(--card2);overflow:hidden;display:flex;align-items:center;justify-content:center;font-weight:700;color:var(--muted)}
.art img{width:100%;height:100%;object-fit:cover;display:block}
.name,.artist{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.artist{color:var(--muted)}

/* 선 그래프 */
.lc{width:100%;display:block}
.lc text{font-family:'Pretendard','Noto Sans KR','Noto Sans CJK KR',sans-serif;fill:#4a5060}
.legend{display:flex;flex-wrap:wrap;justify-content:center;gap:8px 26px;margin-top:10px;font-size:16px;color:var(--text)}
.legend span{display:inline-flex;align-items:center;gap:8px}
.legend i{display:inline-block;width:26px;height:3px;border-radius:2px}
.legend b{font-weight:600}

/* 표형 (2단) */
.cols{display:grid;grid-template-columns:1fr 1fr;gap:0 36px}
.t{display:grid;grid-template-columns:34px 46px 40px minmax(0,1fr);gap:10px;align-items:center;
border-bottom:1px solid var(--rule);padding:6px 4px}
.t>div{min-width:0}
.t .rank{font-size:18px;font-weight:700;text-align:center;font-variant-numeric:tabular-nums;color:var(--ink)}
.t.top .rank{color:var(--accent);font-size:20px;font-weight:800}
.t .chg{font-size:12.5px;font-weight:700;text-align:center;font-variant-numeric:tabular-nums}
.t .art{width:40px;height:40px;border-radius:6px;font-size:16px}
.t .name{font-size:16px;font-weight:700;color:var(--ink)}
.t .artist{font-size:12.5px;margin-top:1px}

/* 이용자 수치 표 (TOP100) */
.tc{display:grid;grid-template-columns:44px 56px 44px minmax(0,1fr) 130px 130px;gap:12px;align-items:center;
border-bottom:1px solid var(--rule);padding:6px 8px}
.tc>div{min-width:0}
.tc.head{color:var(--accent);font-size:12.5px;font-weight:700;letter-spacing:.08em;border-bottom:1px solid var(--ink)}
.tc.head div:nth-child(n+5){text-align:right}
.tc .rank{font-size:19px;font-weight:700;text-align:center;font-variant-numeric:tabular-nums;color:var(--ink)}
.tc.top .rank{color:var(--accent);font-weight:800}
.tc .chg{font-size:13px;font-weight:700;text-align:center}
.tc .art{width:44px;height:44px;border-radius:6px;font-size:17px}
.tc .name{font-size:17px;font-weight:700;color:var(--ink)}
.tc .artist{font-size:13px}
.tc .cnt{font-size:17px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}
.tc .cnt small{display:block;font-size:12px;font-weight:700}

/* 24시간 이용자 수 (곡별 표) */
.ugrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:36px;align-items:start}
.ublk{background:transparent}
.ucov{width:100%;aspect-ratio:1/1;background:linear-gradient(135deg,#e9e6df,#d8d4ca);overflow:hidden;margin-bottom:16px}
.ucov img{width:100%;height:100%;object-fit:cover;display:block}
.uhead{padding:0 2px 14px;border-bottom:1px solid var(--ink)}
.uhead b{display:block;font-size:22px;font-weight:700;color:var(--ink);letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.uhead .ar{font-size:13px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
.uhead .pk{font-size:13px;color:var(--text);margin-top:10px;font-variant-numeric:tabular-nums}
.uhead .pk em{font-style:normal;font-weight:700}
.uhead .rg{font-size:12px;color:var(--muted);margin-top:2px}
.hr{display:grid;grid-template-columns:13% 11% 12% 36% 28%;font-size:13.5px;font-variant-numeric:tabular-nums;
border-bottom:1px solid var(--rule);color:var(--text);align-items:stretch}
.hr>div{padding:4px 4px;text-align:center;white-space:nowrap;min-height:27px;display:flex;align-items:center;justify-content:center}
.hr.h{color:var(--muted);font-size:12px;font-weight:600;letter-spacing:.08em;border-bottom:1px solid var(--rule)}
.hr>div:first-child{justify-content:flex-start;color:var(--muted)}
.hr .c{justify-content:flex-end;padding-right:6px}
.hr .rk{font-weight:600;color:var(--ink)}
.hr .rk:empty:after{content:""}
.hr>div:nth-child(3){color:var(--muted)}
.hr .mx{font-weight:800;color:var(--ink)}
.hr .c.up{color:var(--up)}
.hr .c.down{color:var(--down)}
.hr .c.flat{color:var(--muted)}
.hr .c.est{color:#6b7385;font-style:italic}
.hr .c.rough{color:#a3a8b3;font-style:italic}
.unote{margin:14px 2px 0;font-size:12px;color:#6b7385}
/* 순위표 새 디자인: 앨범 커버 위주 (rank_style = list1 / list2) */
.rc-row{display:grid;grid-template-columns:78px 112px minmax(0,1fr) 124px;gap:22px;align-items:center;padding:14px 6px;border-bottom:1px solid var(--rule)}
.rc-row>div{min-width:0}
.rc-rank{font-size:42px;font-weight:300;text-align:center;color:var(--ink);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.rc-art{width:112px;height:112px;border-radius:10px;box-shadow:0 6px 18px rgba(20,26,43,.16);background:var(--card2);overflow:hidden;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:34px;color:var(--muted)}
.rc-art img{width:100%;height:100%;object-fit:cover;display:block}
.rc-name{font-size:31px;font-weight:700;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rc-artist{font-size:22px;color:var(--muted);margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rc-chg{font-size:28px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}
.rc-top{grid-template-columns:78px 204px minmax(0,1fr) 124px;padding:24px 6px}
.rc-top .rc-art{width:204px;height:204px;border-radius:16px;box-shadow:0 12px 30px rgba(20,26,43,.22);font-size:64px}
.rc-top .rc-rank{color:var(--accent);font-size:72px;font-weight:200}
.rc-top .rc-name{font-size:44px;white-space:normal;line-height:1.2;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.rc-top .rc-artist{font-size:26px;margin-top:8px}
.rc-top .rc-chg{font-size:34px}
.rc-sep{height:3px;background:var(--accent);width:64px;margin:6px 0 4px}
/* 2열형 */
.rc-hero{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:30px;margin:6px 0 30px}
.rc-card{text-align:center;min-width:0}
.rc-card .rc-art{width:100%;height:auto;aspect-ratio:1/1;border-radius:18px;box-shadow:0 16px 38px rgba(20,26,43,.24);font-size:110px;position:relative}
.rc-card .rc-badge{display:inline-block;margin:18px 0 6px;font-size:22px;font-weight:700;letter-spacing:.24em;color:var(--accent)}
.rc-card .rc-name{font-size:38px;font-weight:800}
.rc-card .rc-artist{font-size:24px}
.rc-card .rc-chg{text-align:center;margin-top:8px;font-size:32px}
.rc-cols{display:grid;grid-template-columns:1fr 1fr;gap:0 52px}
.rc-cols .rc-row{grid-template-columns:64px 96px minmax(0,1fr) 96px;gap:18px;padding:11px 4px}
.rc-cols .rc-art{width:96px;height:96px;border-radius:9px;font-size:30px}
.rc-cols .rc-rank{font-size:36px}
.rc-cols .rc-name{font-size:27px}
.rc-cols .rc-artist{font-size:19px}
.rc-cols .rc-chg{font-size:24px}
"""



# ───────────────────────── 그래프형 (선 그래프) ─────────────────────────
LINE_COLORS = ["#3f5bd0", "#c8472a", "#e8a23a", "#4a9a2a", "#8e1a9a"]
TOP_LINES = 3


def _x_labels(chart: Chart):
    """칸마다 x축 라벨. 5분 차트는 시:분, 24시간 그래프는 시각(숫자)."""
    n, start = chart.spec.slots, chart.hour_start
    if chart.spec.layout in ("five", "rankfive"):
        return [f"{start + timedelta(minutes=5 * i):%H:%M}" for i in range(n)]
    return [f"{(start - timedelta(hours=n - 1 - i)).hour}" for i in range(n)]


RANK_COLORS = ["#2563eb", "#ea580c", "#059669", "#7c3aed", "#db2777"]


def _rank_linechart(chart: Chart):
    W, H = 1000, 640
    L, R, T, B = 74, 34, 96, 64
    n = chart.spec.slots
    rows = chart.rows[:TOP_LINES]
    vals = [int(v) for r in rows for v in (r.values or []) if v]
    lo, hi = (min(vals), max(vals)) if vals else (1, 5)
    lo_p, hi_p = max(1, lo - 1), hi + 1
    if hi_p - lo_p < 3:
        hi_p = lo_p + 3
    span = hi_p - lo_p
    step = 1 if span <= 12 else (2 if span <= 24 else 5)
    ys = lambda v: T + (H - T - B) * (v - lo_p) / (hi_p - lo_p)
    xs = lambda i: L + (W - L - R) * (i + .5) / n
    g = []
    t = lo_p
    while t <= hi_p:
        y = ys(t)
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e2dfd6" stroke-width="1.3"/>')
        g.append(f'<text x="{L - 14}" y="{y + 7:.1f}" font-size="22" font-weight="700" text-anchor="end">{t}</text>')
        t += step
    labels = _x_labels(chart)
    every = 1 if n <= 14 else 2
    for i, lab in enumerate(labels):
        g.append(f'<line x1="{xs(i):.1f}" x2="{xs(i):.1f}" y1="{T - 6}" y2="{H - B}" stroke="#efece4" stroke-width="1"/>')
        if i % every == (n - 1) % every:
            g.append(f'<text x="{xs(i):.1f}" y="{H - B + 34}" font-size="21" text-anchor="middle">{lab}</text>')
    g.append(f'<text x="{L - 14}" y="{T - 22}" font-size="18" text-anchor="end" style="fill:#8a8f9c">\uc21c\uc704</text>')
    series = []
    for k, r in enumerate(rows):
        col = RANK_COLORS[k % len(RANK_COLORS)]
        pts = [(i, int(v)) for i, v in enumerate(r.values or []) if v]
        series.append((col, pts))
        segs, cur, prev = [], [], None
        for i, v in pts:
            if prev is not None and i != prev + 1:
                segs.append(cur)
                cur = []
            cur.append((xs(i), ys(v)))
            prev = i
        if cur:
            segs.append(cur)
        for sg in segs:
            if len(sg) > 1:
                d = " ".join(f"{x:.1f},{y:.1f}" for x, y in sg)
                g.append(f'<polyline points="{d}" fill="none" stroke="#ffffff" stroke-width="9" stroke-linejoin="round" stroke-linecap="round"/>')
                g.append(f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="4.6" stroke-linejoin="round" stroke-linecap="round"/>')
        for i, v in pts:
            last = (i, v) == pts[-1]
            g.append(f'<circle cx="{xs(i):.1f}" cy="{ys(v):.1f}" r="{8 if last else 5}" fill="{col}" stroke="#fff" stroke-width="2"/>')
    for i in range(n):
        at = sorted((v, k) for k, (_, pts) in enumerate(series) for ii, v in pts if ii == i)
        for j, (v, k) in enumerate(at):
            col = series[k][0]
            above = j == 0 or (at[j][0] - at[j - 1][0]) > 1
            dy = -15 if above else 28
            g.append(f'<text x="{xs(i):.1f}" y="{ys(v) + dy:.1f}" font-size="18" font-weight="800" text-anchor="middle" '
                     f'style="fill:{col};paint-order:stroke;stroke:#ffffff;stroke-width:4px;stroke-linejoin:round">{v}</text>')
    colw = (W - 2 * 30) / max(1, len(rows))
    for k, r in enumerate(rows):
        col = RANK_COLORS[k % len(RANK_COLORS)]
        x = 30 + colw * k
        name = r.name if len(r.name) <= 13 else r.name[:12] + "\u2026"
        g.append(f'<line x1="{x:.1f}" x2="{x + 40:.1f}" y1="34" y2="34" stroke="{col}" stroke-width="6" stroke-linecap="round"/>')
        g.append(f'<text x="{x + 52:.1f}" y="41" font-size="23" font-weight="800" style="fill:#141a2b">{html.escape(name)}</text>')
    return f'<svg class="lc" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">{"".join(g)}</svg>'


def _linechart(chart: Chart):
    rank_mode = chart.spec.layout in ("rankgraph24", "rankfive")  # 순위 그래프: 1위가 위쪽
    if rank_mode:
        return _rank_linechart(chart)
    W, H = 1000, 440
    L, R, T, B = 46, 16, (30 if rank_mode else 14), 40
    n = chart.spec.slots
    rows = chart.rows[:TOP_LINES]
    vals = [v for r in rows for v in (r.values or []) if v]
    if rank_mode:
        top = max(5, max(vals, default=5))
        top = int(math.ceil(top / (1 if top <= 10 else 5)) * (1 if top <= 10 else 5))
        step = 1 if top <= 10 else 5
        ticks = [1] + list(range(step if step > 1 else 2, top + 1, step)) if step == 1 else [1] + list(range(5, top + 1, 5))
        ys = lambda v: T + (H - T - B) * (v - 1) / (top - 1)
    else:
        top = max(1, math.ceil(max(vals) + 0.45)) if vals else 1   # 맨 위 값의 라벨이 잘리지 않게 여백을 둔다
        step = 1 if top <= 10 else (2 if top <= 20 else 5)
        top = math.ceil(top / step) * step
        ticks = list(range(0, top + 1, step))
        ys = lambda v: T + (H - T - B) * (1 - v / top)
    xs = lambda i: L + (W - L - R) * (i + .5) / n
    g = []
    for t in ticks:
        y = ys(t)
        base = (t == 1) if rank_mode else (t == 0)
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{"#222a3d" if (t == 0 and not rank_mode) else "#e3e0d8"}" stroke-width="{1.4 if (t == 0 and not rank_mode) else 1}"/>')
        g.append(f'<text x="{L - 10}" y="{y + 5:.1f}" font-size="15" text-anchor="end">{t}</text>')
    for i, lab in enumerate(_x_labels(chart)):
        g.append(f'<text x="{xs(i):.1f}" y="{H - B + 24}" font-size="15" text-anchor="middle">{lab}</text>')
    legend, ends = [], []
    for k, r in enumerate(rows):
        col = LINE_COLORS[k % len(LINE_COLORS)]
        legend.append(f'<span><i style="background:{col}"></i><b>{html.escape(r.name)}</b></span>')
        seg = []
        segs = []
        for i, v in enumerate(r.values or []):
            if v:
                seg.append((xs(i), ys(v)))
            else:
                if seg:
                    segs.append(seg)
                seg = []
        if seg:
            segs.append(seg)
        for sg in segs:
            if len(sg) > 1:
                d = " ".join(f"{x:.1f},{y:.1f}" for x, y in sg)
                g.append(f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>')
            for x, y in sg:
                g.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{col}"/>')
        # 시점마다 점수 표시: 바로 위 선과 가까우면 점 아래에, 아니면 위에 쓴다
        for i, v in enumerate(r.values or []):
            if not v:
                continue
            higher = [o.values[i] for o in rows if o is not r and o.values and i < len(o.values) and o.values[i] and o.values[i] > v]
            near = bool(higher) and (min(higher) - v) / top * (H - T - B) < 26
            ty = ys(v) + (19 if near else -9)
            lab = f"{v:.3f}".rstrip("0").rstrip(".")
            g.append(f'<text x="{xs(i):.1f}" y="{ty:.1f}" font-size="{12 if n > 13 else 13}" font-weight="600" text-anchor="middle" '
                     f'style="fill:{col};stroke:#fff;stroke-width:3;paint-order:stroke">{lab}</text>')
        # 가장 최근 값 표시 (소수 첫째 자리, 겹치지 않게 위아래로 조금씩 밀어냄)
        idx = [i for i, v in enumerate(r.values or []) if v and rank_mode]
        if idx:
            i = idx[-1]
            ends.append([xs(i), ys(r.values[i]) - 10, (f"{int(r.values[i])}위" if rank_mode else f"{r.values[i]:.1f}"), col])
    ends.sort(key=lambda e: e[1])
    for j in range(1, len(ends)):
        if ends[j][1] - ends[j - 1][1] < 16:
            ends[j][1] = ends[j - 1][1] + 16
    for x, y, t, col in ends:
        g.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="13" font-weight="700" text-anchor="middle" style="fill:{col}">{t}</text>')
    svg = f'<svg class="lc" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">{"".join(g)}</svg>'
    return svg + f'<div class="legend">{"".join(legend)}</div>'


# ───────────────────────── 표형 ─────────────────────────
def _table(chart: Chart, images):
    rows = chart.rows
    per = math.ceil(len(rows) / 2) if len(rows) > 10 else len(rows)
    cols = []
    for part in (rows[:per], rows[per:]):
        cells = []
        for r in part:
            c, cls = _rank_change(r.rank, r.previous)
            cells.append(
                f'<div class="t{" top" if r.rank <= 3 else ""}"><div class="rank">{r.rank}</div>'
                f'<div class="chg {cls}">{c}</div><div class="art">{_art(r, images)}</div>'
                f'<div><div class="name">{html.escape(r.name)}</div><div class="artist">{html.escape(r.artists)}</div></div></div>'
            )
        cols.append(f"<div>{''.join(cells)}</div>")
    return f'<div class="cols">{"".join(cols)}</div>'

RANK_STYLE = "classic"      # classic(기존 2단 표) / list1(1열, 앨범 큰 목록) / list2(2열, 1~3위 큰 카드 + 2열 목록)


def _rc_row(r, images, top=False):
    c, cls = _rank_change(r.rank, r.previous)
    return (f'<div class="rc-row{" rc-top" if top else ""}"><div class="rc-rank">{r.rank}</div>'
            f'<div class="rc-art">{_art(r, images)}</div>'
            f'<div><div class="rc-name">{html.escape(r.name)}</div><div class="rc-artist">{html.escape(r.artists)}</div></div>'
            f'<div class="rc-chg {cls}">{c}</div></div>')


def _rank_cards(chart: Chart, images, style: str):
    rows = chart.rows
    if style == "list1":
        return "".join(_rc_row(r, images, top=r.rank <= 3) for r in rows)
    hero = []
    for r in rows[:3]:
        c, cls = _rank_change(r.rank, r.previous)
        hero.append(f'<div class="rc-card"><div class="rc-art">{_art(r, images)}</div><div class="rc-badge">{r.rank}위</div>'
                    f'<div class="rc-name">{html.escape(r.name)}</div><div class="rc-artist">{html.escape(r.artists)}</div>'
                    f'<div class="rc-chg {cls}">{c}</div></div>')
    # 4 5 / 6 7 / 8 9 … 가로로 읽는 순서 (왼쪽 열 끝까지 내려갔다 올라오지 않게)
    cells = "".join(_rc_row(r, images) for r in rows[3:])
    return f'<div class="rc-hero">{"".join(hero)}</div><div class="rc-cols">{cells}</div>'



def _table_counts(chart: Chart, images):
    out = ['<div class="tc head"><div></div><div></div><div></div><div>곡</div><div>1시간 이용자 수</div><div>24시간 이용자 수</div></div>']
    for r in chart.rows:
        c, cls = _rank_change(r.rank, r.previous)

        def cell(v, d):
            t, k = _signed(d)
            sm = f'<small class="{k}">{t}</small>' if d else ""
            return f'<div class="cnt">{_num(v)}{sm}</div>'

        out.append(
            f'<div class="tc{" top" if r.rank <= 3 else ""}"><div class="rank">{r.rank}</div>'
            f'<div class="chg {cls}">{c}</div><div class="art">{_art(r, images)}</div>'
            f'<div><div class="name">{html.escape(r.name)}</div><div class="artist">{html.escape(r.artists)}</div></div>'
            f"{cell(r.count1, r.count1_diff)}{cell(r.count2, r.count2_diff)}</div>"
        )
    return "".join(out)


def _heat(rank, top):
    """순위 칸 배경: 1위가 가장 진하고 5위까지만 칠한다. (스타일 문자열, 글자색 클래스 없음)"""
    if not rank or rank > 5:
        return ""
    alpha = top - (rank - 1) * top / 5
    color = "#141a2b"
    return f' style="background:rgba(201,154,46,{alpha:.2f});color:{color}"'


def _users_history(chart: Chart, images):
    blocks = []
    for h in chart.history or []:
        mx = h.window_max
        first, last = h.rows[0].time, h.rows[-1].time
        rng = f"{first:%Y.%m.%d}({_wd(first)}) ~ {last:%Y.%m.%d}({_wd(last)})"
        img = images.get(h.image)
        hero = f'<img src="{img}" alt="">' if img else ""
        rows = ['<div class="hr h"><div>시간</div><div>순위</div><div>T100</div><div>이용자수</div><div>증감</div></div>']
        for r in h.rows:
            if r.diff:
                dcls = "up" if r.diff > 0 else "down"
                dtxt = f"{r.diff:+,}"
            else:
                dcls, dtxt = "flat", ("0" if r.diff == 0 else "")
            is_max = mx is not None and r.count == mx
            rows.append(
                f'<div class="hr">'
                f'<div>{r.time.hour}시</div>'
                f'<div class="rk">{r.rank or ""}</div>'
                f'<div>{r.t100 or ""}</div>'
                f'<div class="c{" mx" if is_max else ""}{(" " + r.est) if getattr(r, "est", None) else ""}">{_num(r.count) if r.count else ""}</div>'
                f'<div class="c {dcls}">{dtxt}</div></div>'
            )
        blocks.append(
            f'<div class="ublk"><div class="ucov">{hero}</div><div class="uhead"><b>{html.escape(h.name)}</b>'
            f'<div class="ar">{html.escape(h.artists)}</div>'
            f'<div class="pk">최고 이용자수 <em>{_num(h.peak)}</em></div>'
            f'<div class="rg">{rng}</div></div>{"".join(rows)}</div>'
        )
    note = ""
    if any(getattr(r, "est", None) for h in chart.history or [] for r in h.rows):
        note = '<div class="unote">회색 기울임: 추정값 (이 곡이 상위 3위 안에 있던 때의 실측 비율 사용) · 연한 회색: 대략값 (실측 이력이 없어 평균 비율 사용)</div>'
    return f'<div class="ugrid">{"".join(blocks)}</div>{note}'


# ───────────────────────── 조립 ─────────────────────────
def effective_layout(chart: Chart) -> str:
    """TOP100 에 이용자 수치가 하나도 없으면 빈 열 대신 단순 표로 그린다."""
    if chart.spec.layout == "table_counts" and not any(
        r.count1 is not None or r.count2 is not None for r in chart.rows
    ):
        return "table"
    return chart.spec.layout


def render_html(chart: Chart, images: dict | None = None) -> str:
    images = images or {}
    layout = effective_layout(chart)
    start = chart.hour_start
    day = f"{start:%Y.%m.%d} ({_wd(start)})"
    shown = (len(chart.history) if layout == "table_users" and chart.history is not None
             else min(TOP_LINES, len(chart.rows)) if layout in ("five", "graph24", "rankgraph24", "rankfive") else len(chart.rows))
    note = ""
    if layout in ("rankgraph24", "rankfive"):
        if layout == "rankfive":
            sub, stamp = f"{day} {start:%H}시 구간 · 5분 단위 순위 · 상위 {min(TOP_LINES, len(chart.rows))}곡", f"{chart.stamp:%H:%M}"
        else:
            sub, stamp = f"{day} · 최근 24시간 순위 · 상위 {min(TOP_LINES, len(chart.rows))}곡", f"{start:%H}:00"
        body = _linechart(chart)
    elif layout == "five":
        from . import scoregraph
        return scoregraph.five_page(chart)
    elif layout == "graph24":
        sub, stamp = f"{day} · 최근 24시간 · 1시간 단위 · 상위 {min(TOP_LINES, len(chart.rows))}곡", f"{start:%H}:00"
        body = _linechart(chart)
    elif layout == "table_users":
        sub, stamp = f"{day} {start:%H}시 기준 · 최근 24시간 이용자 수 추이", f"{start:%H}:00"
        body = "<style>header:after{display:none}.stamp small{color:var(--muted)}</style>" + _users_history(chart, images)
    else:
        rng = f"1~{shown}위" if shown == chart.total or not chart.total else f"1~{shown}위 (전체 {chart.total}곡)"
        sub, stamp = f"{day} {start:%H}시 기준 · {rng}", f"{start:%H}:00"
        from . import rankstyles
        if layout == "table" and RANK_STYLE in rankstyles.STYLES and len(chart.rows) > 10:
            fn, width, _scale, _desc = rankstyles.STYLES[RANK_STYLE]
            css_x, body = fn(chart, images)
            body = f"<style>body{{width:{width}px}}{css_x}</style>" + body
        elif layout == "table" and RANK_STYLE in ("list1", "list2") and len(chart.rows) > 10:
            body = _rank_cards(chart, images, RANK_STYLE)
            if RANK_STYLE == "list2":
                body = '<style>body{width:1480px}</style>' + body
        else:
            body = _table_counts(chart, images) if layout == "table_counts" else _table(chart, images)
        if chart.spec.layout == "table_counts" and layout == "table":
            note = "※ 이 시간대는 가이섬에서 이용자 수치를 제공하지 않아 순위만 표시합니다"
    foot_r = f"{shown}곡" if layout in ("five", "graph24", "table_users", "rankgraph24", "rankfive") or shown == chart.total or not chart.total else f"상위 {shown}곡"
    return (
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(chart.title)} {chart.stamp:%H:%M}</title>'
        f"<style>{CSS}</style></head><body>"
        f'<header><div><h1>{html.escape(chart.title)}</h1><div class="sub">{sub}</div></div>'
        f'<div class="stamp">{stamp}<small>기준</small></div></header>'
        f"{body}"
        + (f'<footer><span>{chart.spec.credit}{(" · " + note) if note else ""}</span><span>{foot_r}</span></footer>' if layout != "table_users" else "") + "</body></html>"
    )


def png_scale(chart: Chart) -> float:
    """곡이 많은 표는 이미지가 너무 길어지지 않게 배율을 낮춘다 (100곡 수치 표는 세로 6400px 안팎)."""
    layout = effective_layout(chart)
    from . import rankstyles
    if layout == "table" and RANK_STYLE in rankstyles.STYLES and len(chart.rows) > 10:
        return rankstyles.STYLES[RANK_STYLE][2]
    if layout == "table" and RANK_STYLE in ("list1", "list2") and len(chart.rows) > 10:
        return 1.0 if RANK_STYLE == "list1" else 1.4     # 1열은 세로가 길어 배율을 낮춤
    if len(chart.rows) > 30:
        if layout == "table_counts":
            return 1.0
        if layout == "table":
            return 1.5
    return 2.0


def render_png(html_text: str, path: Path, scale: float = 2.0) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 400}, device_scale_factor=scale)
        page.set_content(html_text, wait_until="load")
        w = page.evaluate("Math.ceil(document.body.getBoundingClientRect().right + (parseFloat(getComputedStyle(document.body).marginRight) || 0))")
        if 300 < w < 1080:
            page.set_viewport_size({"width": w, "height": 400})
        page.screenshot(path=str(path), full_page=True)
        browser.close()


# ───────────────────────── 게시글 텍스트 ─────────────────────────
def body_text(chart: Chart) -> str:
    layout = effective_layout(chart)
    lines = []
    if layout == "five":
        from . import scoregraph
        return scoregraph.five_text(chart) + f"\n\n{chart.spec.credit}"
    if layout == "graph24":
        for r in chart.rows:
            vals = "|".join("-" if v is None else f"{v:g}" for v in r.values)
            lines.append(f"[{r.rank}위] {r.name} - {r.artists}\n{vals}")
        sep = "\n\n"
    elif layout in ("rankgraph24", "rankfive"):
        for r in chart.rows[:TOP_LINES]:
            c, _ = _rank_change(r.rank, r.previous)
            lines.append(f"{r.rank}위 ({c}) {r.name} - {r.artists}")
        sep = "\n"
    elif layout == "table_users":
        from . import scoregraph
        return scoregraph.users_text(chart)
    else:
        for r in chart.rows:
            c, _ = _rank_change(r.rank, r.previous)
            extra = ""
            if layout == "table_counts":
                extra = f" | 1시간 {_num(r.count1)} / 24시간 {_num(r.count2)}"
            lines.append(f"{r.rank}위 ({c}) {r.name} - {r.artists}{extra}")
        sep = "\n"
    return sep.join(lines) + f"\n\n{chart.spec.credit}"


def post_title(chart: Chart) -> str:
    return f"[{chart.stamp:%H:%M}] {chart.title}"
