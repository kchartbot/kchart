"""네트워크 없이 samples/ 폴더로 가이섬 응답을 흉내 내는 Fetcher.

`python run.py render` 와 테스트가 운영과 똑같은 코드 경로(get_chart -> 이력 수집 -> 렌더)를 오프라인으로 돌리게 해 준다.
  차트 페이지   samples/{플랫폼}-{차트}.json              (현재 시간대)
  지난 시간대   samples/hist-{차트}.json                  (요청 시각이 샘플 시각보다 과거일 때)
  곡 상세       samples/song-melon-{곡ID}.json
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .fetch import Fetcher


class SampleFetcher(Fetcher):
    def __init__(self, root):
        super().__init__(min_gap=0)
        self.root = Path(root)

    def get(self, url: str) -> str:
        if "music-flo.com" in url:
            return (self.root / "direct-flo.json").read_text(encoding="utf-8")
        if "melon.com/chart" in url:
            return (self.root / "direct-melon.html").read_text(encoding="utf-8")
        if "genie.co.kr/chart" in url:
            return (self.root / f"direct-genie-{url[-1]}.html").read_text(encoding="utf-8")
        if "music.bugs.co.kr/chart" in url:
            return (self.root / "direct-bugs.html").read_text(encoding="utf-8")
        m = re.search(r"/song/melon/(\d+)$", url)
        if m:
            return (self.root / f"song-melon-{m.group(1)}.json").read_text(encoding="utf-8")
        m = re.search(r"/chart/(\w+)/([\w-]+)/(\d{8})/(\d{2})$", url)
        if not m:
            raise FileNotFoundError(url)
        plat, path, ymd, hh = m.groups()
        main = self.root / f"{plat}-{path}.json"
        hist = self.root / f"hist-{path}.json"
        asked = datetime.strptime(ymd + hh, "%Y%m%d%H")
        sample_time = datetime.fromisoformat(json.loads(main.read_text(encoding="utf-8"))["time"])
        if asked < sample_time and hist.exists():
            return hist.read_text(encoding="utf-8")
        return main.read_text(encoding="utf-8")


def seed_sample_history(platform: str, now, fetcher, store_dir) -> None:
    """render 용: 최신 순위를 저장한 뒤, 지난 26시간의 순위를 무작위 변동으로 채워 그래프를 그릴 수 있게 한다 (샘플 전용)."""
    import random
    from datetime import timedelta

    from .direct import _floor5, _stamp, ensure_snapshot

    path = Path(store_dir) / f"{platform}.json"
    if path.exists():
        path.unlink()
    st = ensure_snapshot(platform, now, fetcher, store_dir)
    rnd = random.Random(platform)
    top = [r["sid"] for r in st["latest"]["rows"][:8]]
    cur = {sid: i + 1 for i, sid in enumerate(top)}
    t = _floor5(now)
    for k in range(1, 26 * 12):
        for sid in top:
            cur[sid] = max(1, min(14, cur[sid] + rnd.choice([-1, 0, 0, 0, 1])))
        st["hist"][_stamp(t - timedelta(minutes=5 * k))] = dict(cur)
    path.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
