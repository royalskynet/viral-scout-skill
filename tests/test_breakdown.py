#!/usr/bin/env python3
"""breakdown.py 鉤子與鏡頭統計的最小自檢。判準改錯這支要 fail。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import breakdown as b  # noqa: E402

fails = []
w = [{"w": "你", "t0": 0.1}, {"w": "知道", "t0": 0.5}, {"w": "嗎", "t0": 2.9}, {"w": "後面", "t0": 3.0}]
if b.hook(w) != "你知道嗎":
    fails.append(f"鉤子應只含 3 秒前開口的字，得 {b.hook(w)!r}")
s = b.shot_stats([{"seconds": 1.0}, {"seconds": 2.0}, {"seconds": 6.0}])
if (s["n"], s["avg"], s["median"], s["first"]) != (3, 3.0, 2.0, 1.0):
    fails.append(f"鏡頭統計錯：{s}")

if fails:
    print("FAIL\n  " + "\n  ".join(fails))
    sys.exit(1)
print("OK breakdown 自檢 2/2")
