from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

BASE = "https://xn--o39an51b2re.com"
SOURCE_CREDIT = "출처: 가이섬.com"


@dataclass(frozen=True)
class Spec:
    key: str
    platform: str
    path: str
    title: str
    layout: str
    cadence: str
    slots: int = 0
    max_rows: int = 100
    source: str = "gaisum"

    @property
    def credit(self) -> str:
        if self.source == "direct":
            return f"출처: {({'melon': '멜론', 'genie': '지니', 'bugs': '벅스'})[self.platform]} 차트 (공개 순위)"
        return SOURCE_CREDIT


SPECS = {s.key: s for s in [
    Spec("melon_top100",       "melon", "top100",        "멜론 TOP100",         "table_counts", "hourly"),
    Spec("melon_hot100_five",  "melon", "hot100-five",   "멜론 HOT100 5분 차트", "five",         "five",   13),
    Spec("melon_hot100_graph", "melon", "hot100-graph",  "멜론 HOT100 그래프",   "graph24",      "hourly", 24),
    Spec("melon_five",         "melon", "realtime-five", "멜론 5분 차트",        "five",         "five",   13),
    Spec("melon_realtime",     "melon", "realtime",      "멜론 실시간 차트",     "table",        "hourly"),
    Spec("melon_24h_count",    "melon", "24hour-count",  "멜론 이용자수 추이", "table_users",  "hourly"),
    Spec("genie_realtime",     "genie", "realtime",      "지니 실시간 차트",     "table",        "hourly"),
    Spec("flo_chart",          "flo",   "24hour",        "플로 차트",           "table",        "hourly"),
    Spec("bugs_realtime",      "bugs",  "realtime",      "벅스 실시간 차트",     "table",        "hourly"),
]}
for _p, _n in (("melon", "멜론"), ("genie", "지니"), ("bugs", "벅스")):
    for _s in (
        Spec(f"{_p}_rank",       _p, "direct", f"{_n} 실시간 순위",          "table",       "hourly", source="direct"),
        Spec(f"{_p}_rank_graph", _p, "direct", f"{_n} 순위 추이 (24시간)",   "rankgraph24", "hourly", 24, source="direct"),
        Spec(f"{_p}_rank_five",  _p, "direct", f"{_n} 순위 5분 추이",        "rankfive",    "five",   13, source="direct"),
    ):
        SPECS[_s.key] = _s

ALIASES = {"five": "melon_five", "hot100": "melon_hot100_five"}

def sample_name(spec: Spec) -> str:
    return f"{spec.platform}-{spec.path}.json"


_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def resolve(key: str) -> Spec:
    key = ALIASES.get(key, key)
    if key not in SPECS:
        raise KeyError(f"알 수 없는 차트 키: {key} (사용 가능: {', '.join(SPECS)})")
    return SPECS[key]


@dataclass
class Row:
    rank: int
    previous: int | None
    name: str
    artists: str
    album: str
    image: str
    values: list | None = None
    count1: int | None = None
    count2: int | None = None
    count1_diff: int | None = None
    count2_diff: int | None = None
    count: int | None = None
    count_diff: int | None = None
    ratio: dict | None = None
    sid: str = ""


@dataclass
class Chart:
    spec: Spec
    hour_start: datetime
    rows: list
    total: int = 0
    history: list | None = None

    @property
    def title(self):
        return self.spec.title

    @property
    def latest_slot(self):
        n = self.spec.slots
        last = None
        for i in range(n):
            if any(r.values and r.values[i] is not None for r in self.rows):
                last = i
        return last

    @property
    def stamp(self):
        if self.spec.cadence == "five":
            s = self.latest_slot
            if s is not None:
                return self.hour_start + timedelta(minutes=5 * s)
        return self.hour_start


def build_url(key: str, hour_start: datetime) -> str:
    s = resolve(key)
    return f"{BASE}/chart/{s.platform}/{s.path}/{hour_start:%Y%m%d}/{hour_start:%H}"


def extract_page_props(text: str) -> dict:
    m = _NEXT.search(text)
    obj = json.loads(m.group(1)) if m else json.loads(text)
    return obj["props"]["pageProps"] if "props" in obj else obj


def extract_data(text: str) -> dict:
    m = _NEXT.search(text)
    obj = json.loads(m.group(1)) if m else json.loads(text)
    if "props" in obj:
        obj = obj["props"]["pageProps"]["data"]
    if not obj or "data" not in obj:
        raise ValueError("차트 데이터를 찾지 못했습니다 (사이트 구조가 바뀌었을 수 있음)")
    return obj


def parse_chart(key: str, text: str) -> Chart:
    spec = resolve(key)
    d = extract_data(text)
    rows = []
    for item in d["data"]:
        song = item["song"]
        album = song.get("album") or {}
        vals = item.get("values")
        if vals is not None and spec.slots:
            vals = (list(vals) + [None] * spec.slots)[: spec.slots]
        rows.append(Row(
            rank=int(item["ranking"]),
            previous=item.get("previous"),
            name=song["name"],
            artists=", ".join(a["name"] for a in song.get("artists", [])),
            album=album.get("name", ""),
            image=album.get("image", ""),
            values=vals,
            count1=item.get("count1"), count2=item.get("count2"),
            count1_diff=item.get("count1Diff"), count2_diff=item.get("count2Diff"),
            count=item.get("count"), count_diff=item.get("countDiff"),
            ratio=item.get("ratio"),
            sid=str(song.get("id") or ""),
        ))
    rows.sort(key=lambda r: r.rank)
    total = int(d.get("totalSize") or d.get("size") or len(rows))
    return Chart(spec=spec, hour_start=datetime.fromisoformat(d["time"]), rows=rows[: spec.max_rows], total=total)


class RateLimited(RuntimeError):
    pass


class Fetcher:

    def __init__(self, user_agent="chartbot/1.0", min_gap=3.0, timeout=15, retries=2):
        self.ua = user_agent
        self.min_gap = min_gap
        self.timeout = timeout
        self.retries = retries
        self._last = 0.0

    def get(self, url: str) -> str:
        err = None
        for attempt in range(self.retries + 1):
            wait = self.min_gap * random.uniform(1.0, 1.5) - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "text/html",
                                                       "Accept-Language": "ko-KR,ko;q=0.9"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                err = e
                if e.code == 429:
                    ra = e.headers.get("Retry-After") if e.headers else None
                    raise RateLimited(f"요청이 제한되었습니다 (HTTP 429, Retry-After={ra}): {url}") from e
                if e.code >= 500:
                    time.sleep(10 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as e:
                err = e
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"요청 실패: {url} ({err})")


def get_chart(key: str, now: datetime, fetcher: Fetcher, cache_dir=None) -> Chart:
    spec = resolve(key)
    if spec.source == "direct":
        from .direct import get_direct_chart

        return get_direct_chart(key, now, fetcher, Path(cache_dir).parent / "rank" if cache_dir else "rank")
    hour = now.replace(minute=0, second=0, microsecond=0)
    for h in (hour, hour - timedelta(hours=1)):
        chart = parse_chart(key, fetcher.get(build_url(key, h)))
        if not chart.rows:
            continue
        if spec.cadence == "five" and chart.latest_slot is None:
            continue
        if spec.layout == "table_users":
            from .history import attach_history

            attach_history(chart, fetcher, cache_dir)
        return chart
    raise RuntimeError("최근 두 시간대 모두 데이터가 비어 있습니다")
