#!/usr/bin/env python3
"""中文熱榜雷達：台灣（PTT 爆文、YouTube 台灣發燒）＋中國（微博／抖音／知乎／B 站／頭條）。

  scripts/trend_zh.py            寫 ~/.vibe-trends/zh-<日期>.md，印一行摘要
  scripts/trend_zh.py --selftest 只跑 PTT 解析自檢，不連網

為什麼另開一支（2026-10-20）：trend_scan.py 只看 HN／Reddit／英文維基，量到的是英文工程師圈，
選出的題對中文觀眾沒感。這支只負責列熱度，選題由 session 判斷（對得上深夜對談格式再做）。
中國熱榜走 newsnow 公開 API（newsnext/newsnow MIT ★22k）；台灣觀眾用的是繁中，
中國榜只當「華語共通話題」參考。零 token。
"""
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "publish"))
sys.path.insert(0, str(HERE))

OUT_DIR = Path.home() / ".vibe-trends"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) vibe-shorts trend_zh"
NEWSNOW = "https://newsnow.busiyi.world/api/s?id="
CN_SOURCES = {"weibo": "微博", "douyin": "抖音", "zhihu": "知乎",
              "bilibili-hot-search": "B 站", "toutiao": "頭條"}
# PTT 走 pttweb「今日全站熱門」（翻 PTT 目錄頁一板 6 頁只有兩小時份，八卦板 0 篇，2026-10-20 實測）。
PTT_HOT = "https://www.pttweb.cc/hot/all/today"
# 做不成深夜對談的板：運動、遊戲、直播單、股票盤勢、政黨口水。其餘全收，選題由 session 判斷。
PTT_SKIP = {"NBA", "Baseball", "BaseballXXXX", "LoL", "C_Chat", "Stock", "HatePolitics",
            "basketballTW", "Elephants", "Lions", "Guardians", "MLB", "Steam", "PlayStation"}
TOP = 20


def get(url, cookie=None):
    h = {"User-Agent": UA}
    if cookie:
        h["Cookie"] = cookie
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def parse_pttweb(page):
    """回 [(推文數, 回應數, 看板, 標題, 網址)]，照推文數排序。標題可能被切成兩個 span，要接回來。"""
    out = []
    for blk in page.split("e7-recommendScore")[1:]:
        s = re.match(r'[^>]*>.*?</i>\s*(\d+)', blk, re.S)
        c = re.search(r'e7description="回應:"[^>]*></i>\s*(\d+)', blk)
        u = re.search(r'href="(/bbs/([^/"]+)/M\.[^"]+)"', blk)
        t = re.search(r'e7-show-if-device-is-not-xs"[^>]*><span[^>]*>([^<]*)</span>'
                      r'(?:<span class="__e7-full-title-appended-part"[^>]*>([^<]*)</span>)?', blk)
        if s and u and t:
            out.append((int(s.group(1)), int(c.group(1)) if c else 0, u.group(2),
                        html.unescape(t.group(1) + (t.group(2) or "")).strip(),
                        "https://www.ptt.cc" + u.group(1) + ".html"))
    return sorted(out, key=lambda r: -r[0])


def collect_ptt():
    try:
        rows = parse_pttweb(get(PTT_HOT))
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[warn] PTT：{e}", file=sys.stderr)
        return []
    if not rows:  # 頁面改版：寧可吵也不要默默變 0
        print("[warn] PTT：pttweb 解析 0 條，頁面可能改版", file=sys.stderr)
    return [r for r in rows if r[2] not in PTT_SKIP]


def collect_cn():
    out = {}
    for sid, name in CN_SOURCES.items():
        try:
            d = json.loads(get(NEWSNOW + sid))
            out[name] = [(i["title"], i.get("url", "")) for i in d.get("items", [])[:TOP]]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            print(f"[warn] {name}：{e}", file=sys.stderr)
    return out


