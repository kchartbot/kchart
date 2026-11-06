import re, sys, json, urllib.request
from datetime import datetime, timezone, timedelta
sys.path.insert(0, ".")
from chartbot import direct as D
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
now = datetime.now(timezone(timedelta(hours=9)))
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}), timeout=20).read().decode("utf-8", "replace")
g = get("https://www.genie.co.kr/chart/top200?ditc=D&rtm=Y&pg=1")
for pat in (r'.{0,80}\d{4}\.\d{2}\.\d{2}.{0,80}', r'.{0,60}(?:hh|ymd|curHour|rankHour|chartDate)[^\n]{0,120}', r'.{0,60}\d{1,2}:00.{0,60}'):
    for m in re.findall(pat, g)[:6]:
        print("GENIE", re.sub(r"\s+", " ", m)[:220])
g2 = get(f"https://www.genie.co.kr/chart/top200?ditc=D&ymd={now:%Y%m%d}&hh={(now + timedelta(hours=1)):%H}&rtm=Y&pg=1")
print("GENIE_FUTURE rows", len(D.parse_genie(g2)), [r["name"][:8] for r in D.parse_genie(g2)[:3]])
b = get("https://music.bugs.co.kr/chart/track/realtime/total")
for m in re.findall(r'.{0,160}\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}.{0,120}', b)[:4]:
    print("BUGS", re.sub(r"\s+", " ", m)[:300])
f = json.loads(get("https://www.music-flo.com/api/display/v1/browser/chart/1/track/list?size=100"))
d = f["data"]
print("FLO keys", {k: v for k, v in d.items() if k != "trackList"})
for t in d["trackList"][:12]:
    print("FLO", t["name"][:10], json.dumps(t.get("rank"), ensure_ascii=False), t.get("updateDateTime"))
print("FLO track keys", list(d["trackList"][0].keys()))
for t in d["trackList"]:
    if (t.get("rank") or {}).get("newYn") == "Y":
        print("FLO NEW", t["name"][:10], t["rank"]); break
for u in ("https://www.music-flo.com/api/display/v1/browser/chart/1/list", "https://www.music-flo.com/api/display/v1/browser/chart/1"):
    try:
        x = json.loads(get(u)); print("FLO EXTRA", u, json.dumps({k: v for k, v in (x.get("data") or {}).items() if k != "trackList"}, ensure_ascii=False)[:400])
    except Exception as e:
        print("FLO EXTRA ERR", u, e)
