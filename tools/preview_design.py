"""Actions 에서 실행: 실제 멜론 TOP100 + 앨범 커버로 순위표 디자인 10종을 그려 위쪽 일부와 전체 크기를 저장한다."""
import sys, tempfile, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
import chartbot.render as R
import chartbot.rankstyles as RS
from chartbot.fetch import Fetcher
from chartbot.direct import get_direct_chart

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
only = sys.argv[2].split(",") if len(sys.argv) > 2 else list(RS.STYLES)
now = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
f = Fetcher(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", min_gap=3.0)
chart = get_direct_chart("melon_rank", now, f, tempfile.mkdtemp())
images = R.embed_images(chart, f, Path(tempfile.mkdtemp()), budget=100, gap=0.3, size=None)
print("곡", len(chart.rows), "작은 이미지 받음", len(images), "주소 없음", [r.rank for r in chart.rows if not r.image])
print("샘플 이미지 주소:", chart.rows[0].image)
big = R.upgrade_covers(images, chart.rows, n=100, size=300)
print("큰(300) 커버 받음:", big, "/ 100")
info = {}
for k in only:
    R.RANK_STYLE = k
    png = out / f"{k}.png"
    R.render_png(R.render_html(chart, images), png, R.png_scale(chart))
    im = Image.open(png); info[k] = im.size
    im.crop((0, 0, im.width, min(im.height, 3000))).save(out / f"{k}_top.png")
    png.unlink()
    print(k, im.size)
(out / "sizes.json").write_text(json.dumps(info), encoding="utf-8")
