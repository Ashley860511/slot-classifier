# Slot Classifier — 競品截圖分類工具

> 把遊戲錄影丟進來，自動截圖並依遊戲狀態分類，最後產出可在瀏覽器操作的人工審核頁面。

---

## 目錄

1. [專案說明](#1-專案說明)
2. [環境需求](#2-環境需求)
3. [安裝步驟](#3-安裝步驟)
4. [以 Claude 串聯完整流程（推薦）](#4-以-claude-串聯完整流程推薦)
5. [手動執行指令（不使用 Claude）](#5-手動執行指令不使用-claude)
6. [輸出目錄結構](#6-輸出目錄結構)
7. [人工審核流程](#7-人工審核流程)
8. [常見問題](#8-常見問題)

---

## 1. 專案說明

本工具將遊戲錄影自動分類為以下狀態截圖：

| 類別 | 說明 |
|------|------|
| `Basegame` | 一般底層遊戲畫面 |
| `Feature game` | 特殊功能觸發中 |
| `BigWin` | 大獎演出畫面 |
| `Transition` | 轉場畫面 |
| `Result` | 結算畫面 |
| `Help` | 說明頁 |
| `loading` | 載入畫面 |
| `Other` | 無法歸類 |

分類完成後產出：
- `classification_result.csv`：完整分類紀錄（含信心分數）
- `review.html`：可在瀏覽器操作的人工審核頁，支援改分類與排除

---

## 2. 環境需求

| 項目 | 版本需求 |
|------|----------|
| Python | **3.10**（建議，其他版本未測） |
| Claude Code CLI | 最新版 |
| 作業系統 | Windows 10/11、macOS、Linux |
| 磁碟空間 | 每部影片約 500 MB～2 GB 輸出 |
| 記憶體 | 建議 8 GB 以上（OCR 使用） |

> ⚠️ 本工具使用 **CPU-only PaddleOCR**，不需要 GPU，但首次執行會下載約 300 MB 模型檔。

---

## 3. 安裝步驟

### 3-1. 取得專案

```bash
git clone https://github.com/Ashley860511/slot-classifier.git
cd slot-classifier
```

### 3-2. 建立 Python 虛擬環境

```bash
# 建立虛擬環境
python3.10 -m venv .venv

# 啟動（macOS / Linux）
source .venv/bin/activate

# 啟動（Windows PowerShell）
.venv\Scripts\Activate.ps1

# 安裝依賴
pip install -r requirements.txt
```

> 📦 PaddleOCR 安裝約需 3～10 分鐘，視網路速度而定。

### 3-3. 安裝 Claude Code CLI

```bash
npm install -g @anthropic/claude-code
```

> 需要 Node.js 18 以上。若尚未安裝 Node.js，請至 https://nodejs.org 下載。

登入 Anthropic 帳號：

```bash
claude login
```

### 3-4. 驗證環境

```bash
python check_environment.py
```

輸出應顯示各套件版本無誤。

### 3-5. 建立影片放置目錄

```bash
mkdir -p project/input_videos
```

---

## 4. 以 Claude 串聯完整流程（推薦）

> **這是最簡單的使用方式。** 所有步驟由 Claude 自動協調，你只需要用中文告訴它要做什麼。

### 4-1. 啟動 Claude Code

在專案根目錄執行：

```bash
claude
```

Claude 會自動讀取 `CLAUDE.md`，載入本專案的工作規則。

### 4-2. 放入影片

把要分析的影片（`.mp4`）放到：

```
project/input_videos/WildTrain.mp4
```

### 4-3. 告訴 Claude 開始分析

在 Claude Chat 輸入：

```
幫我分析 WildTrain
```

Claude 會自動執行以下步驟：

```
① 確認影片存在於 input_videos/
② 執行 Auto ROI 偵測，生成邊框預覽頁
③ 告知你開啟瀏覽器確認 ROI 位置
④ 等你回覆確認後，開始全片分類
⑤ 分類完成，生成 review.html
⑥ 自動啟動 http://localhost:8765（本機審核 Server）
⑦ 告知你各類別截圖數量與需人工審核的張數
```

### 4-4. 確認 ROI 邊框

Claude 偵測到遊戲畫面區域後，會給你一個本機瀏覽器連結，例如：

```
file:///path/to/project/output/WildTrain/_debug/roi_adjust.html
```

在瀏覽器中：

1. 檢查**綠色邊框**是否對齊遊戲畫面（不包含到影片外框）
2. 若需調整：拖曳邊框四角或側邊調整範圍
3. 按「**✅ 確認 ROI**」→ 頁面自動複製座標訊息到剪貼簿
4. 貼回 Claude Chat 送出：

```
ROI 確認：400,50,650,950
```

若邊框位置正確不需調整，回覆：

```
ROI OK
```

### 4-5. 等待分類完成

分類過程中 Claude 會顯示進度。完成後會自動啟動審核 Server：

```
► 啟動審核 Server（http://localhost:8765）...
  在瀏覽器開啟上方網址即可進行人工修正
  完成後按 Ctrl+C 停止
```

### 4-6. 人工審核（選做）

開瀏覽器進入 `http://localhost:8765`，對中低信心的截圖進行複審。
詳細操作說明見第 7 節。

### 4-7. 其他可對 Claude 說的指令

```
# 只生成審核頁，不重跑分類
幫我重新生成 WildTrain 的審核頁

# 查看分類統計
WildTrain 各類別各幾張？

# 重新分類但跳過 ROI 確認（使用已知座標）
用 ROI 400,50,650,950 重新分類 WildTrain

# 確認目前有哪些影片可以分析
input_videos 裡有什麼？
```

---

## 5. 手動執行指令（不使用 Claude）

若不使用 Claude，可直接執行以下指令：

### 完整流程（含 ROI 確認）

```bash
# 步驟一：執行 Auto ROI 偵測
# 看到 WAITING_ROI_CONFIRM: 後，在瀏覽器確認 ROI 再繼續
bash classify_with_roi_confirm.sh --video-id WildTrain

# 步驟二：確認後帶座標重跑（自動完成分類 + 審核頁 + 啟動 Server）
bash classify_with_roi_confirm.sh --video-id WildTrain --roi 400,50,650,950
```

### 只跑分類（不確認 ROI）

```bash
bash run_classify.sh --video-id WildTrain
```

### 單獨生成審核頁

```bash
.venv/bin/python app/generate_review_page.py project/output/WildTrain
```

### 單獨啟動審核 Server

```bash
.venv/bin/python review_server.py --video-id WildTrain
# 開瀏覽器前往 http://localhost:8765
```

### 套用審核修正（從 JSON 檔）

```bash
.venv/bin/python apply_corrections.py corrections.json
```

---

## 6. 輸出目錄結構

```
project/output/WildTrain/
├── Basegame/                   # 各類別截圖
├── Feature game/
├── BigWin/
├── Transition/
├── Result/
├── Help/
├── loading/
├── Other/
├── needs_review/               # 中低信心截圖（分類副本，供快速複審）
│   ├── Basegame/
│   └── Feature game/
├── excluded/                   # 人工審核後排除的截圖
├── _debug/
│   ├── auto_roi_preview.jpg    # ROI 偵測預覽圖
│   └── roi_adjust.html         # 互動式 ROI 調整頁
├── classification_result.csv   # 完整分類紀錄
└── review.html                 # 人工審核頁
```

### CSV 欄位說明

| 欄位 | 說明 |
|------|------|
| `video_name` | 影片檔名 |
| `frame_idx` | 截圖幀編號 |
| `final_category` | 最終分類結果 |
| `diff_score` | 與上一幀的差異分數（越高越不同）|
| `blur_score` | 模糊程度（越低越模糊）|
| `top_score` | 最高類別分數 |
| `feature_subtype` | Feature 子類型（若適用）|
| `raw_texts` | OCR 辨識文字清單 |
| `category_scores` | 各類別分數明細 |
| `matched_keywords` | 命中的關鍵字 |
| `roi` | 使用的 ROI 座標 `(x,y,w,h)` |
| `save_path` | 截圖檔案絕對路徑 |
| `confidence_level` | 信心等級（`high` / `medium` / `low`）|
| `confidence_score` | 信心分數（0.0 ～ 1.0）|

---

## 7. 人工審核流程

### 信心等級說明

分類器對每張截圖計算信心分數，分三個等級：

| 信心等級 | 意義 | 審核頁標籤顏色 |
|----------|------|---------------|
| `high` | 分類確定，可信賴 | 🟢 綠色 |
| `medium` | 有把握但邊界模糊 | 🟡 黃色 |
| `low` | 信心不足，需確認 | 🔴 紅色 |

`medium` 與 `low` 的截圖會同時複製到 `needs_review/<類別>/`，方便快速找到待確認的項目。

### 審核操作

開瀏覽器前往 `http://localhost:8765`（或直接開 `review.html`）：

| 操作 | 說明 |
|------|------|
| ✅ 正確 | 標記為已確認，檔案不移動 |
| 🔀 改分類 | 從下拉選單選正確類別，套用後自動移動截圖 |
| 🗑️ 排除 | 移動到 `excluded/`，從統計中移除 |

右上角會顯示「待處理 N 張」，處理完畢後按「**套用修正**」。

套用後 `classification_result.csv` 自動更新，截圖也會移到對應資料夾。

> **注意：** 若以 `file://` 直接開啟（非 localhost），按下「套用修正」會**複製 JSON 到剪貼簿**，請執行：
> ```bash
> .venv/bin/python apply_corrections.py --json '<貼上剪貼簿內容>'
> ```

---

## 8. 常見問題

### Q: PaddleOCR 安裝失敗

```bash
# 分開安裝
pip install paddlepaddle==2.6.2
pip install paddleocr==2.7.3
```

Windows 若出現 C++ 編譯錯誤，請先安裝 [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)。

### Q: 第一次執行很慢（等很久才開始處理圖片）

PaddleOCR 首次執行會自動下載語言模型（約 300 MB），屬正常現象，後續執行不會重複下載。

### Q: ROI 調整頁開啟後是空白或 404

確認路徑中沒有中文或特殊字元。手動重新生成：

```bash
.venv/bin/python app/generate_roi_preview.py --video-id WildTrain
```

再用瀏覽器開啟：`project/output/WildTrain/_debug/roi_adjust.html`

### Q: review server 啟動失敗（port 8765 已占用）

```bash
.venv/bin/python review_server.py --video-id WildTrain --port 8766
```

### Q: 分類速度很慢

OCR 是主要瓶頸。可調高取樣間隔降低工作量：

```python
# app/constants.py
FRAME_INTERVAL = 30  # 預設 20，調高可加快速度但會降低截圖密度
```

### Q: 套用修正後 needs_review/ 裡還有舊截圖

`needs_review/` 是分類時自動產生的副本，`apply_corrections` 只移動主目錄的原始檔。
`needs_review/` 的副本可手動刪除，不影響 CSV 紀錄與截圖檔案。

### Q: 想重新分類，但不想刪掉舊截圖

手動建一個備份資料夾，再刪除 `project/output/WildTrain/` 後重跑。

---

## 效能參考

| 設定 | 預設值 | 調整方式 |
|------|--------|----------|
| `FRAME_INTERVAL` | 20 幀取 1 張 | `app/constants.py` |
| `OCR_MAX_SIDE` | 480 px | `app/ocr_utils.py` |
| `cpu_threads` | 2 核心 | `app/ocr_utils.py` |
| `AUTO_ROI_SAMPLE_COUNT` | 40 幀 | `app/config.py` |

以 4 分鐘影片（720p）為例，預期分類時間約 **5～10 分鐘**（CPU-only 環境）。

---

*維護者：ashleyli　｜　分支：`main`*
