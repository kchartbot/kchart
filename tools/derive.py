import json, sys
from datetime import datetime, timedelta
from pathlib import Path

K_HOT = 4755.15
K_BASIS = "20261103-1900"
R_HOUR = {
    13: {0: 2.0192, 5: 1.7055, 10: 1.7124, 15: 1.7107, 20: 1.7525, 25: 1.7715, 30: 1.8162, 35: 1.8468, 40: 1.8829, 45: 1.9187, 50: 1.9640, 55: 2.0020},
    14: {0: 2.0322, 5: 1.6660, 10: 1.7294, 15: 1.7733, 20: 1.8105, 25: 1.8454, 30: 1.8904, 35: 1.9188, 40: 1.9416, 45: 1.9686, 50: 2.0017, 55: 2.0323},
}
R_BY_MIN = {m: round((R_HOUR[13][m] + R_HOUR[14][m]) / 2, 4) for m in R_HOUR[13]}


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
            rt = R_HOUR.get(int(key[9:11]), R_BY_MIN)
            s["melon_est"] = {lab: round(v / rt[int(lab[3:])], 5) for lab, v in s["hot"].items() if int(lab[3:]) in rt}
            inc = {}
            for lab, v in s["hot"].items():
                m = int(lab[3:])
                if m < 5 or v <= 0: continue
                p = s["hot"].get(f"{lab[:3]}{m - 5:02d}") if m > 5 else 0.0
                if p is None or (m > 5 and p <= 0): continue
                inc[lab] = round((v * m - (p * (m - 5) if m > 5 else 0.0)) / 60 * K_HOT)
            s["inc_users_5min_rel"] = inc
            s["users_1h_rel"] = None
            z = s["hot"].get(key[9:11] + ":00")
            if z is not None: s["users_1h_rel"] = round(z * K_HOT)
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
                         "hot_score": z, "users_1h_rel": round(z * K_HOT) if z is not None else None})
        save(data / "derived" / "hot100" / f"{key}00.json", {"hour": key + "00", "source": Path(f).stem, "rows": rows})


MINUS = "\u2212"


def n5(v):
    t = repr(round(float(v), 5))
    return "0" if t in ("0.0", "-0.0") else t


def sg(v):
    return ("+" if v >= 0 else MINUS) + repr(round(abs(float(v)), 5))


def post_body(series):
    out = []
    for k, (name, vs) in enumerate(series):
        d = vs[-1] - (vs[-2] if len(vs) > 1 else 0.0)
        out += [f"[{k + 1}위 예측] {name} ({sg(d)})", "|".join(n5(v) for v in vs)]
        if k + 1 < len(series):
            out += ["", f"[{n5(vs[-1] - series[k + 1][1][-1])}]", ""]
    return "\n".join(out)


def melon5(data):
    out = {}
    for f in sorted((data / "raw" / "fivetop").glob("*.json")):
        r = (load(f) or {}).get("response")
        if not r or not r.get("GRAPHDATALIST") or not str(r.get("FIVETIME", "")).isdigit(): continue
        st = stamp_dt(f)
        h = (int(r["FIVETIME"]) - 1) % 24
        d = st.replace(hour=h, minute=0)
        if h > st.hour: d -= timedelta(days=1)
        key = d.strftime("%Y%m%d-%H00")
        hk = out.setdefault(key, {})
        for g in r["GRAPHDATALIST"]:
            sid = str(g["SONGID"])
            vals = [num(p.get("VAL")) for p in g.get("GRAPHDATA", [])]
            e = hk.setdefault(sid, {"name": (g.get("GRAPHCHARTINFO") or {}).get("SONGNAME"), "prev": None, "vals": {}})
            if vals: e["prev"] = vals[0]
            for i, v in enumerate(vals[1:]):
                if v is not None: e["vals"][5 * i] = v
    for key, hk in out.items():
        save(data / "derived" / "melon5" / f"{key}.json", {"hour": key, "songs": {sid: {"name": e["name"], "prev": e["prev"], "vals": {f"{key[9:11]}:{m:02d}": v for m, v in sorted(e["vals"].items())}} for sid, e in hk.items()}})
    return out


