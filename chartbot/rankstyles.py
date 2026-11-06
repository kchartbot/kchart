"""순위표 디자인 후보 10종. 각 함수는 (css, html) 을 돌려준다. STYLES[이름] = (함수, 이미지 가로폭, PNG 배율, 설명)."""
import html as _h
from . import render as R


def _chg(r):
    return R._rank_change(r.rank, r.previous)


def _art(r, images):
    return R._art(r, images)


def _esc(x):
    return _h.escape(x or "")


# ── 1·2 : 기존 새 디자인 ──
def s1(chart, images):
    return "", R._rank_cards(chart, images, "list1")


def s2(chart, images):
    return "", R._rank_cards(chart, images, "list2")


# ── 3 : 다크 누아르 2열 ──
def s3(chart, images):
    css = (":root{--bg:#0d1017;--ink:#f4efe3;--text:#e9e5da;--muted:#8c93a3;--rule:#222838;--card2:#1a2030;--accent:#d6b25e}"
           "body{background:#0d1017}.rc-art{box-shadow:0 10px 28px rgba(0,0,0,.6)}.rc-card .rc-art{box-shadow:0 18px 44px rgba(0,0,0,.7)}"
           ".up{color:#ff6b61}.down{color:#6aa3ff}")
    return css, R._rank_cards(chart, images, "list2")


# ── 4 : 포스터 그리드 5열 (커버 위주) ──
def _tile(r, images, cls=""):
    c, k = _chg(r)
    return (f'<div class="pt {cls}"><div class="pa">{_art(r, images)}<b class="pn">{r.rank}</b><i class="pc {k}">{c}</i></div>'
            f'<div class="pnm">{_esc(r.name)}</div><div class="par">{_esc(r.artists)}</div></div>')


PT_CSS = """
.pg{display:grid;gap:34px 24px}
.pt{min-width:0}
.pa{position:relative;aspect-ratio:1/1;border-radius:14px;overflow:hidden;background:var(--card2);box-shadow:0 10px 26px rgba(20,26,43,.2);display:flex;align-items:center;justify-content:center;font-size:54px;font-weight:700;color:var(--muted)}
.pa img{width:100%;height:100%;object-fit:cover;display:block}
.pn{position:absolute;left:0;top:0;min-width:56px;padding:6px 14px 8px;background:rgba(255,255,255,.93);color:var(--ink);font-size:30px;font-weight:800;border-bottom-right-radius:14px;text-align:center;font-variant-numeric:tabular-nums}
.pc{position:absolute;right:10px;bottom:10px;padding:3px 11px 4px;background:rgba(255,255,255,.93);border-radius:20px;font-style:normal;font-size:22px;font-weight:800}
.pnm{margin-top:14px;font-size:26px;font-weight:800;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.par{font-size:20px;color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
"""


def s4(chart, images):
    return PT_CSS + ".pg{grid-template-columns:repeat(5,minmax(0,1fr))}", f'<div class="pg">{"".join(_tile(r, images) for r in chart.rows)}</div>'


# ── 5 : 1위만 크게 + 4열 ──
def s5(chart, images):
    css = PT_CSS + (".pg{grid-template-columns:repeat(4,minmax(0,1fr))}.pt.big{grid-column:span 2;grid-row:span 2}"
                    ".pt.big .pa{font-size:120px}.pt.big .pn{font-size:56px;min-width:100px;padding:10px 24px 14px;border-bottom-right-radius:20px}"
                    ".pt.big .pc{font-size:34px;right:18px;bottom:18px}.pt.big .pnm{font-size:44px;margin-top:20px}.pt.big .par{font-size:28px}")
    cells = "".join(_tile(r, images, "big" if r.rank == 1 else "") for r in chart.rows)
    return css, f'<div class="pg">{cells}</div>'


