"""Poll Melon hourly endpoints every 2s around the top of the hour and print when each one changes."""
import hashlib, json, sys, time
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "tools")
import recorder as R

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
top = now.replace(minute=0, second=0, microsecond=0) + (timedelta(hours=1) if now.minute >= 30 else timedelta())
start, end = top - timedelta(seconds=20), top + timedelta(minutes=8)
while datetime.now(KST) < start:
    time.sleep(1)
last = {}


def sig(name, o):
    r = o.get("response") or {}
    s = {"RANKHOUR": r.get("RANKHOUR"), "RANKDAY": r.get("RANKDAY")}
    if name == "hourtop":
        s["cnt"] = [(g.get("CHARTSTATIC") or {}).get("SUMMCNT") for g in r.get("GRAPHDATALIST") or []]
    elif name == "hourly":
        s["top"] = [(x.get("SONGNAME"), x.get("CURRANK")) for x in (r.get("CHARTLIST") or [])[:3]]
    else:
        s["h"] = hashlib.md5(json.dumps(r, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]
    return json.dumps(s, ensure_ascii=False)


while datetime.now(KST) < end:
    for name in ("hourtop", "hourgraph", "hourly"):
        try:
            u, p = R.RAW[name]
            v = sig(name, R.raw_get(u, p))
        except Exception as e:
            v = "ERR " + type(e).__name__
        if last.get(name) != v:
            last[name] = v
            print(datetime.now(KST).strftime("%H:%M:%S"), name, v, flush=True)
    time.sleep(2)
