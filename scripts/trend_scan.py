#!/usr/bin/env python3
"""① 追趨勢：每天抓一次熱度，列候選題，附同題爆款連結。

零 token：只有 HTTP 抓公開介面＋關鍵字打分，沒有任何模型呼叫。

用法：
  scripts/trend_scan.py                 抓熱度並寫當天報告
  scripts/trend_scan.py --refs          另外用 yt-dlp 找同題爆款（慢，約 +30 秒）
  scripts/trend_scan.py --selftest      只跑打分器的自檢，不連網
  scripts/trend_scan.py --hot           熱點快線：HN 24h 內 AI 新品發布，只印沒推過的（scripts/hot-watch.sh 每 2h）

報告寫到 ~/.vibe-trends/<日期>.md。

為什麼不抓 Google Trends 當主力：台灣每日搜尋趨勢幾乎都是新聞、賽事、藝人，
跟「數學悖論／冷門定理／哲學概念」這種題型對不上。主力訊號改成知識類
subreddit 與 HN 首頁，用題型關鍵字過濾後再按互動量排序。
"""
import argparse
import json
import math
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

# Reddit 要求 UA 寫成「平台:程式:版本 (by /u/帳號)」並且會擋假冒瀏覽器的。
# 2026-10-11 實測：前面掛 Mozilla/5.0 一律 429，改成下面這樣就 200。
# 退避重試救不了這種擋法，重試三次還是 429。
UA = "macos:vibe-shorts-pipeline:1.0 (by /u/royalskynet)"
OUT_DIR = Path.home() / ".vibe-trends"
TOP_N = 5