# ── 6 : 매거진 (1위 배너) ──
def s6(chart, images):
    r1 = chart.rows[0]
    c1, k1 = _chg(r1)
    src = images.get(r1.image, "")
    bg = f'<img class="mgbg" src="{src}" alt="">' if src else ""
    css = (".mg{position:relative;overflow:hidden;border-radius:20px;background:#141a2b;margin:6px 0 34px;padding:46px 46px}"
           ".mgbg{position:absolute;inset:-40px;width:calc(100% + 80px);height:calc(100% + 80px);object-fit:cover;filter:blur(36px) brightness(.55);transform:scale(1.1)}"
           ".mgin{position:relative;display:flex;gap:46px;align-items:center}"
           ".mgart{width:380px;height:380px;border-radius:16px;overflow:hidden;flex:none;box-shadow:0 20px 50px rgba(0,0,0,.5);background:var(--card2);display:flex;align-items:center;justify-content:center;font-size:110px;color:var(--muted)}"
           ".mgart img{width:100%;height:100%;object-fit:cover}.mgtx{color:#fff;min-width:0}"
           ".mgrk{font-size:20px;font-weight:700;letter-spacing:.3em;color:#e8c878}.mgnm{font-size:56px;font-weight:800;line-height:1.15;margin:12px 0 10px}"
           ".mgar{font-size:30px;color:#d8dbe4}.mgch{font-size:30px;margin-top:20px;font-weight:800}.mgch.up{color:#ff8a80}.mgch.down{color:#8fb8ff}.mgch.flat{color:#cfd3dc}"
           ".mgtwo{display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-bottom:30px}"
           ".mgsm{display:flex;gap:24px;align-items:center;padding:18px;border:1px solid var(--rule);border-radius:16px;box-shadow:0 8px 24px rgba(20,26,43,.08)}")
    big = (f'<div class="mg">{bg}<div class="mgin"><div class="mgart">{_art(r1, images)}</div><div class="mgtx"><div class="mgrk">NO. 1</div>'
           f'<div class="mgnm">{_esc(r1.name)}</div><div class="mgar">{_esc(r1.artists)}</div><div class="mgch {k1}">{c1}</div></div></div></div>')
    two = "".join(f'<div class="mgsm"><div class="rc-rank" style="font-size:54px;width:74px;color:var(--accent);font-weight:200">{r.rank}</div>'
                  f'<div class="rc-art" style="width:150px;height:150px;flex:none">{_art(r, images)}</div>'
                  f'<div style="min-width:0"><div class="rc-name" style="font-size:32px">{_esc(r.name)}</div><div class="rc-artist">{_esc(r.artists)}</div>'
                  f'<div class="rc-chg {_chg(r)[1]}" style="text-align:left;margin-top:8px">{_chg(r)[0]}</div></div></div>' for r in chart.rows[1:3])
    cells = "".join(R._rc_row(r, images) for r in chart.rows[3:])
    return css, f'{big}<div class="mgtwo">{two}</div><div class="rc-cols">{cells}</div>'


# ── 7 : 에디토리얼 (큰 숫자, 얇은 선) ──
def s7(chart, images):
    css = (".ed{display:grid;grid-template-columns:1fr 1fr;gap:0 70px}"
           ".edr{display:grid;grid-template-columns:96px 104px minmax(0,1fr) 84px;gap:16px;align-items:center;padding:16px 0;border-top:1px solid var(--ink)}"
           ".edr:nth-child(-n+2){border-top:3px solid var(--ink)}"
           ".edn{font-size:70px;font-weight:200;line-height:1;color:var(--ink);letter-spacing:-.04em;font-variant-numeric:tabular-nums}"
           ".edr.t3 .edn{color:var(--accent);font-weight:300}"
           ".eda{width:104px;height:104px;overflow:hidden;background:var(--card2);display:flex;align-items:center;justify-content:center;font-size:34px;color:var(--muted)}.eda img{width:100%;height:100%;object-fit:cover}"
           ".edt{font-size:27px;font-weight:700;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"
           ".eds{font-size:19px;color:var(--muted);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.edc{font-size:25px;font-weight:800;text-align:right}")
    cells = "".join(f'<div class="edr{" t3" if r.rank <= 3 else ""}"><div class="edn">{r.rank}</div><div class="eda">{_art(r, images)}</div>'
                    f'<div style="min-width:0"><div class="edt">{_esc(r.name)}</div><div class="eds">{_esc(r.artists)}</div></div>'
                    f'<div class="edc {_chg(r)[1]}">{_chg(r)[0]}</div></div>' for r in chart.rows)
    return css, f'<div class="ed">{cells}</div>'


