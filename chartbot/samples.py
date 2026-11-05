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
