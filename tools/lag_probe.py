import json, sys, time, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import recorder as rec
KST = timezone(timedelta(hours=9))
minutes = int(sys.argv[1])
log = Path("lag_out/lag.txt")
log.parent.mkdir(exist_ok=True)
last = {}
def now(): return datetime.now(KST)
def note(s):
    with open(log, "a", encoding="utf-8") as f: f.write(f"{now():%H:%M:%S} {s}\n")
def labs(o, key):
    r = o["response"]
    g = r["GRAPHDATALIST"][0]
    xs = r.get("XCATE") or []
    v = [l for l, p in zip(xs, g["GRAPHDATA"]) if p.get("VAL") not in ("", None)]
    return f"{r.get('RANKHOUR')}|{v[-1] if v else None}|{len(g['GRAPHDATA'])}|{g['GRAPHDATA'][-1].get('VAL')}"
def check(name, fn):
    try: v = fn()
    except Exception as e: v = "ERR " + type(e).__name__
    if last.get(name) != v:
        note(f"{name} {v}"); last[name] = v
def push():
    subprocess.run("cd lag_out && git init -q 2>/dev/null; git checkout -q -B lag; git add -A; git -c user.name=lag -c user.email=lag@x commit -qm lag; git push -q -f \"$LAG_REMOTE\" lag", shell=True)
end = time.time() + minutes * 60
tp = time.time()
while time.time() < end:
    check("five", lambda: labs(rec.raw_get(*rec.RAW["five"]), "five"))
    check("fivetop", lambda: (lambda r: f"{r.get('FIVETIME')}|{r.get('RANKHOUR')}|{[p.get('VAL') for p in r['GRAPHDATALIST'][0]['GRAPHDATA']][-1]}")(rec.raw_get(*rec.RAW["fivetop"])["response"]))
    check("hourly", lambda: (lambda r: f"{r['RANKHOUR']}|{r['CHARTLIST'][0]['SONGNAME']}|{r['CHARTLIST'][0]['CURRANK']}")(rec.raw_get(*rec.RAW["hourly"])["response"]))
    check("hourtop", lambda: (lambda r: f"{r['RANKHOUR']}|{r['GRAPHDATALIST'][0]['CHARTSTATIC']['SUMMCNT']}")(rec.raw_get(*rec.RAW["hourtop"])["response"]))
    check("report", lambda: (lambda r: f"{r.get('RECENTTIME')}|{rec.report_lite({'response': r}, '1')['predicted']}")(rec.raw_get(rec.REPORT[0], {**rec.REPORT[1], "songId": "603712834"})["response"]))
    if time.time() - tp > 240: push(); tp = time.time()
    time.sleep(2)
push()
