"""점수형 그래프(써클차트 스타일): 남색 판, 점마다 값 표시, 범례, 본문 텍스트(비율/변화/순위 차)."""
from __future__ import annotations
import html
from pathlib import Path

from .render import render_png

COLORS = ["#a6e22e", "#ff9a3c", "#4aa8ff", "#ff6fae", "#b58cff"]


def _f(v: float) -> str:
    return f"{v:.6g}"


def _s(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def build_svg(labels: list[str], series: list[dict], title: str) -> str:
    W, H = 1000, 560
    L, R, T, B = 52, 20, 26, 44
    n = len(labels)
    vals = [v for s in series for v in s["values"] if v is not None]
    top = int(max(vals)) + 1
    xs = lambda i: L + 34 + (W - L - R - 68) * i / max(1, n - 1)
    ys = lambda v: T + (H - T - B) * (1 - v / top)
    g = [f'<rect x="{L}" y="{T}" width="{W - L - R}" height="{H - T - B}" fill="#3d4a6b"/>']
    for t in range(0, top + 1):
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{ys(t):.1f}" y2="{ys(t):.1f}" stroke="#7d89a8" stroke-width="1" opacity=".55"/>')
        g.append(f'<text x="{L - 8}" y="{ys(t) + 5:.1f}" font-size="14" text-anchor="end" fill="#333">{t}</text>')
    for i, lab in enumerate(labels):
        g.append(f'<line x1="{xs(i):.1f}" x2="{xs(i):.1f}" y1="{T}" y2="{H - B}" stroke="#7d89a8" stroke-width="1" opacity=".3"/>')
        g.append(f'<text x="{xs(i):.1f}" y="{H - B + 22}" font-size="14" text-anchor="middle" fill="#333">{lab}</text>')
    for k, s in enumerate(series):
        col = COLORS[k % len(COLORS)]
        pts = [(xs(i), ys(v), v) for i, v in enumerate(s["values"]) if v is not None]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
        g.append(f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="3.4" stroke-linejoin="round" stroke-linecap="round"/>')
        for x, y, v in pts:
            g.append(f'<text x="{x:.1f}" y="{y - 9:.1f}" font-size="13" font-weight="600" text-anchor="middle" fill="{col}" stroke="#2b3550" stroke-width="3" paint-order="stroke">{_s(v)}</text>')
    lx, ly = W - R - 250, T + 10
    g.append(f'<rect x="{lx}" y="{ly}" width="236" height="{22 * len(series) + 14}" rx="4" fill="#f1f1f1" opacity=".95"/>')
    for k, s in enumerate(series):
        col = COLORS[k % len(COLORS)]
        y = ly + 20 + 22 * k
        g.append(f'<line x1="{lx + 10}" x2="{lx + 40}" y1="{y - 5}" y2="{y - 5}" stroke="{col}" stroke-width="3.4"/>')
        g.append(f'<text x="{lx + 48}" y="{y}" font-size="14" fill="#222">{html.escape(s["name"])}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg">{"".join(g)}</svg>'


def build_text(series: list[dict]) -> str:
    last = [next(v for v in reversed(s["values"]) if v is not None) for s in series]
    total = sum(last)
    out = []
    for k, s in enumerate(series):
        vs = [v for v in s["values"] if v is not None]
        delta = vs[-1] - vs[-2] if len(vs) > 1 else 0
        out.append(f"[{k + 1}위 {last[k] / total * 100:.2f}%] {s['name']} ({delta:+.6g})")
        out.append("|".join(_f(v) if v is not None else "None" for v in s["values"]))
        if k + 1 < len(series):
            out.append(f"\n[{last[k] - last[k + 1]:.3f}]\n")
    return "\n".join(out)


def render(labels, series, title, out_png: Path) -> str:
    page = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>'
        "body{margin:0;background:#fff;width:1080px;padding:28px 28px 22px;font-family:'Pretendard','Noto Sans KR','Noto Sans CJK KR',sans-serif}"
        "h1{font-size:22px;text-align:center;margin:0 0 10px;color:#222;font-weight:600}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>{build_svg(labels, series, title)}</body></html>"
    )
    render_png(page, out_png, 2.0)
    return build_text(series)
