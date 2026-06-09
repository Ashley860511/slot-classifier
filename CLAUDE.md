# Slot Classifier — Claude 工作指引

## 專案說明

這是競品老虎機影片截圖自動分類工具。
把遊戲錄影放入 `project/input_videos/`，執行後會將截圖依遊戲狀態分類到 `project/output/<影片名>/` 各子資料夾。

---

## 環境需求

```bash
# 建立虛擬環境（首次）
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

---

## 核心指令

| 指令 | 說明 |
|------|------|
| `bash classify_with_roi_confirm.sh --video-id WildTrain` | 完整流程（含 ROI 人工確認） |
| `bash run_classify_roi.sh --video-id WildTrain --roi x,y,w,h` | 直接指定 ROI 跑分類 |
| `python app/generate_review_page.py project/output/WildTrain` | 單獨生成審核頁 |

---

## 收到分析任務時的標準流程

用戶說「幫我分析 WildTrain」或「對 WildTrain 做競品截圖分類」時：

### 步驟 1 — 確認影片存在
```bash
ls project/input_videos/
```
若影片不在，告知用戶把 mp4 放入 `project/input_videos/`。

### 步驟 2 — 執行 ROI 偵測（取得預覽）
```bash
bash classify_with_roi_confirm.sh --video-id {VIDEO_ID}
```

腳本輸出若包含 `WAITING_ROI_CONFIRM:`，代表需要人工確認 ROI：
- 告知用戶：「請用瀏覽器開啟以下檔案確認 ROI 邊框」
- 路徑：`project/output/{VIDEO_ID}/_debug/roi_adjust.html`
- Windows 用 `file://` 或網路磁碟路徑開啟

### 步驟 3 — 等待用戶確認 ROI
用戶回覆以下任一格式：
- `ROI 確認：630,80,650,950` → 使用指定座標
- `ROI OK` → 使用 auto 偵測值（從 WAITING_ROI_CONFIRM 後的座標取得）

### 步驟 4 — 執行分類
```bash
# 使用確認的 ROI
bash classify_with_roi_confirm.sh --video-id {VIDEO_ID} --roi {x,y,w,h}
```

### 步驟 5 — 生成審核頁
```bash
# 生成截圖審核頁（含 Symbol Review 區塊）
# Symbol 提取已由 pipeline.py 在分類時自動完成，無需另外執行
python app/generate_review_page.py project/output/{VIDEO_ID}
```

### 步驟 6 — 告知用戶開啟審核頁
分類完成後，告知用戶：
- 審核頁位置：`project/output/{VIDEO_ID}/review.html`
- 各類別截圖數量（從 CSV 統計）
- 需要人工複審的張數（needs_review 資料夾）

### 步驟 7 — Symbol 審核（主動提示用戶）

**這步很重要，不能省略。** 告知用戶：

> review.html 底部有「Symbol 審核」區塊，請捲到最下方：
> 1. 確認自動提取的 symbol 是否完整
> 2. 若有遺漏（例如某個麻將牌、特殊符號），點擊下方 Help 截圖縮圖
> 3. 在彈出的裁切工具上拖曳框選遺漏的 symbol
> 4. 輸入名稱（選填）→「加入為 Symbol」
>
> 若用 `file://` 開啟，按「加入」會下載 PNG，請手動放到：
> `project/output/{VIDEO_ID}/symbol_table/symbols/`

**Claude 自己也要主動判斷：** 若 symbol 數量明顯偏少（少於 5 個）或有重複，
主動說明可能原因（如 Help 頁只截到規則頁、paytable 滾動位置不完整），
並建議用戶在 review.html 的 Symbol 審核區塊手動補切。

### 步驟 8 — 主動確認審核完成，接著生成競品報告

告知用戶所有審核步驟後，**主動詢問**：

> 「請確認以下兩項都完成後告訴我：
> 1. ✅ review.html 的截圖審核（改分類 / 排除）已套用
> 2. ✅ Symbol 審核區塊已確認（有補切遺漏的 symbol）
>
> 完成後我會立刻幫你生成競品分析報告 (report.html)。」

