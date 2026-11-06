from __future__ import annotations
import html

COLORS = ["#a6e22e", "#ff9a3c", "#4aa8ff", "#ff6fae", "#b58cff"]
MINUS = "−"


def top_n(chart) -> int:
    return 5 if (chart.spec.platform == "melonhot" or "hot100" in chart.spec.key) else 3


def _series(chart):
    last = chart.latest_slot
    if last is None:
        return []
    out = []
    for r in chart.rows[: top_n(chart)]:
        out.append({"name": r.name, "values": [(v or 0.0) for v in (r.values or [])[: last + 1]]})
    return out


def _n(v: float) -> str:
    t = repr(round(float(v), 5))
    return "0" if t in ("0.0", "-0.0") else t


def _signed(v: float) -> str:
    t = repr(round(abs(float(v)), 5))
    return ("+" if v >= 0 else MINUS) + t


def five_text(chart) -> str:
    series = _series(chart)
    lines = []
    for k, s in enumerate(series):
        vs = s["values"]
        delta = vs[-1] - (vs[-2] if len(vs) > 1 else 0.0)
        lines.append(f"[{k + 1}위 예측] {s['name']} ({_signed(delta)})")
        lines.append("|".join(_n(v) for v in vs))
        if k + 1 < len(series):
            lines.append("")
            lines.append(f"[{_n(vs[-1] - series[k + 1]['values'][-1])}]")
            lines.append("")
    return "\n".join(lines)


def _label(v: float) -> str:
    return str(round(v, 2))


def five_svg(chart) -> str:
    series = _series(chart)
    W, H = 1000, 520
    L, R, T, B = 40, 14, 12, 40
    top = max([v for s in series for v in s["values"]] + [1.0]) * 1.06
    step = 1 if top <= 6 else 2
    ymax = int(top // step + 1) * step
    xs = lambda m: L + (W - L - R) * m / 60
    ys = lambda v: T + (H - T - B) * (1 - v / ymax)
    g = [f'<rect x="{L}" y="{T}" width="{W - L - R}" height="{H - T - B}" fill="#3d4a6b"/>']
    for t in range(0, ymax + 1, step):
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{ys(t):.1f}" y2="{ys(t):.1f}" stroke="#c9d1e6" stroke-width="1" opacity=".6"/>')
        g.append(f'<text x="{L - 6}" y="{ys(t) + 5:.1f}" font-size="13" text-anchor="end" fill="#222">{t}</text>')
    for m in range(0, 61, 10):
        g.append(f'<line x1="{xs(m):.1f}" x2="{xs(m):.1f}" y1="{T}" y2="{H - B}" stroke="#c9d1e6" stroke-width="1" opacity=".6"/>')
        g.append(f'<text x="{xs(m):.1f}" y="{H - B + 20}" font-size="13" text-anchor="middle" fill="#222">{m}</text>')
    for k, s in enumerate(series):
        col = COLORS[k % len(COLORS)]
        pts = [(xs(5 * i), ys(v), v) for i, v in enumerate(s["values"])]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
        g.append(f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="3" stroke-linejoin="round"/>')
        for x, y, v in pts:
            g.append(f'<text x="{x:.1f}" y="{y - 7:.1f}" font-size="12" text-anchor="middle" fill="{col}">{_label(v)}</text>')
    lx, ly = W - R - 224, T + 8
    g.append(f'<rect x="{lx}" y="{ly}" width="214" height="{18 * len(series) + 10}" rx="3" fill="#f2f2f2" opacity=".92"/>')
    for k, s in enumerate(series):
        col = COLORS[k % len(COLORS)]
        y = ly + 19 + 18 * k
        g.append(f'<line x1="{lx + 8}" x2="{lx + 30}" y1="{y - 4}" y2="{y - 4}" stroke="{col}" stroke-width="3"/>')
        g.append(f'<text x="{lx + 38}" y="{y}" font-size="11" fill="#222">{html.escape(s["name"][:22])}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg">{"".join(g)}</svg>'


def five_title(chart) -> str:
    return f"[{chart.stamp:%Y%m%d %H:%M}] {chart.title}"


def five_page(chart) -> str:
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>'
        "body{margin:0;background:#fff;width:1000px;padding:14px 18px 12px;font-family:'Pretendard','Noto Sans KR','Noto Sans CJK KR',sans-serif}"
        "h1{font-size:17px;text-align:center;margin:0 0 6px;color:#111;font-weight:400}</style></head><body>"
        f"<h1>{html.escape(five_title(chart))}</h1>{five_svg(chart)}</body></html>"
    )


def _fw(s: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in s)


def _gap(v: int) -> str:
    return (MINUS if v < 0 else "") + str(abs(v))


def users_text(chart) -> str:
    hs = [h for h in (chart.history or []) if h.rows][:3]
    if not hs:
        return ""
    cur = [h.rows[-1].count for h in hs]
    lines = []
    for a, b in ((1, 2), (2, 3), (1, 3)):
        if a <= len(hs) and b <= len(hs) and cur[a - 1] is not None and cur[b - 1] is not None:
            lines.append(_fw(f"[{a}") + "↔" + _fw(f"{b}] ") + _fw(_gap(cur[a - 1] - cur[b - 1])))
    lines.append("")
    lines.append("전일 동시간 대비 변화량")
    for k, h in enumerate(hs):
        first, last = h.rows[0].count, h.rows[-1].count
        if first and last is not None:
            d = last - first
            pct = abs(d) / first * 100
            lines.append(_fw(f"{k + 1}") + "위" + _fw(":") + _fw(("+" if d >= 0 else "-") + str(abs(d)) + "(") + ("▲" if d >= 0 else "▼") + _fw(f"{pct:.2f}%)"))
        else:
            lines.append(_fw(f"{k + 1}") + "위" + _fw(":") + " 전일 동시간 데이터 없음")
    return "\n".join(lines)
