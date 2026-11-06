import re, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
def get(u, raw=False):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "ko-KR"}), timeout=20)
    b = r.read()
    return b if raw else b.decode("utf-8", "replace")
for site, u in (("melon", "https://www.melon.com/chart/index.htm"), ("genie", "https://www.genie.co.kr/chart/top200"),
                ("bugs", "https://music.bugs.co.kr/chart"), ("flo", "https://www.music-flo.com/")):
    try:
        h = get(u)
    except Exception as e:
        print(site, "ERR", e); continue
    links = re.findall(r'<link[^>]+rel="[^"]*(?:icon|apple-touch-icon)[^"]*"[^>]*>', h)
    metas = re.findall(r'<meta[^>]+property="og:image"[^>]*>', h)
    imgs = [m for m in re.findall(r'<img[^>]+>', h) if re.search(r'logo|bi_|brand', m, re.I)][:6]
    hl = re.findall(r'<h1[^>]*>.{0,300}?</h1>', h, re.S)[:2]
    print("=====", site)
    for x in links + metas + imgs: print("  ", re.sub(r"\s+", " ", x)[:260])
    for x in hl: print("  H1", re.sub(r"\s+", " ", x)[:300])
    for m in re.findall(r'url\(([^)]*logo[^)]*)\)', h)[:3]: print("  CSS", m[:200])
