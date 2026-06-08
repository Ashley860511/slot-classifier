#!/bin/bash
# ============================================================
# run_classify_roi.sh — 帶手動 ROI 的分類腳本
# 用法：
#   ./run_classify_roi.sh --video-id FortuneMahjong --roi 624,72,660,960
#
# --roi x,y,w,h  指定手動 ROI（停用 auto-detect）
#                x, y = 左上角座標；w, h = 寬高（原始像素）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[錯誤] 找不到 .venv"
    exit 1
fi

echo "========================================"
echo " Slot Classifier (Manual ROI)"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

# 把所有參數傳給 Python wrapper
"$VENV_PYTHON" "$SCRIPT_DIR/run_classify_roi.py" "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "========================================"
    echo " 生成審核頁面..."
    echo "========================================"
    OUTPUT_ROOT="$SCRIPT_DIR/project/output"
    REVIEW_GEN="$SCRIPT_DIR/app/generate_review_page.py"
    if [ -d "$OUTPUT_ROOT" ] && [ -f "$REVIEW_GEN" ]; then
        for video_dir in "$OUTPUT_ROOT"/*/; do
            if [ -f "$video_dir/classification_result.csv" ]; then
                echo "  → $(basename "$video_dir")"
                "$VENV_PYTHON" "$REVIEW_GEN" "$video_dir" 2>/dev/null || true
            fi
        done
        echo "✅ 審核頁面已生成"
    fi
fi

exit $EXIT_CODE
