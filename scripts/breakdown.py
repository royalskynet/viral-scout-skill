#!/usr/bin/env python3
"""② 拆解：對標頻道各取最高播放 N 支 → 下載 → 鏡頭表＋聯絡表＋口播逐字稿＋前 3 秒鉤子。零 token。

  .venv/bin/python scripts/breakdown.py                 # 預設三個頭部頻道各 3 支
  .venv/bin/python scripts/breakdown.py --per 5
  .venv/bin/python scripts/breakdown.py --summary-only  # 不下載不轉錄，只重寫 refs/BREAKDOWN.md

每支片放 refs/<頻道代號>-<影片ID>/：ref.mp4、ref.info.json（gitignore）、shots/、transcript.json。
已經有的步驟跳過，中途斷掉重跑會接著做。

切點與秒數由 video-shots 量；景別、版面、畫風這類判斷看 shots/sheets/ 聯絡表，不在這支腳本裡做。
"""
import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "refs"
SHOTS = Path.home() / "dev/reelbench-skills/skills/video-shots/scripts/video-shots.mjs"
MODEL = "mlx-community/whisper-large-v3-turbo"   # 跟 narration_check.py 同一個
HOOK_SECONDS = 3.0
SCAN_N = 60   # 每頻道看最近幾支 Shorts 來挑最高播放（benchmarks 量的是 30，這裡放寬一點）
# 代號只用在資料夾名；頻道 ID 取自 refs/benchmarks.tsv
CHANNELS = {
    "sichu": ("四處觀察", "UC6OeJCR9gHsJPVyNhXfK4tA"),
    "cheap": ("cheap", "UCGGrblndNzi86WY5lJkQJiA"),
    "sifang": ("四方異聞", "UCYA6MeGKKNF9rZVSr3T1_bQ"),
}


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} 失敗：\n{r.stderr[-1500:]}")
    return r.stdout


def top_videos(cid, n):
    d = json.loads(run(["yt-dlp", f"https://www.youtube.com/channel/{cid}/shorts", "--flat-playlist",
                        "--no-warnings", "-I", f"1:{SCAN_N}", "-J"], timeout=300))
    es = [e for e in d.get("entries") or [] if e and e.get("view_count")]
    return sorted(es, key=lambda e: e["view_count"], reverse=True)[:n]


def hook(words, seconds=HOOK_SECONDS):
    """前 N 秒內開口的字。鉤子看的是開頭說了什麼，跨過邊界的那個字也算。"""
    return "".join(w["w"] for w in words if w["t0"] < seconds).strip()


def shot_stats(shots):
    secs = [s["seconds"] for s in shots]
    return {"n": len(secs), "avg": statistics.mean(secs), "median": statistics.median(secs),
            "first": secs[0] if secs else 0}


