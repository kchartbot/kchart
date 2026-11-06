import re, os, urllib.request, urllib.parse, json
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
def get(u, raw=False):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "ko-KR"}), timeout=20)
    b = r.read()
    return b if raw else b.decode("utf-8", "replace")
os.makedirs("logos", exist_ok=True)
found = {}
for site, u in (("melon", "https://www.melon.com/chart/index.htm"), ("genie", "https://www.genie.co.kr/chart/top200"),
                ("bugs", "https://music.bugs.co.kr/chart"), ("flo", "https://www.music-flo.com/")):
    h = get(u)
    cands = re.findall(r'(?:href|content|src)="([^"]+\.(?:png|svg|ico|jpg|gif)[^"]*)"', h)
    cands = [c for c in cands if re.search(r"logo|favicon|apple|og_|1200x630|bi", c, re.I)]
    for css in re.findall(r'<link[^>]+href="([^"]+\.css[^"]*)"', h)[:12]:
        cu = urllib.parse.urljoin(u, css)
        try:
            c = get(cu)
        except Exception:
            continue
        for m in re.finditer(r'logo[^{]*\{[^}]*url\(["\']?([^)"\']+)', c, re.I):
            cands.append(urllib.parse.urljoin(cu, m.group(1)))
    for js in re.findall(r'<script[^>]+src="([^"]+\.js[^"]*)"', h)[:15] if site == "flo" else []:
        ju = urllib.parse.urljoin(u, js)
        try:
            c = get(ju)
        except Exception:
            continue
        for m in re.findall(r'["\']([^"\']*logo[^"\']*\.(?:svg|png))["\']', c, re.I)[:10]:
            cands.append(urllib.parse.urljoin(u, m))
    seen = []
    for c in cands:
        c = urllib.parse.urljoin(u, c if not c.startswith("//") else "https:" + c)
        if c in seen: continue
        seen.append(c)
    found[site] = seen[:14]
    for i, c in enumerate(seen[:14]):
        try:
            b = get(c, True)
            ext = re.search(r"\.(png|svg|ico|jpg|gif)", c, re.I).group(1).lower()
            open(f"logos/{site}_{i}.{ext}", "wb").write(b)
            print(site, i, len(b), c[:200])
        except Exception as e:
            print(site, i, "ERR", c[:200], e)
json.dump(found, open("logos/found.json", "w"), indent=1)
