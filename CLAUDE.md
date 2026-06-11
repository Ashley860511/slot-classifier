# Slot Classifier — Claude 工作指引

## 專案說明

這是競品老虎機影片截圖自動分類工具。
把遊戲錄影放入 `project/input_videos/`，執行後會將截圖依遊戲狀態分類到 `project/output/<影片名>/` 各子資料夾，最終產出人工審核頁（review.html）與競品分析報告（report.html）。

---

## 啟動時自動偵測

Claude 啟動後，**立即執行以下偵測，不需等用戶開口**：

### A. 環境偵測

```bash
ls .venv 2>/dev/null && echo "VENV_OK" || echo "VENV_MISSING"
```

- **VENV_MISSING**：環境尚未安裝 → 執行「首次安裝流程」
- **VENV_OK**：環境已就緒 → 執行「分析任務流程」

### B. 作業系統偵測

```bash
uname -s 2>/dev/null || echo "Windows"
```

- Linux / Darwin（macOS）→ 使用 `bash` 指令
- Windows → **不使用 bash 腳本**，改用 PowerShell 直接呼叫 `.venv\Scripts\python.exe`（見下方 Windows 執行規則）

---

## 首次安裝流程（VENV_MISSING）

用親切的語氣告知用戶環境尚未安裝，並引導完成以下步驟：

### 步驟 1 — 確認 Python 版本

```bash
python --version || python3 --version
```

若版本不是 3.10.x，告知用戶需先安裝 Python 3.10：
> 「請前往 https://www.python.org/downloads/release/python-31011/
>  下載 Python 3.10，安裝時記得勾選『Add python.exe to PATH』。
>  安裝完成後告訴我，我會繼續。」

### 步驟 2 — 執行一鍵安裝

```bash
python setup.py
```

或 macOS / Linux：

```bash
python3 setup.py
```

告知用戶：「安裝約需 5～15 分鐘，完成後會顯示『✅ 環境安裝完成』。」

安裝完成後自動接續「分析任務流程」的步驟 1。

---

## 分析任務流程

用戶說「幫我分析 WildTrain」或「分析競品」時執行以下流程。

### 步驟 1 — 確認影片存在

```bash
ls project/input_videos/
```

若影片不在，告知用戶：
> 「請把影片放到 `project/input_videos/` 資料夾，
>  檔案名建議用英文（例如 WildTrain.mp4），放好後告訴我。」

### 步驟 2 — 執行 ROI 偵測

**macOS / Linux：**
```bash
bash classify_with_roi_confirm.sh --video-id {VIDEO_ID}
```

**Windows（PowerShell）：**
```powershell
cd "C:\Users\ashleyli\Documents\slot-classifier"
.\.venv\Scripts\python.exe app\generate_roi_preview.py --video-id {VIDEO_ID}
```

> ⚠️ Windows 上**不要用 bash 腳本**，原因見「Windows 踩坑紀錄」。

腳本輸出包含 `WAITING_ROI_CONFIRM:` 時，告知用戶用瀏覽器開啟：
`project/output/{VIDEO_ID}/_debug/roi_adjust.html`

### 步驟 3 — 等待用戶確認 ROI

引導用戶：
> 「請在瀏覽器確認綠色方框是否框住遊戲主畫面（不含黑邊）。
> - 框線正確 → 在這裡回覆『ROI OK』
> - 需要調整 → 拖曳方框到正確位置 → 按『✅ 確認 ROI』→ 把座標貼回來」

用戶回覆格式：
- `ROI OK` → 使用 auto 偵測座標
- `ROI 確認：630,80,650,950` → 使用指定座標

### 步驟 4 — 執行分類

**macOS / Linux：**
```bash
bash classify_with_roi_confirm.sh --video-id {VIDEO_ID} --roi {x,y,w,h}
```

**Windows（PowerShell）：**
```powershell
cd "C:\Users\ashleyli\Documents\slot-classifier"
.\.venv\Scripts\python.exe run_classify_roi.py --video-id {VIDEO_ID} --roi {x,y,w,h}
```

告知用戶：「分類需 5～15 分鐘，完成後會自動啟動審核 Server，請耐心等候。」

### 步驟 5 — 生成審核頁

分類完成後：