def collect_yt_tw():
    """YouTube 台灣發燒影片（videos.list chart=mostPopular，1 配額單位）。"""
    try:
        import tokens
        tokens.yt_refresh()  # access token 一小時過期，不續會 401（10-20 實測）
        q = urllib.parse.urlencode({"part": "snippet,statistics", "chart": "mostPopular",
                                    "regionCode": "TW", "maxResults": 30})
        req = urllib.request.Request("https://www.googleapis.com/youtube/v3/videos?" + q,
                                     headers={"Authorization": "Bearer " + tokens.read("YT_ACCESS_TOKEN")})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
    except Exception as e:  # 權杖過期、配額用完都只是少一個來源
        print(f"[warn] YouTube TW：{e}", file=sys.stderr)
        return []
    return [(int(i["statistics"].get("viewCount", 0)), html.unescape(i["snippet"]["title"]),
             i["snippet"]["channelTitle"], f"https://www.youtube.com/watch?v={i['id']}")
            for i in d.get("items", [])]


# 竄升 Shorts（2026-10-20 借鏡蔚藍 WEILANX 抖音 108 萬播放教程）：熱榜只給「大家在聊什麼」，
# 要知道「什麼片此刻正被推」得看平台本身：近 RISING_HOURS 小時內發布、每小時播放最高的短片，
# 小頻道爆的優先（爆的是選題不是老粉）。熱榜的 mostPopular 是長片大頻道，對短片選題沒用。
RISING_HOURS = 48
RISING_QS = ["", "冷知識", "心理學", "為什麼", "AI"]   # "" ＝不帶關鍵字，題型由結果決定
SMALL_SUBS = 50_000


def rising_rank(items, subs, now):
    """items: videos.list 的 item；回 [(每小時播放, 播放, 訂閱, 標題, 頻道, 網址)]，只留中文（排日文），照每小時播放排。"""
    out = []
    for i in items:
        t = html.unescape(i["snippet"]["title"])
        if not re.search(r"[㐀-鿿]", t) or re.search(r"[ぁ-ゟ゠-ヿ]", t):
            continue
        pub = datetime.fromisoformat(i["snippet"]["publishedAt"].replace("Z", "+00:00"))
        hrs = max((now - pub).total_seconds() / 3600, 1)
        v = int(i["statistics"].get("viewCount", 0))
        out.append((int(v / hrs), v, subs.get(i["snippet"]["channelId"]), t, i["snippet"]["channelTitle"],
                    f"https://www.youtube.com/shorts/{i['id']}"))
    return sorted(out, key=lambda r: -r[0])


