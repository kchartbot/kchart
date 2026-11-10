"""(그래프·이용자수 추이 등)을 복사해 붙인 텍스트를 곡별 숫자로 바꿔 저장한다.

사용: python tools/ingest.py "<제목, 예: [01:00] 멜론 실시간 그래프>" 글.txt [저장폴더]
저장: 저장폴더/samples/<제목>.json  (원문도 같이 보관 → 나중에 파서를 고쳐도 다시 읽을 수 있음)
형식: "[1위 40.52%] With (-0.4662)" 줄 다음에 "a|b|c..." 값 줄, 그 다음 "[x]" 줄(다음 순위와의 차이) 이 곡마다 반복.
"""
import json, re, sys
from pathlib import Path

HEAD = re.compile(r"\[(\d+)위\s*([\d.]+)%\]\s*(.+?)\s*\(([+\-−]?[\d.]+)\)\s*$")
def num(x): return float(x.replace("−", "-"))

def parse(text):
    songs, cur = [], None
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln: continue
        m = HEAD.match(ln)
        if m:
            cur = {"rank": int(m[1]), "share": float(m[2]), "name": m[3], "change": num(m[4]), "values": [], "gap": None}
            songs.append(cur); continue
        if cur is None: continue
        if re.fullmatch(r"\[[\d.,]+\]", ln):
            cur["gap"] = num(ln.strip("[]").replace(",", "")); continue
        if "|" in ln:
            vals = []
            for t in ln.split("|"):
                t = t.strip().replace(",", "")
                if re.fullmatch(r"-?[\d.]+", t): vals.append(num(t))
                elif t in ("", "-", "None"): vals.append(None)
            cur["values"] += vals
    return songs

if __name__ == "__main__":
    title, src = sys.argv[1], Path(sys.argv[2])
    out = Path(sys.argv[3] if len(sys.argv) > 3 else "data") / "samples"
    text = src.read_text(encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", title)
    (out / f"{safe}.json").write_text(json.dumps({"title": title, "songs": parse(text), "raw": text}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {safe}.json  곡 {len(parse(text))}개")
