"""For 24-hour user count charts: historical data by song and time period.

Where each column of the table comes from (verified by comparing Gaeseom data with the reference images and values)
  User count / change on the song detail page trends: MELON_24HOUR_COUNT
  Real-time chart rankings (MELON_REALTIME_CHART). If not, the 24-hour user count chart ranking
  T100              TOP100 순위 (trends 의 MELON_TOP100_CHART)
  Highest number of users: MELON_24HOUR_COUNT / PEAK_COUNT of the song detail page records

The trends on the song detail page are for the past 24 hours (current time -23h to present), so only the top row of the table (current -24h) is shown
Extract them separately from the three chart pages at that time (24-hour user count / real-time / TOP100).
Since these pages are historical data, they are stored in cache_dir and are not re-downloaded.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .fetch import BASE, Chart, Fetcher, extract_data, extract_page_props

HOURS = 25            # 현재 -24h ... 현재, 총 25행
MAX_SONGS = 6         # 한 이미지에 담는 최대 곡 수 (3곡씩 줄바꿈)
NIGHT = range(2, 8)   # 2~7시: 새벽 시간대 (음영 표시, 실시간 순위 데이터가 비면 직전 값을 이어 씀)


@dataclass
class HRow:
    time: datetime
    rank: int | None
    t100: int | None
    count: int | None
    diff: int | None
    est: str | None = None


@dataclass
class SongHistory:
    sid: str
    name: str
    artists: str
    album: str
    image: str
    peak: int | None
    rows: list  # HRow, 오래된 시간 -> 최신

    @property
    def window_max(self):
        counts = [r.count for r in self.rows if r.count]
        return max(counts) if counts else None


def _hour_maps(hour: datetime, fetcher: Fetcher, cache_dir) -> dict:
    """한 시간대의 {곡ID: {"rt": 실시간순위, "top": TOP100순위, "cnt": [순위, 이용자수, 증감]}}."""
    cache = Path(cache_dir) / "hist" / f"{hour:%Y%m%d%H}.json" if cache_dir else None
    if cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    maps, complete = {}, True
    for field, path in (("cnt", "24hour-count"), ("rt", "realtime"), ("top", "top100")):
        url = f"{BASE}/chart/melon/{path}/{hour:%Y%m%d}/{hour:%H}"
        try:
            data = extract_data(fetcher.get(url))
        except Exception:  # 페이지가 없거나 비어 있으면 그 열만 비운다 (이번엔 캐시하지 않고 다음에 다시 시도)
            complete = False
            continue
        for item in data["data"]:
            sid = str(item["song"].get("id") or "")
            if not sid:
                continue
            maps.setdefault(sid, {})[field] = (
                [item["ranking"], item.get("count"), item.get("countDiff")] if field == "cnt" else item["ranking"]
            )
    if cache and complete:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(maps, ensure_ascii=False), encoding="utf-8")
    return maps


def _by_time(props: dict, chart_name: str) -> dict:
    for t in props.get("trends") or []:
        if t.get("chart") == chart_name:
            return {datetime.fromisoformat(d["time"]): d for d in t.get("data") or []}
    return {}


def build_song_history(row, end: datetime, fetcher: Fetcher, first_hour_maps: dict) -> SongHistory:
    props = extract_page_props(fetcher.get(f"{BASE}/song/melon/{row.sid}"))
    top = _by_time(props, "MELON_TOP100_CHART")
    rt = _by_time(props, "MELON_REALTIME_CHART")
    cnt = _by_time(props, "MELON_24HOUR_COUNT")
    peak = next(
        (r.get("score") for r in props.get("records") or [] if r.get("chart") == "MELON_24HOUR_COUNT" and r.get("type") == "PEAK_COUNT"),
        None,
    )
    first = first_hour_maps.get(row.sid, {})
    rows, last_rank = [], None
    for i in range(HOURS):
        h = end - timedelta(hours=HOURS - 1 - i)
        if i == 0:  # trends 가 닿지 않는 맨 윗줄
            c = first.get("cnt") or [None, None, None]
            rt_rank, t100, c_rank, count, diff = first.get("rt"), first.get("top"), c[0], c[1], c[2]
        else:
            ci = cnt.get(h) or {}
            rt_rank = (rt.get(h) or {}).get("ranking")
            t100 = (top.get(h) or {}).get("ranking")
            c_rank, count, diff = ci.get("ranking"), ci.get("count"), ci.get("countDiff")
        rank = rt_rank if rt_rank is not None else c_rank
        if rank is None and last_rank is not None and h.hour in NIGHT:
            rank = last_rank  # 새벽에 실시간 순위가 수집되지 않은 구간은 직전 순위를 이어 쓴다
        if rank is not None:
            last_rank = rank
        rows.append(HRow(h, rank, t100, count, diff))
    return SongHistory(row.sid, row.name, row.artists, row.album, row.image, peak, rows)


def attach_history(chart: Chart, fetcher: Fetcher, cache_dir=None) -> None:
    songs = [r for r in chart.rows if r.sid][:MAX_SONGS]
    first_hour = chart.hour_start - timedelta(hours=HOURS - 1)
    maps = _hour_maps(first_hour, fetcher, cache_dir) if songs else {}
    chart.history = [build_song_history(r, chart.hour_start, fetcher, maps) for r in songs]
