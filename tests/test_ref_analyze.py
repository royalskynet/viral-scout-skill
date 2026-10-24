#!/usr/bin/env python3
"""ref_analyze 切點自檢：三段純色硬切要抓到 2 刀，一段慢慢變亮的漸層要抓到 0 刀。"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from ref_analyze import find_cuts, frame_diffs  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    hard = os.path.join(d, "hard.mp4")
    ins = []
    for c in ("black", "gray", "white"):
        ins += ["-f", "lavfi", "-i", f"color={c}:s=64x36:d=1:r=30"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", "concat=n=3:v=1",
                    "-pix_fmt", "yuv420p", hard], check=True)
    cuts = find_cuts(frame_diffs(hard), 30)
    assert len(cuts) == 2, cuts
    assert abs(cuts[0] - 1) < 0.05 and abs(cuts[1] - 2) < 0.05, cuts

    fade = os.path.join(d, "fade.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=white:s=64x36:d=2:r=30",
                    "-vf", "fade=in:0:60", "-pix_fmt", "yuv420p", fade], check=True)
    assert find_cuts(frame_diffs(fade), 30) == [], find_cuts(frame_diffs(fade), 30)
print("ok")