def users24(data):
    tl = {}
    for f in sorted((data / "raw" / "hourtop").glob("*.json")):
        r = (load(f) or {}).get("response")
        if not r or not r.get("RANKDAY"): continue
        key = r["RANKDAY"].replace(".", "") + "-" + r["RANKHOUR"][:2] + "00"
        rows = []
        for g in r.get("GRAPHDATALIST", []):
            c = g.get("CHARTSTATIC") or {}
            rows.append({"rank": g.get("GRAPHRANK"), "id": str(g.get("SONGID")), "name": (g.get("GRAPHCHARTINFO") or {}).get("SONGNAME"),
                         "users24": c.get("SUMMCNT"), "female": c.get("FEMALERT"), "male": c.get("MALERT"),
                         "age": [c.get(f"AGE{a}RT") for a in (10, 20, 30, 40, 50, 60)], "share": g.get("SHAREVALUE"),
                         "hourly": dict(zip(r.get("XCATE", "").split(","), [num(p.get("VAL")) for p in g.get("GRAPHDATA", [])]))})
        save(data / "derived" / "users24" / f"{key}.json", {"hour": key, "rows": rows})
        for x in rows:
            tl.setdefault(x["id"], {"name": x["name"], "users24": {}})["users24"][key] = x["users24"]
    save(data / "derived" / "stats" / "users24.json", tl)


def listener_series(data):
    L = {}
    for f in sorted((data / "raw" / "reportlite").glob("*.json")):
        st = stamp_dt(f)
        for r in (load(f) or {}).get("rows", []):
            rc, v = r.get("recent"), r.get("listeners")
            if not rc or v is None: continue
            t = st.replace(hour=int(rc[:2]), minute=int(rc[3:5]))
            if t > st: t -= timedelta(days=1)
            L.setdefault(r["id"], {})[t] = v
    return L


def window_sum(series, t, hours=24):
    w = [v for k, v in series.items() if t - timedelta(hours=hours) < k <= t]
    need = hours * 6 * 0.7
    return (sum(w) / len(w) * hours * 6, len(w)) if len(w) >= need else (None, len(w))


