import sys, time, traceback
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "tools")
import recorder as R

url, params = R.RAW["hourly"]
items = R.raw_get(url, params)["response"]["CHARTLIST"][:100]
rurl, base = R.REPORT


def one(x):
    t = time.time()
    try:
        o = R.raw_get(rurl, {**base, "songId": str(x["SONGID"])})
        r = R.report_lite(o, str(x["SONGID"]))
        return x["CURRANK"], "ok", round(time.time() - t, 2), r["recent"], r["predicted"], r["predict_text"], list((o.get("response") or {}).keys())[:6]
    except Exception as e:
        return x["CURRANK"], "ERR", round(time.time() - t, 2), type(e).__name__, str(e)[:120]


for n in (16, 16, 1):
    print(f"=== threads={n}", time.strftime("%H:%M:%S"), flush=True)
    with ThreadPoolExecutor(n) as ex:
        for row in ex.map(one, items):
            print(*row, flush=True)
    time.sleep(3)
