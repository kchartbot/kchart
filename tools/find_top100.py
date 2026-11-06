import json, sys, urllib.request, urllib.parse
sys.path.insert(0, "tools")
import recorder as R

KEYS = [{"cpId": "IS40", "cpKey": "17LNM9"}, {"cpId": "AS40", "cpKey": "14LNM3"}]
HOSTS = ["https://m2.melon.com", "https://m.app.melon.com"]
PATHS = ["/m6/chart/hot100/list.json", "/m6/chart/top100/list.json", "/m6/chart/hour/list.json", "/m6/chart/realtime/list.json",
         "/m6/chart/day/list.json", "/m6/chart/hourly/list.json", "/m6/chart/main/list.json", "/m6/chart/chartList.json",
         "/chart/hourly/hourlyChartList.json", "/chart/top100/list.json", "/chart/realtime/list.json", "/chart/day/list.json",
         "/m6/chart/top/list.json", "/m6/chart/total/list.json"]
TYPES = [None, "D100", "TOP100", "T100", "H100", "24H", "HOUR", "REALTIME", "RT", "D24", "H24", "TOP", "HOT100", "DAY"]
for h in HOSTS:
    for p in PATHS:
        for t in TYPES:
            for k in KEYS:
                q = {**k, "v": "4.0", "appVer": "6.22.1", "resolution": "2", "pageSize": "100"}
                if t: q["chartType"] = t
                try:
                    o = R.raw_get(h + p, q)
                except Exception as e:
                    c = getattr(e, "code", type(e).__name__)
                    if c not in (404, 400, "URLError"):
                        print("ERR", h + p, t, c)
                    continue
                r = o.get("response") or o.get("RESPONSE") or {}
                lst = r.get("CHARTLIST") or r.get("SONGLIST") or []
                top = [(x.get("CURRANK"), (x.get("SONGNAME") or "")[:6]) for x in lst[:6]]
                print("OK", h + p, t, k["cpId"], r.get("RANKHOUR"), r.get("PAGE"), top, flush=True)