def process(d, url):
    d.mkdir(parents=True, exist_ok=True)
    mp4 = d / "ref.mp4"
    if not mp4.exists():
        dl = ["yt-dlp", url, "--no-warnings", "--merge-output-format", "mp4",
              "-o", str(mp4), "--write-info-json", "--no-write-playlist-metafiles", "-f"]
        try:
            run(dl + ["bv*[height<=1920]+ba/b"], timeout=600)
        except RuntimeError as e:
            # 10-14 實測：個別影片的 https 直連格式一直 403，m3u8 格式下得到
            if "403" not in str(e):
                raise
            run(dl + ["bv*[protocol^=m3u8][height<=1920]+ba/b"], timeout=600)
        info = mp4.with_suffix(".info.json")
        if info.exists():
            info.rename(d / "ref.info.json")
    sh = d / "shots"
    if not (sh / "shots.md").exists():
        sh.mkdir(exist_ok=True)
        js = run(["node", str(SHOTS), "seed", str(mp4), "--track", str(sh / "track.json")], timeout=600)
        (sh / "shots.json").write_text(js, encoding="utf-8")
        md = run(["node", str(SHOTS), "render", str(sh / "shots.json"), "--md", "--track", str(sh / "track.json")])
        (sh / "shots.md").write_text(md, encoding="utf-8")
    if not (sh / "sheets").exists():
        run(["node", str(SHOTS), "frames", str(sh / "shots.json"), "--video", str(mp4),
             "--dir", str(sh / "frames"), "--single"], timeout=600)
        run(["node", str(SHOTS), "sheet", str(sh / "shots.json"), "--dir", str(sh / "frames"),
             "--out", str(sh / "sheets"), "--pick", "a"], timeout=600)
    tr = d / "transcript.json"
    if not tr.exists():
        import mlx_whisper
        # 參數照 narration_check.py：temperature 0 可重現、靜音段不幻聽
        r = mlx_whisper.transcribe(str(mp4), path_or_hf_repo=MODEL, language="zh", word_timestamps=True,
                                   temperature=0.0, condition_on_previous_text=False,
                                   hallucination_silence_threshold=2.0)
        words = [{"w": w["word"], "t0": round(w["start"], 2), "t1": round(w["end"], 2)}
                 for s in r["segments"] for w in s.get("words", [])]
        segs = [{"t0": round(s["start"], 2), "t1": round(s["end"], 2), "text": s["text"].strip()}
                for s in r["segments"]]
        tr.write_text(json.dumps({"model": MODEL, "text": r["text"], "segments": segs, "words": words},
                                 ensure_ascii=False, indent=1), encoding="utf-8")


def summary():
    md = ["# 對標拆解（② 拆解）", "",
          "`scripts/breakdown.py` 產生。每支：鏡頭數／平均鏡頭長／前 3 秒口播／逐字稿。",
          "畫面判斷看各資料夾 `shots/sheets/`（gitignore，本機才有）。", ""]
    for key, (name, _) in CHANNELS.items():
        md += [f"## {name}", ""]
        for d in sorted(REFS.glob(f"{key}-*")):
            info = json.loads((d / "ref.info.json").read_text()) if (d / "ref.info.json").exists() else {}
            shots = json.loads((d / "shots" / "shots.json").read_text())["shots"]
            tr = json.loads((d / "transcript.json").read_text())
            st = shot_stats(shots)
            words_per_s = len("".join(w["w"] for w in tr["words"]).replace(" ", "")) / max(info.get("duration") or 1, 1)
            md += [f"### {info.get('title', d.name)}", "",
                   f"- {info.get('view_count', 0) / 10_000:.1f} 萬播放，{info.get('duration')} 秒，"
                   f"{info.get('webpage_url', '')}",
                   f"- 鏡頭 {st['n']} 個，平均 {st['avg']:.1f} 秒，中位數 {st['median']:.1f} 秒，第一鏡 {st['first']:.1f} 秒",
                   f"- 口播語速 {words_per_s:.1f} 字／秒",
                   f"- 前 {HOOK_SECONDS:.0f} 秒：「{hook(tr['words'])}」",
                   "", "<details><summary>逐字稿</summary>", ""]
            md += [f"`{s['t0']:>5.1f}` {s['text']}" + "  " for s in tr["segments"]]
            md += ["", "</details>", ""]
    (REFS / "BREAKDOWN.md").write_text("\n".join(md), encoding="utf-8")
    print(f"寫入 {REFS / 'BREAKDOWN.md'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=3)
    ap.add_argument("--summary-only", action="store_true")
    a = ap.parse_args()
    if not a.summary_only:
        fails = []
        for key, (name, cid) in CHANNELS.items():
            for e in top_videos(cid, a.per):
                d = REFS / f"{key}-{e['id']}"
                print(f"{name} {e['id']} {e['view_count']:,}：{(e.get('title') or '')[:30]}", file=sys.stderr)
                try:
                    process(d, f"https://www.youtube.com/shorts/{e['id']}")
                except RuntimeError as err:   # 一支壞不擋其他支，最後一起報
                    fails.append(f"{d.name}: {err}")
        if fails:
            print("失敗：\n" + "\n".join(fails), file=sys.stderr)
            return 1
    summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
