"""24시간 이용자 수 차트용: 곡별 시간대별 이력.

표의 각 열이 어디서 오는지 (가이섬 데이터, 참고 이미지와 값을 대조해 확인함)
  이용자수 / 증감   곡 상세 페이지 trends 의 MELON_24HOUR_COUNT
  순위              실시간 차트 순위 (trends 의 MELON_REALTIME_CHART). 없으면 24시간 이용자 수 차트의 순위
  T100              TOP100 순위 (trends 의 MELON_TOP100_CHART)
  최고 이용자수     곡 상세 페이지 records 의 MELON_24HOUR_COUNT / PEAK_COUNT

곡 상세 페이지 trends 는 최근 24시간(현재 시각 -23h ~ 현재)이라, 표의 맨 윗줄(현재 -24h)만
그 시각의 차트 페이지 3개(24시간 이용자 수 / 실시간 / TOP100)에서 따로 가져온다.
이 페이지들은 과거 데이터라 변하지 않으므로 cache_dir 에 저장해 두고 다시 받지 않는다.
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