def users24_est(data):
    L = listener_series(data)
    actual = {}
    for f in (data / "derived" / "users24").glob("*.json"):
        x = load(f) or {}
        for r in x.get("rows", []):
            if r.get("users24"): actual[(x["hour"], r["id"])] = r["users24"]
    rho = {}
    for (key, sid), u in actual.items():
        s, n = window_sum(L.get(sid, {}), datetime.strptime(key, "%Y%m%d-%H%M"))
        if s: rho.setdefault(sid, []).append((key, u / s))
    allr = sorted(v for xs in rho.values() for _, v in xs)
    default = allr[len(allr) // 2] if allr else None
    timeline = {}
    for f in sorted((data / "derived" / "realtime").glob("*.json")):
        x = load(f) or {}
        key = x.get("hour")
        if not key: continue
        t = datetime.strptime(key, "%Y%m%d-%H%M")
        rows = []
        for r in x.get("rows", [])[:30]:
            sid = str(r["id"])
            out = {"rank": r["rank"], "id": sid, "name": r["name"], "users24": None, "source": None, "rho": None}
            if (key, sid) in actual:
                out.update(users24=actual[(key, sid)], source="melon")
            else:
                s, n = window_sum(L.get(sid, {}), t)
                if s:
                    cand = rho.get(sid)
                    if cand:
                        k0, r0 = min(cand, key=lambda kv: abs((datetime.strptime(kv[0], "%Y%m%d-%H%M") - t).total_seconds()))
                        out.update(users24=round(r0 * s), source="est", rho=round(r0, 4), rho_at=k0)
                    elif default:
                        out.update(users24=round(default * s), source="rough", rho=round(default, 4))
            rows.append(out)
            if out["users24"]:
                timeline.setdefault(sid, {"name": r["name"], "hours": {}})["hours"][key] = {"users24": out["users24"], "source": out["source"], "rank": r["rank"]}
        save(data / "derived" / "users24_table" / f"{key}.json", {"hour": key, "rows": rows})
    save(data / "derived" / "stats" / "users24_est.json", {"rho": {k: v for k, v in rho.items()}, "default_rho": default, "songs": timeline})


def r_measured(data, hours, m5):
    out = {}
    for key, h in hours.items():
        hk = m5.get(key)
        if not hk: continue
        hh = key[9:11]
        for m in range(0, 60, 5):
            rs = []
            for sid, s in h["songs"].items():
                v = s["hot"].get(f"{hh}:{m:02d}")
                w = (hk.get(sid) or {}).get("vals", {}).get(m)
                if v and w: rs.append(v / w)
            if rs: out.setdefault(key, {})[f"{m:02d}"] = round(sorted(rs)[len(rs) // 2], 5)
    save(data / "derived" / "stats" / "r_measured.json", out)


def melon_predict(data):
    rt = {}
    for f in (data / "derived" / "realtime").glob("*.json"):
        x = load(f) or {}
        rt[x.get("hour")] = {str(r["id"]): r["rank"] for r in x.get("rows", [])}
    rounds = []
    for f in sorted((data / "raw" / "reportlite").glob("*.json")):
        x = load(f) or {}
        if x.get("n") != 100: continue
        st = stamp_dt(f)
        nxt = (st.replace(minute=0) + timedelta(hours=1)).strftime("%Y%m%d-%H00")
        rows = [r for r in x.get("rows", []) if r.get("predicted")]
        rec = {"stamp": x["stamp"], "target": nxt, "rows": rows}
        save(data / "derived" / "predict_melon" / f"{x['stamp']}.json", rec)
        act = rt.get(nxt)
        if act:
            pairs = [(int(r["predicted"]), act[r["id"]]) for r in rows if r["id"] in act]
            top10 = [p for p in pairs if p[1] <= 10]
            rounds.append({"stamp": x["stamp"], "target": nxt, "n": len(pairs), "exact": sum(1 for a, b in pairs if a == b),
                           "top10_exact": sum(1 for a, b in top10 if a == b), "mae": round(mean([abs(a - b) for a, b in pairs]), 3) if pairs else None})
    save(data / "derived" / "stats" / "predict_melon.json", {"rounds": rounds})


def posts(data, hours, m5=None):
    m5 = m5 or {}
    for key, h in hours.items():
        hh = key[9:11]
        rt = R_HOUR.get(int(hh), R_BY_MIN)
        labs = sorted({int(l[3:]) for s in h["songs"].values() for l in s["hot"]})
        for m in labs:
            hot, mel = [], []
            for s in h["songs"].values():
                vs = [s["hot"].get(f"{hh}:{x:02d}") or 0.0 for x in range(0, m + 1, 5)]
                if s["hot"].get(f"{hh}:{m:02d}") is None: continue
                hot.append((s["name"], vs))
                if all(x in rt for x in range(0, m + 1, 5)):
                    mel.append((s["name"], [round(v / rt[5 * i], 5) for i, v in enumerate(vs)]))
            est = True
            act = [(e["name"], [e["vals"].get(x) or 0.0 for x in range(0, m + 1, 5)]) for e in (m5.get(key) or {}).values() if m in e["vals"]]
            if act:
                mel, est = act, False
            hot.sort(key=lambda x: -x[1][-1])
            mel.sort(key=lambda x: -x[1][-1])
            day = key[:8]
            tick = f"{hh}:{m:02d}"
            rec = {"tick": f"{day} {tick}",
                   "hot100": {"title": f"[{tick}] 멜론 HOT100 5분 차트", "image_title": f"[{day} {tick}] 멜론 HOT100 5분 차트", "body": post_body(hot[:5])},
                   "melon": {"title": f"[{tick}] 멜론 5분 차트", "image_title": f"[{day} {tick}] 멜론 5분 차트", "body": post_body(mel[:3]), "estimated": est}}
            save(data / "derived" / "posts" / f"{day}-{hh}{m:02d}.json", rec)


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
                                 "users_1h_rel": s["users_1h_rel"]}
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
        ser = {k: v["users_1h_rel"] for k, v in s["hours"].items() if v["users_1h_rel"] is not None}
        if not ser: continue
        ks = sorted(ser)
        ch = {b: round((ser[b] - ser[a]) / ser[a] * 100, 2) for a, b in zip(ks, ks[1:])}
        u[sid] = {"name": s["name"], "hourly": ser, "change_pct": ch, "mean": round(mean(list(ser.values()))), "max": max(ser.values()), "min": min(ser.values())}
    save(out / "users.json", {"K": K_HOT, "K_basis": K_BASIS, "relative": True, "songs": u})
    save(out / "summary.json", {"updated": max(hours) if hours else None, "hours": len(hours), "K": K_HOT, "K_basis": K_BASIS, "R_BY_MIN": R_BY_MIN,
                                "decay_5min_median": med(decay), "spike_05_over_00_median": med(spike), "entries": len(entry)})


def run(data):
    data = Path(data)
    hours = five(data)
    realtime(data)
    hot100(data, hours)
    stats(data, hours)
    m5 = melon5(data)
    users24(data)
    users24_est(data)
    r_measured(data, hours, m5)
    melon_predict(data)
    posts(data, hours, m5)


if __name__ == "__main__":
    run(sys.argv[1])
