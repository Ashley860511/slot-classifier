#!/bin/bash
# ============================================================
# classify_with_roi_confirm.sh — 完整分類流程（含 ROI 人工確認）
#
# 用法：
#   ./classify_with_roi_confirm.sh --video-id WildTrain
#   ./classify_with_roi_confirm.sh --video-id WildTrain --roi 400,50,520,900
#
# 步驟：
#   1. 若未指定 --roi：跑 auto ROI 偵測 → 生成瀏覽器預覽頁
#      → 印出確認提示，等用戶回覆座標後中斷
#   2. 若已指定 --roi：直接跑分類（跳過確認）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
ROI_PREVIEW_SCRIPT="$SCRIPT_DIR/app/generate_roi_preview.py"

VIDEO_ID=""
ROI=""

# 解析參數
while [[ $# -gt 0 ]]; do
    case "$1" in
        --video-id) VIDEO_ID="$2"; shift 2 ;;
        --roi)      ROI="$2";      shift 2 ;;
        *) echo "未知參數：$1"; exit 1 ;;
    esac
done

if [ -z "$VIDEO_ID" ]; then
    echo "[錯誤] 請指定 --video-id，例如：--video-id WildTrain"
    exit 1
fi

echo "========================================"
echo " Slot Classifier — $VIDEO_ID"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

# ── 步驟 1：ROI 確認（若未手動指定）──────────────────────────
if [ -z "$ROI" ]; then
    echo ""
    echo "► 步驟 1/2：偵測 Auto ROI..."
    echo ""

    ROI_RESULT=$("$VENV_PYTHON" "$SCRIPT_DIR/app/generate_roi_preview.py" \
        --video-id "$VIDEO_ID" 2>&1)

    echo "$ROI_RESULT"

    # generate_roi_preview.py 成功時最後一行輸出：ROI=x,y,w,h
    DETECTED_ROI=$(echo "$ROI_RESULT" | grep "^ROI=" | tail -1 | sed 's/ROI=//')

    if [ -n "$DETECTED_ROI" ]; then
        echo ""
        echo "┌─────────────────────────────────────────────────────┐"
        echo "│  ⚠️  請先確認 ROI 邊框再繼續分類                    │"
        echo "│                                                     │"
        echo "│  Auto 偵測結果：$DETECTED_ROI"
        echo "│                                                     │"
        echo "│  1. 開瀏覽器查看預覽頁（網址見上方輸出）            │"
        echo "│  2. 若 ROI 需要調整，拖曳邊框後複製新座標           │"
        echo "│  3. 在 chat 回覆：                                   │"
        echo "│     「ROI 確認：x,y,w,h」                           │"
        echo "│     或：「ROI OK」（使用 auto 偵測值）               │"
        echo "└─────────────────────────────────────────────────────┘"
        echo ""
        echo "WAITING_ROI_CONFIRM:$DETECTED_ROI"
        # 結束此腳本 — Claude 讀到 WAITING_ROI_CONFIRM 後等用戶回覆
        exit 0
    else
        echo "[警告] Auto ROI 偵測失敗，將使用 config.py 的 fallback ROI"
    fi
fi

# ── 步驟 2：執行分類 ──────────────────────────────────────────
echo ""
echo "► 步驟 2/2：開始分類..."
echo ""

if [ -n "$ROI" ]; then
    "$VENV_PYTHON" "$SCRIPT_DIR/run_classify_roi.py" \
        --video-id "$VIDEO_ID" --roi "$ROI"
else
    "$VENV_PYTHON" "$SCRIPT_DIR/app/main.py" --video-id "$VIDEO_ID"
fi

EXIT_CODE=$?

# ── 分類後生成審核頁 ─────────────────────────────────────────
if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "► 生成審核頁面..."
    OUTPUT_DIR="$SCRIPT_DIR/project/output/$VIDEO_ID"
    if [ -d "$OUTPUT_DIR" ]; then
        "$VENV_PYTHON" "$SCRIPT_DIR/app/generate_review_page.py" "$OUTPUT_DIR" 2>/dev/null || true
        echo "✅ 完成：$OUTPUT_DIR/review.html"
    fi
fi

exit $EXIT_CODE