**收到用戶確認後**（例如「好了」「完成」「可以開始報告」），
在執行 slot-report skill 之前，**必須先完整閱讀以下資料夾的所有截圖**，確保對玩法機制有完整理解，再撰寫報告：

### 報告前必讀截圖清單（依優先順序）

1. **`Help/`** — 官方說明頁，包含賠率表、特殊符號說明、所有機制文字
2. **`low_score/Help/`** — 同為說明頁但信心度較低，補充 Help/ 的捲動漏讀部分
3. **`needs_review/`（各子資料夾）** — 低信心截圖，可能包含賠率頁的其他段落、特殊演出

> **重點：賠率表通常跨多張截圖（頁面捲動），M4 / 低值符號賠率容易遺漏在後半段。
> 機制說明（Cascade、Multiplier 觸發條件）須從 Help 文字確認，不可從截圖外觀推測。**

確認閱讀完畢後，立刻使用 **slot-report skill** 生成競品分析報告：

```
# Claude 內部執行（使用 slot-report skill）
觸發條件：用戶確認審核完成
輸入：project/output/{VIDEO_ID}/
輸出：project/output/{VIDEO_ID}/report.html
```

生成完成後回報：
- 報告位置：`project/output/{VIDEO_ID}/report.html`
- 提醒用戶可在瀏覽器開啟，並用「✏️ 編輯模式」替換圖片或修改文字

**同時主動列出「可能有誤的欄位」**，讓用戶知道哪些需要人工確認，例如：

> 報告已生成，以下欄位由 Claude 推斷，請人工核對：
> - **開發商**：從畫面 Logo 推測，請確認
> - **格局（Grid）**：從截圖目測，請確認格柱數
> - **最高倍率**：從 Free Spins 畫面讀取，請對照 Help 頁
> - **賠率數字**：從 OCR 讀取 Help 頁，可能有誤讀
> - **Wild 規則**：從 Help 文字推斷，請確認觸發條件

用戶在「✏️ 編輯模式」修改報告後，**修改內容會自動同步回 tags.json 與 assets.json**（由報告內建 JS 處理）。

---

## ROI 確認說明（給用戶）

分類前會先偵測遊戲畫面區域（ROI）。若偵測框偏移，分類準確度會下降。

- **開啟** `_debug/roi_adjust.html`（瀏覽器）
- **拖曳** 綠色邊框到正確的遊戲區域
- **按「✅ 確認 ROI」**，頁面會複製訊息到剪貼板
- **貼回 chat** 送出即可繼續分類

---

## 輸出目錄結構

```
project/output/{VIDEO_ID}/
├── Basegame/          # 基本遊戲畫面
├── Feature game/      # 特殊功能遊戲
├── BigWin/            # 大獎演出
├── Transition/        # 轉場畫面
├── Result/            # 結算畫面
├── Help/              # 說明頁
├── loading/           # 載入畫面
├── Other/             # 其他
├── needs_review/      # 低信心、需人工複審
├── _debug/
│   ├── auto_roi_preview.jpg   # ROI 偵測預覽
│   └── roi_adjust.html        # 互動式 ROI 調整頁
├── classification_result.csv  # 完整分類結果
├── review.html                # 審核頁（含 Symbol Review 區塊）
└── symbol_table/
    ├── symbols/               # 最終 symbol PNG（自動 + 手動補切）
    │   ├── symbol_candidate_NNN_*.png   # 自動提取
    │   └── symbol_manual_NNN*.png       # 手動補切
    └── icon_candidates/       # 候選池（供除錯）
```

---

## 效能說明

- **FRAME_INTERVAL = 20**：每 20 幀取一張（~4 分鐘影片約 325 幀）
- **OCR 輸入限 480px**：自動縮圖後執行，box 座標自動還原
- **cpu_threads = 2**：限制 PaddleOCR 核心佔用，避免主機過載

如需調整取樣密度，修改 `app/constants.py` 的 `FRAME_INTERVAL`。

---

## 禁止操作

- 禁止直接修改 `project/output/` 內已分類的截圖（會破壞 CSV 索引）
- 禁止在分類進行中刪除輸出目錄
