#!/usr/bin/env python3
"""拉片：時長、切點、每鏡停留秒數與中位數、抽幀拼圖（全尺寸＋手機 360px）。

用法：python3 scripts/ref_analyze.py <影片> --out <前綴> [--cells 20]
產出 <前綴>-sheet.jpg、<前綴>-sheet-360.jpg、<前綴>-info.json，並印摘要。

切點用 64x36 灰階相鄰幀差：平均絕對差 >12，且大於前後鄰幀差的 3 倍。
ffmpeg scene 偵測在對談片（慢推、同場景換機位）抓到 0 刀，所以不用。
拼圖部分改寫自 xilo-opus-video analyze_video.py（MIT，https://github.com/Kianzzz/xilo-opus-video）。
"""
import argparse
import json
import pathlib
import statistics
import subprocess

W, H = 64, 36
DIFF_MIN = 12     # 相鄰幀平均絕對差（0–255）
NEIGHBOR_X = 3    # 要大於前後鄰幀差的幾倍；慢推、淡入淡出的差值連續偏高，靠這條排除


def probe(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                        "-show_streams", video], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    num, den = map(int, v["r_frame_rate"].split("/"))
    return float(d["format"]["duration"]), num / den if den else 0, v["width"], v["height"]


def frame_diffs(video):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"scale={W}:{H},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    n = W * H
    frames = [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]
    return [sum(abs(a - b) for a, b in zip(f0, f1)) / n for f0, f1 in zip(frames, frames[1:])]


def find_cuts(diffs, fps):
    """diffs[i] 是第 i 幀到第 i+1 幀的差；切點時間取第 i+1 幀。"""
    cuts = []
    for i, d in enumerate(diffs):
        prev = diffs[i - 1] if i > 0 else 0
        nxt = diffs[i + 1] if i + 1 < len(diffs) else 0
        if d > DIFF_MIN and d > NEIGHBOR_X * max(prev, nxt):
            cuts.append(round((i + 1) / fps, 2))
    return cuts


def sheet(video, path, dur, cells, width):
    cols = 5 if cells > 12 else 4
    rows = -(-cells // cols)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf",
                    f"fps={cells}/{dur},scale={width}:-2,tile={cols}x{rows}",
                    "-frames:v", "1", "-q:v", "3", path], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", required=True, help="輸出前綴，例如 refs/ig-xxx/ref")
    ap.add_argument("--cells", type=int, default=20)
    ap.add_argument("--no-sheet", action="store_true")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    dur, fps, w, h = probe(a.video)
    cuts = find_cuts(frame_diffs(a.video), fps)
    bounds = [0.0] + cuts + [dur]
    lens = [round(b - x, 2) for x, b in zip(bounds, bounds[1:])]
    info = {"video": a.video, "duration": round(dur, 2), "size": f"{w}x{h}", "fps": round(fps, 2),
            "cuts": cuts, "shot_seconds": lens, "median_shot": round(statistics.median(lens), 2)}
    if not a.no_sheet:
        info["sheet"] = f"{out}-sheet.jpg"
        info["sheet_phone"] = f"{out}-sheet-360.jpg"
        sheet(a.video, info["sheet"], dur, a.cells, 1600 // (5 if a.cells > 12 else 4))
        sheet(a.video, info["sheet_phone"], dur, a.cells, 360)
    pathlib.Path(f"{out}-info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n")
    print(f"{a.video}：{dur:.2f}s {w}x{h} {fps:.2f}fps")
    print(f"切點 {len(cuts)} 刀：{', '.join(map(str, cuts)) or '無'}")
    print(f"每鏡中位數 {info['median_shot']}s")
    if not a.no_sheet:
        print(f"拼圖 {info['sheet']}、{info['sheet_phone']}")


if __name__ == "__main__":
    main()
