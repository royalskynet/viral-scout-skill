---
name: viral-scout
description: 營銷號（vibe-shorts）找爆款：選題、鉤子、節奏、畫面要依據時，跨 YouTube／X／Threads／IG／FB 找同題爆款並附播放數與連結。先讀已有結果與本檔已驗證命令，不從頭查。說「找爆款」「選題提案」「這題有沒有爆款」「對標」時用。
---

# viral-scout — 爆款證據，先查帳再出門

原則：凡營銷號需要資訊都以爆款為據；工具開源輪子優先，不寫爬蟲（wheel 卡 2026-10-11、10-13）。
專案：`/Users/you/dev/vibe-shorts-pipeline`。做片走 skill `vibe-shorts`。

## 0. 先查帳（命中就引用，不重抓）

| 要什麼 | 先看 | 新鮮度 |
|---|---|---|
| 某題有沒有爆款 | `refs/VIRAL-LEDGER.md`（逐題證據帳） | 30 天內直接用 |
| 頭部頻道、中位數 | `refs/BENCHMARKS.md`（`scripts/benchmarks.py` 產生） | 90 天 |
| 爆款怎麼拍（鏡頭／鉤子／逐字稿） | `refs/BREAKDOWN.md`、`refs/<頻道>-<id>/` | 不過期 |
| 今天熱度候選 | `~/.vibe-trends/<日期>.md`（launchd 每天跑 `daily-trends.sh`） | 當天 |

## 1. 各平台已驗證命令

只寫實測過的；狀態欄標最後驗證日。失敗的也記，下次不再試。

| 平台 | 命令 | 拿得到 | 狀態 |
|---|---|---|---|
| YouTube 搜爆款 | `yt-dlp --flat-playlist -J "ytsearch50:<q>"` 再依 view_count 排；結果多是長片，要篩 `duration ≤ 180` 才是 Shorts 證據 | 播放數、片長、連結 | ✅ 10-14 實跑 |
| YouTube 近期頭部 | `python3 scripts/benchmarks.py`（Data API search.list order=viewCount，約 3500 配額） | 頻道中位數、離群榜 | 有產出 refs/BENCHMARKS.md；10-14 未重跑 |
| YouTube 拆片 | `.venv/bin/python scripts/breakdown.py` | 鏡頭表、逐字稿、前 3 秒鉤子 | 有產出 refs/BREAKDOWN.md；10-14 未重跑 |
| YouTube API 配額 | Data API search 每次 100 單位、日上限 1 萬；用完回 `HTTP 429 Quota exceeded` | — | ⚠️ 10-14 用完，同日改 `yt-dlp ytsearch40`（只依相關度） |
| Instagram | Exa 搜 `site:instagram.com/reel <q>` 找網址 → `yt-dlp -J <reel URL>` 讀 like_count | 讚數；播放數 NA | ✅ 10-14；無熱度排序，清單不代表頭部 |
| Facebook | Exa 找網址 → `yt-dlp -J <影片頁 URL>` | 影片頁有播放與互動 | ✅ 10-14 只限 `/videos/` 頁；貼文頁回 `Unsupported URL`／`Cannot parse data` |
| Threads | Exa 搜 `site:threads.com <q>` → `curl -s "https://r.jina.ai/<貼文 URL>"` 讀 `N views` | 瀏覽數；無讚數 | ✅ 10-14 |
| X | Exa `site:x.com` | — | ❌ 10-14 三次 0 筆 |
| Exa 本身 | — | — | ❌ 10-14 本 session 無 Exa 工具（`ToolSearch "exa"` 只回 WebSearch／WebFetch）；IG／FB／Threads 三列的第一步因此跑不動 |
| IG／Threads 降級 | `WebSearch "site:instagram.com/reel <q>"`、`WebSearch "site:threads.com <q>"` | — | ❌ 10-14 兩組皆 0 筆目標貼文（只回第三方網站）；Exa 不可用時這題直接寫「無數字」 |
| X | `twitter search` | — | ❌ 未跑：環境無 `TWITTER_AUTH_TOKEN`／`TWITTER_CT0`，`~/.agent-reach/twitter-cookies.txt` 被 canary 擋（正確行為，勿繞） |
| IG／FB／X | `opencli <平台> search` | — | ❌ 10-14 `BROWSER_CONNECT: Browser Bridge extension not connected` |
| YouTube 逐字稿 | `yt-dlp --skip-download --write-auto-subs --sub-langs en --sub-format vtt`；並發 4 支以上就 `HTTP Error 429: Too Many Requests`，逐支跑也 429 | 字幕 | ⚠️ 10-16 前 7 支成功後全 429 |
| YouTube 逐字稿（降級） | `yt-dlp -f ba -o "%(id)s.%(ext)s"` 抓音訊 → `.venv/bin/python` 跑 `mlx_whisper.transcribe(..., "mlx-community/whisper-large-v3-turbo", language="en")` | 有時間碼的逐字稿 | ✅ 10-16 字幕 429 時音訊照樣能抓；沒口白的片（聊天截圖＋配樂）會幻聽成重複句，要丟掉 |
| YouTube 頻道 Shorts 頁 | `yt-dlp --flat-playlist -J "https://www.youtube.com/@<頻道>/shorts"` | — | ❌ 10-16 @JadenWilliams 回空 |
| 拉片（切點／鏡長／拼圖） | `python3 scripts/ref_analyze.py <影片> --out <前綴>`；ffmpeg scene 偵測在對談片抓 0 刀，不用 | 切點、每鏡秒數中位數、全尺寸＋360px 拼圖 | ✅ 10-18 agentmorphy Dd7fGY6gLbH 14 刀／中位 3.17s；DeEYUXSAtIB 18 刀／中位 2.4s |
| 體檢 | `~/.local/bin/agent-reach doctor --json`（本機無 conda） | 各平台後端 | ✅ 10-14 |

量級參考（10-14）：中文地理 YT Shorts 頭部 100–450 萬；英文 1000 萬–1.7 億；Threads 地理題頭部 10–17 萬。

## 2. 證據格式（寫進 VIRAL-LEDGER）

```
## <題目>（<YYYY-MM-DD> 查）
- <平台>｜<播放或讚>｜<標題>｜<URL>
判定：有爆款（≥100 萬或離群 ≥×5）／弱（10–100 萬）／無
```
抓不到數字寫「無數字」，不准估。

## 3. 收尾（經驗入帳，不然下次又從頭查）

1. 本次查到的證據 append 到 `refs/VIRAL-LEDGER.md`。
2. 新驗證成功或失敗的命令，更新第 1 節表格（含日期、失敗原因原文）。
3. commit。
