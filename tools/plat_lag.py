import re, sys, json, time, urllib.request, hashlib
from datetime import datetime, timezone, timedelta
sys.path.insert(0, ".")
from chartbot import direct as D
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
KST = timezone(timedelta(hours=9))
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}), timeout=20).read().decode("utf-8", "replace")
def sig(rows):
    return hashlib.md5("|".join(f"{r['rank']}:{r['sid']}:{r['previous']}" for r in rows).encode()).hexdigest()[:8]
last = {}
end = time.time() + int(sys.argv[1]) * 60
while time.time() < end:
    now = datetime.now(KST)
    for p, u in (("genie", "https://www.genie.co.kr/chart/top200?ditc=D&rtm=Y&pg=1"), ("bugs", "https://music.bugs.co.kr/chart/track/realtime/total"),
                 ("flo", "https://www.music-flo.com/api/display/v1/browser/chart/1/track/list?size=100")):
        try:
            t = get(u)
            rows = D.PARSERS[p](t)
            lab = re.findall(r'\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}', t)[:1]
            v = f"{lab} {sig(rows)} top={[r['name'][:6] for r in rows[:3]]}"
        except Exception as e:
            v = "ERR " + type(e).__name__
        if last.get(p) != v:
            print(f"{now:%H:%M:%S} {p} {v}", flush=True)
            last[p] = v
    time.sleep(10)
