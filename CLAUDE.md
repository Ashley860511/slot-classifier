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

### 步驟 5 — 回報結果
分類完成後，告知用戶：
- 審核頁位置：`project/output/{VIDEO_ID}/review.html`
- 各類別截圖數量（從 CSV 統計）
- 需要人工複審的張數（needs_review 資料夾）

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
└── review.html                # 審核頁（瀏覽器開啟）
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
