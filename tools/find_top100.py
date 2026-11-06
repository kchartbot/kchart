import re, urllib.request

req = urllib.request.Request("https://www.melon.com/chart/index.htm", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36", "Accept-Language": "ko-KR,ko;q=0.9"})
h = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
print("LEN", len(h))
for m in re.finditer(r'(year|hour|calendar_prid|d_time)[^<]{0,80}', h[:200000]):
    pass
print(re.findall(r'<span class="year">[^<]*</span>|<span class="hour">.*?</span>', h, re.S)[:4])
rows = re.findall(r'<tr[^>]*data-song-no="(\d+)"(.*?)</tr>', h, re.S)
print("ROWS", len(rows))
for sid, body in rows[:10]:
    name = re.search(r'class="ellipsis rank01">\s*<span>\s*<a[^>]*>(.*?)</a>', body, re.S)
    art = re.search(r'class="ellipsis rank02">.*?<a[^>]*>(.*?)</a>', body, re.S)
    rk = re.search(r'class="rank">(\d+)', body)
    gap = re.search(r'class="(up|down|none|new)"', body)
    gn = re.search(r'class="rank_wrap".*?<span class="[^"]*">\s*([^<]*)</span>', body, re.S)
    img = re.search(r'<img src="([^"]+)"', body)
    print(sid, rk and rk.group(1), name and name.group(1).strip()[:14], art and art.group(1).strip()[:10], gap and gap.group(1), gn and gn.group(1).strip(), img and img.group(1)[:90])
