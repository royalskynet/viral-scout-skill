---
name: viral-scout
description: 營銷號（vibe-shorts）找爆款：選題、鉤子、節奏、畫面要依據時，跨 YouTube／X／Threads／IG／FB 找同題爆款並附播放數與連結。說「找爆款」「選題提案」「這題有沒有爆款」「對標」時用。
---

# viral-scout — 爆款證據，先查帳再出門

凡營銷號需要資訊都以爆款為據。工具用開源輪子，不寫爬蟲。腳本在 `scripts/`；做片走 skill `vibe-shorts`。

## 0. 先查帳（命中就引用，不重抓）

沒有 `refs/` 就先開帳：`mkdir -p refs && cp templates/*.md refs/`。

| 要什麼 | 先看 | 新鮮度 |
|---|---|---|
| 某題有沒有爆款 | `refs/VIRAL-LEDGER.md`（逐題證據帳） | 30 天 |
| 頭部頻道、中位數 | `refs/BENCHMARKS.md`（`scripts/benchmarks.py`，私有端、綁 YouTube Data API 憑證） | 90 天 |
| 爆款怎麼拍（鏡頭／鉤子／逐字稿） | `refs/BREAKDOWN.md`、`refs/<頻道>-<id>/` | 不過期 |
| 今天熱度候選 | `~/.vibe-trends/<日期>.md`（排程跑 `scripts/trend_scan.py`） | 當天 |

## 1. 各平台已驗證命令

只寫實測過的，附最後驗證日；失敗的也記，下次不再試。

| 平台 | 命令 | 拿得到 | 狀態 |
|---|---|---|---|
| YouTube 搜爆款 | `yt-dlp --flat-playlist -J "ytsearch50:<q>"` 依 view_count 排；篩 `duration ≤ 180` 才算 Shorts 證據 | 播放數、片長、連結 | ✅ 10-14 |
| YouTube 近期頭部 | `python3 scripts/benchmarks.py`（search.list order=viewCount，約 3500 配額） | 頻道中位數、離群榜 | 產出在 refs/BENCHMARKS.md |
| YouTube API 配額 | search 每次 100 單位、日上限 1 萬；用完回 `HTTP 429 Quota exceeded` → 當日改 `yt-dlp ytsearch40`（只依相關度） | — | ⚠️ 10-14 |
| YouTube 拆片 | `.venv/bin/python scripts/breakdown.py` | 鏡頭表、逐字稿、前 3 秒鉤子 | 產出在 refs/BREAKDOWN.md |
| YouTube 逐字稿 | `yt-dlp --skip-download --write-auto-subs --sub-langs en --sub-format vtt`；連跑約 7 支後 `HTTP Error 429`（逐支也會） | 字幕 | ⚠️ 10-16 |
| YouTube 逐字稿降級 | `yt-dlp -f ba -o "%(id)s.%(ext)s"` → `.venv/bin/python` 跑 `mlx_whisper.transcribe(..., "mlx-community/whisper-large-v3-turbo", language="en")`；沒口白的片會幻聽成重複句，丟掉 | 有時間碼逐字稿 | ✅ 10-16 |
| Instagram | Exa 搜 `site:instagram.com/reel <q>` → `yt-dlp -J <reel URL>` 讀 like_count；無熱度排序，清單不代表頭部 | 讚數（播放 NA） | ✅ 10-14 |
| Facebook | Exa 找網址 → `yt-dlp -J <影片頁 URL>`；只限 `/videos/` 頁 | 播放與互動 | ✅ 10-14 |
| Threads | Exa 搜 `site:threads.com <q>` → `curl -s "https://r.jina.ai/<貼文 URL>"` 讀 `N views` | 瀏覽數 | ✅ 10-14 |
| 拉片（切點／鏡長／拼圖） | `python3 scripts/ref_analyze.py <影片> --out <前綴>` | 切點、鏡長中位數、拼圖 | ✅ 10-18（對談片中位約 2.4–3.2s） |
| 體檢 | `~/.local/bin/agent-reach doctor --json` | 各平台後端 | ✅ 10-14 |

已驗證失敗，不再試：

- Exa 工具不在時（`ToolSearch "exa"` 只回 WebSearch／WebFetch），IG／FB／Threads 第一步跑不動；`WebSearch "site:instagram.com/reel …"`／`"site:threads.com …"` 只回第三方網站 → 該題寫「無數字」。❌ 10-14
- X：Exa `site:x.com` 0 筆；`twitter search` 缺 `TWITTER_AUTH_TOKEN`／`TWITTER_CT0`，cookie 檔被 canary 擋是正確行為，**不繞**。❌ 10-14
- `opencli <平台> search`：`BROWSER_CONNECT: Browser Bridge extension not connected`。❌ 10-14
- FB 貼文頁：`Unsupported URL`／`Cannot parse data`。❌ 10-14
- `yt-dlp --flat-playlist -J "https://www.youtube.com/@<頻道>/shorts"` 回空。❌ 10-16
- `yt-dlp ytsearch` 只依相關度排序，拿來「找 100 萬級題目」命中率低（10-29：38 組查詢只 3 支 ≥100 萬）；找爆款題先翻 `refs/BENCHMARKS.md` 離群榜。IG 帳號頁（ladder cdp）未登入只有粉絲數、沒有各片播放數。⚠️ 10-29
- ffmpeg scene 偵測在對談片抓 0 刀，拉片改用 `ref_analyze.py`。

量級參考：中文地理 YT Shorts 頭部 100–450 萬；英文 1000 萬–1.7 億；Threads 地理題頭部 10–17 萬。

## 2. 證據格式（寫進 VIRAL-LEDGER）

```
## <題目>（<YYYY-MM-DD> 查）
- <平台>｜<播放或讚>｜<標題>｜<URL>
判定：有爆款（≥100 萬或離群 ≥×5）／弱（10–100 萬）／無
```

抓不到數字寫「無數字」，不准估。

## 3. 收尾（經驗入帳）

1. 證據 append 到 `refs/VIRAL-LEDGER.md`。
2. 新驗證成功或失敗的命令更新第 1 節（含日期、失敗訊息原文），改既有列不另加。
3. commit。

## 查表

- 帳本範本、各腳本做什麼與外部依賴、證據下游怎麼被 precheck 用 → `SOURCES.md`