# ── 8 : 카드 1열 (회색 바탕 위 흰 카드) ──
def s8(chart, images):
    css = (":root{--bg:#f2f1ee}.cd{display:flex;flex-direction:column;gap:16px}"
           ".cdr{display:grid;grid-template-columns:90px 124px minmax(0,1fr) 120px;gap:22px;align-items:center;background:#fff;border-radius:22px;padding:16px 26px 16px 16px;box-shadow:0 6px 22px rgba(20,26,43,.08)}"
           ".cdn{justify-self:center;width:66px;height:66px;border-radius:50%;background:#141a2b;color:#fff;display:flex;align-items:center;justify-content:center;font-size:30px;font-weight:700}"
           ".cdr.t3 .cdn{background:linear-gradient(135deg,#e6c36a,#a07c26);font-size:34px}"
           ".cda{width:124px;height:124px;border-radius:16px;overflow:hidden;background:var(--card2);display:flex;align-items:center;justify-content:center;font-size:40px;color:var(--muted)}.cda img{width:100%;height:100%;object-fit:cover}"
           ".cdt{font-size:31px;font-weight:800;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.cds{font-size:22px;color:var(--muted);margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"
           ".cdc{font-size:28px;font-weight:800;text-align:right}.cdr.t3{padding:22px 26px 22px 16px}.cdr.t3 .cda{width:160px;height:160px}.cdr.t3{grid-template-columns:90px 160px minmax(0,1fr) 120px}.cdr.t3 .cdt{font-size:38px}")
    cells = "".join(f'<div class="cdr{" t3" if r.rank <= 3 else ""}"><div class="cdn">{r.rank}</div><div class="cda">{_art(r, images)}</div>'
                    f'<div style="min-width:0"><div class="cdt">{_esc(r.name)}</div><div class="cds">{_esc(r.artists)}</div></div>'
                    f'<div class="cdc {_chg(r)[1]}">{_chg(r)[0]}</div></div>' for r in chart.rows)
    return css, f'<div class="cd">{cells}</div>'


# ── 9 : 원형 커버(LP) 2열 ──
def s9(chart, images):
    css = (".lp{display:grid;grid-template-columns:1fr 1fr;gap:6px 56px}"
           ".lpr{display:grid;grid-template-columns:62px 132px minmax(0,1fr) 84px;gap:20px;align-items:center;padding:12px 0;border-bottom:1px solid var(--rule)}"
           ".lpn{font-size:36px;font-weight:300;text-align:center;color:var(--ink)}.lpr.t3 .lpn{color:var(--accent);font-weight:700}"
           ".lpa{position:relative;width:132px;height:132px;border-radius:50%;overflow:hidden;background:var(--card2);box-shadow:0 8px 22px rgba(20,26,43,.25);display:flex;align-items:center;justify-content:center;font-size:40px;color:var(--muted)}"
           ".lpa img{width:100%;height:100%;object-fit:cover}.lpa:after{content:'';position:absolute;left:50%;top:50%;width:24px;height:24px;margin:-12px 0 0 -12px;border-radius:50%;background:#fff;box-shadow:0 0 0 5px rgba(255,255,255,.35)}"
           ".lpt{font-size:27px;font-weight:700;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.lps{font-size:19px;color:var(--muted);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.lpc{font-size:25px;font-weight:800;text-align:right}")
    cells = "".join(f'<div class="lpr{" t3" if r.rank <= 3 else ""}"><div class="lpn">{r.rank}</div><div class="lpa">{_art(r, images)}</div>'
                    f'<div style="min-width:0"><div class="lpt">{_esc(r.name)}</div><div class="lps">{_esc(r.artists)}</div></div>'
                    f'<div class="lpc {_chg(r)[1]}">{_chg(r)[0]}</div></div>' for r in chart.rows)
    return css, f'<div class="lp">{cells}</div>'


