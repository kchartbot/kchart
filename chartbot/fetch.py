"""가이섬.com 에서 멜론/지니/플로/벅스 차트를 가져와 파싱한다.

가이섬 페이지는 Next.js 서버 렌더링이라 HTML 안의 <script id="__NEXT_DATA__"> 에
차트 데이터가 JSON으로 그대로 들어 있다. JS 실행 없이 일반 HTTP GET 한 번이면 된다.

이용약관(6조 2항)에 따라 출처 표기가 필요하다. 렌더/업로드 단계에서 SOURCE_CREDIT 을 항상 붙인다.
"""
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

BASE = "https://xn--o39an51b2re.com"  # 가이섬.com (punycode)
SOURCE_CREDIT = "출처: 가이섬.com"


@dataclass(frozen=True)
class Spec:
    key: str
    platform: str     # 사이트 경로의 플랫폼 (melon / genie / flo / bugs)
    path: str         # 사이트 경로의 차트 이름
    title: str        # 게시글 제목에 쓰는 이름
    layout: str       # five | graph24 | table | table_counts | table_users
    cadence: str      # five = 5분마다, hourly = 정시 기준 시간당 1회
    slots: int = 0    # 그래프 칸 수 (five=13, graph24=24)
    max_rows: int = 100
    source: str = "gaisum"   # gaisum = 가이섬.com, direct = 각 플랫폼 공개 차트 페이지에서 직접 수집 (direct.py)

    @property
    def credit(self) -> str:
        if self.source == "direct":
            return f"출처: {({'melon': '멜론', 'genie': '지니', 'bugs': '벅스'})[self.platform]} 차트 (공개 순위)"
        return SOURCE_CREDIT


# 요청하신 구성: 멜론 6종 + 지니/플로/벅스는 가이섬에 있는 해당 항목만
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
# 가이섬을 거치지 않고 각 플랫폼 공개 차트에서 직접 수집하는 순위 중심 차트 (이용자 수·점수는 없음)
for _p, _n in (("melon", "멜론"), ("genie", "지니"), ("bugs", "벅스")):
    for _s in (
        Spec(f"{_p}_rank",       _p, "direct", f"{_n} 실시간 순위",          "table",       "hourly", source="direct"),
        Spec(f"{_p}_rank_graph", _p, "direct", f"{_n} 순위 추이 (24시간)",   "rankgraph24", "hourly", 24, source="direct"),
        Spec(f"{_p}_rank_five",  _p, "direct", f"{_n} 순위 5분 추이",        "rankfive",    "five",   13, source="direct"),
    ):
        SPECS[_s.key] = _s

# 이전 버전 설정 키 호환
ALIASES = {"five": "melon_five", "hot100": "melon_hot100_five"}

# samples/ 폴더의 샘플 파일 이름 (python run.py render 용)
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
    values: list | None = None      # 그래프 차트: 칸마다 값 (없는 칸 None, 차트 밖 0)
    count1: int | None = None       # TOP100: 1시간 이용자 수
    count2: int | None = None       # TOP100: 24시간 이용자 수
    count1_diff: int | None = None
    count2_diff: int | None = None
    count: int | None = None        # 24시간 이용자 수 차트
    count_diff: int | None = None
    ratio: dict | None = None       # 24시간 이용자 수 차트: 성별/연령 비율
    sid: str = ""                   # 가이섬 곡 ID (곡 상세 페이지 /song/melon/{sid})


@dataclass
class Chart:
    spec: Spec
    hour_start: datetime
    rows: list
    total: int = 0                  # 사이트 기준 전체 곡 수 (rows 는 max_rows 로 잘릴 수 있음)
    history: list | None = None     # 24시간 이용자 수 차트: 곡별 시간대별 이력 (history.py)

    @property
    def title(self):
        return self.spec.title

    @property
    def latest_slot(self):
        """그래프 차트에서 값이 하나라도 채워진 마지막 칸 인덱스. 없으면 None."""
        n = self.spec.slots
        last = None
        for i in range(n):
            if any(r.values and r.values[i] is not None for r in self.rows):
                last = i
        return last

    @property
    def stamp(self):
        """게시글 제목에 쓰는 기준 시각. 5분 차트는 가장 최근 칸, 나머지는 정시."""
        if self.spec.cadence == "five":
            s = self.latest_slot
            if s is not None:
                return self.hour_start + timedelta(minutes=5 * s)
        return self.hour_start


def build_url(key: str, hour_start: datetime) -> str:
    s = resolve(key)
    return f"{BASE}/chart/{s.platform}/{s.path}/{hour_start:%Y%m%d}/{hour_start:%H}"


def extract_page_props(text: str) -> dict:
    """페이지 HTML(또는 저장해 둔 JSON)에서 pageProps 전체를 꺼낸다 (곡 상세 페이지 등)."""
    m = _NEXT.search(text)
    obj = json.loads(m.group(1)) if m else json.loads(text)
    return obj["props"]["pageProps"] if "props" in obj else obj


def extract_data(text: str) -> dict:
    """페이지 HTML(또는 저장해 둔 JSON)에서 차트 데이터 dict 를 꺼낸다."""
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
    """가이섬이 429 를 돌려줌. 재시도하지 않고 이번 주기를 중단한다 (차단/제한 상태에서 계속 요청하지 않기 위해)."""


class Fetcher:
    """요청 간격을 지키는 단순 HTTP 클라이언트 (사이트 부하 최소화)."""

    def __init__(self, user_agent="chartbot/1.0", min_gap=3.0, timeout=15, retries=2):
        self.ua = user_agent
        self.min_gap = min_gap
        self.timeout = timeout
        self.retries = retries
        self._last = 0.0

    def get(self, url: str) -> str:
        err = None
        for attempt in range(self.retries + 1):
            # 간격에 약간의 무작위를 섞어 요청이 일정한 박자로 몰리지 않게 한다 (사이트 부하 분산)
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
                if e.code >= 500:  # 서버가 느리거나 제한을 건 경우: 천천히 재시도
                    time.sleep(10 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as e:
                err = e
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"요청 실패: {url} ({err})")


def get_chart(key: str, now: datetime, fetcher: Fetcher, cache_dir=None) -> Chart:
    """현재 시각 기준 최신 차트. 정시 직후라 새 시간대 페이지가 비어 있으면 직전 시간대를 쓴다.

    24시간 이용자 수 차트는 곡별 24시간 이력(chart.history)까지 함께 채운다.
    cache_dir 는 지난 시간대 페이지를 저장해 두는 폴더다 (과거 데이터는 변하지 않으므로 한 번만 받는다).
    """
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
