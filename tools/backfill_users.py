import json, sys, time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chartbot.fetch import Fetcher, build_url, parse_chart

OUT = Path(sys.argv[1])
START = datetime.strptime(sys.argv[2], "%Y%m%d%H")
END = datetime.strptime(sys.argv[3], "%Y%m%d%H")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f = Fetcher(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", min_gap=4.0, retries=1)
    h = START
    while h <= END:
        p = OUT / f"{h:%Y%m%d-%H}00.json"
        try:
            c = parse_chart("melon_24h_count", f.get(build_url("melon_24h_count", h)))
            rows = [{"rank": r.rank, "name": r.name, "artists": r.artists, "sid": r.sid, "count": r.count, "diff": r.count_diff} for r in c.rows]
            p.write_text(json.dumps({"hour": f"{h:%Y%m%d-%H}00", "rows": rows}, ensure_ascii=False), encoding="utf-8")
            print(h, len(rows), [(r["name"], r["count"]) for r in rows])
        except Exception as e:
            print(h, "실패", type(e).__name__, str(e)[:100])
        h += timedelta(hours=1)
        time.sleep(1)


if __name__ == "__main__":
    main()
