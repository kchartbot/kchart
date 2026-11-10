import sys, json, time
sys.path.insert(0, "tools")
import recorder as R

print(time.strftime("%H:%M:%S"), flush=True)
h = R.raw_get(*R.RAW["hourly"])["response"]
print("hourly", h.get("RANKHOUR"))
ht = R.raw_get(*R.RAW["hourtop"])["response"]
print("hourtop", ht.get("RANKHOUR"), [(g["SONGID"], g["CHARTSTATIC"]["SUMMCNT"]) for g in ht.get("GRAPHDATALIST") or []])
rurl, base = R.REPORT
for x in h["CHARTLIST"][:12]:
    o = R.raw_get(rurl, {**base, "songId": str(x["SONGID"])})
    d = o.get("response") or o
    print(x["CURRANK"], x["SONGID"], x["SONGNAME"][:10], "|", json.dumps(d.get("LISTENERDATA"), ensure_ascii=False), "|",
          json.dumps((d.get("LISTENERCHART") or {}).get("INFO", {}).get("INFOLIST"), ensure_ascii=False)[:300], "|", d.get("RECENTTIME"), flush=True)
