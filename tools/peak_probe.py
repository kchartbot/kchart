import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import recorder as rec
from chartbot.fetch import BASE, Fetcher, extract_page_props
out = Path("peak_out"); out.mkdir(exist_ok=True)
hourly = rec.raw_get(*rec.RAW["hourly"])["response"]["CHARTLIST"][:int(sys.argv[1])]
f = Fetcher(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", min_gap=4.0, retries=1)
res = {}
for x in hourly:
    sid = str(x["SONGID"])
    try:
        props = extract_page_props(f.get(f"{BASE}/song/melon/{sid}"))
        rec_ = [r for r in props.get("records") or [] if r.get("chart") == "MELON_24HOUR_COUNT"]
        res[sid] = {"name": x["SONGNAME"], "records": rec_}
        print(sid, x["SONGNAME"], [(r.get("type"), r.get("score"), r.get("time")) for r in rec_])
    except Exception as e:
        print(sid, "실패", type(e).__name__, str(e)[:80])
    (out / "peaks.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
