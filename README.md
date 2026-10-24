# viral-scout — a Claude Code skill for sourcing viral evidence

繁中在下面 ↓

Before a short-video topic gets made, it has to show evidence that the topic already went viral somewhere. This skill is how that evidence gets found, and more importantly, how it stops being re-found.

- **Check the ledger first.** Each question routes to a local file with an explicit freshness window — topic evidence good for 30 days, channel medians for 90, shot breakdowns never expire, today's trend candidates from a daily cron. Only a miss goes to the network.
- **Only verified commands, with their failure dates.** The platform table records what actually ran, what it returned, and when. Failures stay in the table with the verbatim error, so the next session doesn't retry a dead path: quota exhaustion and its fallback, transcript rate limits and the audio-plus-Whisper workaround, browser-bridge and cookie-auth dead ends, a platform that returned zero results three times.
- **Numbers or nothing.** Evidence is logged as platform / views / title / URL, with a verdict threshold. No estimating — "no number" is a valid, required answer.
- **Experience goes back in.** Every run appends evidence to the ledger and updates the command table, including newly broken commands. That write-back is the point: the ledger is what makes the next lookup cheap.

The downstream pipeline enforces this mechanically — its pre-publish gate refuses to ship a film whose treatment lacks a viral-evidence line with a link and a view count above a floor.

## Install

```bash
git clone https://github.com/royalskynet/viral-scout-skill ~/.claude/skills/viral-scout
```

## Scope

This is the **de-identified documentation layer**, published as portfolio work. The ledgers it reads and the films it feeds stay private, so paths and repo links here point at a private source.

The pipeline that consumes this evidence is a separate skill: [vibe-shorts](https://github.com/royalskynet/vibe-shorts-skill).

---

# viral-scout — 找爆款證據的 Claude Code 技能包

一個短影音題目要能開工，先得證明這題已經在某處爆過。這個技能包是找證據的方法，更重要的是**讓同一份證據不用找第二次**。

- **先查帳**。每種問題對應一個本機檔案，各有明寫的新鮮度：逐題證據 30 天內直接用、頻道中位數 90 天、拆片鏡頭表不過期、當天熱度候選由每日排程產出。查不到才上網。
- **只寫實測過的命令，連失敗日期一起寫**。平台表記的是真的跑過什麼、拿到什麼、哪天驗的。失敗的留在表上並附錯誤原文，下次不再試死路：API 配額用完與降級做法、逐字稿 429 與改抓音訊跑 Whisper 的繞法、瀏覽器橋接與 cookie 認證的死巷、連查三次 0 筆的平台。
- **有數字才算**。證據格式是平台／播放或讚／標題／URL，附判定門檻。不准估 ——「無數字」是合法且必須寫出來的答案。
- **經驗入帳**。每次查完把證據 append 回帳本、把新驗證或新壞掉的命令更新回表格。這個回寫才是重點：帳本就是下次查得便宜的原因。

下游流水線用機械手段強制這件事：發布前閘門會擋下 treatment 裡沒有「爆款證據」行（含連結與播放數且超過門檻）的片子。

## 安裝

```bash
git clone https://github.com/royalskynet/viral-scout-skill ~/.claude/skills/viral-scout
```

## 範圍

這是**脫敏後的文件層**，作為作品集公開。它讀的帳本與餵的片子保持私有，所以文件裡的路徑與連結指向私有正本。

吃這些證據的流水線在另一個技能包：[vibe-shorts](https://github.com/royalskynet/vibe-shorts-skill)。