```bash
python app/generate_review_page.py project/output/{VIDEO_ID}
```

從 CSV 統計各類別數量後告知用戶：
> 「分類完成！結果如下：
> - Basegame：XX 張
> - Feature：XX 張
> - Help：XX 張
> - needs_review（需人工確認）：XX 張
>
> **審核頁（review.html）** 需啟動 Server 後開啟，按鈕才能正常運作：
> → 啟動後請用 **http://localhost:8765**
>
> ⚠️ 請勿直接用 file:// 開啟 review.html，否則 Symbol 圖片無法顯示，排除/正確按鈕也會失效。
>
> **競品報告（report.html）** 是純靜態頁面，不需要 Server，可直接用檔案路徑開啟：
> → `project/output/{VIDEO_ID}/report.html`」

### 步驟 6 — 啟動審核 Server（若未自動啟動）

<<<<<<< HEAD
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
=======
若 classify_with_roi_confirm.sh 已自動啟動 Server，跳過此步。
若未啟動（用戶說「找不到 Server」），執行：
>>>>>>> e206c684a16e8161a0a0ef33153d7cd7225b954c

```bash
python review_server.py --video-id {VIDEO_ID}
```

### 步驟 7 — 引導人工審核

告知用戶 review.html 的兩個區塊：

**上半部 — 截圖分類審核**
> 「請切換到『中信心』和『低信心』分頁，確認截圖分類是否正確。
>  若有分錯，點選截圖後選正確分類或按『排除』，完成後按『套用修正』。」

**下半部 — Symbol 符號審核（重要，請提醒用戶捲到最下方）**
> 「請捲到頁面最下方的『Symbol 審核』區塊：
>  1. 確認自動提取的遊戲符號圖示是否完整
>  2. 若有遺漏，點選 Help 截圖縮圖，拖曳框選缺少的符號
>  3. 輸入符號名稱（選填）→ 按『加入為 Symbol』，圖示會直接存到 symbol_table/symbols/」

**主動判斷**：若 symbol 數量少於 5 個或有明顯重複，主動說明可能原因並建議補切。

### 步驟 8 — 確認審核完成，生成競品報告

主動詢問：
> 「請確認以下兩項都完成後告訴我：
> 1. ✅ 截圖審核已套用（中低信心截圖都確認過）
> 2. ✅ Symbol 審核已確認（符號清單完整）
>
> 完成後我會立刻幫你生成競品分析報告。」

**收到確認後**，依以下優先順序生成報告：

**若有 slot-report skill：**
```
# 使用 slot-report skill
輸入：project/output/{VIDEO_ID}/
輸出：project/output/{VIDEO_ID}/report.html
```

**若沒有 slot-report skill（讀取 CSV + 截圖直接產出）：**

```bash
python -c "
import csv
with open('project/output/{VIDEO_ID}/classification_result.csv') as f:
    rows = list(csv.DictReader(f))
    cats = {}
    for r in rows:
        cats[r['final_category']] = cats.get(r['final_category'], 0) + 1
    print(cats)
"
```

讀取 CSV、Help 截圖與 symbol 圖示後，直接在對話中生成結構化的競品分析報告（HTML 格式），
儲存到 `project/output/{VIDEO_ID}/report.html`。

生成完成後，主動列出需人工核對的欄位：
> - **開發商**：從畫面 Logo 推測，請確認
> - **格局（Grid）**：從截圖目測，請確認格柱數
> - **最高倍率**：從 Free Spins 畫面讀取，請對照 Help 頁
> - **賠率數字**：OCR 讀取，可能有誤讀
> - **Wild 規則**：從 Help 文字推斷，請確認觸發條件

### 步驟 9 — 人工審閱報告，完成後備份到 fileserver

告知用戶：
> 「報告已生成！請用以下方式審閱與修改：
>
> **審閱 + 換圖（需 Server）：**
> 1. 啟動 Server：`.\.venv\Scripts\python.exe review_server.py --video-id {VIDEO_ID}`
> 2. 開啟 `http://localhost:8765/report`
> 3. 點「✏️ 編輯模式」可替換任何圖片（換圖自動寫回磁碟）
> 4. 點「✅ 完成編輯」自動儲存 report.html
>
> **純瀏覽（無需 Server）：**
> → 直接開啟 `project/output/{VIDEO_ID}/report.html`
>
> 確認報告內容正確後，告訴我，我會幫你備份到 fileserver。」

