import re, urllib.request

req = urllib.request.Request("https://www.melon.com/chart/index.htm", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36", "Accept-Language": "ko-KR,ko;q=0.9"})
h = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
rows = re.findall(r'<tr[^>]*data-song-no="\d+".*?</tr>', h, re.S)
print("ROWS", len(rows))
def squeeze(s): return re.sub(r"\s+", " ", s)
print("ROW6", squeeze(rows[5])[:2600])
for i, r in enumerate(rows):
    if "NEW" in r or "new" in re.findall(r'class="(\w+)"', r):
        print("NEWROW", i + 1, squeeze(r)[:900]); break
