import os


# Portable package layout:
# package_root/
#   app/main.py
#   project/input_videos/
#   project/output/
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_DIR = os.path.join(BASE_DIR, "project")
INPUT_DIR = os.path.join(PROJECT_DIR, "input_videos")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")

# 若只想跑單支影片，填檔名；若想跑 input_videos 內所有 mp4，改成 None
SINGLE_VIDEO_NAME = None
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")
CATEGORIES = ["Basegame", "Feature game", "Feature Buy", "BigWin", "Transition", "Help", "loading", "Result", "Other"]

# ROI / 自動裁切設定
AUTO_DETECT_ROI = True

# 自動裁切失敗時使用的 fallback ROI
DEFAULT_ROI_X = 694
DEFAULT_ROI_Y = 0
DEFAULT_ROI_W = 532
DEFAULT_ROI_H = 1032

# 自動偵測用參數
AUTO_ROI_SAMPLE_COUNT = 40
AUTO_ROI_MOTION_THRESHOLD = 8
AUTO_ROI_MIN_AREA_RATIO = 0.08
AUTO_ROI_PADDING = 28
SAVE_ROI_DEBUG_IMAGE = True

# 如果偵測框過度貼近全畫面，代表網頁背景也在動，可以先關掉 AUTO_DETECT_ROI 或調高 threshold
MAX_ROI_AREA_RATIO = 0.92

# 手機直式 slot 常在網頁中央；背景也會動時，用高細節直式欄位把左右邊界收窄
AUTO_ROI_TIGHTEN_PORTRAIT_COLUMN = True
AUTO_ROI_COLUMN_PADDING = 8
AUTO_ROI_MAX_WIDTH_RATIO = 0.36
AUTO_ROI_MIN_WIDTH_RATIO = 0.18
AUTO_ROI_USE_MOTION_BBOX_FOR_PORTRAIT = True
AUTO_ROI_MOTION_X_PADDING = 10
AUTO_ROI_MOTION_Y_PADDING = 8
AUTO_ROI_TRIM_BROWSER_TOP = True
AUTO_ROI_BROWSER_TOP_RATIO = 0.07
AUTO_ROI_LANDSCAPE_MIN_WIDTH_RATIO = 0.42
AUTO_ROI_LANDSCAPE_MAX_WIDTH_RATIO = 0.62
AUTO_ROI_LANDSCAPE_MAX_HEIGHT_RATIO = 0.62
AUTO_ROI_LANDSCAPE_PADDING = 18
AUTO_ROI_NATIVE_PORTRAIT_ASPECT_MAX = 0.80
AUTO_ROI_NATIVE_PORTRAIT_MIN_WIDTH_RATIO = 0.98
AUTO_ROI_WEB_HELP_WIDE_RATIO = 0.72
AUTO_ROI_WEB_HELP_TALL_RATIO = 0.55
WEB_HELP_FULL_PAGE_CROP = True
WEB_HELP_FULL_PAGE_MIN_ASPECT = 1.25
