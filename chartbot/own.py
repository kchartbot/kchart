import base64
import dataclasses
import glob
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from chartbot import predtable
from chartbot.fetch import SPECS, Chart, Row
from chartbot.history import HRow, SongHistory
from chartbot.render import body_text, post_title, render_html, render_png

log = logging.getLogger("chartbot.own")

KEYS = ("own_top100", "own_users", "own_hot5", "own_melon5", "own_predict")


def _rec():
    import recorder
    return recorder


def _arts(x):
    return ", ".join(a["ARTISTNAME"] for a in (x or {}).get("ARTISTLIST", []))


def _int(v):
    try:
        n = int(v)
        return n if n > 0 else None
    except Exception:
        return None


class Own:
    def __init__(self, out, live=None, gaisum=None):
        self.out = Path(out)
        self.dir = self.out / "own"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.live = Path(live) if live else None
        self.gaisum = Path(gaisum) if gaisum else None
        self.rec = _rec()
        self.rec.DATA = self.dir
        self.cache = {}
        self.now = datetime.now()

    def get(self, name, max_age=3.0):
        c = self.cache.get(name)
        if c and time.monotonic() - c[0] < max_age:
            return c[1]
        url, params = self.rec.RAW[name]
        o = self.rec.raw_get(url, params)
        d = self.dir / "raw" / name
        self.rec.save(d / f"{self.now:%Y%m%d-%H%M}.json", o)
        for f in sorted(d.glob("*.json"))[:-40]:
            f.unlink(missing_ok=True)
        self.cache[name] = (time.monotonic(), o)
        return o

    def covers(self, hourly, ids=None):
        self.rec.covers_small(hourly)

    def images(self, items):
        out = {}
        for x in items:
            f = self.dir / "raw" / "covers_s" / f"{x.get('ALBUMID')}.jpg"
            if f.exists():
                out[str(x["ALBUMID"])] = "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
        return out

    def top100(self, now, state):
        if now.minute >= 20:
            return None
        stamp = f"{now:%Y%m%d%H}00"
        if state.get("own_top100") == stamp:
            return None
        hourly = self.get("hourly")
        if hourly["response"].get("RANKHOUR") != f"{now:%H}:00":
            return None
        items = hourly["response"]["CHARTLIST"][:100]
        self.covers(hourly)
        rows = [{"rank": _int(x["CURRANK"]), "cur": _int(x.get("PASTRANK")), "name": x["SONGNAME"], "artists": _arts(x),
                 "image": str(x["ALBUMID"])} for x in items]
        title = f"{now:%Y.%m.%d} {now:%H}:00 멜론 TOP100 순위표"
        html = predtable.page(title, rows, self.images(items), counts=True)
        return self.job("own_top100", stamp, f"[{now:%H}:00] 멜론 TOP100 순위표", "", html, 2.0)

    def predict(self, now, state):
        if now.minute < 30 or now.minute % 10 >= 6:
            return None
        slot = now.minute // 10 * 10
        stamp = f"{now:%Y%m%d%H}{slot:02d}"
        if state.get("own_predict") == stamp:
            return None
        hourly = self.get("hourly")
        items = hourly["response"]["CHARTLIST"][:100]
        url, base = self.rec.REPORT
        first = self.rec.report_lite(self.rec.raw_get(url, {**base, "songId": str(items[0]["SONGID"])}), str(items[0]["SONGID"]))
        if first.get("recent") != f"{now:%H}:{slot:02d}":
            return None
        self.covers(hourly)
        from concurrent.futures import ThreadPoolExecutor

        def one(x):
            try:
                o = self.rec.raw_get(url, {**base, "songId": str(x["SONGID"])})
                return x, self.rec.report_lite(o, str(x["SONGID"]))
            except Exception as e:
                log.warning("예측 수집 실패 %s %s", x.get("SONGID"), type(e).__name__)
                return x, None

        by = {}
        with ThreadPoolExecutor(8) as ex:
            for x, r in ex.map(one, items):
                p = _int((r or {}).get("predicted"))
                if p:
                    by.setdefault(p, []).append((x, r))
        if len(by) < 50:
            log.warning("예측 값이 너무 적어 건너뜀 (%d)", len(by))
            return None
        rows = []
        for k in range(1, 101):
            c = by.get(k)
            if not c:
                rows.append({"rank": k, "unknown": True})
                continue
            x, r = sorted(c, key=lambda z: _int(z[1].get("rank")) or 999)[0]
            rows.append({"rank": k, "cur": _int(r.get("rank")), "name": x["SONGNAME"], "artists": _arts(x), "image": str(x["ALBUMID"])})
        title = f"{now:%Y.%m.%d} {now:%H}:{slot:02d} 멜론 TOP100 순위 예측"
        html = predtable.page(title, rows, self.images(items))
        return self.job("own_predict", stamp, f"[{now:%H}:{slot:02d}] 멜론 TOP100 순위 예측", "", html, 2.0)

    def five_hours(self):
        import derive
        derive.five(self.dir)
        derive.melon5(self.dir)
        hours = {}
        for f in sorted((self.dir / "derived" / "five").glob("*.json")):
            hours[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        m5 = {}
        for f in sorted((self.dir / "derived" / "melon5").glob("*.json")):
            x = json.loads(f.read_text(encoding="utf-8"))
            m5[f.stem] = {sid: {"name": s["name"], "vals": {int(l[3:]): v for l, v in s["vals"].items()}} for sid, s in x["songs"].items()}
        return hours, m5

    def five(self, now, state, kind):
        key = "own_hot5" if kind == "hot" else "own_melon5"
        name = "five" if kind == "hot" else "fivetop"
        m = now.minute // 5 * 5
        stamp = f"{now:%Y%m%d%H}{m:02d}"
        if state.get(key) == stamp:
            return None
        self.get(name)
        hours, m5 = self.five_hours()
        hk = f"{now:%Y%m%d}-{now:%H}00"
        if kind == "hot":
            labs = {int(l[3:]) for s in (hours.get(hk) or {"songs": {}})["songs"].values() for l in s["hot"]}
        else:
            labs = {mm for e in (m5.get(hk) or {}).values() for mm in e["vals"]}
        if m not in labs:
            return None
        ms = list(range(0, m + 1, 5))
        items = []
        if kind == "hot":
            for s in (hours.get(hk) or {"songs": {}})["songs"].values():
                if s["hot"].get(f"{now:%H}:{m:02d}") is None:
                    continue
                items.append((s["name"], [s["hot"].get(f"{now:%H}:{x:02d}") or 0.0 for x in ms]))
            n, spec = 5, "melon_hot100_five"
        else:
            items = [(e["name"], [e["vals"].get(x) or 0.0 for x in ms]) for e in (m5.get(hk) or {}).values() if m in e["vals"]]
            n, spec = 3, "melon_five"
        items.sort(key=lambda z: -z[1][-1])
        rows = []
        for i, (nm, vs) in enumerate(items[:n]):
            vals = [None] * 13
            for j, v in enumerate(vs):
                vals[j] = v
            rows.append(Row(rank=i + 1, previous=None, name=nm, artists="", album="", image="", values=vals))
        chart = Chart(dataclasses.replace(SPECS[spec], source="direct"), now.replace(minute=0, second=0, microsecond=0), rows)
        return self.job(key, stamp, post_title(chart), self.body(chart), render_html(chart), 2.0, chart)

    def users(self, now, state):
        if now.minute >= 20:
            return None
        stamp = f"{now:%Y%m%d%H}00"
        if state.get("own_users") == stamp:
            return None
        ht = self.get("hourtop")["response"]
        if ht["RANKHOUR"][:2] != f"{now:%H}":
            return None
        hourly = self.get("hourly")
        end = now.replace(minute=0, second=0, microsecond=0)
        cnt, gai, rt, t100 = {}, {}, {}, {}
        files = sorted(glob.glob(str(self.dir / "raw/hourtop/*.json")))
        if self.live:
            files = sorted(glob.glob(str(self.live / "raw/hourtop/*.json"))) + files
        for f in files:
            try:
                r = json.load(open(f))["response"]
                key = r["RANKDAY"].replace(".", "") + "-" + r["RANKHOUR"][:2] + "00"
                for g in r["GRAPHDATALIST"]:
                    cnt[(key, str(g["SONGID"]))] = g["CHARTSTATIC"]["SUMMCNT"]
            except Exception:
                continue
        if self.gaisum:
            for f in glob.glob(str(self.gaisum / "*.json")):
                x = json.load(open(f))
                for r in x["rows"]:
                    gai[(x["hour"], str(r["sid"]))] = r["count"]
        if self.live:
            for f in glob.glob(str(self.live / "derived/realtime/*.json")):
                x = json.load(open(f))
                for r in x["rows"]:
                    rt[(x["hour"], str(r["id"]))] = r["rank"]
            for f in glob.glob(str(self.live / "top100/*.json")):
                x = json.load(open(f))
                for r in x["rows"]:
                    t100[(x["time"], r["name"])] = r["rank"]
        items = hourly["response"]["CHARTLIST"]
        hk = f"{end:%Y%m%d-%H}00"
        for x in items:
            rt[(hk, str(x["SONGID"]))] = _int(x["CURRANK"])
        try:
            hg = self.get("hourgraph")["response"]
            ex = hg["ENTCHARTXCATE"]
            for g in hg["GRAPHDATALIST"]:
                for i, e in enumerate(g.get("ENTGRAPHDATA", [])):
                    t = end.replace(hour=int(ex[i][:2]))
                    if t > end:
                        t -= timedelta(days=1)
                    if e.get("RANK"):
                        t100[(t.strftime("%Y%m%d-%H00"), g["GRAPHCHARTINFO"]["SONGNAME"])] = int(e["RANK"])
        except Exception:
            log.warning("T100 수집 실패")
        top = items[:3]
        self.rec.covers([ht])
        cov = {}
        for g in ht["GRAPHDATALIST"]:
            f = self.dir / "raw" / "covers" / f"{g['GRAPHCHARTINFO']['ALBUMID']}.jpg"
            if f.exists():
                cov[str(g["SONGID"])] = "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
        hist, rows = [], []
        for x in top:
            sid = str(x["SONGID"])
            hr, prev = [], None
            for i in range(24, -1, -1):
                t = end - timedelta(hours=i)
                key = t.strftime("%Y%m%d-%H00")
                c = cnt.get((key, sid)) or gai.get((key, sid))
                hr.append(HRow(time=t, rank=rt.get((key, sid)), t100=t100.get((key, x["SONGNAME"])), count=c, diff=(c - prev) if (c and prev) else None))
                prev = c
            cs = [h.count for h in hr if h.count]
            hist.append(SongHistory(sid=sid, name=x["SONGNAME"], artists=_arts(x), album="", image=cov.get(sid, ""), peak=max(cs) if cs else None, rows=hr))
            rows.append(Row(rank=_int(x["CURRANK"]), previous=_int(x.get("PASTRANK")), name=x["SONGNAME"], artists=_arts(x), album="", image="", sid=sid))
        chart = Chart(SPECS["melon_24h_count"], end, rows, history=hist)
        return self.job("own_users", stamp, post_title(chart), self.body(chart), render_html(chart, {v: v for v in cov.values()}), 1.6, chart)

    def body(self, chart):
        t = body_text(chart)
        c = chart.spec.credit
        return t[: -len(c)].rstrip() if c and t.endswith(c) else t

    def job(self, key, stamp, title, body, html, scale, chart=None):
        png = self.out / f"{key}_{stamp}.png"
        (self.out / f"{key}_{stamp}.html").write_text(html, encoding="utf-8")
        render_png(html, png, scale)
        return {"key": key, "stamp": stamp, "title": title, "body": body, "png": png}

    def jobs(self, now, state):
        self.now = now
        for fn in (lambda: self.five(now, state, "hot"), lambda: self.five(now, state, "mel"),
                   lambda: self.top100(now, state), lambda: self.users(now, state),
                   lambda: self.predict(now, state)):
            try:
                j = fn()
            except Exception:
                log.exception("own 차트 준비 실패")
                continue
            if j:
                yield j
