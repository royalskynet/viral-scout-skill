#!/usr/bin/env python3
"""爆款文本累積：每天從中文雷達的「竄升 Shorts」取前 N 支 → 只抓音軌 → 本機 whisper 轉逐字稿。零 token。

  .venv/bin/python scripts/viral_text.py              讀今天的 ~/.vibe-trends/zh-<日期>.md，取前 PER_DAY 支
  .venv/bin/python scripts/viral_text.py --selftest   只跑解析自檢，不連網

輸出 refs/viral-text/<影片ID>.json（逐字稿，別人的內容，gitignore）＋ refs/viral-text/index.tsv
（日期、每小時播放、播放、頻道、標題、前 3 秒、字數），選題與寫稿時 grep index.tsv 找同型爆款。

為什麼（2026-10-20）：使用者要「多看爆款累積文本量」。breakdown.py 一次只拆三個頭部頻道；
竄升榜每天換，一天累 10 支，一個月就有 300 支近期爆款的口播稿可比對開頭與節奏。
用途限學習結構（鉤子、節拍、收尾）；成片台詞照「台詞非照抄」門重寫。
轉錄參數照 breakdown.py／narration_check.py。
"""
import json
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "refs" / "viral-text"
INDEX = OUT / "index.tsv"
ZH = Path.home() / ".vibe-trends"
MODEL = "mlx-community/whisper-large-v3-turbo"
PER_DAY = 10
HOOK_SECONDS = 3.0
LINE = re.compile(r"^- ([\d,]+)/h · ([\d,]+) · ★?(.+?)（[^）]*訂閱） · \[(.+)\]\((https://www\.youtube\.com/shorts/([\w-]+))\)$")


def parse_rising(md):
    """回 [(每小時播放, 播放, 頻道, 標題, 網址, 影片ID)]，照報告順序。"""
    out, on = [], False
    for ln in md.splitlines():
        if ln.startswith("## "):
            on = ln.startswith("## YouTube 竄升")
            continue
        m = on and LINE.match(ln)
        if m:
            out.append((int(m[1].replace(",", "")), int(m[2].replace(",", "")), m[3], m[4], m[5], m[6]))
    return out


def transcribe(url):
    import mlx_whisper
    with tempfile.TemporaryDirectory() as td:
        # 預設播放器端有些片回 403；跳過 tv 端就通（yt-dlp 2026.08.19，10-20 實測）
        r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "-f", "ba", "--extractor-args",
                            "youtube:player_client=default,-tv", "-o", f"{td}/a.%(ext)s", url],
                           capture_output=True, text=True, timeout=300)
        files = list(Path(td).glob("a.*"))
        if r.returncode != 0 or not files:
            raise RuntimeError(f"yt-dlp 失敗：{r.stderr.strip()[-300:]}")
        res = mlx_whisper.transcribe(str(files[0]), path_or_hf_repo=MODEL, language="zh", word_timestamps=True,
                                     temperature=0.0, condition_on_previous_text=False,
                                     hallucination_silence_threshold=2.0)
    words = [{"w": w["word"], "t0": round(w["start"], 2), "t1": round(w["end"], 2)}
             for s in res["segments"] for w in s.get("words", [])]
    return res["text"].strip(), words


def hook(words):
    return "".join(w["w"] for w in words if w["t0"] < HOOK_SECONDS).strip()


def selftest():
    md = ("## YouTube 竄升 Shorts（近 48h）\n\n"
          "- 17,828/h · 174,441 · 萬物研究院（327,000 訂閱） · [為什麼老電工?#科普](https://www.youtube.com/shorts/0nC5L7Tl49E)\n"
          "- 9,236/h · 56,894 · ★哈囉tv（? 訂閱） · [標題 [有括號]](https://www.youtube.com/shorts/a_H7AMuKQLY)\n"
          "\n## PTT 今日熱門\n\n- 273／646 · Gossiping · [x](https://www.ptt.cc/a.html)\n")
    r = parse_rising(md)
    assert [x[5] for x in r] == ["0nC5L7Tl49E", "a_H7AMuKQLY"], r
    assert r[0][:3] == (17828, 174441, "萬物研究院") and r[1][2] == "哈囉tv" and r[1][3] == "標題 [有括號]", r
    assert hook([{"w": "你知", "t0": 0.1}, {"w": "道嗎", "t0": 2.9}, {"w": "後面", "t0": 3.0}]) == "你知道嗎"
    print("✅ viral_text selftest 全過")
    return 0


def main():
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    if sys.argv[1:]:  # 未知旗標不能落到真實下載（fix 10432 類型）
        print(__doc__, file=sys.stderr)
        return 0 if sys.argv[1] in ("-h", "--help") else 2
    rep = ZH / f"zh-{date.today().isoformat()}.md"
    if not rep.exists():
        sys.exit(f"沒有今天的雷達報告 {rep}，先跑 scripts/trend_zh.py")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [r for r in parse_rising(rep.read_text(encoding="utf-8")) if not (OUT / f"{r[5]}.json").exists()]
    ok = fail = 0
    for ph, v, ch, title, url, vid in rows[:PER_DAY]:
        try:
            text, words = transcribe(url)
        except Exception as e:  # 單支失敗（下架、地區限制）不擋其他支
            print(f"[warn] {vid}：{e}", file=sys.stderr)
            fail += 1
            continue
        (OUT / f"{vid}.json").write_text(json.dumps(
            {"id": vid, "url": url, "title": title, "channel": ch, "views": v, "per_hour": ph,
             "date": date.today().isoformat(), "model": MODEL, "text": text, "words": words},
            ensure_ascii=False, indent=1), encoding="utf-8")
        new = not INDEX.exists()
        with INDEX.open("a", encoding="utf-8") as f:
            if new:
                f.write("date\tper_hour\tviews\tchannel\ttitle\thook3s\tchars\tid\n")
            clean = lambda s: s.replace("\t", " ").replace("\n", " ")
            f.write(f"{date.today().isoformat()}\t{ph}\t{v}\t{clean(ch)}\t{clean(title)}\t{clean(hook(words))}\t{len(text)}\t{vid}\n")
        ok += 1
    total = len(list(OUT.glob("*.json")))
    print(f"爆款文本 +{ok}（失敗 {fail}），累計 {total} 支 → {INDEX}")
    return 0 if ok or not rows[:PER_DAY] else 1


if __name__ == "__main__":
    sys.exit(main())