# 題型桶：命中桶才算候選，桶名直接寫進報告，省掉「為什麼選這題」的人工判斷。
#
# `viral` 欄是這個題型的爆款實證結果，值只有四種，一律引 refs/VIRAL-LEDGER.md
# 的逐題判定，不准估（判準見 skills/viral-scout/SKILL.md 第 2 節：
# ≥100 萬播放或離群 ≥×5 算有爆款，10–100 萬算弱）：
#   viral    → 已有同題爆款，才進主榜
#   weak     → 查過，頭部只有 10–100 萬，進待驗區
#   unproven → 還沒查過，進待驗區
#   failed   → 實際做過一支，成效被否決，連待驗區都不列
#
# 2026-10-15 改這個結構的原因：舊版只按 log(互動量)×命中桶數排序，完全沒把
# 「有沒有同題爆款」當門檻，所以每天 21 條候選幾乎全部「同題爆款：沒找到」，
# 而且選出的費馬片（冷門定理桶）發出去被判定「結構對人沒意義」、三平台刪除。
BUCKETS = {
    # ── viral：refs/VIRAL-LEDGER.md 2026-10-14 查過有爆款 ──
    "地理尺度": {
        "kw": ["border", "time zone", "antipode", "map projection", "mercator",
               "enclave", "exclave", "國界", "時區", "飛地", "投影"],
        "viral": "viral", "why": "時區 3182 萬／奇怪國界 4690 萬／對蹠點 1.72 億",
    },
    "台灣反直覺": {
        "kw": ["taiwan", "formosa", "台灣"],
        "viral": "viral", "why": "台灣與菲律賓地理淵源 457 萬／台灣地理冷知識 327 萬",
    },
    "人口與財富分布": {
        # 2026-10-15 實跑誤判：單獨的 "wealth" 把「抹大拉的馬利亞的財富從哪來」
        # 拉進主榜，那題做不出地圖包裝。這個桶的爆款全靠地圖，所以關鍵字
        # 一律要帶分布或地點。
        "kw": ["population density", "wealth distribution", "wealth gap",
               "richest countr", "richest cit", "where people live",
               "人口密度", "貧富差距", "財富分布"],
        "viral": "viral", "why": "台灣富人集中 350 萬／50% 人口住這圈 517 萬（需地圖包裝）",
    },
    "極端天氣與地震": {
        "kw": ["typhoon", "earthquake", "hurricane", "颱風", "地震"],
        "viral": "viral", "why": "台灣史上最大颱風／世紀大地震 各 160 萬",
    },
    "AI 協作痛點": {
        # 2026-10-15 實跑誤判：單獨的 "prompt" 命中「prompting 205 students
        # to come forward」這種當普通動詞用的 prompt，把作弊醜聞拉進主榜。
        "kw": ["claude", "chatgpt", "codex", "copilot", "cursor", "llm agent",
               "vibe coding", "hallucinat", "context window",
               "system prompt", "prompt engineering",
               "renamed my", "deleted my"],
        # 2026-10-15 實跑：光靠 AI 詞會把「收到 claude code 貼紙了」「來分享你
        # 用 Claude 做的東西」這類非敘事貼文全撈進來。爆款的梗一律是「它弄壞了
        # 我的什麼」，所以這個桶要同時命中一個痛點詞才算。
        "kw2": ["lost", "broke", "broken", "deleted", "renamed", "wrong",
                "forgot", "forget", "again", "stop", "stopped", "fail",
                "ruined", "wasted", "hate", "gave up", "nightmare", "regret",
                "worst", "useless", "lied", "pretend"],
        "viral": "viral",
        "why": "IG low-poly 角色＋Clawd 吉祥物對話 5.43 萬／5.69 萬讚（純娛樂號同量級）；"
               "梗要取自開發者痛點敘事，不是新模型名稱",
    },
    # ── weak：查過但中文頭部上不去 ──
    "約會與婚戀": {
        "kw": ["dating", "marriage", "divorce", "約會", "結婚", "離婚"],
        "viral": "weak", "why": "中文 ≤17.6 萬（英文 236 萬）",
    },
    "海洋尺度": {
        "kw": ["ocean", "trench", "antarctic", "abyss", "海溝", "南極"],
        "viral": "weak", "why": "Threads 地理題頭部僅 10–17 萬",
    },
    # ── unproven：原有的題型桶，都還沒跑過 viral-scout ──
    "數學悖論": {
        "kw": ["paradox", "banach-tarski", "zeno", "russell's", "悖論"],
        "viral": "unproven", "why": "",
    },
    "機率反直覺": {
        "kw": ["probability", "bayes", "monty hall", "birthday problem",
               "counterintuitive", "random walk", "機率"],
        "viral": "unproven", "why": "",
    },
    "哲學概念": {
        "kw": ["philosophy", "philosophical", "consciousness", "free will",
               "ethics", "ontolog", "epistem", "哲學"],
        "viral": "unproven", "why": "",
    },
    "歷史考古": {
        "kw": ["archaeolog", "ancient", "excavat", "artifact", "ruins",
               "tomb", "考古"],
        "viral": "unproven", "why": "",
    },
    "演算法直覺": {
        "kw": ["algorithm", "optimum", "optimal", "entropy", "complexity",
               "np-hard", "gradient", "local minim", "演算法"],
        "viral": "unproven", "why": "",
    },
    "物理反直覺": {
        "kw": ["quantum", "relativity", "thermodynamic", "entangle",
               "black hole", "物理"],
        "viral": "unproven", "why": "",
    },
    # ── failed：做過一支，被否決 ──
    # 刻意不收單獨的 "proof"：實測會把 "zero-knowledge proofs"、
    # "proof that autonomous cars save lives" 這種非數學題拉進來
    "冷門定理": {
        "kw": ["theorem", "conjecture", "lemma", "godel", "gödel",
               "incompleteness", "infinity", "mathematical proof", "定理"],
        "viral": "failed",
        "why": "費馬片 flt-11days 使用者判定「結構對人沒意義」，三平台全刪（2026-10-14）",
    },
}

# 只有這一級進主榜。
VIRAL_OK = "viral"
# 這一級連待驗區都不列。
VIRAL_DROP = "failed"

