"""Actions 에서 실행: 실제 멜론 TOP100 + 앨범 커버로 새 순위표 디자인(list1/list2)을 그려 8000px 이하로 나눠 저장한다."""
import sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
import chartbot.render as R
from chartbot.fetch import Fetcher
from chartbot.direct import get_direct_chart

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
now = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
f = Fetcher(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", min_gap=3.0)
chart = get_direct_chart("melon_rank", now, f, tempfile.mkdtemp())
cache = Path(tempfile.mkdtemp())
images = R.embed_images(chart, f, cache, budget=100, gap=0.4, size=None)
miss = [r.rank for r in chart.rows if r.image and r.image not in images]
noimg = [r.rank for r in chart.rows if not r.image]
print("곡", len(chart.rows), "이미지 받음", len(images), "못 받음", miss, "주소 없음", noimg)
print("큰 커버:", R.upgrade_covers(images, chart.rows), "/3")
for style in ("list2",):
    R.RANK_STYLE = style
    png = out / f"{style}.png"
    R.render_png(R.render_html(chart, images), png, R.png_scale(chart))
    im = Image.open(png); n = 2 if im.height > 7500 else 1
    step = -(-im.height // n)
    for i in range(n):
        im.crop((0, i * step, im.width, min(im.height, (i + 1) * step))).save(out / f"{style}_{i + 1}.png")
    png.unlink()
    print(style, im.size, "→", n, "장")
