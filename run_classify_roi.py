"""
run_classify_roi.py — 帶手動 ROI 覆蓋的分類入口
用法（透過 run_classify_roi.sh 呼叫）：
    python run_classify_roi.py --video-id FortuneMahjong --roi 624,72,660,960
"""
import argparse
import os
import sys

# ── 解析參數 ──────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Slot classifier with manual ROI override.")
parser.add_argument("--video-id", default=None, metavar="ID",
                    help="只跑指定影片（e.g. FortuneMahjong）")
parser.add_argument("--roi", default=None, metavar="x,y,w,h",
                    help="手動 ROI，格式：x,y,w,h（原始像素）。指定後停用 auto-detect。")
parser.add_argument("--skip-symbols", action="store_true")
parser.add_argument("--symbol-debug", action="store_true")
args = parser.parse_args()

# ── 在 import pipeline 之前 patch config ─────────────────────
SKILLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SKILLS_DIR, "app"))

import config  # noqa: E402

if args.roi:
    try:
        parts = [int(v.strip()) for v in args.roi.split(",")]
        if len(parts) != 4:
            raise ValueError("需要 4 個數字")
        rx, ry, rw, rh = parts
        # 停用 auto-detect，直接使用手動值
        config.AUTO_DETECT_ROI = False
        config.DEFAULT_ROI_X = rx
        config.DEFAULT_ROI_Y = ry
        config.DEFAULT_ROI_W = rw
        config.DEFAULT_ROI_H = rh
        print(f"[Manual ROI] x={rx}, y={ry}, w={rw}, h={rh}  (auto-detect 已停用)")
    except Exception as e:
        print(f"[錯誤] --roi 格式錯誤：{e}，應為 x,y,w,h（整數）")
        sys.exit(1)
else:
    print("[ROI] 未指定 --roi，使用 auto-detect")

# ── 正式執行 ────────────────────────────────────────────────
from pipeline import run_classifier  # noqa: E402
from config import INPUT_DIR, OUTPUT_DIR  # noqa: E402
from video_io import get_video_list  # noqa: E402

video_list = get_video_list()
if not video_list:
    print(f"找不到影片，請放入：{INPUT_DIR}")
    sys.exit(1)

if args.video_id:
    target = args.video_id.strip()
    video_list = [
        p for p in video_list
        if os.path.splitext(os.path.basename(p))[0] == target
    ]
    if not video_list:
        print(f"找不到影片 id='{target}'（目錄：{INPUT_DIR}）")
        sys.exit(1)

run_classifier(
    video_paths=video_list,
    output_root=OUTPUT_DIR,
    skip_symbols=args.skip_symbols,
    symbol_debug=args.symbol_debug,
)
