import html

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#fff;width:720px;padding:16px 18px 18px;font-family:'Pretendard','Noto Sans KR','Noto Sans CJK KR',sans-serif;color:#1c2230}
.ttl{font-size:19px;font-weight:600;color:#222;margin:0 0 8px;display:flex;align-items:center;gap:7px;white-space:nowrap}
.ttl img{height:28px;width:auto;display:block}
.hd,.r{display:grid;align-items:center;font-variant-numeric:tabular-nums}
.hd{border-top:1px solid #222;border-bottom:1px solid #222;font-size:15px;font-weight:600;padding:8px 0;text-align:center}
.r{border-bottom:1px solid #e4e6eb;min-height:74px}
.c2 .hd,.c2 .r{grid-template-columns:62px 66px 78px 1fr}
.c4 .hd,.c4 .r{grid-template-columns:62px 66px 78px 1fr 130px 130px}
.rk{text-align:center;font-weight:700;font-size:26px}
.ch{text-align:center;font-size:16px;font-weight:700}
.up{color:#d6453d}.dn{color:#2f6fd0}.nw{color:#d6453d}.eq{color:#aab0bd}
.ar{width:68px;height:68px;margin:3px 4px;background:#e9e6df;overflow:hidden;display:flex;align-items:center;justify-content:center;font-size:22px;color:#8a8f9c}
.ar img{width:100%;height:100%;object-fit:cover;display:block}
.nm{padding-left:12px;min-width:0}
.nm b{display:block;font-size:21px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nm i{display:block;font-style:normal;font-size:15px;margin-top:3px;color:#8a8f9c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cn{text-align:center;font-size:16px;color:#555}
.un{grid-column:1/-1;text-align:center;font-size:17px;color:#555;background:#f4f5f7;padding:12px 0}
"""


def _chg(cur, new):
    if cur is None:
        return "NEW", "nw"
    d = cur - new
    if d > 0:
        return f"▲{d}", "up"
    if d < 0:
        return f"▼{-d}", "dn"
    return "", "eq"


def page(title, rows, images=None, counts=False, logo=None, brand=None):
    images = images or {}
    cls = "c4" if counts else "c2"
    head = '<div class="hd"><div></div><div></div><div></div><div style="text-align:center">곡</div>' + ('<div>1시간 이용자수</div><div>24시간 이용자수</div>' if counts else "") + "</div>"
    out = []
    for r in rows:
        if r.get("unknown"):
            out.append(f'<div class="r"><div class="rk">{r["rank"]}</div><div class="un" style="grid-column:2/-1">알 수 없음</div></div>')
            continue
        t, k = _chg(r.get("cur"), r["rank"])
        img = images.get(r.get("image"))
        art = f'<img src="{img}" alt="">' if img else html.escape((r["name"] or "♪")[:1])
        cnt = f'<div class="cn">{r.get("c1") or "-"}</div><div class="cn">{r.get("c2") or "-"}</div>' if counts else ""
        out.append(
            f'<div class="r"><div class="rk">{r["rank"]}</div><div class="ch {k}">{t}</div><div class="ar">{art}</div>'
            f'<div class="nm"><b>{html.escape(r["name"] or "")}</b><i>{html.escape(r.get("artists") or "")}</i></div>{cnt}</div>'
        )
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{CSS}</style></head><body class="{cls}">'
            f'<div class="ttl">{_title(title, logo, brand)}</div>{head}{"".join(out)}</body></html>')


def _title(title, logo, brand=None):
    if not logo:
        return html.escape(title)
    mark = logo if logo.startswith("<") else f'<img src="{logo}" alt="">'
    return f'<span>{html.escape(title)}</span>{mark}'


def mark(src, crop=None, h=30):
    if not crop:
        return f'<img src="{src}" alt="" style="height:{h}px;width:auto;border-radius:6px">'
    iw, ih, cx, cy, cw, ch = crop
    s = h / ch
    return (f'<span style="display:inline-block;height:{h}px;width:{round(cw * s)}px;border-radius:6px;background:url({src}) no-repeat;'
            f'background-size:{iw * s:.1f}px {ih * s:.1f}px;background-position:-{cx * s:.1f}px -{cy * s:.1f}px"></span>')
