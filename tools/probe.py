import json, sys, time, urllib.request, urllib.parse
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "probe_out")
UA = "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36"
WITH, NEON, BHY, LOVE = "603712834", "603382333", "603712835", "602290711"
M2 = "https://m2.melon.com"
APP = "https://m.app.melon.com"
CAND = {
    "fivetop_app": f"{APP}/chart/hourly/fiveChartGraph.json?cpId=AS40&cpKey=14LNC3&v=4.0",
    "fivetop_app_nocp": f"{APP}/chart/hourly/fiveChartGraph.json?v=4.0",
    "fivetop_m2": f"{M2}/chart/hourly/fiveChartGraph.json?cpId=AS40&cpKey=14LNC3&v=4.0",
    "hourtop_graph_m2": f"{M2}/chart/hourly/hourlyChartGraph.json?appVer=5.0.4&cpId=IS40&cpKey=17LNM9&resolution=2&v=4.0",
    "hourtop_graph_app": f"{APP}/chart/hourly/hourlyChartGraph.json?cpId=AS40&cpKey=14LNC3&v=4.0&resolution=2",
    "m6_top_five": f"{M2}/m6/chart/top/five/graph.json?v=4.0&cpId=IS40&cpKey=17LNM9",
    "m6_ent_five": f"{M2}/m6/chart/ent/five/graph.json?v=4.0&cpId=IS40&cpKey=17LNM9",
    "m6_realtime_five": f"{M2}/m6/chart/realtime/five/graph.json?v=4.0&cpId=IS40&cpKey=17LNM9",
    "m6_hourly_five": f"{M2}/m6/chart/hourly/five/graph.json?v=4.0&cpId=IS40&cpKey=17LNM9",
    "m6_ent_graph": f"{M2}/m6/chart/ent/graph.json?v=4.0&cpId=IS40&cpKey=17LNM9",
    "hot_five_top100": f"{M2}/m6/chart/hour/five/graph.json?v=4.0&cpId=IS40&cpKey=17LNM9&chartType=TOP100",
    "hot_five_d30": f"{M2}/m6/chart/hour/five/graph.json?v=4.0&cpId=IS40&cpKey=17LNM9&chartType=D30",
    "hot_five_past": f"{M2}/m6/chart/hour/five/graph.json?v=4.0&cpId=IS40&cpKey=17LNM9&rankDay=20261106&rankHour=13:00",
    "stream_card_with": f"{M2}/m6/chart/streaming/card.json?cpId=AS40&cpKey=14LNC3&appVer=6.0.0&songId={WITH}",
    "stream_card_love": f"{M2}/m6/chart/streaming/card.json?cpId=AS40&cpKey=14LNC3&appVer=6.0.0&songId={LOVE}",
    "song_info_with": f"{M2}/m6/v5/song/info.json?cpId=IS40&cpKey=17LNM9&adultFlg=3&songId={WITH}",
    "report_a": f"{M2}/m6/chart/song/chartReport.json?appVer=6.6.2.1&songId={WITH}",
    "report_b": f"{M2}/m6/chart/song/chartReport.json?cpId=AS40&cpKey=14LNC3&appVer=6.22.1&songId={WITH}",
    "report_c": f"{M2}/m6/chart/song/chartReport.json?cpId=IS40&cpKey=17LNM9&appVer=6.22.1&songId={WITH}",
    "report_love": f"{M2}/m6/chart/song/chartReport.json?cpId=AS40&cpKey=14LNC3&appVer=6.2.0&songId={LOVE}",
    "top100_ent": f"{M2}/m6/chart/ent/songChartList.json?cpId=IS40&cpKey=17LNM9&appVer=6.22.1",
    "info_chart": f"{M2}/chart/chartInfo.htm",
    "info_hot100": f"{M2}/m6/chart/hot100ChartInfo.htm",
    "info_graph": f"{M2}/m6/chart/chartGraphInfo.htm",
    "info_ent": f"{M2}/m6/chart/chartEntInfo.htm?cpId=IS40&appVer=6.22.1",
    "info_day": f"{M2}/m5/chart/chartDayInfo.htm",
}


def brief(o, depth=0):
    if isinstance(o, dict):
        return {k: brief(v, depth + 1) if depth < 2 else type(v).__name__ for k, v in list(o.items())[:40]}
    if isinstance(o, list):
        return [len(o), brief(o[0], depth + 1) if o and depth < 2 else None]
    return o if not isinstance(o, str) or len(o) < 80 else o[:80]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name, url in CAND.items():
        rec = {"url": url}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html"})
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
                rec["status"] = r.status
                rec["type"] = r.headers.get("content-type")
            text = body.decode("utf-8", "replace")
            ext = "json"
            try:
                o = json.loads(text)
                rec["shape"] = brief(o)
            except Exception:
                ext = "html"
                rec["len"] = len(text)
            (OUT / f"{name}.{ext}").write_text(text, encoding="utf-8")
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        summary[name] = rec
        print(name, rec.get("status"), rec.get("error", ""), str(rec.get("shape", rec.get("len", "")))[:300])
        time.sleep(2)
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