# ── 10 : 시상대 + 4~10위 타일 + 11위 이후 3열 컴팩트 ──
def s10(chart, images):
    css = PT_CSS + (".pd{display:grid;grid-template-columns:1fr 1.25fr 1fr;gap:34px;align-items:end;margin:10px 0 40px}"
                    ".pd .pt{text-align:center}.pd .pa{border-radius:18px}.pd .pnm{font-size:30px}.pd .par{font-size:21px}"
                    ".pd .p1 .pnm{font-size:38px}.pd .p1 .pa{box-shadow:0 22px 56px rgba(160,124,38,.45)}"
                    ".pd .pb{margin-top:16px;border-radius:12px 12px 0 0;color:#fff;font-weight:800;font-size:44px;padding-top:14px;background:linear-gradient(180deg,#141a2b,#2a3350)}"
                    ".pd .p1 .pb{height:96px;background:linear-gradient(180deg,#e6c36a,#a07c26)}.pd .p2 .pb{height:64px}.pd .p3 .pb{height:44px}"
                    ".ps{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:18px;margin-bottom:38px}"
                    ".ps .pa{border-radius:10px}.ps .pn{font-size:20px;min-width:36px;padding:3px 9px 5px}.ps .pc{font-size:15px;right:6px;bottom:6px;padding:2px 8px 3px}.ps .pnm{font-size:17px;margin-top:8px}.ps .par{font-size:14px}"
                    ".pm{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 38px}"
                    ".pmr{display:grid;grid-template-columns:48px 68px minmax(0,1fr) 54px;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--rule)}"
                    ".pmn{font-size:22px;font-weight:600;text-align:center;color:var(--ink)}.pma{width:68px;height:68px;border-radius:8px;overflow:hidden;background:var(--card2);display:flex;align-items:center;justify-content:center;color:var(--muted)}.pma img{width:100%;height:100%;object-fit:cover}"
                    ".pmt{font-size:19px;font-weight:700;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pms{font-size:14px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pmc{font-size:17px;font-weight:800;text-align:right}")
    rows = chart.rows

    def pod(r, cls):
        return (f'<div class="pt {cls}"><div class="pa">{_art(r, images)}</div><div class="pnm" style="margin-top:16px">{_esc(r.name)}</div>'
                f'<div class="par">{_esc(r.artists)}</div><div class="pb">{r.rank}</div></div>')
    podium = f'<div class="pd">{pod(rows[1], "p2")}{pod(rows[0], "p1")}{pod(rows[2], "p3")}</div>'
    strip = f'<div class="ps">{"".join(_tile(r, images) for r in rows[3:10])}</div>'
    small = "".join(f'<div class="pmr"><div class="pmn">{r.rank}</div><div class="pma">{_art(r, images)}</div>'
                    f'<div style="min-width:0"><div class="pmt">{_esc(r.name)}</div><div class="pms">{_esc(r.artists)}</div></div>'
                    f'<div class="pmc {_chg(r)[1]}">{_chg(r)[0]}</div></div>' for r in rows[10:])
    return css, f'{podium}{strip}<div class="pm">{small}</div>'


STYLES = {
    "s1": (s1, 1080, 1.0, "1열 · 1~3위 큰 커버 목록 (밝은 고급)"),
    "s2": (s2, 1480, 1.4, "2열 · 상단 1~3위 큰 카드 + 가로 읽기 목록"),
    "s3": (s3, 1480, 1.4, "2열 · 다크 누아르 (검정+금색)"),
    "s4": (s4, 1500, 1.4, "포스터 그리드 5열 · 커버 위주"),
    "s5": (s5, 1500, 1.4, "그리드 4열 · 1위만 2×2 크게"),
    "s6": (s6, 1480, 1.4, "매거진 · 1위 와이드 배너 + 2·3위 카드 + 2열"),
    "s7": (s7, 1500, 1.4, "에디토리얼 · 큰 얇은 숫자 + 각진 커버 2열"),
    "s8": (s8, 1080, 1.0, "카드 1열 · 회색 바탕 흰 카드, 금빛 1~3위 배지"),
    "s9": (s9, 1480, 1.4, "원형 커버(LP) 2열"),
    "s10": (s10, 1500, 1.4, "시상대(2-1-3) + 4~10위 타일 + 11위 이후 3열 컴팩트"),
}
