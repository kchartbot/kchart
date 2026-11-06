import json, sys
from datetime import datetime, timedelta
from pathlib import Path

K_HOT = 4755.15
R_BY_MIN = {5: 1.567, 10: 1.536, 15: 1.572, 20: 1.590, 25: 1.618, 30: 1.649, 35: 1.679, 40: 1.702, 45: 1.739, 50: 1.757, 55: 1.778}


def load(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return None


def save(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")


def num(v):
    try: return float(v)
    except Exception: return None


def stamp_dt(path):
    return datetime.strptime(Path(path).stem[:13], "%Y%m%d-%H%M")


def hour_dt(path, first_label):
    s = stamp_dt(path)
    h = int(first_label[:2])
    d = s.replace(hour=h, minute=0)
    if h > s.hour: d -= timedelta(days=1)
    return d


def five(data):
    hours = {}
    for f in sorted((data / "raw" / "five").glob("*.json")):
        r = (load(f) or {}).get("response")
        if not r or not r.get("XCATE"): continue
        hd = hour_dt(f, r["XCATE"][0])
        key = hd.strftime("%Y%m%d-%H00")
        h = hours.setdefault(key, {"hour": key, "songs": {}})
        h["updated"] = Path(f).stem
        for g in r["GRAPHDATALIST"]:
            sid = str(g["SONGID"])
            s = h["songs"].setdefault(sid, {"name": g["GRAPHCHARTINFO"].get("SONGNAME"), "hot": {}})
            for lab, p in zip(r["XCATE"], g["GRAPHDATA"]):
                v = num(p.get("VAL"))
                if v is not None: s["hot"][lab] = v
    for key, h in hours.items():
        for s in h["songs"].values():
            s["melon_est"] = {lab: round(v / R_BY_MIN[int(lab[3:])], 5) for lab, v in s["hot"].items() if int(lab[3:]) in R_BY_MIN}
            s["users_1h_est"] = None
            z = s["hot"].get(key[9:11] + ":00")
            if z is not None: s["users_1h_est"] = round(z * K_HOT)
        save(data / "derived" / "five" / f"{key}.json", h)
    return hours


def realtime(data):
    best = {}
    for f in sorted((data / "raw" / "hourly").glob("*.json")):
        best[Path(f).stem[:11]] = f
    for key, f in best.items():
        r = (load(f) or {}).get("response")
        if not r: continue
        rows = [{"rank": int(x["CURRANK"]), "past": int(x["PASTRANK"]), "id": x["SONGID"], "name": x["SONGNAME"],
                 "artists": [a["ARTISTNAME"] for a in x.get("ARTISTLIST", [])]} for x in r.get("CHARTLIST", [])]
        save(data / "derived" / "realtime" / f"{key}00.json", {"hour": key + "00", "source": Path(f).stem, "rows": rows})


def hot100(data, hours):
    best = {}
    for f in sorted((data / "raw" / "hot100").glob("*.json")):
        best[Path(f).stem[:11]] = f
    for key, f in best.items():
        r = (load(f) or {}).get("response")
        if not r: continue
        h = hours.get(key + "00", {"songs": {}})["songs"]
        rows = []
        for x in r.get("SONGLIST", []):
            s = h.get(str(x["SONGID"]))
            z = s["hot"].get(key[9:11] + ":00") if s else None
            rows.append({"rank": int(x["CURRANK"]), "past": int(x["PASTRANK"]), "id": x["SONGID"], "name": x["SONGNAME"],
                         "artists": [a["ARTISTNAME"] for a in x.get("ARTISTLIST", [])],
                         "hot_score": z, "users_1h_est": round(z * K_HOT) if z is not None else None})
        save(data / "derived" / "hot100" / f"{key}00.json", {"hour": key + "00", "source": Path(f).stem, "rows": rows})


def run(data):
    data = Path(data)
    hours = five(data)
    realtime(data)
    hot100(data, hours)


if __name__ == "__main__":
    run(sys.argv[1])
