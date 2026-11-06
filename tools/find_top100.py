import re, sys, json, urllib.request
from datetime import datetime, timezone, timedelta
sys.path.insert(0, ".")
from chartbot import direct as D

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
now = datetime.now(timezone(timedelta(hours=9)))


def get(u, ref=None):
    h = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    if ref: h["Referer"] = ref
    r = urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=20)
    return r.status, r.read().decode("utf-8", "replace")


for p in ("genie", "bugs", "flo"):
    print("=====", p)
    text = ""
    for u in D.urls(p, now):
        try:
            st, t = get(u)
            print("GET", st, len(t), u)
            text += t if p != "flo" else t
            if p == "flo":
                print("FLOHEAD", t[:300])
                break
        except Exception as e:
            print("ERR", u, type(e).__name__, str(e)[:120])
    try:
        rows = D.PARSERS[p](text)
        print("ROWS", len(rows))
        for r in rows[:5]:
            print("  ", {k: (str(v)[:40]) for k, v in r.items()})
    except Exception as e:
        print("PARSE ERR", type(e).__name__, e)
    for m in re.findall(r'(\d{4}[.\-]\d{2}[.\-]\d{2}[^<]{0,30}\d{1,2}(?::\d{2}|시))', text)[:3]:
        print("TIME", m)

st, t = get("https://www.genie.co.kr/chart/top200?ditc=D&rtm=Y")
ids = re.findall(r'songid="(\d+)"', t)[:2]
print("GENIE IDS", ids)
for sid in ids[:1]:
    st, s = get(f"https://www.genie.co.kr/detail/songInfo?xgnm={sid}")
    for k in ("청취자", "재생", "좋아요", "listener", "play"):
        for m in re.findall(r'.{0,120}' + k + r'.{0,160}', s)[:3]:
            print("SONG", k, re.sub(r"\s+", " ", m)[:260])
for u in ("https://music.bugs.co.kr/chart/track/day/total", "https://www.genie.co.kr/chart/top200?ditc=D&rtm=N",
          "https://www.music-flo.com/api/display/v1/browser/chart/list"):
    try:
        st, x = get(u)
        print("EXTRA", st, len(x), u, re.sub(r"\s+", " ", x[:200]))
    except Exception as e:
        print("EXTRA ERR", u, type(e).__name__, str(e)[:100])
