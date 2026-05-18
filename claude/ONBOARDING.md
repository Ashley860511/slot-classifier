# 老虎機競品分析報告 Skill — 使用指南

> 這個 Skill 讓 Claude 自動讀取遊戲截圖資料夾，生成一份完整的競品分析 HTML 報告，
> 包含符號賠率表、玩法機制說明、互動式遊戲流程圖，並支援直接在瀏覽器內點選替換圖片與編輯文字。

---

## 安裝方式

### 步驟 1：找到 Skills 資料夾

在 Claude Code 中執行以下指令，找到你的 skills 存放路徑：

```
/skills
```

或直接前往以下路徑（Windows）：
```
%APPDATA%\Claude\local-agent-mode-sessions\skills-plugin\<uuid>\<uuid>\skills\
```

### 步驟 2：建立 slot-report 資料夾

在 skills 資料夾內新增 `slot-report/` 子目錄，並將 `SKILL.md` 放入其中：

```
skills/
└── slot-report/
    └── SKILL.md   ← 將以下內容貼入此檔案
```

### 步驟 3：複製 SKILL.md 內容

將本指南末尾的完整 `SKILL.md` 內容複製，貼入 `slot-report/SKILL.md` 並儲存。

---

## 使用方式

### 前置條件：遊戲資料夾結構

Skill 需要遊戲資料夾內有以下子目錄（由截圖分類工具產生）：

```
遊戲資料夾/（例如 "Lucky Piggy/"）
├── loading/              ← 載入畫面截圖
├── Basegame/             ← 主遊戲截圖
├── Transition/           ← 轉場截圖
├── Feature game/         ← 特色遊戲截圖
├── BigWin/               ← 大獎截圖
├── Result/               ← 結算截圖
└── symbol_table/
    └── symbols/          ← 符號 PNG（symbol_candidate_NNN_...png）
```

### 觸發方式

在 Claude Code 對話中輸入以下任一句話，Skill 即自動啟動：

```
幫我製作 [遊戲資料夾路徑] 的競品報告
```

```
幫我分析 C:\...\output\Lucky Piggy 這款遊戲，生成 report.html
```

```
用 slot-report skill 生成 [遊戲名稱] 的競品分析報告
```

### Claude 自動執行的步驟

1. **掃描** 截圖資料夾，讀取各分類的影格清單
2. **檢視** loading/、Basegame/、Transition/、Feature game/ 等關鍵截圖，辨識遊戲名稱與特色
3. **讀取** symbol_table/symbols/ 內的符號 PNG，識別符號種類
4. **決定** 色彩主題（依遊戲風格選擇紅/綠/紫/粉紅/橙/藍/棕）
5. **撰寫** 完整的 report.html 並存檔

---

## 報告功能說明

### 三大段落

| 段落 | 內容 |
|------|------|
| 符號賠率表 | 特殊符號（Scatter/Wild）、主力符號（M1–M5）、低值符號（字牌），各附圖片與賠率 |
| 玩法機制 | 4–6 張機制卡，說明觸發條件、特效規則、連鎖機制等 |
| 遊戲流程圖 | 2 列橫向流程：主遊戲流程 + 免費旋轉流程，各節點附截圖縮圖 |

### 可編輯功能

報告右下角有兩個固定按鈕：

- **✏️ 編輯模式** — 啟動後：
  - 所有文字變為可直接點選編輯（contenteditable）
  - 所有圖片 hover 顯示 🔄，點擊後開啟本機檔案選擇器替換圖片
- **📋 複製 HTML** — 編輯模式中出現，一鍵複製整份 HTML（已替換的圖片以 base64 內嵌）

---

## 色彩主題對照

| 遊戲風格 | 主色 | 適用範例 |
|----------|------|----------|
| 中式/財神（紅） | `#8b2030` | Caishen Wins、招財進寶 |
| 足球/運動（綠） | `#207840` | Goal Rush、足球嘉年華 |
| Emoji/趣味（紫） | `#7030a0` | Emoji Riches |
| 幸運/經典（粉紅）| `#c03065` | Lucky Piggy |
| 遊樂園/橙 | `#c06020` | WildCoaster |
| 奇幻/藍 | `#2050a0` | 奇幻冒險類 |
| 動物/棕 | `#805020` | 動物主題類 |

---

## 流程圖節點顏色規範

| 顏色 | CSS Class | 用途 |
|------|-----------|------|
| 金框 | `c-gold` | Loading、重要觸發節點 |
| 紅框 | `c-red` | Base Game 主遊戲 |
| 銀框 | `c-silver` | 一般特色節點 |
| 綠框 | `c-green` | Free Spins 流程節點 |
| 綠光 | `c-bw1` | BIG WIN |
| 紫光 | `c-bw2` | SUPER WIN |
| 金光 | `c-bw3` | MEGA WIN / JUMBO WIN |
| 暗框 | `c-result` | 結算節點 |

---

## 完整 SKILL.md 內容

> 將以下內容複製至 `skills/slot-report/SKILL.md`

```markdown
---
name: slot-report
description: >
  產生老虎機競品分析報告（report.html）。當使用者提到「競品報告」「slot report」
  「分析報告」「report.html」「老虎機分析」時立即使用。
  輸出單一 report.html 檔案，包含符號賠率表、玩法機制、遊戲流程圖三大段落，
  所有圖片與文字均可在瀏覽器內直接點選替換／編輯，無需重新執行腳本。
  若資料夾內已有 symbol_table/symbols/ 與分類截圖，一律自動填入。
---

（請參照已安裝的 SKILL.md 原始檔）
```

> 完整 SKILL.md 已由 Skill Creator 生成並存放於你的 skills 目錄中。

---

## 已生成的報告範例

以下遊戲已使用此 Skill 生成報告：

| 遊戲 | 開發商 | 主題 | 特色 |
|------|--------|------|------|
| Caishen Wins | — | 中式/財神 | 243 Ways、Stacked Wild |
| 9（足球嘉年華）| — | 足球/綠 | Respin、全螢幕爆分 |
| 12 | — | 足球/綠 | Respin、鎖軸 |
| Emoji Riches | — | 趣味/紫 | Cluster Pays、Tumble、倍率累加 |
| Lucky Piggy | — | 幸運/粉紅 | Scatter Wild、Cascade、Sticky Wild |
| WildCoaster | — | 遊樂園/橙 | 4096 Ways、Tumble、Expanding Wild |
| Goal Rush | Omniplay | 足球/綠 | 3×3、罰球特效、500× 乘數、Jackpot |
