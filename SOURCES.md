# 來源：viral-scout 的實作與帳本

路徑相對技能包根目錄。標「私有端」的留在流水線正本（綁帳號或是內容資產），技能包不帶。

## 帳本（第 0 節「先查帳」）

帳本內容是資產，不公開；格式與開帳方式在 `templates/`：

| 帳本 | 空範本 | 新鮮度 | 誰產生 |
|---|---|---|---|
| `refs/VIRAL-LEDGER.md` 逐題證據 | `templates/VIRAL-LEDGER.md` | 30 天 | 手寫（每次查完 append） |
| `refs/BENCHMARKS.md` 頭部頻道與中位數 | `templates/BENCHMARKS.md` | 90 天 | `scripts/benchmarks.py`（私有端，綁 YouTube OAuth） |
| `refs/BREAKDOWN.md` 爆款怎麼拍 | `templates/BREAKDOWN.md` | 不過期 | `scripts/breakdown.py` |
| `refs/postmortem.md` 自己發過的片 | `templates/postmortem.md` | 每片兩次 | 手寫＋平台數據 |
| 當天熱度候選 `~/.vibe-trends/<日期>.md` | — | 當天 | `scripts/trend_scan.py`（排程） |

## 抓取與分析腳本（第 1 節表格）

| 腳本 | 做什麼 | 外部依賴 |
|---|---|---|
| `scripts/trend_scan.py` | 每日熱度掃描、關鍵字打分（零 token、只抓公開介面） | 無 |
| `scripts/trend_zh.py` | 中文熱度來源 | 無 |
| `scripts/breakdown.py` | 拆片：鏡頭表、逐字稿、前 3 秒鉤子 | [yt-dlp](https://github.com/yt-dlp/yt-dlp)、ffmpeg；逐字稿降級用 [mlx-whisper](https://github.com/ml-explore/mlx-examples) |
| `scripts/ref_analyze.py` | 拉片：切點、鏡長中位數、拼圖 | ffmpeg |
| `scripts/viral_text.py` | 文字題的爆款訊號 | 無 |
| `tests/test_breakdown.py`、`tests/test_ref_analyze.py` | 最小自檢（不連網） | 無 |
| `scripts/benchmarks.py` | YouTube Data API 頭部與中位數（約 3500 配額） | **私有端**：沿用 `scripts/publish/tokens.py` 的 OAuth |

## 下游（證據怎麼被用）

- 做片技能包：[vibe-shorts](https://github.com/royalskynet/vibe-shorts-skill)
- 它的 `scripts/precheck.py` 有「爆款證據」門（`VIRAL_MIN = 100_000`）：片子的 `TREATMENT.md` 沒有含連結與播放數的證據行就不給出片
- 私有端：`refs/dialogue-corpus/`（對談原稿與直譯，「台詞非照抄」門比對用）、`refs/vkv/style-guide.md`（節奏基準的逆向來源）
