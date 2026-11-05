from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

from .fetch import Chart, Fetcher, Row, Spec, resolve

PLATFORM_NAMES = {"melon": "멜론", "genie": "지니", "bugs": "벅스"}
KEEP_HOURS = 30
GRAPH_TOP = 5


def _txt(el) -> str:
    return " ".join(el.get_text(" ", strip=True).replace("\xa0", " ").split()) if el else ""


def _prev(rank: int, kind: str, n: int | None) -> int | None:
    if kind == "new":
        return None
    if kind == "up":
        return rank + (n or 0)
    if kind == "down":
        return max(1, rank - (n or 0))
    return rank


def _int(s: str) -> int | None:
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else None


def parse_melon(html: str) -> list[dict]:
    out = []
    for tr in BeautifulSoup(html, "html.parser").select("tr.lst50, tr.lst100"):
        rank = _int(_txt(tr.select_one("span.rank")))
        if not rank:
            continue
        w = tr.select_one("span.rank_wrap")
        icon = w.select_one(".bullet_icons") if w else None
        cls = " ".join(icon.get("class", [])) if icon else ""
        kind = "up" if "rank_up" in cls else "down" if "rank_down" in cls else "new" if "rank_new" in cls else "same"
        n = _int(_txt(w.select_one("span.up, span.down"))) if w else None
        img = tr.select_one("img")
        out.append(dict(rank=rank, previous=_prev(rank, kind, n), sid=tr.get("data-song-no", ""),
                        name=_txt(tr.select_one(".rank01 a")), artists=_txt(tr.select_one(".rank02 a")),
                        album=_txt(tr.select_one(".rank03 a")), image=(img.get("src") if img else "") or ""))
    return out


def parse_genie(html: str) -> list[dict]:
    out = []
    for tr in BeautifulSoup(html, "html.parser").select("table.list-wrap tbody tr.list"):
        num = tr.select_one("td.number")
        rank = _int(num.find(string=True, recursive=False) or "") if num else None
        if not rank:
            continue
        ch = num.select_one("span.rank span.rank > span")
        cls = " ".join(ch.get("class", [])) if ch else ""
        kind = "up" if "rank-up" in cls else "down" if "rank-down" in cls else "new" if "rank-new" in cls else "same"
        n = _int(ch.find(string=True, recursive=False) or "") if ch else None
        img = tr.select_one("a.cover img")
        src = (img.get("src") if img else "") or ""
        out.append(dict(rank=rank, previous=_prev(rank, kind, n), sid=tr.get("songid", ""),
                        name=_txt(tr.select_one("a.title")), artists=_txt(tr.select_one("a.artist")),
                        album=_txt(tr.select_one("a.albumtitle")), image="https:" + src if src.startswith("//") else src))
    return out


def parse_bugs(html: str) -> list[dict]:
    out = []
    for tr in BeautifulSoup(html, "html.parser").select("table.list.trackList tbody tr[trackid]"):
        rank = _int(_txt(tr.select_one("div.ranking strong")))
        if not rank:
            continue
        ch = tr.select_one("div.ranking p.change")
        cls = " ".join(ch.get("class", [])) if ch else ""
        kind = "up" if "up" in cls.split() else "down" if "down" in cls.split() else "new" if "new" in cls.split() else "same"
        n = _int(_txt(ch.select_one("em"))) if ch else None
        img = tr.select_one("a.thumbnail img")
        out.append(dict(rank=rank, previous=_prev(rank, kind, n), sid=tr.get("trackid", ""),
                        name=_txt(tr.select_one("p.title a")), artists=_txt(tr.select_one("p.artist a")),
                        album=_txt(tr.select_one("a.album")), image=(img.get("src") if img else "") or ""))
    return out


def urls(platform: str, now: datetime) -> list[str]:
    if platform == "melon":
        return ["https://www.melon.com/chart/index.htm"]
    if platform == "genie":
        base = f"https://www.genie.co.kr/chart/top200?ditc=D&ymd={now:%Y%m%d}&hh={now:%H}&rtm=Y&pg="
        return [base + "1", base + "2"]
    if platform == "bugs":
        return ["https://music.bugs.co.kr/chart/track/realtime/total"]
    raise KeyError(platform)


PARSERS = {"melon": parse_melon, "genie": parse_genie, "bugs": parse_bugs}


def _stamp(dt: datetime) -> str:
    return f"{dt:%Y%m%d%H%M}"


def _floor5(now: datetime) -> datetime:
    return now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"latest": None, "names": {}, "hist": {}}


def ensure_snapshot(platform: str, now: datetime, fetcher: Fetcher, store_dir) -> dict:
    store_dir = Path(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / f"{platform}.json"
    st = _load(path)
    stamp = _stamp(_floor5(now))
    if st["latest"] and st["latest"]["stamp"] == stamp:
        return st
    rows = []
    for u in urls(platform, now):
        rows += PARSERS[platform](fetcher.get(u))
    seen, uniq = set(), []
    for r in sorted(rows, key=lambda r: r["rank"]):
        if r["rank"] not in seen:
            seen.add(r["rank"])
            uniq.append(r)
    uniq = uniq[:100]
    if not uniq:
        raise RuntimeError(f"{PLATFORM_NAMES[platform]} 차트에서 곡을 찾지 못했습니다 (사이트 구조가 바뀌었을 수 있음)")
    st["latest"] = {"stamp": stamp, "rows": uniq}
    st["hist"][stamp] = {r["sid"]: r["rank"] for r in uniq if r["sid"]}
    for r in uniq:
        if r["sid"]:
            st["names"][r["sid"]] = {k: r[k] for k in ("name", "artists", "album", "image")}
    cutoff = _stamp(_floor5(now) - timedelta(hours=KEEP_HOURS))
    st["hist"] = {k: v for k, v in st["hist"].items() if k >= cutoff}
    path.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return st


def _row(d: dict, **kw) -> Row:
    return Row(rank=d["rank"], previous=d["previous"], name=d["name"], artists=d["artists"], album=d["album"],
               image=d["image"], sid=d["sid"], **kw)


def _value_at(hist: dict, when: datetime, sid: str, window_min: int):
    for k in range(0, window_min, 5):
        snap = hist.get(_stamp(when + timedelta(minutes=k)))
        if snap is not None:
            return snap.get(sid)
    return None


def build_chart(spec: Spec, now: datetime, store: dict) -> Chart:
    latest = store["latest"]
    hour = now.replace(minute=0, second=0, microsecond=0)
    rows = latest["rows"]
    if spec.layout == "table":
        return Chart(spec=spec, hour_start=hour, rows=[_row(d) for d in rows[: spec.max_rows]], total=len(rows))
    hist = store["hist"]
    out = []
    for d in rows[:GRAPH_TOP]:
        sid = d["sid"]
        if spec.layout == "rankgraph24":
            vals = [_value_at(hist, hour - timedelta(hours=spec.slots - 1 - i), sid, 20) for i in range(spec.slots)]
            vals[-1] = d["rank"]
        else:
            vals = [hist.get(_stamp(hour + timedelta(minutes=5 * i)), {}).get(sid) if _stamp(hour + timedelta(minutes=5 * i)) <= latest["stamp"] else None
                    for i in range(spec.slots)]
        out.append(_row(d, values=vals))
    return Chart(spec=spec, hour_start=hour, rows=out, total=len(rows))


def get_direct_chart(key: str, now: datetime, fetcher: Fetcher, store_dir) -> Chart:
    spec = resolve(key)
    store = ensure_snapshot(spec.platform, now, fetcher, store_dir)
    return build_chart(spec, now, store)