**收到用戶確認報告已完成後**，執行備份：

```powershell
cd "C:\Users\ashleyli\Documents\slot-classifier"
powershell -ExecutionPolicy Bypass -File archive_to_fileserver.ps1 -VideoId {VIDEO_ID}
```

備份完成後告知用戶：
> 「✅ 已備份到 fileserver！包含 report.html、tags.json、assets.json 及所有截圖與符號圖片。」

---

## 核心指令速查

| 指令 | 說明 |
|------|------|
| `python setup.py` | 一鍵安裝環境（首次） |
| `bash classify_with_roi_confirm.sh --video-id WildTrain` | 完整分類流程（含 ROI 確認） |
| `bash run_classify_roi.sh --video-id WildTrain --roi x,y,w,h` | 直接指定 ROI 跑分類 |
| `python app/generate_review_page.py project/output/WildTrain` | 單獨生成審核頁 |
| `python review_server.py --video-id WildTrain` | 手動啟動審核 Server |

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
├── review.html                # 審核頁（含 Symbol Review）
└── symbol_table/
    ├── symbols/               # 最終 symbol PNG
    └── icon_candidates/       # 候選池（除錯用）
```

---

## 效能說明

- **FRAME_INTERVAL = 20**：每 20 幀取一張（~4 分鐘影片約 325 幀）
- **OCR 輸入限 480px**：自動縮圖，box 座標自動還原
- **cpu_threads = 2**：限制 PaddleOCR 核心佔用，避免主機過載

如需調整取樣密度，修改 `app/constants.py` 的 `FRAME_INTERVAL`。

---

## 禁止操作

- 禁止直接修改 `project/output/` 內已分類的截圖（會破壞 CSV 索引）
- 禁止在分類進行中刪除輸出目錄

---

## Windows 踩坑紀錄

### 1. 不要用 bash 腳本（`classify_with_roi_confirm.sh`）

bash 腳本在 Windows 有兩個致命問題，**一律改用 PowerShell 直接呼叫 Python**：

| 問題 | 症狀 | 原因 |
|------|------|------|
| `.venv/bin/python` 不存在 | exit code 127 | Windows venv 路徑是 `.venv\Scripts\python.exe`，bash 腳本寫死 Linux 路徑 |
| Git Bash 路徑轉換 crash | `fatal error - add_item failed` / exit code 5 | Git Bash 把 Windows 路徑轉 Unix 時若含特殊字元或空格會崩潰 |

**Windows 正確指令：**
```powershell
# ROI 偵測
cd "C:\Users\ashleyli\Documents\slot-classifier"
.\.venv\Scripts\python.exe app\generate_roi_preview.py --video-id {VIDEO_ID}

# 執行分類
.\.venv\Scripts\python.exe run_classify_roi.py --video-id {VIDEO_ID} --roi {x,y,w,h}

# 生成審核頁
.\.venv\Scripts\python.exe app\generate_review_page.py project\output\{VIDEO_ID}
```

### 2. Video ID 不能含空格或特殊字元

影片名稱如 `Pinata Wins.mp4` → video-id 必須改為 `PinataWins`。

流程：
1. 影片可以放在任何地方，**複製**一份到 `project\input_videos\`
2. 複製時用無空格的 CamelCase 命名：`PinataWins.mp4`
3. video-id 對應無空格的檔名（不含副檔名）：`--video-id PinataWins`

**命名規則：**
- ✅ `PinataWins`、`SugarKaboom`、`WildTrain`
- ❌ `Pinata Wins`（空格）、`Sugar-Kaboom`（連字符可能引發問題）

### 3. 除錯步驟

遇到 PowerShell 背景任務失敗時，**先看完整 output 內容**：

| exit code | 意義 | 排查方向 |
|-----------|------|----------|
| 127 | 指令找不到 | 確認 python 路徑是否正確（`Scripts` vs `bin`） |
| 1 | 腳本邏輯錯誤 | 看 stderr 訊息，通常有明確說明 |
| 5 | Git Bash 路徑崩潰 | 改用 PowerShell，或確認 video-id 不含空格 |