SUBREDDITS = ["todayilearned", "math", "philosophy", "askscience",
              "Physics", "AskHistorians", "explainlikeimfive",
              # AI 協作痛點桶的料源：爆款的梗是「它重命名了我的資料庫」
              # 這種協作日常，抱怨貼文比產品發布有用
              "ClaudeAI", "ChatGPT"]

# HN 用關鍵字搜尋而不是只看首頁：首頁幾乎全是產業新聞，
# 2026-10-11 實測首頁 29 條沒有一條命中題型桶。
HN_QUERIES = ["paradox", "theorem", "counterintuitive", "probability puzzle",
              "infinity", "mathematical proof", "philosophy", "archaeology",
              "entropy", "local optimum", "quantum", "illusion",
              # AI 協作痛點桶
              "vibe coding", "coding agent", "AI hallucination"]
HN_WINDOW_DAYS = 45
REDDIT_GAP = 61


def fetch(url: str, timeout: int = 20, tries: int = 3) -> str:
    """抓一個網址，被節流就退避重試。

    2026-10-11 首跑六個 subreddit 全部回 429：原本連續打六次沒有間隔。
    Reddit 回 429 時會附 Retry-After，有就照它說的等，沒有就用 2 的次方退避。
    retry-after 超過 70 秒就不等了——報告是每天跑的，等不到就當今天沒這個來源。
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json,*/*"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == tries - 1:
                raise
            # Reddit 不給 Retry-After，但給 x-ratelimit-reset（秒）；2026-10-13 實測窗口 60 秒
            reset = e.headers.get("Retry-After") or e.headers.get("x-ratelimit-reset") or 0
            wait = (float(reset) + 1 if float(reset) else 0) or 2 ** (attempt + 1)
            if wait > 70:
                raise
            print(f"[warn] {e.code}，等 {wait:.0f} 秒後重試", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def buckets_of(text: str) -> list[str]:
    """命中桶名。有 `kw2` 的桶是 AND：兩組都要中一個才算。"""
    low = text.lower()
    hit = []
    for name, b in BUCKETS.items():
        if not any(k in low for k in b["kw"]):
            continue
        if "kw2" in b and not any(k in low for k in b["kw2"]):
            continue
        hit.append(name)
    return hit


def has_viral(hit_buckets: list[str]) -> bool:
    """命中的桶裡有沒有一個已經驗出爆款。這是進主榜的硬門檻。"""
    return any(BUCKETS[n]["viral"] == VIRAL_OK for n in hit_buckets)


def is_dropped(hit_buckets: list[str]) -> bool:
    """命中的桶全是做過被否決的題型，就整條丟掉。"""
    return bool(hit_buckets) and all(
        BUCKETS[n]["viral"] == VIRAL_DROP for n in hit_buckets)


def score_of(engagement: int, hit_buckets: list[str]) -> float:
    """互動量取 log（避免單一爆文壓死其他候選），題型命中是乘數。

    沒命中任何桶就是 0 分：寧可少列候選，也不要列出跟格式對不上的題。
    這個分數只決定同一榜內的排序，進不進主榜看 has_viral()。
    """
    if not hit_buckets:
        return 0.0
    return math.log1p(max(engagement, 0)) * (1 + 0.5 * (len(hit_buckets) - 1))


def collect_reddit() -> list[dict]:
    """盡力而為：Reddit 的 .json 介面 2026-10 起對一般 UA 回 403，
    RSS 也會隨機被節流。抓不到就當這個來源今天沒資料，不讓它擋住整份報告。"""
    items = []
    for i, sub in enumerate(SUBREDDITS):
        if i:
            # Reddit 未登入 RSS 配額 2026-10-13 實測降到每 60 秒 1 次
            # （x-ratelimit-remaining 0.0、reset 59；隔 8 秒連打四版只過第一版）。
            # 原本隔 6 秒，六版只過一版。背景每天跑一次，多等 5 分鐘不影響。
            time.sleep(REDDIT_GAP)
        url = f"https://www.reddit.com/r/{sub}/top/.rss?t=day"
        try:
            xml = fetch(url, timeout=12)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"[warn] r/{sub} 抓不到：{e}", file=sys.stderr)
            continue
        for m in re.finditer(r"<entry>(.*?)</entry>", xml, re.S):
            block = m.group(1)
            t = re.search(r"<title>(.*?)</title>", block, re.S)
            link = re.search(r'<link href="(.*?)"', block)
            if not t:
                continue
            items.append({
                "title": re.sub(r"\s+", " ", t.group(1)).strip(),
                "source": f"r/{sub}",
                # RSS 不給票數，用一個保守的基準分，排序主要靠題型命中數
                "engagement": 500,
                "comments": 0,
                "url": link.group(1) if link else f"https://reddit.com/r/{sub}",
            })
    return items


def collect_hn() -> list[dict]:
    """用題型關鍵字搜 HN，限定最近 HN_WINDOW_DAYS 天，按分數排。"""
    import time

    since = int(time.time()) - HN_WINDOW_DAYS * 86400
    out = []
    for q in HN_QUERIES:
        url = ("https://hn.algolia.com/api/v1/search?"
               + urllib.parse.urlencode({
                   "query": q, "tags": "story", "hitsPerPage": 10,
                   "numericFilters": f"created_at_i>{since},points>30"}))
        try:
            data = json.loads(fetch(url))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            print(f"[warn] HN「{q}」抓不到：{e}", file=sys.stderr)
            continue
        for h in data.get("hits", []):
            title = (h.get("title") or "").strip()
            if not title:
                continue
            out.append({
                "title": title,
                "source": "HN",
                "engagement": int(h.get("points") or 0),
                "comments": int(h.get("num_comments") or 0),
                "url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            })
    return out


# 熱點快線（2026-10-20）：Kin 48 天萬粉復盤，爆款多是 AI 新品發布當天就出的中文片／貼文。
# 題型桶看 45 天窗，趕不上當天；這裡另看 24 小時、只收「AI 主體＋發布動作」。
HOT_ENTITY = ["openai", "anthropic", "claude", "chatgpt", "gpt-", "gemini", "grok",
              "deepseek", "qwen", "llama", "mistral", "sora", "codex", "copilot", "cursor"]
HOT_ACTION = ["introducing", "launch", "release", "announc", "now available", "unveil",
              "open-source", "open source", "open-weight"]
# 2026-10-20 實測 HN 7 天 AI 標題：發布貼多半是裸型號加版號（「Gemini 4 Argon」
# 「DeepSeek V4.1 Flash 1017」），沒有發布動詞，所以型號＋數字也算。
HOT_VERSION = re.compile(r"\b(gpt|claude|gemini|grok|deepseek|qwen|llama|mistral|sora|codex)[\s-]*v?\d")
HOT_MODEL = re.compile(r"\b(foundation|frontier|open|reasoning|new)[\s-]+models?\b")
HOT_MIN_POINTS = 150
HOT_SEEN = Path.home() / ".vibe-trends" / "hot-seen.json"


def is_hot(title: str) -> bool:
    low = title.lower()
    if not any(k in low for k in HOT_ENTITY):
        return False
    return (any(k in low for k in HOT_ACTION) or bool(HOT_VERSION.search(low))
            or bool(HOT_MODEL.search(low)))


def collect_hot() -> list[dict]:
    """HN 24 小時內 ≥HOT_MIN_POINTS 分、AI 主體＋發布動作的 story，分數高的在前。"""
    since = int(time.time()) - 86400
    url = ("https://hn.algolia.com/api/v1/search?"
           + urllib.parse.urlencode({
               "tags": "story", "hitsPerPage": 100,
               "numericFilters": f"created_at_i>{since},points>{HOT_MIN_POINTS}"}))
    data = json.loads(fetch(url))
    out = [{"id": h["objectID"], "title": h["title"].strip(), "points": int(h.get("points") or 0),
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"}
           for h in data.get("hits", []) if h.get("title") and is_hot(h["title"])]
    return sorted(out, key=lambda x: -x["points"])


def hot_main() -> int:
    """印出沒推過的熱點（每行一條），推過的記進 HOT_SEEN。沒新的就不印。"""
    seen = set(json.loads(HOT_SEEN.read_text())) if HOT_SEEN.is_file() else set()
    new = [h for h in collect_hot() if h["id"] not in seen]
    for h in new:
        print(f"{h['points']}分 {h['title']} {h['url']}")
    HOT_SEEN.parent.mkdir(exist_ok=True)
    HOT_SEEN.write_text(json.dumps(sorted(seen | {h["id"] for h in new})))
    return 0


def collect_wikipedia() -> list[dict]:
    """英文維基前一天瀏覽量前 1000 條，命中題型桶的留下來。

    這是最穩的一軸：免金鑰、不節流，而且「大家昨天在查什麼冷知識」
    本身就是選題訊號。用前一天的資料，當天的統計還沒結算。
    """
    from datetime import timedelta

    d = date.today() - timedelta(days=2)
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
           f"en.wikipedia/all-access/{d.year}/{d.month:02d}/{d.day:02d}")
    try:
        data = json.loads(fetch(url, timeout=25))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"[warn] Wikipedia 抓不到：{e}", file=sys.stderr)
        return []
    out = []
    for a in data.get("items", [{}])[0].get("articles", []):
        art = a.get("article", "")
        if art.startswith(("Special:", "Wikipedia:", "Main_Page", "Portal:")):
            continue
        out.append({
            "title": art.replace("_", " "),
            "source": f"Wikipedia {d.isoformat()}",
            "engagement": int(a.get("views") or 0) // 100,  # 壓到跟 HN 分數同量級
            "comments": 0,
            "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(art)}",
        })
    return out


def collect_google_tw() -> list[dict]:
    """台灣每日搜尋趨勢，當側訊號用：命中題型桶才會留下來，通常一條都不留。"""
    try:
        xml = fetch("https://trends.google.com/trending/rss?geo=TW")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[warn] Google Trends 抓不到：{e}", file=sys.stderr)
        return []
    out = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        block = m.group(1)
        t = re.search(r"<title>(.*?)</title>", block, re.S)
        traffic = re.search(r"approx_traffic>\+?([\d,]+)", block)
        if not t:
            continue
        n = int(traffic.group(1).replace(",", "")) if traffic else 0
        out.append({
            "title": t.group(1).strip(),
            "source": "Google Trends TW",
            "engagement": n,
            "comments": 0,
            "url": "https://trends.google.com/trending?geo=TW",
        })
    return out


def youtube_refs(query: str, n: int = 3) -> list[str]:
    """同題爆款：yt-dlp 搜尋後按觀看數排序，只取前幾條。"""
    # 分隔符不能用 \t：yt-dlp 的 --print 不解讀轉義，會原樣印出兩個字元
    sep = " ||| "
    cmd = ["yt-dlp", f"ytsearch{n * 3}:{query}", "--flat-playlist",
           "--no-warnings", "--print",
           f"%(view_count)s{sep}%(title)s{sep}%(webpage_url)s"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split(sep)
        if len(parts) != 3:
            continue
        views = int(parts[0]) if parts[0].isdigit() else 0
        rows.append((views, parts[1], parts[2]))
    rows.sort(reverse=True)
    return [f"{v:,} 次觀看 · [{t}]({u})" for v, t, u in rows[:n]]


def dedup(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        key = re.sub(r"\W+", "", it["title"].lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def viral_note(hit_buckets: list[str]) -> str:
    """把命中桶的爆款實證理由攤出來，報告讀起來才知道憑什麼選它。"""
    return "；".join(BUCKETS[n]["why"] for n in hit_buckets if BUCKETS[n]["why"])


def render(main: list[dict], pending: list[dict], with_refs: bool) -> str:
    today = date.today().isoformat()
    lines = [f"# 候選題 {today}", "",
             "來源：HN 題型關鍵字搜尋 ＋ 英文維基前日瀏覽榜 ＋ "
             f"{len(SUBREDDITS)} 個 subreddit（常被節流）＋ Google Trends TW。",
             "主榜門檻：命中的題型桶必須已經驗出同題爆款（`refs/VIRAL-LEDGER.md`）。"
             "沒驗過的進待驗區，做過被否決的不列。榜內排序＝log(互動量) × 題型命中數。", ""]
    if not main:
        lines += ["今天沒有已驗爆款題型的候選。可能是來源抓不到，"
                  "或今天的熱點真的都落在沒驗過的題型上（看下面待驗區）。", ""]
    for i, it in enumerate(main[:TOP_N], 1):
        lines += [
            f"## {i}. {it['title']}",
            "",
            f"- 題型：{'、'.join(it['buckets'])}",
            f"- 熱度：{it['source']} {it['engagement']:,} 讚／分、{it['comments']:,} 留言（分數 {it['score']:.1f}）",
            f"- 題型爆款證據：{viral_note(it['buckets'])}",
            f"- 原文：{it['url']}",
        ]
        if with_refs:
            refs = it.get("refs") or []
            lines.append("- 同題現抓：" + ("" if refs else "沒找到（題型證據仍成立）"))
            lines += [f"  - {r}" for r in refs]
        lines.append("")
    rest = main[TOP_N:]
    if rest:
        lines += ["---", "", "## 其餘已驗題型的候選", ""]
        lines += [f"- [{it['title']}]({it['url']}) · {it['source']} · {'、'.join(it['buckets'])}"
                  for it in rest[:20]]
        lines.append("")
    if pending:
        lines += ["---", "",
                  "## 待驗區（題型還沒跑過 viral-scout，要做先查爆款）", ""]
        lines += [f"- [{it['title']}]({it['url']}) · {it['source']} · {'、'.join(it['buckets'])}"
                  for it in pending[:20]]
        lines.append("")
    lines += ["---", "",
              "下一步：挑一題交給 `video-shots` 拆同題爆款，再用 `lemo-opuscar` 出片（見 PLAN.md）。", ""]
    return "\n".join(lines)


def selftest() -> int:
    """打分器要能把知識題排在運動／藝人新聞前面，而且後者要是 0 分。"""
    know = {"t": "This theorem shows an infinity paradox", "e": 800}
    sport = {"t": "Lakers win game 7 in overtime", "e": 50000}
    bk, bs = buckets_of(know["t"]), buckets_of(sport["t"])
    assert bk, "知識題應該命中題型桶"
    assert bs == [], f"運動新聞不該命中任何桶，卻命中 {bs}"
    sk, ss = score_of(know["e"], bk), score_of(sport["e"], bs)
    assert ss == 0.0, "沒命中桶就該是 0 分"
    assert sk > ss, "高互動量的無關新聞不該壓過低互動量的對路題"
    # 命中兩個桶要贏過命中一個桶的同互動量題目
    assert score_of(800, ["數學悖論", "冷門定理"]) > score_of(800, ["數學悖論"])
    # 熱點快線：AI 主體＋發布動作兩個都要中
    assert is_hot("Introducing GPT-6"), "新品發布應該算熱點"
    assert is_hot("Anthropic releases Claude 5"), "新品發布應該算熱點"
    assert not is_hot("Why I stopped using Claude"), "沒有發布動作不算熱點"
    assert not is_hot("Introducing a new Rust web framework"), "非 AI 主體不算熱點"
    # 2026-10-20 HN 真實標題
    for t in ["Gemini 4 Argon", "DeepSeek V4.1 Flash 1017 (Max)",
              "Timestral: Mistral's time-series foundation models"]:
        assert is_hot(t), f"裸型號發布應該算熱點：{t}"
    for t in ["OpenAI engineer arrested in bugging of executive conference room",
              "Anthropic assigned highest junk credit rating in June",
              "Llama.cpp on a jailbroken PS5: run any GGUF model natively on the console",
              "How the Claude Code team does code review"]:
        assert not is_hot(t), f"新聞／教學不算發布：{t}"
    # 去重要認出同一條（標點與大小寫不同）
    assert len(dedup([{"title": "A Theorem!"}, {"title": "a theorem"}])) == 1

    # 爆款硬門檻：每個桶的 viral 值只能是這四種，否則 has_viral／is_dropped 會默默放行
    assert all(b["viral"] in ("viral", "weak", "unproven", "failed")
               for b in BUCKETS.values()), "BUCKETS 有不認識的 viral 值"
    # 已驗爆款的桶必須寫得出憑什麼
    assert all(b["why"] for b in BUCKETS.values() if b["viral"] == "viral"), \
        "viral 桶一定要填 why（引 VIRAL-LEDGER）"

    # 費馬片那條路要被擋死：冷門定理是 failed，整條不列
    flt = buckets_of("Formalizing Fermat's Last Theorem")
    assert "冷門定理" in flt, f"費馬題應該命中冷門定理桶，實際 {flt}"
    assert is_dropped(flt), "failed 桶的題不該出現在任何榜上"
    assert not has_viral(flt), "failed 桶不該算有爆款"

    # 沒驗過的題型只能進待驗區，不能進主榜
    qm = buckets_of("Universal Pattern Revealed in Quantum Matter")
    assert qm and not has_viral(qm), f"物理反直覺還沒驗爆款，不該進主榜（{qm}）"
    assert not is_dropped(qm), "unproven 不等於 failed，待驗區要留著"

    # 2026-10-15 實跑抓到的兩個誤判，關鍵字放寬回去就會重現
    cheat = ("TIL that in 2010, UCF professor Richard Quinn uncovered a cheating "
             "scandal, prompting 205 students to come forward")
    assert "AI 協作痛點" not in buckets_of(cheat), \
        "prompt 當普通動詞用，不該算 AI 協作痛點"
    mary = ("How would women of 1st century Judea attain this wealth to "
            "financially support Jesus")
    assert "人口與財富分布" not in buckets_of(mary), \
        "單獨的 wealth 不該算人口與財富分布（這個桶要靠地圖）"

    # 已驗爆款的兩類題要進主榜
    ai = buckets_of("Claude renamed my database and I lost a day")
    assert "AI 協作痛點" in ai and has_viral(ai), f"AI 痛點題應進主榜，實際 {ai}"
    # kw2 的 AND：有 AI 詞但沒有痛點敘事的不算
    assert "AI 協作痛點" not in buckets_of("got my claude code stickers in the mail"), \
        "沒有痛點敘事的 Claude 貼文不該算 AI 協作痛點"
    geo = buckets_of("Why do time zones look so strange")
    assert "地理尺度" in geo and has_viral(geo), f"地理尺度題應進主榜，實際 {geo}"

    print("✅ selftest 全過（題型過濾、0 分、多桶加權、去重、爆款門檻、failed 丟棄）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", action="store_true", help="用 yt-dlp 找同題爆款（慢）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--hot", action="store_true", help="熱點快線：只看 24h AI 發布")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.hot:
        return hot_main()

    items = dedup(collect_hn() + collect_wikipedia() + collect_reddit()
                  + collect_google_tw())
    main_list, pending = [], []
    for it in items:
        bks = buckets_of(it["title"])
        s = score_of(it["engagement"], bks)
        if s <= 0 or is_dropped(bks):
            continue
        row = {**it, "buckets": bks, "score": s}
        (main_list if has_viral(bks) else pending).append(row)
    for lst in (main_list, pending):
        lst.sort(key=lambda x: -x["score"])

    if args.refs:
        for it in main_list[:TOP_N]:
            it["refs"] = youtube_refs(it["title"][:80])

    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"{date.today().isoformat()}.md"
    path.write_text(render(main_list, pending, args.refs), encoding="utf-8")
    print(f"{path}  主榜 {len(main_list)} 條／待驗 {len(pending)} 條／掃過 {len(items)} 條")
    return 0


if __name__ == "__main__":
    sys.exit(main())
