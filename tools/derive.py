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
            inc = {}
            for lab, v in s["hot"].items():
                m = int(lab[3:])
                if m < 5 or v <= 0: continue
                p = s["hot"].get(f"{lab[:3]}{m - 5:02d}") if m > 5 else 0.0
                if p is None or (m > 5 and p <= 0): continue
                inc[lab] = round((v * m - (p * (m - 5) if m > 5 else 0.0)) / 60 * K_HOT)
            s["inc_users_5min_est"] = inc
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


def med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def mean(v):
    return sum(v) / len(v) if v else None


def stats(data, hours):
    out = data / "derived" / "stats"
    songs = {}
    cover = {}
    decay, spike, entry = [], [], []
    for key, h in sorted(hours.items()):
        hh = key[9:11]
        pts = {l for s in h["songs"].values() for l in s["hot"]}
        cover[key] = {"points": len(pts), "expected": 12, "last": max(pts) if pts else None}
        for sid, s in h["songs"].items():
            d = s["hot"]
            labs = sorted(d, key=lambda x: int(x[3:]))
            vals = [d[l] for l in labs]
            nz = [(l, d[l]) for l in labs if d[l] > 0]
            if not nz: continue
            rec = songs.setdefault(sid, {"name": s["name"], "hours": {}})
            peak = max(nz, key=lambda x: x[1])
            rec["hours"][key] = {"first": nz[0][1], "first_at": nz[0][0], "peak": peak[1], "peak_at": peak[0], "last": nz[-1][1],
                                 "last_at": nz[-1][0], "mean": round(mean([v for _, v in nz]), 5), "n": len(nz),
                                 "users_1h_est": s["users_1h_est"]}
            for a, b in zip(nz, nz[1:]):
                if int(a[0][3:]) >= 15 and int(b[0][3:]) - int(a[0][3:]) == 5: decay.append(b[1] / a[1])
            if "00:00".replace("00:00", hh + ":00") in d and hh + ":05" in d and d[hh + ":00"] > 0:
                spike.append(d[hh + ":05"] / d[hh + ":00"])
            if labs and d[labs[0]] == 0 and len(nz) > 1 and labs[0][3:] != "00":
                entry.append({"hour": key, "song": s["name"], "enter_at": labs[0], "first_score": nz[0][1]})
    save(out / "five_hot.json", {"songs": songs, "decay_5min_median": med(decay), "decay_5min_mean": mean(decay), "decay_n": len(decay),
                                 "spike_05_over_00_median": med(spike), "spike_n": len(spike), "entries": entry, "coverage": cover})
    r = {}
    for f in sorted((data / "derived" / "realtime").glob("*.json")):
        x = load(f)
        for row in x["rows"]:
            e = r.setdefault(row["id"], {"name": row["name"], "ranks": {}})
            e["ranks"][x["hour"]] = row["rank"]
    for e in r.values():
        v = list(e["ranks"].values()); k = list(e["ranks"])
        ch = [abs(a - b) for a, b in zip(v, v[1:])]
        e.update(best=min(v), worst=max(v), mean=round(mean(v), 2), hours=len(v), top10_hours=sum(1 for i in v if i <= 10),
                 mean_abs_change=round(mean(ch), 2) if ch else None)
    save(out / "realtime.json", {"songs": r})
    u = {}
    for sid, s in songs.items():
        ser = {k: v["users_1h_est"] for k, v in s["hours"].items() if v["users_1h_est"] is not None}
        if not ser: continue
        ks = sorted(ser)
        ch = {b: round((ser[b] - ser[a]) / ser[a] * 100, 2) for a, b in zip(ks, ks[1:])}
        u[sid] = {"name": s["name"], "hourly": ser, "change_pct": ch, "mean": round(mean(list(ser.values()))), "max": max(ser.values()), "min": min(ser.values())}
    save(out / "users.json", {"K": K_HOT, "songs": u})
    save(out / "summary.json", {"updated": max(hours) if hours else None, "hours": len(hours), "K": K_HOT, "R_BY_MIN": R_BY_MIN,
                                "decay_5min_median": med(decay), "spike_05_over_00_median": med(spike), "entries": len(entry)})


def run(data):
    data = Path(data)
    hours = five(data)
    realtime(data)
    hot100(data, hours)
    stats(data, hours)


if __name__ == "__main__":
    run(sys.argv[1])