def collect_yt_rising():
    try:
        import benchmarks  # 共用 search.list 呼叫與權杖
        benchmarks.tokens.yt_refresh()
        now = datetime.now(timezone.utc)
        after = (now - timedelta(hours=RISING_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ids = []
        for q in RISING_QS:  # 每次 100 配額單位，5 次＝500／日上限 1 萬
            p = dict(part="snippet", type="video", order="viewCount", videoDuration="short",
                     publishedAfter=after, regionCode="TW", relevanceLanguage="zh-Hant", maxResults=50)
            if q:
                p["q"] = q
            ids += [x["id"]["videoId"] for x in benchmarks.yt_api("search", **p).get("items", [])]
        ids = list(dict.fromkeys(ids))
        items = []
        for k in range(0, len(ids), 50):
            items += benchmarks.yt_api("videos", part="snippet,statistics", id=",".join(ids[k:k + 50]))["items"]
        cids = list({i["snippet"]["channelId"] for i in items})
        subs = {}
        for k in range(0, len(cids), 50):
            for c in benchmarks.yt_api("channels", part="statistics", id=",".join(cids[k:k + 50]))["items"]:
                if not c["statistics"].get("hiddenSubscriberCount"):
                    subs[c["id"]] = int(c["statistics"].get("subscriberCount", 0))
    except Exception as e:  # 權杖過期、配額用完都只是少一個來源
        print(f"[warn] YouTube 竄升：{e}", file=sys.stderr)
        return []
    return rising_rank(items, subs, now)


def render(ptt, yt, cn, rising=()):
    L = [f"# 中文熱榜 {date.today().isoformat()}", "",
         f"台灣：PTT 今日全站熱門（去掉 {len(PTT_SKIP)} 個運動／遊戲／政黨板）、YouTube 台灣發燒。中國：newsnow 熱榜（華語共通話題參考）。",
         "選題看能不能做成「女主＋Clawd 深夜對談」：生活、感情、職場、錢、人性的反直覺。", ""]
    L += [f"## YouTube 竄升 Shorts（近 {RISING_HOURS}h，每小時播放；★＝訂閱 <{SMALL_SUBS // 10000} 萬，爆的是選題）", ""]
    L += [f"- {ph:,}/h · {v:,} · {'★' if s is not None and s < SMALL_SUBS else ''}{c}"
          f"（{'?' if s is None else f'{s:,}'} 訂閱） · [{t}]({u})"
          for ph, v, s, t, c, u in rising[:30]] or ["- 抓不到"]
    L += ["", "## PTT 今日熱門（推文／回應）", ""]
    L += [f"- {n}／{c} · {b} · [{t}]({u})" for n, c, b, t, u in ptt[:40]] or ["- 抓不到"]
    L += ["", "## YouTube 台灣發燒", ""]
    L += [f"- {v:,} · {c} · [{t}]({u})" for v, t, c, u in yt] or ["- 抓不到"]
    for name, items in cn.items():
        L += ["", f"## {name}", ""]
        L += [f"- [{t}]({u})" for t, u in items]
    return "\n".join(L) + "\n"


def selftest():
    blk = ('<div class="e7-recommendScore text-no-wrap f11" x><i e7description="推文:" class="v"></i>\n 249\n </div>'
           '<div class="e7-recommendCount"><i aria-hidden="true" e7description="回應:" class="v"></i>\n 711\n </div>'
           '<a href="/bbs/Gossiping/M.1792383274.A.F45" class="e7-article-default"><span class="e7-title">'
           '<span class="e7-show-if-device-is-not-xs" data-v-1><span data-v-1>[新聞] 65歲免健保 &amp; 白黨團攤</span>'
           '<span class="__e7-full-title-appended-part" data-v-1>預算轟</span></span></span></a>')
    blk2 = ('<div class="e7-recommendScore" x><i e7description="推文:"></i> 836 </div>'
            '<a href="/bbs/NBA/M.1.A.F" ><span class="e7-show-if-device-is-not-xs" d><span d>[情報] 跟腱</span></span></a>')
    rows = parse_pttweb("head" + blk + blk2)
    assert [r[0] for r in rows] == [836, 249], f"推文數或排序錯：{rows}"
    g = rows[1]
    assert g[1:4] == (711, "Gossiping", "[新聞] 65歲免健保 & 白黨團攤預算轟"), f"回應數／看板／標題接回錯：{g}"
    assert g[4] == "https://www.ptt.cc/bbs/Gossiping/M.1792383274.A.F45.html", g[4]
    now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    mk = lambda vid, t, pub, v, cid: {"id": vid, "snippet": {"title": t, "publishedAt": pub, "channelId": cid,
                                                             "channelTitle": cid}, "statistics": {"viewCount": str(v)}}
    r = rising_rank([mk("a", "老片很多播放", "2026-10-18T12:00:00Z", 48000, "c1"),   # 48h → 1000/h
                     mk("b", "新片少但快", "2026-10-20T10:00:00Z", 6000, "c2"),      # 2h → 3000/h
                     mk("c", "日本語のタイトル", "2026-10-20T11:00:00Z", 99999, "c3"),
                     mk("d", "English only", "2026-10-20T11:00:00Z", 99999, "c4")], {"c2": 800}, now)
    assert [x[5][-1] for x in r] == ["b", "a"], f"每小時播放排序或語言過濾錯：{r}"
    assert r[0][:3] == (3000, 6000, 800) and r[1][2] is None, r
    print("✅ trend_zh selftest 全過")
    return 0


def main():
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    if sys.argv[1:]:  # 未知旗標不能落到真實抓取（fix 10432 類型）
        print(__doc__, file=sys.stderr)
        return 0 if sys.argv[1] in ("-h", "--help") else 2
    ptt, yt, cn, rising = collect_ptt(), collect_yt_tw(), collect_cn(), collect_yt_rising()
    OUT_DIR.mkdir(exist_ok=True)
    p = OUT_DIR / f"zh-{date.today().isoformat()}.md"
    p.write_text(render(ptt, yt, cn, rising), encoding="utf-8")
    print(f"{p}  竄升 {len(rising)}／PTT {len(ptt)}／YT {len(yt)}／中國榜 {sum(map(len, cn.values()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
