import argparse
import os
import cv2
import numpy as np
import shutil
import re
import ast
from collections import defaultdict
from pathlib import Path

try:
    from .config import (
        AUTO_DETECT_ROI,
        CATEGORIES,
        DEFAULT_ROI_H,
        DEFAULT_ROI_W,
        DEFAULT_ROI_X,
        DEFAULT_ROI_Y,
        INPUT_DIR,
        OUTPUT_DIR,
    )
except ImportError:
    from config import (
        AUTO_DETECT_ROI,
        CATEGORIES,
        DEFAULT_ROI_H,
        DEFAULT_ROI_W,
        DEFAULT_ROI_X,
        DEFAULT_ROI_Y,
        INPUT_DIR,
        OUTPUT_DIR,
    )

try:
    from .auto_roi import auto_detect_game_area, get_web_help_page_roi
except ImportError:
    from auto_roi import auto_detect_game_area, get_web_help_page_roi

try:
    from .ocr_utils import extract_ocr_items, get_ocr_result, init_ocr
except ImportError:
    from ocr_utils import extract_ocr_items, get_ocr_result, init_ocr

try:
    from .video_io import (
        append_csv_row,
        get_video_csv_path,
        get_video_list,
        get_video_output_dir,
        imread_image,
        imwrite_image,
        prepare_output_dirs,
        safe_short_name,
        write_csv_header,
    )
except ImportError:
    from video_io import (
        append_csv_row,
        get_video_csv_path,
        get_video_list,
        get_video_output_dir,
        imread_image,
        imwrite_image,
        prepare_output_dirs,
        safe_short_name,
        write_csv_header,
    )

# =========================
# 取樣 / 分類設定
# =========================
FRAME_INTERVAL = 15
DIFF_THRESHOLD = 15.0
FORCE_SAMPLE_INTERVAL_FRAMES = 120
HELP_DENSE_SAMPLE_AFTER_FRAMES = 260
TRANSITION_DENSE_SAMPLE_AFTER_FRAMES = 90
FEATURE_DENSE_SAMPLE_AFTER_FRAMES = 180
DENSE_SAMPLE_STEP = 10
SCORE_THRESHOLD = 0.6
OCR_LANG = "en"

# 模糊過濾：數值越高越嚴格。若有漏圖，先降到 35~45
ENABLE_BLUR_FILTER = True
BLUR_THRESHOLD = 45.0

# 爆光過濾：過濾大範圍亮色光效，避免特效遮住畫面時被拿去分類/取樣
ENABLE_OVEREXPOSURE_FILTER = True
OVEREXPOSURE_SCORE_THRESHOLD = 4.0

# 轉場殘影/雜訊過濾：過濾多層半透明文字與特效重疊的畫面，避免污染 Feature game 取樣
ENABLE_TRANSITION_NOISE_FILTER = True
TRANSITION_NOISE_SCORE_THRESHOLD = 3.4
NOISE_PROTECT_UI_MARGIN = 2.0

# 若最高分低於這個值，直接判定為 Basegame
MIN_CATEGORY_SCORE = 3

# 類別保留數量
TOP_K_DEFAULT = 10
TOP_K_SHORT_EVENTS = 3          # Transition / Result / loading
TOP_K_TRANSITION = 6
TOP_K_BIGWIN = 12
TOP_K_RESULT = 6
TOP_K_LOADING = 6
TOP_K_HELP = 160
TOP_K_FEATURE_BUY = 6
BIGWIN_EVENT_GAP_FRAMES = 600
TRANSITION_EVENT_GAP_FRAMES = 600
HELP_EVENT_GAP_FRAMES = 360
HELP_MAX_FINAL_PAGES = 32
HELP_DEDUP_JACCARD_THRESHOLD = 0.985
HELP_MIN_QUALITY_SCORE = 8.0
HELP_RULE_TEXT_MIN_QUALITY_SCORE = 2.5
HELP_RULE_TEXT_MIN_LINES = 6
HELP_RULE_TEXT_MIN_TOKENS = 22
HELP_RULE_TEXT_MIN_LONG_LINES = 3
HELP_PAYTABLE_KEEP_COUNT = 24
HELP_VISUAL_DEDUP_MAX_MAD = 0.006
HELP_VISUAL_DEDUP_MIN_HIST_CORR = 0.995
VISUAL_CLUSTER_CATEGORIES = ["Basegame", "Feature game", "BigWin"]
VISUAL_CLUSTER_COUNT = 3        # Basegame / Feature game 分 3 群
VISUAL_KEEP_PER_CLUSTER = 3     # 每群取 3 張，共 9 張
BIGWIN_VISUAL_CLUSTER_COUNT = 3
BIGWIN_VISUAL_KEEP_PER_CLUSTER = 4
BIGWIN_KEEP_MIN_SCORE = 10.0
BASEGAME_UI_MIN_SCORE = 2.5
DROP_LOW_SCORE_MAJORITY_CLUSTER_CATEGORIES = ["Feature game"]
LOW_SCORE_MAJORITY_CLUSTER_RATIO = 0.65
BASEGAME_KEEP_TOP_UI_RATIO = 0.45
BASEGAME_MIN_UI_SCORE_FOR_KEEP = 3.0
BASEGAME_FINAL_MAX_OBSTRUCTION_SCORE = 5.5
BASEGAME_FINAL_MAX_NOISE_SCORE = 4.6
BASEGAME_FINAL_MAX_EXPOSURE_SCORE = 3.6
FEATURE_UI_KEEP_TOP_RATIO = 0.70
FEATURE_UI_MIN_SCORE_FOR_KEEP = 3.5
FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP = 8.0
FEATURE_BOARD_OBSTRUCTION_THRESHOLD = 2.8
ENABLE_BOTTOM_UI_CLUSTER_REFINEMENT = True
BOTTOM_UI_CLUSTER_MIN_RECORDS = 8
BOTTOM_UI_CLUSTER_MIN_FEATURE_EVIDENCE = 2.0
BOTTOM_UI_CLUSTER_MIN_SEPARATION = 0.18
BOTTOM_UI_CLUSTER_LOW_FEATURE_COUNT = 2

CATEGORY_NAMES = ["loading", "Help", "Feature Buy", "BigWin", "Transition", "Feature game", "Result", "Basegame", "Other"]


# =========================
# 關鍵字權重設定
# =========================
CATEGORY_KEYWORDS = {
    "loading": {
        "loading resource": 8,
        "loading": 7,
        "please wait": 6,
        "wait": 1,
    },
    "BigWin": {
        "sensational": 8,
        "super mega win": 8,
        "super megawin": 8,
        "big win": 6,
        "bigwin": 6,
        "bis win": 6,
        "mega win": 5,
        "megawin": 5,
        "meca win": 5,
        "mega wi": 5,
        "super win": 5,
        "superwin": 5,
        "superi win": 5,
        "jumbo win": 5,
        "jumbowin": 5,
        "jumbown": 5,
        "jumbo loin": 5,
        "huge win": 5,
        "hugewin": 5,
        "massive win": 4,
        "massivewin": 4,
        "epic win": 4,
        "epicwin": 4,
        "amazing win": 3,
        "great win": 3,
        "awesome win": 3,
        "win big": 5,
        "winner": 1,
    },
    "Transition": {
        "congratulations": 8,
        "congradulations": 8,
        "you have won": 8,
        "start button": 12,
        "press start": 12,
        "tap to start": 12,
        "click to start": 12,
        "continue": 5,
        "confirm": 5,
        "next": 5,
        "skip": 5,
        "enter free game": 4,
        "begin": 3,
        "start": 2,
        "go": 1,
        "press": 1,
        "tap": 1,
        "click": 1,
    },
    "Feature game": {
        "remaining free spins": 18,
        "free spins remaining": 18,
        "remaining free spin": 18,
        "free spins left": 18,
        "free spin left": 18,
        "spin remaining": 14,
        "spins remaining": 14,
        "free spin mode": 10,
        "free spins intro": 8,
        "respin": 4,
        "extra spins": 4,
        "extra spin": 4,
        "free spins": 3,
        "free spin": 2,
        "freespins": 2,
        "freespin": 2,
        "bonus round": 3,
        "bonus game": 3,
        "free game": 3,
        "free games": 3,
        "feature activated": 2,
        "features activated": 2,
        "all features activated": 2,
        "all features are activated": 2,
        "super bonus": 3,
        "bonus": 1,
    },
    "Feature Buy": {
        "buy super free spins": 12,
        "buy free spins": 12,
        "buy super free spin": 12,
        "buy free spin": 12,
        "feature buy": 10,
        "buy feature": 10,
        "super feature buy": 10,
        "buy bonus": 8,
        "cost": 5,
        "bet": 3,
        "quantity": 4,
        "select start": 6,
        "current cost": 4,
        "current bet": 4,
        "cancel": 3,
        "buy": 3,
    },
    "Help": {
        "paytable": 12,
        "pay table": 12,
        "symbol payout values": 12,
        "symbol payout": 10,
        "payout values": 8,
        "game rules": 10,
        "rules": 6,
        "how to play": 8,
        "help": 6,
        "wild symbol": 6,
        "scatter symbol": 6,
        "during any spins": 6,
        "during any spin": 6,
        "reels": 3,
        "symbols": 3,
        "ways": 3,
        "occupy": 3,
        "payout": 3,
    },
    "Result": {
        "total win": 10,
        "you've won": 10,
        "youve won": 10,
        "you won": 10,
        "collect": 10,
        "reward": 3,
        "payout": 4,
        "congratulations": 4,
        "congrats": 4,
        "game over": 4,
        "lose": 2,
        "lost": 2,
        "no win": 4,
        "score": 2,
        "total": 1,
    },
    "Basegame": {}
}


LOADING_PHRASES = ["loading resource", "loading", "please wait"]
LOADING_COVER_VENDOR_TERMS = [
    "pg soft", "pgsoft", "pocket games soft", "rights reserved",
    "licensed", "license", "certified", "mga", "bmm", "testlabs",
]
LOADING_COVER_MARKETING_TERMS = [
    "featuring", "free spin", "free spins", "wild symbol", "wild symbols",
    "multiplier", "multipliers", "loading game", "downloading",
]
TRANSITION_COVER_TERMS = [
    "chance to play", "chances to play", "chance top lay", "chances top lay",
    "chance toplay", "chances toplay", "every ball",
    "randomly awards", "random awards", "start",
]

TRANSITION_ACTION_PHRASES = [
    "start button", "press start", "tap to start", "click to start",
    "continue", "confirm", "next", "skip", "enter free game",
]

FEATURE_INTRO_PHRASES = [
    "you have won", "free spins won",
    "feature activated", "features activated", "features are activated",
    "all features activated", "all features are activated",
    "bonus game", "bonus round", "free game", "free games",
    "free spins", "free spin", "transforms into", "is removed",
    "increase the total win multiplier", "total win multiplier", "win with",
]

FEATURE_INTRO_PATTERNS = [
    r"all\s*\d*\s*features?\s*(?:are\s*)?activated",
    r"\d+\s*features?\s*(?:are\s*)?activated",
    r"features?\s*(?:are\s*)?activated",
]

FEATURE_RUNNING_PHRASES = [
    "remaining free spins", "free spins remaining", "remaining free spin",
    "spin remaining", "spins remaining", "free spin mode",
    "remaining free", "remains until end of free", "free spin remaining",
    "free spins remain", "free spin remain", "free spins left", "free spin left",
    "retrigger", "respin",
]

FEATURE_ACTIVE_TERMS = [
    "remaining free spins", "free spins remaining", "last free spin",
    "round", "rounds", "chance", "chances", "current multiplier",
    "multiplier", "tap to shoot", "tap to pick", "pick", "choose",
    "reveal", "spin the wheel", "wheel", "hold and win", "respin",
    "bonus game", "feature win", "win:",
]

FEATURE_ACTIVE_INTERACTION_TERMS = [
    "tap to shoot", "tap to pick", "pick", "choose", "reveal",
    "shoot", "spin the wheel", "stop", "tap", "hold",
]

FEATURE_ACTIVE_INTRO_ONLY_TERMS = [
    "start", "continue", "confirm", "get started", "press start",
    "tap to start", "click to start",
]

FEATURE_SUBTYPE_TERMS = {
    "free_spins_reels": [
        "remaining free spins", "free spins remaining", "last free spin",
        "free spin mode", "free games", "free game",
    ],
    "wheel": [
        "wheel", "spin the wheel", "wheel bonus", "pointer", "segment",
        "sectors",
    ],
    "pick": [
        "pick", "choose", "reveal", "select", "mystery", "box",
        "chest", "card",
    ],
    "minigame": [
        "tap to shoot", "shoot", "goal", "ball", "football", "round",
        "rounds", "chance", "chances", "multiplier",
    ],
    "hold_and_win": [
        "hold and win", "hold", "respin", "cash on reels", "collect",
        "lock",
    ],
}

FEATURE_BUY_PHRASES = [
    "feature buy", "buy feature", "super feature buy", "buy bonus",
    "buy free spins", "buy free spin", "buy super free spins", "buy super free spin",
]

HELP_PHRASES = [
    "paytable", "pay table", "symbol payout values", "symbol payout",
    "payout values", "game rules", "how to play", "wild symbol",
    "scatter symbol", "during any spins", "during any spin",
]

RESULT_STRONG_PHRASES = [
    "total win", "you've won", "youve won", "you won", "collect", "game over",
]

BIGWIN_STRONG_PHRASES = [
    "sensational",
    "big win", "bigwin", "mega win", "megawin", "super mega win", "super megawin",
    "super win", "superwin", "superi win", "jumbo win", "jumbowin", "jumbown", "jumbo loin",
    "huge win", "hugewin", "massive win", "massivewin",
    "epic win", "epicwin", "mega wi", "meca win", "bis win",
]


# =========================
# 自動偵測遊戲區域
# =========================
def normalize_text(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    corrections = {
        "megawin": "mega win",
        "megawi": "mega win",
        "megawis": "mega win",
        "megawiy": "mega win",
        "megawilg": "mega win",
        "megawily": "mega win",
        "megawil": "mega win",
        "megawil}": "mega win",
        "megw": "mega",
        "mecawin": "mega win",
        "meca": "mega",
        "biswin": "big win",
        "bigwin": "big win",
        "superwin": "super win",
        "superiwin": "super win",
        "superi": "super",
        "jumbowin": "jumbo win",
        "jumbown": "jumbo win",
        "jumboloin": "jumbo win",
        "jumbo": "jumbo",
        "loin": "win",
        "congradulations": "congratulations",
        "congradulation": "congratulations",
        "hugewin": "huge win",
        "massivewin": "massive win",
        "epicwin": "epic win",
        "egawint": "mega win",
        "egawin": "mega win",
        "egawink": "mega win",
        "legawink": "mega win",
        "legawint": "mega win",
        "legawin": "mega win",
        "jegawin": "mega win",
        "auper": "super",
        "aupen": "super",
        "huper": "super",
        "nuper": "super",
        "guper": "super",
        "sunen": "super",
        "espins": "spins",
        "snin": "spin",
        "snind": "spin",
        "snins": "spins",
        "freesnins": "free spins",
        "freespinsd": "free spins",
        "tree": "free",
        "treesnin": "free spin",
        "treesnind": "free spin",
        "freespil": "free spin",
        "iofregspins": "10 free spins",
        "respi": "respin",
        "freespins": "free spins",
        "freespin": "free spin",
        "lastfreespins": "last free spins",
        "lastfreespin": "last free spin",
        "remainn": "remaining",
        "feafures": "features",
        "fransforms": "transforms",
        "info": "into",
        "stant": "start",
        "cotal": "total",
        "rotal": "total",
        "colal": "total",
        "x1o": "x10",
    }
    words = [corrections.get(word, word) for word in text.split()]
    text = " ".join(words)
    return text


def has_any(joined, phrases):
    compact_joined = joined.replace(" ", "")
    for phrase in phrases:
        normalized_phrase = normalize_text(phrase)
        if normalized_phrase in joined or normalized_phrase.replace(" ", "") in compact_joined:
            return True
    return False


def has_any_pattern(joined, patterns):
    return any(re.search(pattern, joined) for pattern in patterns)


def get_box_bounds(box):
    try:
        pts = np.array(box, dtype=float)
        xs = pts[:, 0]
        ys = pts[:, 1]
        return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def has_large_lower_start_button(ocr_items, roi_w, roi_h):
    for box, text, score in ocr_items:
        if score < SCORE_THRESHOLD:
            continue

        normalized = normalize_text(text)
        if "start" not in normalized:
            continue

        x1, y1, x2, y2 = get_box_bounds(box)
        w = max(0.0, x2 - x1)
        h = max(0.0, y2 - y1)
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        is_lower_half = cy >= roi_h * 0.50
        is_center_area = roi_w * 0.15 <= cx <= roi_w * 0.85
        is_large_text = h >= 28 or w >= 95

        if is_lower_half and is_center_area and is_large_text:
            return True

    return False


def has_large_result_layout(ocr_items, roi_w, roi_h):
    has_result_text = False
    has_total_word = False
    has_win_word = False
    has_large_number = False
    has_collect = False

    for box, text, score in ocr_items:
        if score < SCORE_THRESHOLD:
            continue

        normalized = normalize_text(text)
        x1, y1, x2, y2 = get_box_bounds(box)
        w = max(0.0, x2 - x1)
        h = max(0.0, y2 - y1)
        cy = (y1 + y2) / 2.0

        if has_any(normalized, ["total win", "youve won", "you won", "you ve won"]):
            if h >= roi_h * 0.045 or w >= roi_w * 0.30:
                has_result_text = True

        is_mid_overlay_text = (
            roi_w * 0.10 <= ((x1 + x2) / 2.0) <= roi_w * 0.90
            and roi_h * 0.16 <= cy <= roi_h * 0.70
            and (h >= roi_h * 0.038 or w >= roi_w * 0.16)
        )
        if is_mid_overlay_text and re.fullmatch(r"total", normalized):
            has_total_word = True
        if is_mid_overlay_text and re.fullmatch(r"win", normalized):
            has_win_word = True

        if "collect" in normalized:
            has_collect = True

        digit_count = sum(ch.isdigit() for ch in normalized)
        is_score_like = digit_count >= 3 and any(token in normalized for token in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"])
        is_large_center_number = (
            is_score_like
            and h >= roi_h * 0.07
            and w >= roi_w * 0.25
            and roi_h * 0.20 <= cy <= roi_h * 0.82
        )
        if is_large_center_number:
            has_large_number = True

    has_split_total_win = has_total_word and has_win_word
    return (
        ((has_result_text or has_split_total_win) and has_large_number)
        or (has_collect and (has_result_text or has_split_total_win or has_large_number))
    )


def has_collect_button_signal(ocr_items, roi_w, roi_h):
    for box, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue

        normalized = normalize_text(text)
        if not re.fullmatch(r"(collect|collec|colect)", normalized):
            continue

        x1, y1, x2, y2 = get_box_bounds(box)
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        if (
            (roi_w <= 0 or roi_w * 0.20 <= cx <= roi_w * 0.80)
            and (roi_h <= 0 or roi_h * 0.48 <= cy <= roi_h * 0.90)
            and (roi_w <= 0 or width >= roi_w * 0.14)
            and (roi_h <= 0 or height >= roi_h * 0.030)
        ):
            return True

    return False


def has_blocking_modal_signal(joined, ocr_items=None, roi_w=0, roi_h=0):
    modal_text = has_any(joined, [
        "official and genuine", "genuine pg games", "verify exclusively",
        "transaction id", "dont show this again", "don t show this again",
        "accept", "ignore", "verification",
        "auto spin", "number of auto spins", "auto spins",
    ])
    if not modal_text:
        return False

    large_center_texts = 0
    for box, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue
        normalized = normalize_text(text)
        if not has_any(normalized, [
            "official", "genuine", "verify", "accept", "ignore", "transaction",
            "auto spin", "auto spins", "number",
        ]):
            continue
        x1, y1, x2, y2 = get_box_bounds(box)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        if roi_w * 0.15 <= cx <= roi_w * 0.85 and roi_h * 0.18 <= cy <= roi_h * 0.82:
            large_center_texts += 1

    return large_center_texts >= 2


def has_brand_logo_splash_signal(img, ocr_items=None):
    if img is None or img.size == 0:
        return False

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return False

    text_items = [
        normalize_text(text)
        for _, text, score in (ocr_items or [])
        if score >= SCORE_THRESHOLD and normalize_text(text)
    ]
    joined = " ".join(text_items)
    compact = joined.replace(" ", "")
    if not text_items or len(text_items) > 5:
        return False

    if has_any(joined, [
        "balance", "total bets", "total bet", "ways", "free game", "free spin",
        "buy feature", "feature buy", "paytable", "symbol", "wild", "scatter",
        "loading", "please wait", "win", "bet", "auto", "turbo", "start",
    ]):
        return False

    explicit_brand_splash = has_any(joined, [
        "entertain beyond boundaries", "beyond boundaries",
    ]) or compact in {"fc", "fclogo"}

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    dark_or_plain_ratio = float(np.mean((val <= 70) | (sat <= 35)))
    edge_ratio = float(np.mean(cv2.Canny(gray, 60, 140) > 0))

    center = img[int(h * 0.24):int(h * 0.68), int(w * 0.12):int(w * 0.88)]
    if center.size == 0:
        return explicit_brand_splash and dark_or_plain_ratio >= 0.65

    center_hsv = cv2.cvtColor(center, cv2.COLOR_BGR2HSV)
    center_sat = center_hsv[:, :, 1]
    center_val = center_hsv[:, :, 2]
    logo_like_ratio = float(np.mean((center_val >= 150) | (center_sat >= 90)))

    return (
        explicit_brand_splash
        and dark_or_plain_ratio >= 0.65
        and logo_like_ratio >= 0.04
        and edge_ratio <= 0.09
    )


def get_basegame_ui_score(img, ocr_items=None):
    if img is None or img.size == 0:
        return 0.0, []

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0, []

    reasons = []
    score = 0.0
    lower = img[int(h * 0.64):h, :]
    lower_h = lower.shape[0]

    gray = cv2.cvtColor(lower, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(lower, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2]
    sat = hsv[:, :, 1]

    dark_ratio = float(np.mean(value < 95))
    if dark_ratio >= 0.16:
        score += 0.8
        reasons.append(f"dark_control_band:{dark_ratio:.2f}")

    edges = cv2.Canny(gray, 70, 160)
    edge_ratio = float(np.mean(edges > 0))
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if 0.035 <= edge_ratio <= 0.16:
        score += 0.5
        reasons.append(f"lower_ui_edges:{edge_ratio:.2f}")

    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(22, w // 8),
        param1=80,
        param2=18,
        minRadius=max(10, w // 38),
        maxRadius=max(18, w // 9),
    )
    circle_count = 0 if circles is None else len(np.round(circles[0]).astype(int))
    if circle_count >= 2:
        score += 1.3
        reasons.append(f"round_buttons:{circle_count}")
    elif circle_count == 1:
        score += 0.6
        reasons.append("round_button:1")

    center = lower[:, int(w * 0.32):int(w * 0.68)]
    if center.size > 0:
        center_gray = cv2.cvtColor(center, cv2.COLOR_BGR2GRAY)
        _, bright = cv2.threshold(center_gray, 145, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        large_center_blocks = 0
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area_ratio = (cw * ch) / float(max(1, center.shape[0] * center.shape[1]))
            if area_ratio >= 0.035 and ch >= lower_h * 0.14:
                large_center_blocks += 1
        if large_center_blocks > 0:
            score += 0.7
            reasons.append(f"spin_or_counter_block:{large_center_blocks}")

    lower_center = img[int(h * 0.55):h, int(w * 0.24):int(w * 0.76)]
    if lower_center.size > 0:
        lc_h, lc_w = lower_center.shape[:2]
        lc_hsv = cv2.cvtColor(lower_center, cv2.COLOR_BGR2HSV)
        lc_sat = lc_hsv[:, :, 1]
        lc_val = lc_hsv[:, :, 2]
        bright_sat = ((lc_sat >= 55) & (lc_val >= 125)).astype(np.uint8) * 255
        bright_sat = cv2.morphologyEx(
            bright_sat,
            cv2.MORPH_CLOSE,
            np.ones((5, 5), np.uint8),
            iterations=1,
        )
        contours, _ = cv2.findContours(bright_sat, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        partial_spin_blocks = 0
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area_ratio = (cw * ch) / float(max(1, lc_w * lc_h))
            cx = x + cw / 2.0
            touches_lower_half = y + ch >= lc_h * 0.52
            centered = lc_w * 0.24 <= cx <= lc_w * 0.76
            if centered and touches_lower_half and area_ratio >= 0.018 and cw >= lc_w * 0.10 and ch >= lc_h * 0.08:
                partial_spin_blocks += 1
        if partial_spin_blocks > 0:
            score += 1.2
            reasons.append(f"partial_center_spin:{partial_spin_blocks}")

    joined = " ".join(
        normalize_text(text)
        for _, text, ocr_score in (ocr_items or [])
        if ocr_score >= SCORE_THRESHOLD
    )
    if has_any(joined, ["turbo", "auto", "spin", "bet", "balance", "credit"]):
        score += 0.8
        reasons.append("ocr_control_words")

    control_word_count = 0
    for word in ["turbo", "auto", "spin", "bet", "balance", "credit"]:
        if word in joined:
            control_word_count += 1
    if control_word_count >= 2:
        score += 0.8
        reasons.append(f"multiple_control_words:{control_word_count}")

    if re.search(r"\bb\d+(?:\s?\d{2,3})*(?:\.\d+)?\b", joined) or re.search(r"\d+\.\d{2}", joined):
        score += 0.4
        reasons.append("money_or_bet_text")

    has_persistent_feature_buy_button = (
        has_any(joined, ["feature buy", "buy feature"])
        and not has_any(joined, ["cost", "quantity", "cancel", "select start", "click buy", "trigger the free"])
    )
    if has_persistent_feature_buy_button:
        score += 0.9
        reasons.append("persistent_feature_buy_button")

    symbol_strip = joined.replace(" ", "")
    has_bottom_controls = has_any(joined, ["turbo", "auto"]) and (
        re.search(r"\bb\d+(?:\s?\d{2,3})*(?:\.\d+)?\b", joined)
        or re.search(r"\d+\.\d{2}", joined)
    )
    if has_bottom_controls:
        score += 0.8
        reasons.append("bottom_controls_with_money")

    if ("+" in symbol_strip or "plus" in joined) and ("-" in symbol_strip or "minus" in joined):
        score += 0.4
        reasons.append("plus_minus_controls")

    return score, reasons


def get_feature_ui_score(img, ocr_items=None, roi_w=0, roi_h=0):
    if img is None or img.size == 0:
        return 0.0, []

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0, []

    if roi_w <= 0:
        roi_w = w
    if roi_h <= 0:
        roi_h = h

    reasons = []
    score = 0.0
    normalized_items = []

    for box, text, ocr_score in (ocr_items or []):
        if ocr_score < SCORE_THRESHOLD:
            continue

        normalized = normalize_text(text)
        if not normalized:
            continue

        x1, y1, x2, y2 = get_box_bounds(box)
        cy = (y1 + y2) / 2.0
        ch = max(0.0, y2 - y1)
        normalized_items.append((normalized, cy, ch))

    joined = " ".join(text for text, _, _ in normalized_items)

    if has_feature_running_signal(joined):
        score += 2.5
        reasons.append("feature_running_text")

    if has_any(joined, [
        "remaining free spins", "remaining free spin",
        "free spins remaining", "free spin remaining",
        "last free spins", "last free spin",
        "free spins left", "free spin left",
    ]):
        score += 2.5
        reasons.append("explicit_remaining_free_spin")

    if re.search(r"(remaining|remain|remains|last|left)\s+\d{1,3}\s*(free\s*)?spins?", joined):
        score += 1.2
        reasons.append("remaining_number_pattern")
    elif re.search(r"(free\s*)?spins?\s+\d{1,3}\s*(remaining|remain|remains|left)", joined):
        score += 1.2
        reasons.append("spin_number_remaining_pattern")

    lower_feature_terms = 0
    for text, cy, ch in normalized_items:
        is_lower_ui_area = cy >= roi_h * 0.48
        is_visible_text = ch >= roi_h * 0.018
        if is_lower_ui_area and is_visible_text and has_any(text, [
            "remaining", "remain", "remains", "last", "left", "free spin", "free spins"
        ]):
            lower_feature_terms += 1

    if lower_feature_terms >= 2:
        score += 2.0
        reasons.append(f"lower_feature_ui_terms:{lower_feature_terms}")
    elif lower_feature_terms == 1:
        score += 0.8
        reasons.append("lower_feature_ui_term:1")

    bottom = img[int(h * 0.72):h, :]
    if bottom.size > 0:
        hsv = cv2.cvtColor(bottom, cv2.COLOR_BGR2HSV)
        value = hsv[:, :, 2]
        dark_ratio = float(np.mean(value < 100))
        if dark_ratio >= 0.12:
            score += 0.4
            reasons.append(f"bottom_ui_band:{dark_ratio:.2f}")

    if re.search(r"\d+", joined) and has_any(joined, ["remaining", "last", "left"]):
        score += 0.5
        reasons.append("remaining_counter_digits")

    return score, reasons


def frame_diff_score(img1, img2):
    if img1 is None or img2 is None:
        return 0.0
    if img1.shape != img2.shape:
        return 0.0
    diff = cv2.absdiff(img1, img2)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    return float(np.mean(diff_gray))


def blur_score(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def overexposure_score(img):
    if img is None or img.size == 0:
        return 0.0, []

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0, []

    # 避開最上方瀏覽器/標題列與最下方金額列，集中看遊戲畫面被光效遮住的主區域。
    roi = img[int(h * 0.08):int(h * 0.82), int(w * 0.05):int(w * 0.95)]
    if roi.size == 0:
        return 0.0, []

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    bright_mask = val >= 222
    very_bright_mask = val >= 240
    neon_yellow_green_mask = (
        (hue >= 18) & (hue <= 70) &
        (sat >= 65) &
        (val >= 175)
    )
    flare_mask = bright_mask | neon_yellow_green_mask

    bright_ratio = float(np.mean(bright_mask))
    very_bright_ratio = float(np.mean(very_bright_mask))
    neon_ratio = float(np.mean(neon_yellow_green_mask))
    flare_ratio = float(np.mean(flare_mask))

    edges = cv2.Canny(gray, 70, 160)
    edge_ratio = float(np.mean(edges > 0))
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    largest_component_ratio = 0.0
    mask_u8 = flare_mask.astype(np.uint8)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    if component_count > 1:
        largest_component_ratio = float(stats[1:, cv2.CC_STAT_AREA].max()) / float(mask_u8.size)

    score = 0.0
    reasons = []
    low_detail = edge_ratio <= 0.045 or lap_var <= 260.0
    huge_washout = flare_ratio >= 0.56 or largest_component_ratio >= 0.32

    # Big Win / Result 往往也很亮，但只要還有明顯文字、數字、框線和物件細節，就不要用爆光規則誤殺。
    if not low_detail and not (flare_ratio >= 0.68 and largest_component_ratio >= 0.42):
        return 0.0, [
            f"kept_detail:edge={edge_ratio:.3f}",
            f"lap={lap_var:.0f}",
            f"flare={flare_ratio:.2f}",
        ]

    if bright_ratio >= 0.50:
        score += 0.9
        reasons.append(f"bright_area:{bright_ratio:.2f}")
    if very_bright_ratio >= 0.26:
        score += 0.8
        reasons.append(f"very_bright_area:{very_bright_ratio:.2f}")
    if neon_ratio >= 0.40:
        score += 1.2
        reasons.append(f"neon_yellow_green:{neon_ratio:.2f}")
    if flare_ratio >= 0.56:
        score += 0.8
        reasons.append(f"flare_area:{flare_ratio:.2f}")
    if largest_component_ratio >= 0.32:
        score += 1.3
        reasons.append(f"large_flare_blob:{largest_component_ratio:.2f}")
    if low_detail and huge_washout:
        score += 1.5
        reasons.append(f"low_detail_under_washout:edge={edge_ratio:.3f},lap={lap_var:.0f}")

    return score, reasons


def transition_noise_score(img):
    if img is None or img.size == 0:
        return 0.0, []

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0, []

    # 避開底部固定 UI，只看容易出現轉場殘影、半透明大字與特效堆疊的主畫面。
    roi = img[int(h * 0.08):int(h * 0.78), int(w * 0.06):int(w * 0.94)]
    if roi.size == 0:
        return 0.0, []

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    saturated_ratio = float(np.mean((sat >= 95) & (val >= 95)))
    yellow_green_flare_ratio = float(np.mean(
        (hue >= 15) & (hue <= 75) &
        (sat >= 70) &
        (val >= 130)
    ))
    bright_flare_ratio = float(np.mean((sat >= 45) & (val >= 205)))

    edges = cv2.Canny(gray, 45, 130)
    edge_ratio = float(np.mean(edges > 0))
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(np.std(gray))

    mixed_effect_mask = (
        ((hue >= 15) & (hue <= 75) & (sat >= 65) & (val >= 125)) |
        ((sat >= 95) & (val >= 170))
    )
    mixed_effect_ratio = float(np.mean(mixed_effect_mask))

    largest_component_ratio = 0.0
    mask_u8 = mixed_effect_mask.astype(np.uint8)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    if component_count > 1:
        largest_component_ratio = float(stats[1:, cv2.CC_STAT_AREA].max()) / float(mask_u8.size)

    score = 0.0
    reasons = []

    if yellow_green_flare_ratio >= 0.24:
        score += 1.0
        reasons.append(f"yellow_green_effect:{yellow_green_flare_ratio:.2f}")
    if saturated_ratio >= 0.42:
        score += 0.8
        reasons.append(f"high_saturation:{saturated_ratio:.2f}")
    if bright_flare_ratio >= 0.28:
        score += 0.6
        reasons.append(f"bright_effect:{bright_flare_ratio:.2f}")
    if mixed_effect_ratio >= 0.38:
        score += 0.8
        reasons.append(f"mixed_effect_area:{mixed_effect_ratio:.2f}")
    if largest_component_ratio >= 0.18:
        score += 0.6
        reasons.append(f"large_effect_blob:{largest_component_ratio:.2f}")
    if edge_ratio >= 0.085:
        score += 0.9
        reasons.append(f"dense_edges:{edge_ratio:.3f}")
    if lap_var >= 950.0:
        score += 0.5
        reasons.append(f"high_texture:{lap_var:.0f}")
    if contrast >= 58.0:
        score += 0.4
        reasons.append(f"high_contrast:{contrast:.1f}")

    if score >= 2.4 and edge_ratio >= 0.070 and mixed_effect_ratio >= 0.30:
        score += 0.7
        reasons.append("transition_overlay_combo")

    return score, reasons


def get_transition_keep_score(ocr_items, roi_w, roi_h, category_scores=None):
    filtered_texts = [
        normalize_text(text)
        for _, text, score in (ocr_items or [])
        if score >= SCORE_THRESHOLD
    ]
    joined = " ".join(filtered_texts)

    score = float((category_scores or {}).get("Transition", 0.0))
    reasons = []
    has_cover_text = has_transition_cover_text_signal(joined)

    if has_cover_text:
        score += 30.0
        reasons.append("transition_cover_text_priority")

    if has_any(joined, ["free spins", "free spin"]) and any(ch.isdigit() for ch in joined):
        score += 5.0
        reasons.append("free_spins_intro")

    if has_any(joined, ["multiplier increases", "after every win", "increase the total win multiplier", "win with"]):
        score += 4.0
        reasons.append("feature_rule_intro")

    if has_any(joined, ["start button", "press start", "tap to start", "click to start", "start"]) and not has_cover_text:
        score -= 4.0
        reasons.append("start_overlay_penalty")

    if has_large_lower_start_button(ocr_items or [], roi_w, roi_h) and not has_cover_text:
        score -= 5.0
        reasons.append("large_start_button_penalty")

    if has_any(joined, ["remaining free spins", "remaining free spin", "last free spin", "last free spins"]):
        score -= 4.0
        reasons.append("feature_running_ui_penalty")

    if has_any(joined, ["triggers", "trigger", "feature buy", "buy feature"]):
        score -= 5.0
        reasons.append("basegame_trigger_hint_penalty")

    basegame_ui_score = float((category_scores or {}).get("BasegameUI", 0.0))
    if basegame_ui_score >= BASEGAME_MIN_UI_SCORE_FOR_KEEP:
        score -= 1.5
        reasons.append("basegame_ui_overlay_penalty")
        if not has_cover_text and has_any(joined, ["buy feature", "feature buy", "turbo", "auto"]):
            score -= 12.0
            reasons.append("persistent_basegame_ui_penalty")

    return score, reasons


def basegame_keep_score(record):
    ui_score = float(record.get("basegame_ui_score", 0.0))
    blur = float(record.get("blur_score", 0.0))
    noise = float(record.get("noise_score", 0.0))
    top_score = float(record.get("top_score", 0.0))
    obstruction = float(record.get("feature_obstruction_score", 0.0))

    # blur_score 在這裡代表細節清晰度；過低常是滾輪動態模糊，過高通常是靜態清楚盤面。
    clear_score = min(3.0, blur / 900.0)
    noise_penalty = min(3.0, noise * 0.6)
    obstruction_penalty = min(8.0, obstruction * 1.4)

    score = ui_score * 2.0 + clear_score - noise_penalty - obstruction_penalty
    if top_score >= 8.0:
        score -= min(4.0, (top_score - 6.0) * 0.35)
    return score


def feature_keep_score(record):
    ui_score = float(record.get("feature_ui_score", 0.0))
    active_score = float(record.get("feature_active_score", 0.0))
    blur = float(record.get("blur_score", 0.0))
    noise = float(record.get("noise_score", 0.0))
    top_score = float(record.get("top_score", 0.0))
    obstruction = float(record.get("feature_obstruction_score", 0.0))
    help_quality = float(record.get("help_quality_score", 0.0))
    has_pp_counter = has_record_pp_free_spins_left(record)

    clear_score = min(2.5, blur / 1000.0)
    noise_penalty = min(3.0, noise * 0.55)
    if active_score >= FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP:
        obstruction_penalty = min(3.0, obstruction * 0.45)
    else:
        obstruction_penalty = min(8.0, obstruction * 1.8)
    score = (
        ui_score * 2.0
        + active_score * 1.6
        + clear_score
        - noise_penalty
        - obstruction_penalty
        + top_score * 0.05
    )
    if has_pp_counter:
        score += 28.0
    elif help_quality >= HELP_MIN_QUALITY_SCORE:
        score -= help_quality * 2.2
    return score


def bigwin_keep_score(record):
    keep_signal = float(record.get("bigwin_keep_score", 0.0))
    top_score = float(record.get("top_score", 0.0))
    noise = float(record.get("noise_score", 0.0))
    blur = float(record.get("blur_score", 0.0))
    score = keep_signal * 2.0 + top_score + min(3.0, blur / 1200.0) - min(4.0, noise * 0.45)
    if keep_signal >= BIGWIN_KEEP_MIN_SCORE:
        score += 20.0
    return score


BIGWIN_TIER_ORDER = [
    "big_win",
    "super_win",
    "mega_win",
    "super_mega_win",
    "jumbo_win",
    "huge_win",
    "massive_win",
    "epic_win",
]


def bigwin_tier_key_from_text(text):
    normalized = normalize_text(text)
    compact = normalized.replace(" ", "")

    has_win = "win" in compact or "wim" in compact or "wi" in compact
    if not has_win:
        return ""

    has_super = any(token in compact for token in ["super", "superi", "auper", "aupen", "huper"])
    has_mega = any(token in compact for token in [
        "mega", "me9a", "meca", "megawi", "megaw", "egawi", "legawi", "jegawi"
    ])

    if has_super and has_mega:
        return "super_mega_win"
    if "jumbo" in compact or "jumbol" in compact:
        return "jumbo_win"
    if has_mega:
        return "mega_win"
    if has_super:
        return "super_win"
    if "bigwin" in compact or "big" in compact or "biswin" in compact or "bis" in compact:
        return "big_win"
    if "huge" in compact:
        return "huge_win"
    if "massive" in compact:
        return "massive_win"
    if "epic" in compact:
        return "epic_win"
    return ""


def bigwin_tier_key(record):
    return bigwin_tier_key_from_text(record_text_joined(record))


def bigwin_tier_label(tier_key):
    return {
        "big_win": "Big Win",
        "super_win": "Super Win",
        "mega_win": "Mega Win",
        "super_mega_win": "Super Mega Win",
        "jumbo_win": "Jumbo Win",
        "huge_win": "Huge Win",
        "massive_win": "Massive Win",
        "epic_win": "Epic Win",
    }.get(tier_key, "Unlabeled BigWin")


def help_text_tokens(ocr_items):
    tokens = set()
    for _, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue
        normalized = normalize_text(text)
        if len(normalized) < 3:
            continue
        for token in normalized.split():
            if len(token) >= 3 and not token.isdigit():
                tokens.add(token)
    return tokens


def help_jaccard_similarity(record_a, record_b):
    tokens_a = record_a.get("help_tokens") or set()
    tokens_b = record_b.get("help_tokens") or set()
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / float(max(1, len(tokens_a | tokens_b)))


def help_visual_signature(rec):
    """Return a compact visual fingerprint for near-identical Help frames."""
    if "_help_visual_signature" in rec:
        return rec.get("_help_visual_signature")

    path = rec.get("save_path")
    if not path or not os.path.exists(path):
        rec["_help_visual_signature"] = None
        return None

    img = imread_image(path)
    if img is None or img.size == 0:
        rec["_help_visual_signature"] = None
        return None

    try:
        small = cv2.resize(img, (96, 96))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist(
            [hsv],
            [0, 1],
            None,
            [24, 16],
            [0, 180, 0, 256]
        )
        hist = cv2.normalize(hist, hist).flatten().astype(np.float32)
        sig = (gray.flatten(), hist)
    except Exception:
        sig = None

    rec["_help_visual_signature"] = sig
    return sig


def help_visual_similarity(record_a, record_b):
    sig_a = help_visual_signature(record_a)
    sig_b = help_visual_signature(record_b)
    if sig_a is None or sig_b is None:
        return 0.0

    gray_a, hist_a = sig_a
    gray_b, hist_b = sig_b
    try:
        mean_abs_diff = float(np.mean(np.abs(gray_a - gray_b)))
        hist_corr = float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL))
    except Exception:
        return 0.0

    if (
        mean_abs_diff <= HELP_VISUAL_DEDUP_MAX_MAD
        and hist_corr >= HELP_VISUAL_DEDUP_MIN_HIST_CORR
    ):
        return 1.0
    return 0.0


def is_duplicate_help_record(rec, kept_records):
    for kept in kept_records:
        if help_jaccard_similarity(rec, kept) >= HELP_DEDUP_JACCARD_THRESHOLD:
            return True
        if help_visual_similarity(rec, kept) >= 1.0:
            return True
    return False


def help_paytable_signal_score(ocr_items=None):
    paytable_title = False
    numeric_item_count = 0
    numeric_value_count = 0
    payout_pair_count = 0
    full_pay_count = 0
    symbol_table_terms = 0
    continuation_terms = 0
    has_paylines = False
    has_wild_or_scatter = False

    for _, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue
        normalized = normalize_text(text)
        if not normalized:
            continue

        if has_any(normalized, ["paytable", "pay table", "symbol payout values"]):
            paytable_title = True
        if re.fullmatch(r"\d{1,3}", normalized):
            numeric_item_count += 1
        numeric_value_count += len(re.findall(r"\b\d{1,4}(?:[,.]\d+)?\b", normalized))
        if re.search(r"\b\d{1,3}\s*-\s*\d{1,4}(?:[,.]\d+)?\b", str(text).lower()):
            payout_pair_count += 1
        if re.search(r"\bfull\b", normalized) and re.search(r"\b\d{1,4}(?:[,.]\d+)?\b", normalized):
            full_pay_count += 1
        if has_any(normalized, ["symbol", "wild", "scatter", "payout"]):
            symbol_table_terms += 1
        if has_any(normalized, ["wild", "scatter"]):
            has_wild_or_scatter = True
        if "paylines" in normalized or "pay lines" in normalized:
            has_paylines = True
        if has_any(normalized, [
            "some symbols", "symbol during payout", "wild symbol",
            "wilds on the way", "scatter symbol",
        ]):
            continuation_terms += 1

    # Paytable pages are often mostly images plus short numeric payout values.
    # PaddleOCR may read them as "Full 2000" or "3 - 120.00" rather than plain numbers.
    if paytable_title and (full_pay_count >= 3 or payout_pair_count >= 4):
        return 3.0
    if paytable_title and numeric_value_count >= 8 and symbol_table_terms >= 1:
        return 2.5
    if paytable_title and numeric_item_count >= 20 and symbol_table_terms >= 3:
        return 3.0
    if paytable_title and numeric_item_count >= 10 and symbol_table_terms >= 10:
        return 2.5
    if paytable_title and numeric_item_count >= 8 and (symbol_table_terms >= 2 or continuation_terms >= 2):
        return 2.0
    if paytable_title and continuation_terms >= 3:
        return 1.5
    if has_paylines and payout_pair_count >= 4 and has_wild_or_scatter:
        return 2.0
    if payout_pair_count >= 6 and (has_wild_or_scatter or symbol_table_terms >= 1):
        return 2.0
    return 0.0


def help_page_quality_score(img, ocr_items=None):
    if img is None or img.size == 0:
        return 0.0, []

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0, []

    roi = img[int(h * 0.06):int(h * 0.94), int(w * 0.06):int(w * 0.94)]
    if roi.size == 0:
        return 0.0, []

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    dark_plain_ratio = float(np.mean((val <= 100) & (sat <= 95)))
    dark_ratio = float(np.mean(val <= 105))
    bright_ratio = float(np.mean(val >= 205))
    colorful_ratio = float(np.mean((sat >= 105) & (val >= 115)))

    text_items = []
    long_lines = 0
    numeric_lines = 0
    numeric_item_count = 0
    paytable_title = False
    symbol_table_terms = 0
    rules_hits = 0
    for box, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue
        normalized = normalize_text(text)
        x1, y1, x2, y2 = get_box_bounds(box)
        cy = (y1 + y2) / 2.0
        if cy < h * 0.03 or cy > h * 0.97:
            continue

        if re.fullmatch(r"\d{1,3}", normalized):
            numeric_item_count += 1
        if has_any(normalized, [
            "paytable", "pay table", "symbol payout values",
            "symbols pay anywhere", "symbols pay",
        ]):
            paytable_title = True
        if has_any(normalized, ["symbol", "symbols pay", "wild", "scatter", "payout"]):
            symbol_table_terms += 1

        if len(normalized) < 3:
            continue
        text_items.append(normalized)
        if len(normalized) >= 14:
            long_lines += 1
        if re.search(r"\b\d+\b", normalized):
            numeric_lines += 1
        if has_any(normalized, [
            "paytable", "symbol", "symbols", "payout", "wild", "scatter",
            "during", "reels", "ways", "winning", "occupy", "feature",
            "free spins", "multipliers", "line", "bet",
        ]):
            rules_hits += 1

    text_count = len(text_items)
    score = 0.0
    reasons = []

    if dark_plain_ratio >= 0.42:
        score += 4.0
        reasons.append(f"dark_plain_bg:{dark_plain_ratio:.2f}")
    elif dark_ratio >= 0.48:
        score += 2.0
        reasons.append(f"dark_bg:{dark_ratio:.2f}")

    if text_count >= 12:
        score += min(4.0, text_count / 5.0)
        reasons.append(f"text_lines:{text_count}")
    elif text_count >= 7:
        score += 1.2
        reasons.append(f"some_text_lines:{text_count}")

    if long_lines >= 4:
        score += min(3.0, long_lines * 0.45)
        reasons.append(f"long_rule_lines:{long_lines}")
    if rules_hits >= 4:
        score += min(3.0, rules_hits * 0.4)
        reasons.append(f"rule_terms:{rules_hits}")
    if numeric_lines >= 4:
        score += 0.8
        reasons.append(f"numeric_rule_lines:{numeric_lines}")

    # Symbol paytable pages are image-heavy and full of short OCR numbers, so they
    # need a separate signal from long text rule pages.
    paytable_signal = help_paytable_signal_score(ocr_items)
    symbol_paytable = paytable_signal >= 2.0
    if paytable_signal >= 3.0:
        score += 7.0
        reasons.append(
            f"symbol_paytable_grid:numbers={numeric_item_count},terms={symbol_table_terms}"
        )
    elif paytable_signal >= 2.0:
        score += 4.5
        reasons.append(
            f"symbol_paytable_continuation:numbers={numeric_item_count},terms={symbol_table_terms}"
        )
    elif paytable_signal > 0:
        score += 2.0
        reasons.append("paytable_rule_continuation")

    if colorful_ratio >= 0.34 and text_count < 10 and not symbol_paytable:
        score -= 4.0
        reasons.append(f"colorful_game_area_penalty:{colorful_ratio:.2f}")
    elif colorful_ratio >= 0.46 and not symbol_paytable:
        score -= 2.0
        reasons.append(f"colorful_content_penalty:{colorful_ratio:.2f}")

    if bright_ratio >= 0.24 and dark_plain_ratio < 0.36:
        score -= 1.5
        reasons.append(f"bright_non_help_penalty:{bright_ratio:.2f}")

    return round(score, 2), reasons


def feature_board_obstruction_score(img):
    if img is None or img.size == 0:
        return 0.0, []

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0, []

    # Feature-game final samples should show the reels clearly. A large foreground
    # mascot, coin burst, or white flash in the reel area means the board is blocked.
    y1, y2 = int(h * 0.16), int(h * 0.64)
    x1, x2 = int(w * 0.07), int(w * 0.93)
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0, []

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    white_flash = (val >= 218) & (sat <= 120)
    bright_yellow = (hue >= 12) & (hue <= 42) & (sat >= 70) & (val >= 180)
    bright_pink = (hue >= 135) & (hue <= 174) & (sat >= 80) & (val >= 185)
    mask = (white_flash | bright_yellow | bright_pink).astype(np.uint8) * 255
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
    )
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    )

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    roi_area = float(max(1, roi.shape[0] * roi.shape[1]))
    central_area = 0.0
    max_component_ratio = 0.0
    wide_components = 0

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = float(cv2.contourArea(cnt))
        if area <= 0:
            continue
        cx = x + cw / 2.0
        cy = y + ch / 2.0
        central = (
            roi.shape[1] * 0.18 <= cx <= roi.shape[1] * 0.82
            and roi.shape[0] * 0.12 <= cy <= roi.shape[0] * 0.88
        )
        ratio = area / roi_area
        if central:
            central_area += area
            max_component_ratio = max(max_component_ratio, ratio)
        if central and cw >= roi.shape[1] * 0.28 and ch >= roi.shape[0] * 0.18:
            wide_components += 1

    central_ratio = central_area / roi_area
    score = 0.0
    reasons = []
    if max_component_ratio >= 0.08:
        score += min(4.0, max_component_ratio * 28.0)
        reasons.append(f"large_foreground_component:{max_component_ratio:.2f}")
    if central_ratio >= 0.16:
        score += min(3.0, central_ratio * 12.0)
        reasons.append(f"central_bright_cover:{central_ratio:.2f}")
    if wide_components >= 1:
        score += 2.0
        reasons.append(f"wide_reel_blocker:{wide_components}")

    return round(score, 2), reasons


def has_loading_strong_signal(joined):
    return has_any(joined, LOADING_PHRASES)


def has_transition_cover_text_signal(joined):
    compact = joined.replace(" ", "")
    if has_any(joined, TRANSITION_COVER_TERMS):
        return True
    if (
        has_any(joined, ["congratulations", "congrats", "you have won", "you won"])
        and has_any(joined, ["free spins", "free spin"])
        and re.search(r"\b\d{1,3}\b", joined)
    ):
        return True
    if re.search(r"(congratulations|youhavewon|youwon)\d{1,3}freespins?", compact):
        return True
    if re.search(r"\b\d+\s*chances?\s*to\s*play\b", joined):
        return True
    if re.search(r"\bchances?\s*to\s*play\b", joined):
        return True
    if "chancestoplay" in compact or "chancestopay" in compact:
        return True
    return False


def has_loading_cover_text_signal(joined):
    compact = joined.replace(" ", "")
    has_vendor_footer = has_any(joined, LOADING_COVER_VENDOR_TERMS) or any(
        term.replace(" ", "") in compact
        for term in LOADING_COVER_VENDOR_TERMS
    )
    if not has_vendor_footer:
        return False

    has_loading_text = has_loading_strong_signal(joined) or has_any(
        joined,
        ["loading game", "downloading", "download over", "download over wi fi"]
    )
    has_active_gameplay_text = (
        has_any(joined, ["tap to shoot", "tap to pick", "pick", "choose", "reveal"])
        or re.search(r"\bwin\s+\d", joined)
        or (
            has_any(joined, ["multiplier"])
            and re.search(r"\bx\s*\d+(?:[.,]\d+)?\b", joined)
        )
    )
    if not has_loading_text and has_active_gameplay_text:
        return False
    if not has_loading_text and has_transition_cover_text_signal(joined):
        return False

    has_cover_marketing = has_any(joined, LOADING_COVER_MARKETING_TERMS)
    has_rules_or_paytable = has_any(joined, [
        "paytable", "pay table", "payout values", "game rules", "how to play",
        "during any spin", "during any spins", "scatter symbol", "reels",
    ])

    return (has_loading_text or has_cover_marketing) and not has_rules_or_paytable


def has_loading_splash_signal(img, ocr_items=None):
    if img is None or img.size == 0:
        return False

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return False

    joined = " ".join(
        normalize_text(text)
        for _, text, score in (ocr_items or [])
        if score >= SCORE_THRESHOLD
    )
    if has_loading_cover_text_signal(joined):
        return True

    compact = joined.replace(" ", "")
    legal_or_vendor_terms = [
        "ver", "certified", "testlabs", "gaming", "institution", "regulations",
        "fair and just", "licensed", "license", "rights reserved", "pocket games soft",
        "pg soft", "omniplay", "omni play", "bmm", "mga", "ga ",
    ]
    has_legal_or_vendor = has_any(joined, legal_or_vendor_terms)
    if not has_legal_or_vendor:
        return False

    # Splash/loading pages usually have vendor/legal marks near the bottom and a
    # long horizontal progress bar, while real game screens have stronger UI words.
    has_real_game_ui = has_any(joined, [
        "balance", "total bets", "total bet", "buy feature", "feature buy",
        "remaining", "total win", "collect",
    ])
    cover_terms = [
        "get started", "win up to", "up to", "score a goal", "free games",
        "featuring", "licensed", "rights reserved",
    ]
    is_cover_like = has_any(joined, cover_terms)
    if has_real_game_ui and not is_cover_like:
        return False

    bottom_text_hits = 0
    game_title_hits = 0
    for box, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue
        normalized = normalize_text(text)
        x1, y1, x2, y2 = get_box_bounds(box)
        cy = (y1 + y2) / 2.0
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        if has_any(normalized, legal_or_vendor_terms + ["fair"]):
            if cy >= h * 0.72:
                bottom_text_hits += 1
        if (
            h * 0.05 <= cy <= h * 0.55
            and width >= w * 0.18
            and height >= h * 0.025
            and not has_any(normalized, ["balance", "total bets", "total bet"])
        ):
            game_title_hits += 1

    action_cover_button = False
    for box, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue
        normalized = normalize_text(text)
        if not has_any(normalized, ["get started", "start game", "play now"]):
            continue
        x1, y1, x2, y2 = get_box_bounds(box)
        cy = (y1 + y2) / 2.0
        width = max(0.0, x2 - x1)
        if cy >= h * 0.48 and width >= w * 0.18:
            action_cover_button = True
            bottom_text_hits += 1

    progress_roi = img[int(h * 0.66):int(h * 0.90), int(w * 0.08):int(w * 0.92)]
    if progress_roi.size == 0:
        return (
            bottom_text_hits >= 3 and ("ver" in compact or bottom_text_hits >= 5)
        ) or (is_cover_like and has_legal_or_vendor and (game_title_hits >= 1 or "getstarted" in compact))

    hsv = cv2.cvtColor(progress_roi, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    bar_mask = (
        (sat >= 45) &
        (val >= 120) &
        (
            ((hue >= 75) & (hue <= 105)) |
            ((hue >= 12) & (hue <= 38)) |
            ((hue >= 100) & (hue <= 135))
        )
    ).astype(np.uint8) * 255
    bar_mask = cv2.morphologyEx(
        bar_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (23, 5))
    )
    contours, _ = cv2.findContours(bar_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    long_bar = False
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw >= progress_roi.shape[1] * 0.40 and bh <= progress_roi.shape[0] * 0.35:
            long_bar = True
            break

    if long_bar:
        return True
    if bottom_text_hits >= 4 and ("ver" in compact or "certified" in compact):
        return True
    return is_cover_like and has_legal_or_vendor and (
        game_title_hits >= 1
        or action_cover_button
        or "getstarted" in compact
        or ("rightreserved" in compact or "rightsreserved" in compact)
    )


def has_feature_running_signal(joined):
    compact = joined.replace(" ", "")
    has_remaining_word = has_any(joined, ["remaining", "remains", "remain", "last", "left"])
    has_free_spin_word = has_any(joined, ["free spin", "free spins", "free game", "free games"])

    if has_remaining_word and has_free_spin_word:
        return True

    if re.search(r"(remaining|remains|remain|last|left)\s+\d*\s*(free\s*)?spins?", joined):
        return True
    if re.search(r"free\s+spins?\s+\d*\s*(?:remaining|remains|remain|last|left)", joined):
        return True
    if re.search(r"remains?\s+until\s+end\s+of\s+free", joined):
        return True
    if re.search(r"last\s+free\s+spins?", joined):
        return True
    if re.search(r"free\s+spins?\s+left", joined):
        return True
    if re.search(r"free\s*(game|games)\s*\d{1,3}\s*/\s*\d{1,3}", joined):
        return True
    if re.search(r"\d{1,3}\s*/\s*\d{1,3}\s*free\s*(game|games)", joined):
        return True
    if "remaining" in compact and "freespin" in compact:
        return True
    if "last" in compact and "freespin" in compact:
        return True
    if "left" in compact and "freespin" in compact:
        return True
    if re.search(r"free(game|games)\d{1,3}/\d{1,3}", compact):
        return True
    if re.search(r"free(game|games|spin|spins)\d{2,4}", compact):
        return True

    return False


def has_feature_intro_signal(joined):
    return has_any(joined, FEATURE_INTRO_PHRASES) or has_any_pattern(joined, FEATURE_INTRO_PATTERNS)


def feature_active_signal_score(joined, ocr_items=None, category_scores=None, help_quality_score=0.0):
    score = 0.0
    reasons = []
    compact = joined.replace(" ", "")

    if has_feature_running_signal(joined):
        score += 8.0
        reasons.append("free_spins_running")

    matched_terms = []
    for term in FEATURE_ACTIVE_TERMS:
        normalized = normalize_text(term)
        if normalized and normalized in joined:
            matched_terms.append(term)
    if matched_terms:
        term_score = min(10.0, len(set(matched_terms)) * 2.0)
        score += term_score
        reasons.append(f"active_terms:{'|'.join(sorted(set(matched_terms))[:6])}:{term_score:.1f}")

    interaction_terms = [
        term for term in FEATURE_ACTIVE_INTERACTION_TERMS
        if normalize_text(term) in joined
    ]
    if interaction_terms:
        score += min(6.0, len(set(interaction_terms)) * 2.5)
        reasons.append(f"interaction:{'|'.join(sorted(set(interaction_terms))[:4])}")

    if re.search(r"\b\d+\s*/\s*\d+\b", joined):
        score += 2.5
        reasons.append("counter_fraction")
    if re.search(r"\bx\s*\d+(?:[.,]\d+)?\b", joined) or re.search(r"\b\d+(?:[.,]\d+)?\s*x\b", joined):
        score += 2.5
        reasons.append("multiplier_value")
    if re.search(r"\bwin\s*[:：]\s*\d", joined):
        score += 3.0
        reasons.append("feature_win_value")
    if "tap" in compact and any(term in compact for term in ["shoot", "pick", "reveal"]):
        score += 3.0
        reasons.append("tap_action")

    help_score = float((category_scores or {}).get("Help", 0.0))
    loading_score = float((category_scores or {}).get("loading", 0.0))
    result_score = float((category_scores or {}).get("Result", 0.0))

    if has_help_signal(joined, ocr_items or [], 0, 0) or help_quality_score >= 6.0:
        penalty = 8.0 if help_quality_score >= 6.0 else 5.0
        score -= penalty
        reasons.append(f"help_page_penalty:{penalty:.1f}")
    if has_loading_strong_signal(joined) or has_loading_cover_text_signal(joined):
        score -= 8.0
        reasons.append("loading_penalty")
    if has_transition_cover_text_signal(joined):
        score -= 5.0
        reasons.append("intro_penalty")
    if result_score >= 12.0 and not has_any(joined, ["round", "chance", "tap", "multiplier"]):
        score -= 6.0
        reasons.append("result_penalty")
    if help_score >= 12.0:
        score -= 3.0
        reasons.append("help_score_penalty")
    if loading_score >= 12.0:
        score -= 3.0
        reasons.append("loading_score_penalty")

    return round(max(0.0, score), 2), reasons


def detect_feature_subtype(joined):
    subtype_scores = {}
    for subtype, terms in FEATURE_SUBTYPE_TERMS.items():
        score = 0
        for term in terms:
            normalized = normalize_text(term)
            if normalized and normalized in joined:
                score += 1
        subtype_scores[subtype] = score

    if not any(subtype_scores.values()):
        return "unknown_feature", subtype_scores

    subtype = max(subtype_scores, key=lambda key: subtype_scores[key])
    if subtype_scores[subtype] <= 0:
        subtype = "unknown_feature"
    return subtype, subtype_scores


def has_feature_buy_signal(joined, ocr_items=None, roi_w=0, roi_h=0):
    title_signal = has_any(joined, FEATURE_BUY_PHRASES)
    if not title_signal:
        return False

    purchase_detail = has_any(joined, [
        "cost", "current cost", "bet size", "bet level", "quantity",
        "select start", "click buy", "trigger the free game", "trigger the free spins",
        "amount", "buy a free game", "buy free game", "click buy to play",
        "with current cost", "buy free spins", "buy super free spins",
        "buy free spin", "buy super free spin",
    ])
    has_amount = bool(re.search(r"\b\d[\d,. ]{1,}\b", joined))

    action_words = set()
    has_large_modal_title = False
    has_center_buy_title = False
    has_center_free_spins_title = False
    for box, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue
        normalized = normalize_text(text)
        x1, y1, x2, y2 = get_box_bounds(box)
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        if has_any(normalized, FEATURE_BUY_PHRASES):
            is_centered = roi_w <= 0 or roi_w * 0.18 <= cx <= roi_w * 0.82
            is_modal_area = roi_h <= 0 or roi_h * 0.16 <= cy <= roi_h * 0.68
            is_large_title = (
                (roi_w <= 0 or width >= roi_w * 0.22)
                and (roi_h <= 0 or height >= roi_h * 0.030)
            )
            if is_centered and is_modal_area and is_large_title:
                has_large_modal_title = True

        is_centered_title_area = (
            (roi_w <= 0 or roi_w * 0.18 <= cx <= roi_w * 0.82)
            and (roi_h <= 0 or roi_h * 0.16 <= cy <= roi_h * 0.68)
            and (roi_w <= 0 or width >= roi_w * 0.10)
            and (roi_h <= 0 or height >= roi_h * 0.030)
        )
        if is_centered_title_area and re.fullmatch(r"buy", normalized):
            has_center_buy_title = True
        if is_centered_title_area and has_any(normalized, [
            "free spins", "free spin", "super free spins", "super free spin",
        ]):
            has_center_free_spins_title = True

        if not has_any(normalized, ["cancel", "start", "buy"]):
            continue
        if roi_h > 0 and cy < roi_h * 0.42:
            continue
        if "cancel" in normalized:
            action_words.add("cancel")
        if "start" in normalized:
            action_words.add("start")
        if re.search(r"\bbuy\b", normalized):
            action_words.add("buy")

    has_action_pair = len(action_words) >= 2
    has_split_modal_title = has_center_buy_title and has_center_free_spins_title
    has_purchase_flow = purchase_detail and (has_action_pair or has_amount)

    # Basegame often has a persistent "Feature Buy" button. Keep Feature Buy for
    # the purchase dialog itself: a modal title plus cost/quantity/action details.
    return has_purchase_flow and (has_large_modal_title or has_split_modal_title or has_action_pair)


def has_help_signal(joined, ocr_items=None, roi_w=0, roi_h=0):
    compact = joined.replace(" ", "")
    symbol_pay_only_over_game_ui = (
        ("symbolspayanywhere" in compact or "symbolspay" in compact)
        and has_any(joined, ["credit", "bet", "autoplay", "free spins left", "buy free spins"])
        and not has_any(joined, [
            "game rules", "paytable", "pay table", "symbol payout", "payout values",
            "wild symbol", "scatter symbol", "page",
        ])
    )
    if symbol_pay_only_over_game_ui:
        return False

    if has_any(joined, HELP_PHRASES):
        return True

    text_items = [
        normalize_text(text)
        for _, text, score in (ocr_items or [])
        if score >= SCORE_THRESHOLD and len(normalize_text(text)) >= 3
    ]
    if len(text_items) < 12:
        return False

    joined_items = " ".join(text_items)
    compact_items = joined_items.replace(" ", "")
    if (
        ("symbolspayanywhere" in compact_items or "symbolspay" in compact_items)
        and has_any(joined_items, ["credit", "bet", "autoplay", "free spins left"])
        and not has_any(joined_items, ["game rules", "paytable", "page", "wild symbol", "scatter symbol"])
    ):
        return False

    rules_terms = [
        "symbol", "symbols", "wild", "scatter", "payout", "paytable",
        "reels", "ways", "spins", "winning", "values", "occupy",
    ]
    term_hits = sum(1 for term in rules_terms if term in joined_items)
    numeric_lines = sum(1 for item in text_items if re.search(r"\b\d+\b", item))
    long_lines = sum(1 for item in text_items if len(item) >= 14)

    return term_hits >= 4 and (numeric_lines >= 5 or long_lines >= 5)


def is_rules_help_page_candidate(
    joined,
    ocr_items=None,
    help_quality_score=0.0,
    category_scores=None,
    help_paytable_score=0.0,
):
    text_items = [
        normalize_text(text)
        for _, text, score in (ocr_items or [])
        if score >= SCORE_THRESHOLD and len(normalize_text(text)) >= 3
    ]
    if len(text_items) < 8:
        return False

    joined_items = " ".join(text_items)
    if has_any(joined_items, HELP_PHRASES):
        return True

    rules_terms = [
        "paytable", "payout", "symbol", "symbols", "wild", "scatter", "paylines",
        "game feature", "feature buy", "jackpot", "reels", "ways", "substitute",
        "trigger", "multiplier", "free game", "free spins",
    ]
    term_hits = sum(1 for term in rules_terms if term in joined_items)
    long_lines = sum(1 for item in text_items if len(item) >= 16)
    numeric_lines = sum(1 for item in text_items if re.search(r"\b\d+(?:[,.]\d+)?\b", item))
    help_score = float((category_scores or {}).get("Help", 0.0))
    paytable_score = max(
        float(help_paytable_score or 0.0),
        float((category_scores or {}).get("HelpPaytable", 0.0)),
    )

    if paytable_score >= 2.0:
        return True
    if help_quality_score >= 6.0 and term_hits >= 2:
        return True
    if help_quality_score >= 3.0 and help_score >= 3.0 and term_hits >= 2:
        return True
    return term_hits >= 4 and (long_lines >= 5 or numeric_lines >= 5)


def has_explicit_basegame_control_signal(joined, basegame_ui_reasons=None):
    reasons = list(basegame_ui_reasons or [])
    compact = joined.replace(" ", "")

    def _reason_count(prefix):
        for reason in reasons:
            if not reason.startswith(prefix):
                continue
            m = re.search(r":(\d+)", reason)
            if m:
                return int(m.group(1))
            return 1
        return 0

    if has_any(joined, ["turbo", "auto spin", "auto", "spin button", "press spin"]):
        return True
    if "plus_minus_controls" in reasons or "bottom_controls_with_money" in reasons:
        return True
    if ("+" in compact or "plus" in joined) and ("-" in compact or "minus" in joined):
        return True

    # Some games show only a large spin/control button with money fields.
    has_center_control = any(
        reason.startswith("spin_or_counter_block") or reason.startswith("partial_center_spin")
        for reason in reasons
    )
    round_button_count = _reason_count("round_buttons")
    if has_center_control and round_button_count >= 3:
        return True

    has_money = "money_or_bet_text" in reasons or re.search(r"\d+\.\d{2}", joined)
    if has_center_control and has_money and has_any(joined, ["balance", "credit", "bet"]):
        return True
    if has_center_control and has_money and (
        "persistent_feature_buy_button" in reasons
        or any(reason.startswith("round_buttons") for reason in reasons)
    ):
        return True

    return False


def has_transition_strong_signal(joined, ocr_items=None, roi_w=0, roi_h=0):
    text_signal = has_any(joined, TRANSITION_ACTION_PHRASES) or (
        has_feature_intro_signal(joined) and not has_feature_running_signal(joined)
    )
    visual_text_signal = has_large_lower_start_button(ocr_items or [], roi_w, roi_h)
    return text_signal or visual_text_signal


def has_result_strong_signal(joined):
    if has_any(joined, ["total win multiplier", "increase the total win multiplier", "win multiplier"]):
        if not has_any(joined, ["collect", "you won", "youve won", "you ve won"]):
            return False
    return has_any(joined, RESULT_STRONG_PHRASES)


def has_inline_win_banner(ocr_items, roi_w, roi_h):
    for box, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue
        normalized = normalize_text(text)
        if has_any(normalized, ["total win", "collect", "you won", "youve won", "you ve won"]):
            continue
        if not re.search(r"\bwin\s+\d+(?:\s?\d{2,3})*(?:\.\d+)?\b", normalized):
            continue

        x1, y1, x2, y2 = get_box_bounds(box)
        cy = (y1 + y2) / 2.0
        width = max(0.0, x2 - x1)
        # 底部固定 WIN 欄位是 basegame UI；只把盤面/中下方橫幅式 win 訊息視為非 Basegame。
        if cy <= roi_h * 0.72 and width >= roi_w * 0.16:
            return True

    return False


def has_large_center_payout_text(ocr_items, roi_w, roi_h):
    for box, text, score in (ocr_items or []):
        if score < SCORE_THRESHOLD:
            continue

        normalized = normalize_text(text)
        compact = normalized.replace(" ", "")
        digit_count = sum(ch.isdigit() for ch in compact)
        if digit_count < 4:
            continue
        if not re.search(r"\d[\d,. ]{3,}", str(text)):
            continue

        x1, y1, x2, y2 = get_box_bounds(box)
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        is_center = roi_w * 0.12 <= cx <= roi_w * 0.88 and roi_h * 0.16 <= cy <= roi_h * 0.62
        is_large = width >= roi_w * 0.22 or height >= roi_h * 0.055
        is_not_bottom_ui = cy <= roi_h * 0.72
        if is_center and is_large and is_not_bottom_ui:
            return True

    return False


def has_large_center_payout_visual(img):
    if img is None or img.size == 0:
        return False

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return False

    # Big/result overlays often show one huge gold amount in the center over a darkened game.
    roi = img[int(h * 0.18):int(h * 0.62), int(w * 0.08):int(w * 0.92)]
    if roi.size == 0:
        return False

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    gold_mask = (
        (hue >= 10) & (hue <= 38) &
        (sat >= 70) &
        (val >= 135)
    ).astype(np.uint8) * 255
    gold_mask = cv2.morphologyEx(
        gold_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    )

    contours, _ = cv2.findContours(gold_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    large_gold_blocks = 0
    total_gold_area = 0
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cv2.contourArea(cnt)
        total_gold_area += area
        if cw >= roi.shape[1] * 0.18 and ch >= roi.shape[0] * 0.08 and area >= roi.size * 0.0008:
            large_gold_blocks += 1

    gold_ratio = total_gold_area / float(max(1, roi.shape[0] * roi.shape[1]))
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    dark_ratio = float(np.mean(gray < 85))

    if large_gold_blocks >= 2 and gold_ratio >= 0.014 and dark_ratio >= 0.12:
        return True

    # Fallback for red-outlined/gold-filled payout numbers where gold is split into many contours.
    red_mask = (
        ((hue <= 8) | (hue >= 170)) &
        (sat >= 70) &
        (val >= 90)
    ).astype(np.uint8) * 255
    payout_mask = cv2.bitwise_or(gold_mask, red_mask)
    payout_mask = cv2.morphologyEx(
        payout_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (15, 7))
    )
    contours, _ = cv2.findContours(payout_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    wide_blocks = 0
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw >= roi.shape[1] * 0.16 and ch >= roi.shape[0] * 0.06:
            wide_blocks += 1

    return wide_blocks >= 2 and dark_ratio >= 0.10


def has_bigwin_strong_signal(joined):
    if has_any(joined, BIGWIN_STRONG_PHRASES):
        return True

    compact = joined.replace(" ", "")
    if re.search(r"(big|mega|meca|super|superi|jumbo|jumbol|huge|massive|epic|egawi|legawi|jegawi|megawi)\w{0,6}(win|wim|wn)", compact):
        return True
    if re.search(r"jumbo\w{0,4}(win|wim|wn|loin)", compact):
        return True
    if (
        "megawi" in compact
        or "egawink" in compact
        or "legawint" in compact
        or "legawin" in compact
        or "jegawin" in compact
    ):
        return True

    return False


def has_pp_bigwin_title_signal(joined):
    compact = joined.replace(" ", "")
    if "sensational" in compact:
        return True
    if re.search(r"\bnice\b", joined) and re.search(r"\d", joined):
        return True
    return False


def has_jackpot_meter_signal(joined):
    if not has_any(joined, ["jackpot", "grand", "major", "minor", "mini"]):
        return False

    # Jackpot meters often show several huge amounts around the top of the game.
    # They are persistent basegame UI, not a win-result overlay.
    amount_hits = re.findall(r"\d[\d,. ]{2,}", joined)
    return len(amount_hits) >= 2


def get_bigwin_keep_signal_score(img, ocr_items, roi_w, roi_h, category_scores=None):
    filtered_texts = [
        normalize_text(text)
        for _, text, score in (ocr_items or [])
        if score >= SCORE_THRESHOLD
    ]
    joined = " ".join(filtered_texts)
    compact = joined.replace(" ", "")
    reasons = []

    strong_win_label = has_bigwin_strong_signal(joined)
    pp_win_label = has_pp_bigwin_title_signal(joined)
    total_win_label = has_any(joined, ["total win", "you won", "youve won", "you ve won"])
    jackpot_meter = has_jackpot_meter_signal(joined)
    result_layout = has_large_result_layout(ocr_items or [], roi_w, roi_h)
    large_amount_text = has_large_center_payout_text(ocr_items or [], roi_w, roi_h)
    large_amount_visual = has_large_center_payout_visual(img)
    strong_score = float((category_scores or {}).get("BigWin", 0.0)) >= 12.0
    has_large_amount = large_amount_text or large_amount_visual
    has_number_text = bool(re.search(r"\d[\d,. ]{2,}", joined))

    intro_or_running_feature = has_any(joined, [
        "free spins", "free spin", "feature buy", "start",
        "remaining free spin", "remaining free spins", "last free spin", "last free spins",
        "free spins won", "triggers", "trigger",
    ])
    only_small_win_banner = has_inline_win_banner(ocr_items or [], roi_w, roi_h) and not (
        strong_win_label or total_win_label
    )

    score = 0.0
    if (strong_win_label or pp_win_label) and has_large_amount:
        score = 14.0
        reasons.append("bigwin_label_with_large_amount")
    elif (strong_win_label or pp_win_label) and has_number_text:
        score = 12.0
        reasons.append("bigwin_label_with_number_text")
    elif total_win_label and result_layout and has_number_text:
        score = 11.0
        reasons.append("total_win_result_layout")
    elif strong_score and strong_win_label:
        score = 10.0
        reasons.append("bigwin_score_with_label")

    # 大型金色數字/光效本身不足以保留 BigWin，因為一般 Win 6.00、
    # freespins 開場與 feature 轉場也會長得很像。
    if jackpot_meter and not (strong_win_label or total_win_label):
        reasons.append("jackpot_meter_not_bigwin")
        score = min(score, 2.0)

    if has_large_amount and not (strong_win_label or total_win_label):
        reasons.append("large_amount_without_win_label")
        score = min(score, 4.0)

    if intro_or_running_feature and not (strong_win_label or total_win_label):
        reasons.append("feature_intro_not_bigwin")
        score = min(score, 3.0)

    if only_small_win_banner:
        reasons.append("small_inline_win_not_bigwin")
        score = min(score, 2.0)

    if re.search(r"(free|feature|start)", compact) and not re.search(r"(big|mega|huge|massive|epic|total).*win", compact):
        score = min(score, 6.0)

    return max(0.0, score), reasons


def add_score(category_scores, matched_keywords, category, amount, reason):
    category_scores[category] = round(category_scores.get(category, 0) + amount, 2)
    matched_keywords.setdefault(category, []).append(f"{reason}:{amount:+g}")


def apply_rule_bonuses(joined, ocr_items, category_scores, matched_keywords, roi_w, roi_h):
    has_digits = any(ch.isdigit() for ch in joined)

    if has_loading_strong_signal(joined):
        add_score(category_scores, matched_keywords, "loading", 10, "loading_strong")
        add_score(category_scores, matched_keywords, "Transition", -8, "loading_not_transition")
    elif has_loading_cover_text_signal(joined):
        add_score(category_scores, matched_keywords, "loading", 14, "loading_cover_text")
        add_score(category_scores, matched_keywords, "Help", -10, "loading_cover_not_help")
        add_score(category_scores, matched_keywords, "Transition", -6, "loading_cover_not_transition")

    if has_transition_cover_text_signal(joined) and not has_loading_strong_signal(joined):
        add_score(category_scores, matched_keywords, "Transition", 16, "transition_cover_text")
        add_score(category_scores, matched_keywords, "loading", -12, "transition_cover_not_loading")
        add_score(category_scores, matched_keywords, "Help", -8, "transition_cover_not_help")

    if has_help_signal(joined, ocr_items, roi_w, roi_h) and not has_loading_cover_text_signal(joined):
        add_score(category_scores, matched_keywords, "Help", 16, "help_strong")
        add_score(category_scores, matched_keywords, "Transition", -8, "help_not_transition")
        add_score(category_scores, matched_keywords, "Feature game", -6, "help_not_feature_game")

    if has_feature_buy_signal(joined, ocr_items, roi_w, roi_h):
        add_score(category_scores, matched_keywords, "Feature Buy", 16, "feature_buy_modal")
        add_score(category_scores, matched_keywords, "Transition", -6, "feature_buy_not_transition")
        add_score(category_scores, matched_keywords, "Basegame", -6, "feature_buy_not_basegame")

    if has_bigwin_strong_signal(joined):
        add_score(category_scores, matched_keywords, "BigWin", 12, "bigwin_strong")

    if has_result_strong_signal(joined):
        add_score(category_scores, matched_keywords, "Result", 8, "result_strong")

    if has_large_result_layout(ocr_items, roi_w, roi_h):
        add_score(category_scores, matched_keywords, "Result", 14, "large_result_layout")
        add_score(category_scores, matched_keywords, "Transition", -6, "result_not_transition")

    if has_any(joined, ["total win multiplier", "increase the total win multiplier", "win with"]) and not has_large_result_layout(ocr_items, roi_w, roi_h):
        add_score(category_scores, matched_keywords, "Transition", 12, "feature_intro_multiplier")
        add_score(category_scores, matched_keywords, "Result", -14, "multiplier_not_result")

    if has_feature_running_signal(joined):
        add_score(category_scores, matched_keywords, "Feature game", 10, "feature_running")

    if has_feature_intro_signal(joined) and not has_feature_running_signal(joined):
        add_score(category_scores, matched_keywords, "Transition", 14, "feature_intro_as_transition")
        add_score(category_scores, matched_keywords, "Feature game", -8, "intro_not_running_penalty")

    if has_any(joined, TRANSITION_ACTION_PHRASES):
        add_score(category_scores, matched_keywords, "Transition", 10, "transition_action")

    if has_large_lower_start_button(ocr_items, roi_w, roi_h) and not has_loading_strong_signal(joined):
        add_score(category_scores, matched_keywords, "Transition", 14, "large_lower_start_button")
        add_score(category_scores, matched_keywords, "Feature game", -6, "start_button_not_running_penalty")

    if "start" in joined and has_digits and not has_loading_strong_signal(joined):
        add_score(category_scores, matched_keywords, "Transition", 2, "start_digits")

    generic_feature_terms = has_any(joined, ["free spins", "free spin", "bonus", "activated", "features", "transforms into"])
    if generic_feature_terms and not has_feature_running_signal(joined):
        add_score(category_scores, matched_keywords, "Transition", 6, "feature_intro_terms")

    return category_scores, matched_keywords


def classify_text(ocr_items, roi_w, roi_h):
    filtered_texts = []
    raw_texts = []

    for _, text, score in ocr_items:
        raw_texts.append((text, score))
        if score >= SCORE_THRESHOLD:
            filtered_texts.append(normalize_text(text))

    joined = " ".join(filtered_texts)

    category_scores = {}
    matched_keywords = {}

    for category, kw_map in CATEGORY_KEYWORDS.items():
        if category == "Basegame":
            continue

        score_sum = 0
        matched_list = []

        for kw, weight in kw_map.items():
            if normalize_text(kw) in joined:
                score_sum += weight
                matched_list.append(f"{kw}:{weight}")

        score_sum += len(matched_list) * 0.5

        if category == "Result" and any(ch.isdigit() for ch in joined):
            score_sum += 1.5
            if matched_list:
                matched_list.append("result_digits:+1.5")

        category_scores[category] = round(score_sum, 2)
        matched_keywords[category] = matched_list

    category_scores, matched_keywords = apply_rule_bonuses(
        joined, ocr_items, category_scores, matched_keywords, roi_w, roi_h
    )

    feature_buy_is_modal = has_feature_buy_signal(joined, ocr_items, roi_w, roi_h)
    if not feature_buy_is_modal and category_scores.get("Feature Buy", 0.0) > 0:
        category_scores["Feature Buy"] = min(category_scores.get("Feature Buy", 0.0), 2.0)
        matched_keywords.setdefault("Feature Buy", []).append("feature_buy_button_only_clamped")

    loading_score = category_scores.get("loading", 0)
    transition_score = category_scores.get("Transition", 0)
    feature_score = category_scores.get("Feature game", 0)
    result_score = category_scores.get("Result", 0)
    bigwin_score = category_scores.get("BigWin", 0)
    help_score = category_scores.get("Help", 0)
    feature_buy_score = category_scores.get("Feature Buy", 0)

    final_category = None
    best_score = max(category_scores.values()) if category_scores else 0.0

    if has_loading_strong_signal(joined) and loading_score >= MIN_CATEGORY_SCORE:
        if result_score < loading_score + 4 and bigwin_score < loading_score + 4:
            final_category = "loading"
            best_score = loading_score
            matched_keywords["loading"].append("priority_loading")

    if final_category is None and has_help_signal(joined, ocr_items, roi_w, roi_h):
        if help_score >= MIN_CATEGORY_SCORE:
            final_category = "Help"
            best_score = help_score
            matched_keywords["Help"].append("priority_help")

    if final_category is None and feature_buy_is_modal:
        if feature_buy_score >= MIN_CATEGORY_SCORE:
            final_category = "Feature Buy"
            best_score = feature_buy_score
            matched_keywords["Feature Buy"].append("priority_feature_buy")

    if final_category is None and has_bigwin_strong_signal(joined):
        if bigwin_score >= MIN_CATEGORY_SCORE:
            final_category = "BigWin"
            best_score = bigwin_score
            matched_keywords["BigWin"].append("priority_bigwin")

    if final_category is None and has_feature_running_signal(joined):
        if feature_score >= MIN_CATEGORY_SCORE:
            final_category = "Feature game"
            best_score = feature_score
            matched_keywords["Feature game"].append("priority_feature_running")

    if final_category is None and (has_result_strong_signal(joined) or has_large_result_layout(ocr_items, roi_w, roi_h)):
        if result_score >= MIN_CATEGORY_SCORE and result_score > transition_score + 4:
            final_category = "Result"
            best_score = result_score
            matched_keywords["Result"].append("priority_result")

    if final_category is None and has_transition_strong_signal(joined, ocr_items, roi_w, roi_h):
        if transition_score >= MIN_CATEGORY_SCORE:
            final_category = "Transition"
            best_score = transition_score
            matched_keywords["Transition"].append("priority_transition")

    if final_category is None and (has_result_strong_signal(joined) or has_large_result_layout(ocr_items, roi_w, roi_h)):
        if result_score >= MIN_CATEGORY_SCORE:
            final_category = "Result"
            best_score = result_score
            matched_keywords["Result"].append("priority_result")

    if final_category is None:
        final_category = "Basegame"
        best_score = 0.0
        for category, score in category_scores.items():
            if score > best_score:
                best_score = score
                final_category = category

        if best_score < MIN_CATEGORY_SCORE:
            final_category = "Basegame"

    return final_category, category_scores, matched_keywords, raw_texts, best_score


def classify_frame(cropped, ocr_items, roi_w, roi_h):
    category, category_scores, matched_keywords, raw_texts, top_score = classify_text(ocr_items, roi_w, roi_h)

    basegame_ui_score, basegame_ui_reasons = get_basegame_ui_score(cropped, ocr_items)
    category_scores["BasegameUI"] = round(basegame_ui_score, 2)
    if basegame_ui_reasons:
        matched_keywords.setdefault("Basegame", []).extend(basegame_ui_reasons)

    feature_ui_score, feature_ui_reasons = get_feature_ui_score(cropped, ocr_items, roi_w, roi_h)
    category_scores["FeatureUI"] = round(feature_ui_score, 2)
    if feature_ui_reasons:
        matched_keywords.setdefault("Feature game", []).extend(feature_ui_reasons)

    help_paytable_score = help_paytable_signal_score(ocr_items)
    if help_paytable_score > 0:
        category_scores["HelpPaytable"] = round(help_paytable_score, 2)
        matched_keywords.setdefault("Help", []).append(f"paytable_signal:{help_paytable_score:.2f}")

    joined = " ".join(
        normalize_text(text)
        for _, text, ocr_score in (ocr_items or [])
        if ocr_score >= SCORE_THRESHOLD
    )
    has_basegame_ui = basegame_ui_score >= BASEGAME_UI_MIN_SCORE
    has_feature_ui = feature_ui_score >= FEATURE_UI_MIN_SCORE_FOR_KEEP
    has_real_result_layout = (
        has_large_result_layout(ocr_items, roi_w, roi_h)
        or has_collect_button_signal(ocr_items, roi_w, roi_h)
    )
    has_start_intro = has_large_lower_start_button(ocr_items, roi_w, roi_h) or has_any(joined, ["press start", "tap to start", "click to start"])
    has_feature_rule_intro = (
        has_any(joined, ["multiplier increases", "after every win", "increase the total win multiplier", "win with"])
        and has_any(joined, ["free spins", "free spin"])
    )
    has_feature_intro_text = has_feature_intro_signal(joined)
    has_basegame_trigger_hint = has_any(joined, ["triggers", "trigger", "feature buy"])
    has_jackpot_meter = has_jackpot_meter_signal(joined)
    has_bigwin_label = has_bigwin_strong_signal(joined)
    has_pp_bigwin_label = has_pp_bigwin_title_signal(joined)
    has_total_win_label = has_any(joined, ["total win", "you won", "youve won", "you ve won"])
    has_help_page = has_help_signal(joined, ocr_items, roi_w, roi_h)
    has_feature_buy_modal = has_feature_buy_signal(joined, ocr_items, roi_w, roi_h)
    has_rules_help_page = is_rules_help_page_candidate(
        joined,
        ocr_items,
        float(category_scores.get("HelpQuality", 0.0)),
        category_scores,
        help_paytable_score,
    ) and not has_feature_buy_modal
    has_loading_splash = has_loading_splash_signal(cropped, ocr_items)
    has_loading_cover_text = has_loading_cover_text_signal(joined)
    has_transition_cover_text = has_transition_cover_text_signal(joined)
    feature_active_score, feature_active_reasons = feature_active_signal_score(
        joined,
        ocr_items,
        category_scores,
        float(category_scores.get("HelpQuality", 0.0)),
    )
    feature_subtype, feature_subtype_scores = detect_feature_subtype(joined)
    category_scores["FeatureActive"] = round(feature_active_score, 2)
    matched_keywords.setdefault("Feature game", []).append(f"feature_subtype:{feature_subtype}")
    if feature_active_reasons:
        matched_keywords.setdefault("Feature game", []).extend(
            f"feature_active:{reason}" for reason in feature_active_reasons
        )
    has_brand_logo_splash = has_brand_logo_splash_signal(cropped, ocr_items)
    has_bigwin_overlay = (
        (has_bigwin_label or has_pp_bigwin_label)
        and (
            has_large_center_payout_text(ocr_items, roi_w, roi_h)
            or has_large_center_payout_visual(cropped)
            or has_feature_running_signal(joined)
        )
    )
    has_free_game_text = has_any(joined, [
        "free spins", "free spin", "last free spin", "last free spins",
        "remaining free spin", "remaining free spins", "free spins won",
    ])
    has_transition_action_text = has_any(joined, [
        "skip", "press", "continue", "confirm", "next", "accept", "ignore",
        "press start", "tap to start", "click to start",
        "congratulations", "you have won",
    ])
    result_or_transition_claim = category in ["Result", "Transition"]

    if has_blocking_modal_signal(joined, ocr_items, roi_w, roi_h):
        category = "Other"
        top_score = max(top_score, 6.0)
        category_scores["Other"] = max(category_scores.get("Other", 0.0), 6.0)
        matched_keywords.setdefault("Other", []).append("blocking_modal")

    if has_brand_logo_splash:
        category = "Other"
        top_score = max(top_score, 8.0)
        category_scores["Other"] = max(category_scores.get("Other", 0.0), 8.0)
        matched_keywords.setdefault("Other", []).append("brand_logo_splash")

    if (
        (has_loading_splash or has_loading_cover_text)
        and not has_transition_cover_text
        and not has_feature_buy_modal
        and not has_bigwin_overlay
    ):
        category = "loading"
        top_score = max(top_score, 12.0)
        category_scores["loading"] = max(category_scores.get("loading", 0.0), 12.0)
        matched_keywords.setdefault("loading", []).append(
            "loading_cover_text" if has_loading_cover_text else "loading_splash_visual"
        )

    if has_transition_cover_text and not has_loading_strong_signal(joined):
        category = "Transition"
        top_score = max(top_score, category_scores.get("Transition", 0.0), 16.0)
        category_scores["Transition"] = max(category_scores.get("Transition", 0.0), 16.0)
        matched_keywords.setdefault("Transition", []).append("priority_transition_cover_text")

    if (
        feature_active_score >= 8.0
        and not has_help_page
        and not has_rules_help_page
        and not has_loading_strong_signal(joined)
        and not has_loading_cover_text
        and not has_feature_buy_modal
        and not has_bigwin_overlay
    ):
        category = "Feature game"
        top_score = max(top_score, feature_active_score)
        category_scores["Feature game"] = max(category_scores.get("Feature game", 0.0), feature_active_score)
        matched_keywords.setdefault("Feature game", []).append("priority_feature_active")

    if has_bigwin_overlay:
        category = "BigWin"
        top_score = max(top_score, category_scores.get("BigWin", 0.0), 12.0)
        category_scores["BigWin"] = max(category_scores.get("BigWin", 0.0), 12.0)
        matched_keywords.setdefault("BigWin", []).append("priority_bigwin_overlay")

    if (has_help_page or has_rules_help_page) and not has_loading_cover_text:
        category = "Help"
        top_score = max(top_score, category_scores.get("Help", 0.0), 12.0)
        category_scores["Help"] = max(category_scores.get("Help", 0.0), 12.0)
        matched_keywords.setdefault("Help", []).append(
            "priority_help_page" if has_help_page else "priority_rules_help_page"
        )

    weak_help_over_game_ui = (
        category == "Help"
        and has_basegame_ui
        and not has_rules_help_page
        and help_paytable_score < 2.0
        and not has_any(joined, HELP_PHRASES)
    )
    if weak_help_over_game_ui:
        category = "Basegame"
        top_score = max(basegame_ui_score, category_scores.get("Basegame", 0.0))
        category_scores["Basegame"] = max(category_scores.get("Basegame", 0.0), basegame_ui_score)
        matched_keywords.setdefault("Basegame", []).append(
            f"basegame_ui_over_weak_help:{basegame_ui_score:.2f}"
        )

    if has_feature_buy_modal and category != "Help":
        category = "Feature Buy"
        top_score = max(top_score, category_scores.get("Feature Buy", 0.0), 12.0)
        category_scores["Feature Buy"] = max(category_scores.get("Feature Buy", 0.0), 12.0)
        matched_keywords.setdefault("Feature Buy", []).append("priority_feature_buy_modal")

    if result_or_transition_claim and (has_basegame_ui or has_feature_ui):
        if category == "Result" and not has_real_result_layout and not has_total_win_label:
            category = "Feature game" if has_feature_ui else "Basegame"
            top_score = max(top_score, feature_ui_score, basegame_ui_score)
            matched_keywords.setdefault(category, []).append(
                f"protected_ui_not_result:base={basegame_ui_score:.2f},feature={feature_ui_score:.2f}"
            )
        elif (
            category == "Transition"
            and not has_transition_cover_text
            and not has_start_intro
            and not has_feature_ui
            and not has_feature_rule_intro
            and not (has_feature_intro_text and not has_basegame_trigger_hint)
            and not has_free_game_text
            and not has_transition_action_text
        ):
            category = "Basegame"
            top_score = max(top_score, basegame_ui_score)
            matched_keywords.setdefault("Basegame", []).append(
                f"protected_basegame_ui_not_transition:{basegame_ui_score:.2f}"
            )
        elif category == "Transition" and (has_feature_rule_intro or (has_feature_intro_text and not has_basegame_trigger_hint)):
            matched_keywords.setdefault("Transition", []).append("protected_feature_rule_intro")

    if (
        category == "Transition"
        and has_basegame_ui
        and (has_feature_rule_intro or has_feature_intro_text)
        and not has_transition_cover_text
        and not has_start_intro
        and not has_feature_ui
        and has_any(joined, ["buy feature", "feature buy", "auto", "turbo"])
    ):
        category = "Basegame"
        top_score = max(top_score, basegame_ui_score)
        category_scores["Basegame"] = max(category_scores.get("Basegame", 0.0), basegame_ui_score)
        matched_keywords.setdefault("Basegame", []).append(
            f"feature_rule_overlay_on_basegame_not_transition:{basegame_ui_score:.2f}"
        )

    if (
        category in ["Help", "Feature Buy", "Result", "Transition"]
        and has_basegame_ui
        and not has_help_page
        and not has_feature_buy_modal
        and not has_real_result_layout
        and not has_transition_cover_text
        and not has_start_intro
        and not has_feature_ui
        and not has_feature_rule_intro
        and top_score <= basegame_ui_score + 1.5
    ):
        category = "Basegame"
        top_score = max(top_score, basegame_ui_score)
        matched_keywords.setdefault("Basegame", []).append(
            f"protected_basegame_ui_low_confidence:{basegame_ui_score:.2f}"
        )

    if category == "Basegame" and has_inline_win_banner(ocr_items, roi_w, roi_h):
        category = "Other"
        top_score = max(top_score, 4.0)
        category_scores["Other"] = max(category_scores.get("Other", 0.0), 4.0)
        matched_keywords.setdefault("Other", []).append("inline_win_banner_not_basegame")

    if category == "Basegame" and not has_explicit_basegame_control_signal(joined, basegame_ui_reasons):
        category = "Other"
        top_score = max(top_score, basegame_ui_score)
        category_scores["Other"] = max(category_scores.get("Other", 0.0), basegame_ui_score)
        matched_keywords.setdefault("Other", []).append(
            f"basegame_missing_explicit_spin_control:{basegame_ui_score:.2f}"
        )

    if (
        category == "Basegame"
        and has_large_center_payout_text(ocr_items, roi_w, roi_h)
        and not has_total_win_label
        and not (has_basegame_ui and has_jackpot_meter and not (has_bigwin_label or has_total_win_label))
    ):
        category = "BigWin"
        top_score = max(top_score, 6.0)
        category_scores["BigWin"] = max(category_scores.get("BigWin", 0.0), 6.0)
        matched_keywords.setdefault("BigWin", []).append("large_center_payout_text")
    elif category == "Basegame" and has_basegame_ui and has_jackpot_meter:
        matched_keywords.setdefault("Basegame", []).append("jackpot_meter_protected_as_basegame")

    if category == "Basegame" and has_free_game_text and not has_basegame_trigger_hint and (
        has_feature_rule_intro
        or has_feature_ui
        or has_any(joined, ["last free spin", "last free spins", "remaining free spin", "remaining free spins", "free spins won"])
    ):
        category = "Feature game" if has_feature_ui else "Transition"
        top_score = max(top_score, category_scores.get(category, 0.0), feature_ui_score)
        matched_keywords.setdefault(category, []).append("free_game_text_not_basegame")

    if category == "Basegame":
        if basegame_ui_score >= BASEGAME_UI_MIN_SCORE:
            category_scores["Basegame"] = round(basegame_ui_score, 2)
            top_score = max(top_score, basegame_ui_score)
            matched_keywords.setdefault("Basegame", []).append("priority_basegame_ui")
        else:
            category = "Other"
            top_score = max(top_score, basegame_ui_score)
            matched_keywords.setdefault("Other", []).append(
                f"basegame_ui_too_weak:{basegame_ui_score:.2f}"
            )

    bigwin_keep, bigwin_keep_reasons = get_bigwin_keep_signal_score(
        cropped, ocr_items, roi_w, roi_h, category_scores
    )
    category_scores["BigWinKeep"] = round(bigwin_keep, 2)
    if category == "BigWin" and bigwin_keep_reasons:
        matched_keywords.setdefault("BigWin", []).extend(
            f"{reason}:{bigwin_keep:.2f}" for reason in bigwin_keep_reasons
        )

    return category, category_scores, matched_keywords, raw_texts, top_score


# =========================
# CSV 寫入
# =========================
def get_image_feature(image_path):
    img = imread_image(image_path)
    if img is None:
        return None

    img = cv2.resize(img, (96, 96))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    hist = cv2.calcHist(
        [hsv],
        [0, 1, 2],
        None,
        [12, 8, 8],
        [0, 180, 0, 256, 0, 256]
    )
    hist = cv2.normalize(hist, hist).flatten()

    # 加入低解析度灰階結構，避免只靠顏色造成不同畫面混在一起
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small_gray = cv2.resize(gray, (16, 16)).astype(np.float32).flatten() / 255.0

    return np.concatenate([hist.astype(np.float32), small_gray])


def get_bottom_ui_color_feature(image_path):
    img = imread_image(image_path)
    if img is None:
        return None

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return None

    y1 = int(h * 0.55)
    y2 = int(h * 0.96)
    x1 = int(w * 0.04)
    x2 = int(w * 0.96)
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    roi = cv2.resize(roi, (128, 64))
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    hist = cv2.calcHist(
        [hsv],
        [0, 1, 2],
        None,
        [16, 5, 4],
        [0, 180, 0, 256, 0, 256]
    )
    hist = cv2.normalize(hist, hist).flatten().astype(np.float32)

    red = np.mean((((hue <= 10) | (hue >= 170)) & (sat >= 70) & (val >= 80)).astype(np.float32))
    pink = np.mean(((hue >= 145) & (hue <= 175) & (sat >= 55) & (val >= 90)).astype(np.float32))
    purple = np.mean(((hue >= 120) & (hue <= 160) & (sat >= 45) & (val >= 70)).astype(np.float32))
    blue = np.mean(((hue >= 88) & (hue <= 125) & (sat >= 45) & (val >= 70)).astype(np.float32))
    cyan = np.mean(((hue >= 75) & (hue <= 100) & (sat >= 45) & (val >= 80)).astype(np.float32))
    gold = np.mean(((hue >= 12) & (hue <= 38) & (sat >= 45) & (val >= 90)).astype(np.float32))
    green = np.mean(((hue >= 42) & (hue <= 82) & (sat >= 45) & (val >= 75)).astype(np.float32))
    dark = np.mean((val <= 70).astype(np.float32))
    bright = np.mean((val >= 210).astype(np.float32))
    high_sat = np.mean((sat >= 120).astype(np.float32))
    mean_sat = float(np.mean(sat) / 255.0)
    mean_val = float(np.mean(val) / 255.0)
    edge_ratio = float(np.mean(cv2.Canny(gray, 60, 140) > 0))
    small_gray = cv2.resize(gray, (16, 8)).astype(np.float32).flatten() / 255.0

    ratios = np.array([
        red, pink, purple, blue, cyan, gold, green, dark, bright,
        high_sat, mean_sat, mean_val, edge_ratio,
    ], dtype=np.float32)
    return np.concatenate([hist, ratios * 2.0, small_gray * 0.35])


def simple_kmeans(features, k=3, max_iter=30):
    n = len(features)
    if n == 0:
        return np.array([]), np.array([])

    k = min(k, n)
    X = np.asarray(features, dtype=np.float32)

    # 初始化：先取平均最遠點，讓群比較分散
    centers = [X[0]]
    while len(centers) < k:
        distances = np.min(
            np.stack([np.linalg.norm(X - c, axis=1) for c in centers], axis=1),
            axis=1
        )
        centers.append(X[int(np.argmax(distances))])

    centers = np.asarray(centers, dtype=np.float32)
    labels = np.zeros(n, dtype=np.int32)

    for _ in range(max_iter):
        dist = np.stack([np.linalg.norm(X - c, axis=1) for c in centers], axis=1)
        new_labels = np.argmin(dist, axis=1)

        if np.array_equal(labels, new_labels):
            break

        labels = new_labels
        for i in range(k):
            members = X[labels == i]
            if len(members) > 0:
                centers[i] = np.mean(members, axis=0)

    return labels, centers


def select_visual_cluster_images(
    records,
    cluster_count=3,
    keep_per_cluster=3,
    drop_low_score_majority_cluster=False,
    keep_score_fn=None
):
    feature_pairs = []
    invalid_records = []

    for rec in records:
        feat = get_image_feature(rec["save_path"])
        if feat is None:
            invalid_records.append(rec)
        else:
            feature_pairs.append((rec, feat))

    if len(feature_pairs) <= cluster_count * keep_per_cluster:
        return [rec for rec, _ in feature_pairs], invalid_records

    recs = [rec for rec, _ in feature_pairs]
    feats = [feat for _, feat in feature_pairs]

    labels, centers = simple_kmeans(feats, k=cluster_count)
    if len(labels) == 0:
        return [], records

    keep_records = []
    keep_ids = set()
    dropped_cluster_ids = set()

    if drop_low_score_majority_cluster and len(centers) >= 2:
        cluster_stats = []
        max_size = 0
        for cid in range(len(centers)):
            member_indices = np.where(labels == cid)[0]
            size = int(len(member_indices))
            if size == 0:
                continue

            avg_score = float(np.mean([recs[idx].get("top_score", 0.0) for idx in member_indices]))
            max_size = max(max_size, size)
            cluster_stats.append((cid, size, avg_score))

        if cluster_stats and max_size > 0:
            majority_candidates = [
                stat for stat in cluster_stats
                if stat[1] >= max(1, int(max_size * LOW_SCORE_MAJORITY_CLUSTER_RATIO))
            ]
            if majority_candidates:
                drop_cid, drop_size, drop_avg_score = min(
                    majority_candidates,
                    key=lambda stat: (stat[2], -stat[1])
                )
                dropped_cluster_ids.add(drop_cid)
                print(
                    f"  drop low-score majority cluster: cluster={drop_cid}, "
                    f"count={drop_size}, avg_score={drop_avg_score:.2f}"
                )

    # 大群優先：取「眾數群」概念，但分成 3 群增加差異性
    cluster_order = sorted(
        [cid for cid in range(len(centers)) if cid not in dropped_cluster_ids],
        key=lambda cid: int(np.sum(labels == cid)),
        reverse=True
    )

    for cid in cluster_order:
        member_indices = np.where(labels == cid)[0]
        if len(member_indices) == 0:
            continue

        center = centers[cid]
        ranked = []
        for idx in member_indices:
            dist = float(np.linalg.norm(feats[idx] - center))
            ranked.append((dist, idx))

        if keep_score_fn is None:
            ranked.sort(key=lambda x: x[0])
        else:
            ranked.sort(
                key=lambda x: (
                    keep_score_fn(recs[x[1]]),
                    -x[0],
                ),
                reverse=True
            )

        for _, idx in ranked[:keep_per_cluster]:
            rec = recs[idx]
            keep_records.append(rec)
            keep_ids.add(id(rec))

    remove_records = [
        rec for idx, rec in enumerate(recs)
        if id(rec) not in keep_ids or labels[idx] in dropped_cluster_ids
    ] + invalid_records
    return keep_records, remove_records


def basegame_final_reject_reasons(rec):
    reasons = []
    joined = record_text_joined(rec)

    if has_record_feature_text(rec):
        reasons.append("feature_running_text")
    if has_feature_intro_signal(joined) and not has_record_base_text(rec):
        reasons.append("feature_intro_text")
    if has_record_result_text(rec):
        reasons.append("result_text")

    obstruction = float(rec.get("feature_obstruction_score", 0.0))
    noise = float(rec.get("noise_score", 0.0))
    if obstruction >= BASEGAME_FINAL_MAX_OBSTRUCTION_SCORE:
        reasons.append(f"board_obstructed:{obstruction:.2f}")
    if noise >= BASEGAME_FINAL_MAX_NOISE_SCORE and obstruction >= FEATURE_BOARD_OBSTRUCTION_THRESHOLD:
        reasons.append(f"noisy_overlay:{noise:.2f}")

    img = imread_image(rec.get("save_path", ""))
    if img is not None:
        exposure_score, _ = overexposure_score(img)
        if exposure_score >= BASEGAME_FINAL_MAX_EXPOSURE_SCORE and obstruction >= FEATURE_BOARD_OBSTRUCTION_THRESHOLD:
            reasons.append(f"overexposed_overlay:{exposure_score:.2f}")

    return reasons


def is_clean_basegame_final_candidate(rec):
    return not basegame_final_reject_reasons(rec)


def select_basegame_ui_images(records, cluster_count=3, keep_per_cluster=3):
    if not records:
        return [], []

    ranked_records = sorted(
        records,
        key=lambda rec: (
            rec.get("basegame_ui_score", 0.0),
            basegame_keep_score(rec),
            -rec.get("noise_score", 0.0),
            rec.get("blur_score", 0.0),
            -rec.get("top_score", 0.0),
        ),
        reverse=True
    )

    min_keep_pool = cluster_count * keep_per_cluster
    top_pool_count = max(min_keep_pool, int(np.ceil(len(ranked_records) * BASEGAME_KEEP_TOP_UI_RATIO)))
    top_pool_count = min(len(ranked_records), top_pool_count)

    candidates = [
        rec for rec in ranked_records[:top_pool_count]
        if rec.get("basegame_ui_score", 0.0) >= BASEGAME_MIN_UI_SCORE_FOR_KEEP
    ]
    rejected_candidates = []
    clean_candidates_for_final = []
    for rec in candidates:
        reject_reasons = basegame_final_reject_reasons(rec)
        if reject_reasons:
            rec.setdefault("basegame_final_reject_reasons", reject_reasons)
            rejected_candidates.append(rec)
        else:
            clean_candidates_for_final.append(rec)
    if clean_candidates_for_final:
        candidates = clean_candidates_for_final

    clean_candidates = [
        rec for rec in candidates
        if rec.get("noise_score", 0.0) < TRANSITION_NOISE_SCORE_THRESHOLD
    ]
    if len(clean_candidates) >= min_keep_pool:
        candidates = clean_candidates
    candidates = sorted(candidates, key=basegame_keep_score, reverse=True)
    if len(candidates) < min_keep_pool:
        fallback_candidates = [
            rec for rec in ranked_records[:min(top_pool_count, len(ranked_records))]
            if is_clean_basegame_final_candidate(rec)
        ]
        if fallback_candidates:
            candidates = fallback_candidates

    candidate_ids = {id(rec) for rec in candidates}
    rejected_ids = {id(rec) for rec in rejected_candidates} if clean_candidates_for_final else set()
    low_ui_records = [
        rec for rec in records
        if id(rec) not in candidate_ids or id(rec) in rejected_ids
    ]

    keep_records, cluster_remove_records = select_visual_cluster_images(
        candidates,
        cluster_count=cluster_count,
        keep_per_cluster=keep_per_cluster,
        drop_low_score_majority_cluster=False,
        keep_score_fn=basegame_keep_score
    )
    return keep_records, low_ui_records + cluster_remove_records


def select_feature_ui_images(records, cluster_count=3, keep_per_cluster=3):
    if not records:
        return [], []

    min_keep_pool = cluster_count * keep_per_cluster
    ranked_records = sorted(
        records,
        key=lambda rec: (
            1 if has_record_pp_free_spins_left(rec) else 0,
            rec.get("feature_active_score", 0.0),
            rec.get("feature_ui_score", 0.0),
            feature_keep_score(rec),
            -rec.get("noise_score", 0.0),
            rec.get("blur_score", 0.0),
            rec.get("top_score", 0.0),
        ),
        reverse=True
    )

    pp_counter_records = [
        rec for rec in ranked_records
        if has_record_pp_free_spins_left(rec)
        and rec.get("feature_obstruction_score", 0.0) < FEATURE_BOARD_OBSTRUCTION_THRESHOLD
    ]
    if len(pp_counter_records) >= min_keep_pool:
        candidates = sorted(pp_counter_records, key=feature_keep_score, reverse=True)
        keep_records = candidates[:min_keep_pool]
        keep_ids = {id(rec) for rec in keep_records}
        remove_records = [rec for rec in records if id(rec) not in keep_ids]
        return keep_records, remove_records

    top_pool_count = max(min_keep_pool, int(np.ceil(len(ranked_records) * FEATURE_UI_KEEP_TOP_RATIO)))
    top_pool_count = min(len(ranked_records), top_pool_count)

    candidates = [
        rec for rec in ranked_records[:top_pool_count]
        if (
            rec.get("feature_ui_score", 0.0) >= FEATURE_UI_MIN_SCORE_FOR_KEEP
            or rec.get("feature_active_score", 0.0) >= FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP
        )
    ]
    clean_candidates = [
        rec for rec in candidates
        if rec.get("noise_score", 0.0) < TRANSITION_NOISE_SCORE_THRESHOLD
    ]
    if len(clean_candidates) >= min_keep_pool:
        candidates = clean_candidates
    visible_board_candidates = [
        rec for rec in candidates
        if (
            rec.get("feature_obstruction_score", 0.0) < FEATURE_BOARD_OBSTRUCTION_THRESHOLD
            or rec.get("feature_active_score", 0.0) >= FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP
        )
        and (
            has_record_pp_free_spins_left(rec)
            or rec.get("help_quality_score", 0.0) < HELP_MIN_QUALITY_SCORE
        )
    ]
    if len(visible_board_candidates) >= min_keep_pool:
        candidates = visible_board_candidates
    candidates = sorted(candidates, key=feature_keep_score, reverse=True)
    if len(candidates) < min_keep_pool:
        candidates = ranked_records[:min(top_pool_count, len(ranked_records))]

    candidate_ids = {id(rec) for rec in candidates}
    weak_ui_records = [rec for rec in records if id(rec) not in candidate_ids]

    keep_records, cluster_remove_records = select_visual_cluster_images(
        candidates,
        cluster_count=cluster_count,
        keep_per_cluster=keep_per_cluster,
        drop_low_score_majority_cluster=False,
        keep_score_fn=feature_keep_score
    )
    return keep_records, weak_ui_records + cluster_remove_records


def select_transition_images(records):
    if not records:
        return [], []

    def transition_rank(rec):
        joined = record_text_joined(rec)
        has_free_spin_award = (
            has_any(joined, ["you have won", "you won", "congratulations"])
            and has_any(joined, ["free spins", "free spin", "freespins", "freespin"])
        )
        has_settings_help_text = has_any(joined, [
            "settings menu", "information screen", "game history",
            "skip screens option", "auto skips",
        ])
        return (
            1 if has_free_spin_award else 0,
            -1 if has_settings_help_text else 0,
            rec.get("transition_keep_score", rec.get("top_score", 0.0)),
            -rec.get("noise_score", 0.0),
            rec.get("top_score", 0.0),
        )

    k = top_k_for_category("Transition")
    groups = []
    current_group = []
    last_frame = None
    for rec in sorted(records, key=lambda item: int(item.get("frame_idx", 0) or 0)):
        frame = int(rec.get("frame_idx", 0) or 0)
        if current_group and last_frame is not None and frame - last_frame > TRANSITION_EVENT_GAP_FRAMES:
            groups.append(current_group)
            current_group = []
        current_group.append(rec)
        last_frame = frame
    if current_group:
        groups.append(current_group)

    keep_records = []
    keep_ids = set()
    event_picks = [max(group, key=transition_rank) for group in groups]
    event_picks.sort(key=transition_rank, reverse=True)
    for rec in event_picks:
        if len(keep_records) >= k:
            break
        keep_records.append(rec)
        keep_ids.add(id(rec))

    remaining = [rec for rec in records if id(rec) not in keep_ids]
    remaining.sort(key=transition_rank, reverse=True)
    for rec in remaining:
        if len(keep_records) >= k:
            break
        keep_records.append(rec)
        keep_ids.add(id(rec))

    remove_records = [rec for rec in records if id(rec) not in keep_ids]
    return keep_records, remove_records


def select_bigwin_images(records):
    if not records:
        return [], []

    qualified_records = [
        rec for rec in records
        if (
            float(rec.get("bigwin_keep_score", 0.0)) >= BIGWIN_KEEP_MIN_SCORE
            or float(rec.get("top_score", 0.0)) >= 6.0
            or bigwin_tier_key(rec)
        )
    ]
    weak_records = [
        rec for rec in records
        if (
            float(rec.get("bigwin_keep_score", 0.0)) < BIGWIN_KEEP_MIN_SCORE
            and float(rec.get("top_score", 0.0)) < 6.0
            and not bigwin_tier_key(rec)
        )
    ]

    if not qualified_records:
        return [], records

    keep_limit = top_k_for_category("BigWin")
    keep_records = []
    keep_ids = set()

    def pick_best_bigwin_record(bucket):
        return max(
            bucket,
            key=lambda rec: (
                bigwin_keep_score(rec),
                rec.get("blur_score", 0.0),
                -rec.get("noise_score", 0.0),
                rec.get("top_score", 0.0),
            )
        )

    def split_bigwin_event_groups(bucket):
        sorted_bucket = sorted(bucket, key=lambda rec: int(rec.get("frame_idx", 0) or 0))
        groups = []
        current_group = []
        last_frame = None
        for rec in sorted_bucket:
            frame = int(rec.get("frame_idx", 0) or 0)
            if current_group and last_frame is not None and frame - last_frame > BIGWIN_EVENT_GAP_FRAMES:
                groups.append(current_group)
                current_group = []
            current_group.append(rec)
            last_frame = frame
        if current_group:
            groups.append(current_group)
        return groups

    tier_buckets = defaultdict(list)
    unlabeled_records = []
    for rec in qualified_records:
        tier = bigwin_tier_key(rec)
        if tier:
            tier_buckets[tier].append(rec)
        else:
            unlabeled_records.append(rec)

    if not tier_buckets.get("big_win"):
        labeled_frames = [
            int(rec.get("frame_idx", 0))
            for rec in qualified_records
            if bigwin_tier_key(rec)
        ]
        if labeled_frames:
            first_labeled_frame = min(labeled_frames)
            inferred_bigwin_records = [
                rec for rec in unlabeled_records
                if int(rec.get("frame_idx", 0)) < first_labeled_frame
                and (
                    float(rec.get("bigwin_keep_score", 0.0)) >= 4.0
                    or float(rec.get("top_score", 0.0)) >= 6.0
                )
            ]
            if inferred_bigwin_records:
                tier_buckets["big_win"].extend(inferred_bigwin_records)
                for rec in inferred_bigwin_records:
                    rec["bigwin_tier"] = "big_win"
                    rec["bigwin_tier_label"] = bigwin_tier_label("big_win")
                    rec.setdefault("matched_keywords", [])

    # 先保留每個 BigWin 階層、每個時間段的一張代表圖。
    # 避免同一段動畫的連續相似幀佔滿名額，導致後段 Jumbo/Super/Mega 被擠到 low_score。
    event_picks = []
    for tier in BIGWIN_TIER_ORDER:
        bucket = tier_buckets.get(tier, [])
        if not bucket:
            continue

        for event_group in split_bigwin_event_groups(bucket):
            pick = pick_best_bigwin_record(event_group)
            event_picks.append((tier, pick))

    event_picks.sort(
        key=lambda item: (
            BIGWIN_TIER_ORDER.index(item[0]) if item[0] in BIGWIN_TIER_ORDER else 999,
            int(item[1].get("frame_idx", 0) or 0),
        )
    )
    for tier, pick in event_picks:
        keep_records.append(pick)
        keep_ids.add(id(pick))
        pick["bigwin_tier"] = tier
        pick["bigwin_tier_label"] = bigwin_tier_label(tier)
        if len(keep_records) >= keep_limit:
            break

    remaining_candidates = [
        rec for rec in qualified_records
        if id(rec) not in keep_ids
    ]
    remaining_candidates.sort(
        key=lambda rec: (
            bigwin_keep_score(rec),
            rec.get("blur_score", 0.0),
            -rec.get("noise_score", 0.0),
        ),
        reverse=True
    )

    for rec in remaining_candidates:
        if len(keep_records) >= keep_limit:
            break
        keep_records.append(rec)
        keep_ids.add(id(rec))

    remove_records = [
        rec for rec in records
        if id(rec) not in keep_ids
    ]

    tier_summary = [
        f"{bigwin_tier_label(tier)}={len(tier_buckets.get(tier, []))}"
        for tier in BIGWIN_TIER_ORDER
        if tier_buckets.get(tier)
    ]
    if tier_summary:
        print("  BigWin OCR tiers: " + ", ".join(tier_summary))

    return keep_records, remove_records


def record_text_items(rec):
    texts = rec.get("raw_texts") or []
    if isinstance(texts, str):
        texts = [texts]

    clean_texts = []
    for item in texts:
        if isinstance(item, (list, tuple)) and item:
            clean_texts.append(str(item[0]))
        else:
            clean_texts.append(str(item))
    return clean_texts


def help_rule_text_stats(rec):
    text_items = [
        normalize_text(text)
        for text in record_text_items(rec)
        if len(normalize_text(text)) >= 2
    ]
    joined = " ".join(text_items)
    token_count = len(set(joined.split()))
    long_line_count = sum(1 for text in text_items if len(text) >= 18)
    return {
        "line_count": len(text_items),
        "token_count": token_count,
        "long_line_count": long_line_count,
        "joined": joined,
    }


def is_plain_rule_help_record(rec):
    stats = help_rule_text_stats(rec)
    quality = float(rec.get("help_quality_score", 0.0))
    paytable_score = float(rec.get("help_paytable_score", 0.0))

    has_lots_of_text = (
        stats["line_count"] >= HELP_RULE_TEXT_MIN_LINES
        and (
            stats["token_count"] >= HELP_RULE_TEXT_MIN_TOKENS
            or stats["long_line_count"] >= HELP_RULE_TEXT_MIN_LONG_LINES
        )
    )
    has_help_context = (
        has_any(stats["joined"], HELP_PHRASES)
        or paytable_score >= 1.0
        or stats["long_line_count"] >= HELP_RULE_TEXT_MIN_LONG_LINES + 1
    )
    return (
        has_lots_of_text
        and has_help_context
        and quality >= HELP_RULE_TEXT_MIN_QUALITY_SCORE
    )


def has_record_web_help_chrome(rec):
    joined = record_text_joined(rec)
    return has_any(joined, [
        "home figma", "notion", "chatgpt", "gitlab", "google chrome",
        "chrome", "pragmatic play",
    ]) and has_any(joined, ["page", "game rules", "information screen", "symbol"])


def help_rule_keep_score(rec):
    stats = help_rule_text_stats(rec)
    return (
        rec.get("help_quality_score", 0.0) * 1.2
        + rec.get("help_paytable_score", 0.0) * 2.0
        + stats["line_count"] * 0.8
        + stats["token_count"] * 0.15
        + stats["long_line_count"] * 1.0
        + rec.get("blur_score", 0.0) * 0.01
        - rec.get("noise_score", 0.0) * 0.6
    )


def select_help_images(records):
    if not records:
        return [], []

    ranked_records = sorted(
        records,
        key=lambda rec: (
            help_rule_keep_score(rec),
            rec.get("help_quality_score", 0.0),
            rec.get("blur_score", 0.0),
            -rec.get("noise_score", 0.0),
            rec.get("top_score", 0.0),
        ),
        reverse=True
    )

    web_help_records = [
        rec for rec in ranked_records
        if has_record_web_help_chrome(rec) and is_plain_rule_help_record(rec)
    ]
    if len(web_help_records) >= 3:
        ranked_records = web_help_records
    else:
        grouped = []
        current_group = []
        last_frame = None
        for rec in sorted(ranked_records, key=lambda item: int(item.get("frame_idx", 0) or 0)):
            frame = int(rec.get("frame_idx", 0) or 0)
            if current_group and last_frame is not None and frame - last_frame > HELP_EVENT_GAP_FRAMES:
                grouped.append(current_group)
                current_group = []
            current_group.append(rec)
            last_frame = frame
        if current_group:
            grouped.append(current_group)
        if grouped:
            best_group = max(
                grouped,
                key=lambda group: (
                    sum(1 for rec in group if is_plain_rule_help_record(rec)),
                    sum(float(rec.get("help_quality_score", 0.0)) for rec in group) / max(1, len(group)),
                    len(group),
                )
            )
            ranked_records = sorted(
                best_group,
                key=lambda rec: (
                    help_rule_keep_score(rec),
                    rec.get("help_quality_score", 0.0),
                    rec.get("blur_score", 0.0),
                    -rec.get("noise_score", 0.0),
                    rec.get("top_score", 0.0),
                ),
                reverse=True
            )

    # Keep Help as a compact rules corpus.  Over-keeping repeated web/browser
    # captures pollutes downstream symbol extraction and reports.
    k = min(top_k_for_category("Help"), HELP_MAX_FINAL_PAGES, len(ranked_records))
    keep_records = []
    keep_ids = set()

    rule_text_records = [
        rec for rec in ranked_records
        if is_plain_rule_help_record(rec)
    ]

    # Help 是給後續 AI 讀規則用，保留策略要偏向「完整資料」而不是只挑少量代表圖。
    for rec in rule_text_records:
        if len(keep_records) >= k:
            break
        if is_duplicate_help_record(rec, keep_records):
            continue
        keep_records.append(rec)
        keep_ids.add(id(rec))

    paytable_records = [
        rec for rec in ranked_records
        if rec.get("help_paytable_score", 0.0) >= 2.0
        and rec.get("help_quality_score", 0.0) >= HELP_RULE_TEXT_MIN_QUALITY_SCORE
        and id(rec) not in keep_ids
    ]
    paytable_records.sort(
        key=lambda rec: (
            rec.get("help_paytable_score", 0.0),
            help_rule_keep_score(rec),
            rec.get("help_quality_score", 0.0),
        ),
        reverse=True
    )
    paytable_added = 0
    paytable_limit = min(HELP_PAYTABLE_KEEP_COUNT, max(0, k - len(keep_records)))
    for rec in paytable_records:
        if paytable_added >= paytable_limit:
            break
        if is_duplicate_help_record(rec, keep_records):
            continue
        keep_records.append(rec)
        keep_ids.add(id(rec))
        paytable_added += 1

    if not keep_records and ranked_records:
        for rec in ranked_records:
            if len(keep_records) >= min(3, k):
                break
            if rec.get("help_quality_score", 0.0) < HELP_RULE_TEXT_MIN_QUALITY_SCORE:
                continue
            if is_duplicate_help_record(rec, keep_records):
                continue
            keep_records.append(rec)
            keep_ids.add(id(rec))

    remove_records = [rec for rec in records if id(rec) not in keep_ids]
    return keep_records, remove_records


def record_category_score(rec, category):
    scores = rec.get("category_scores") or {}
    if isinstance(scores, str):
        try:
            scores = ast.literal_eval(scores)
        except Exception:
            scores = {}
    try:
        return float(scores.get(category, 0.0))
    except Exception:
        return 0.0


def record_matched_keywords(rec, category):
    matched = rec.get("matched_keywords") or {}
    if isinstance(matched, str):
        try:
            matched = ast.literal_eval(matched)
        except Exception:
            matched = {}
    values = matched.get(category, [])
    if isinstance(values, str):
        values = [values]
    return [str(value) for value in values]


def loading_keep_score(rec):
    loading_score = record_category_score(rec, "loading")
    competing_score = max(
        record_category_score(rec, category)
        for category in ["BigWin", "Transition", "Feature game", "Feature Buy", "Result", "Basegame"]
    )
    loading_keywords = record_matched_keywords(rec, "loading")
    keyword_text = " ".join(loading_keywords).lower()
    frame_idx = int(rec.get("frame_idx", 0) or 0)

    score = loading_score * 2.0
    if "loading_splash_visual" in keyword_text:
        score += 14.0
    if "cover" in keyword_text or "splash" in keyword_text:
        score += 4.0
    if frame_idx <= 900:
        score += max(0.0, 9.0 - frame_idx / 120.0)

    # Loading 封面常會有 "massive wins" 等宣傳字，分類時可能同時觸發 BigWin。
    # 最終取樣時只把競爭分數當成輕微扣分，避免真正的封面被擠到 low_score。
    score -= max(0.0, competing_score - loading_score) * 0.45
    score -= float(rec.get("feature_ui_score", 0.0) or 0.0) * 0.25
    score -= float(rec.get("basegame_ui_score", 0.0) or 0.0) * 0.15
    score -= max(0.0, float(rec.get("noise_score", 0.0) or 0.0) - 12.0) * 0.2
    return score


def select_loading_images(records):
    if not records:
        return [], []

    k = top_k_for_category("loading")
    keep_records = []
    keep_ids = set()

    splash_records = [
        rec for rec in records
        if "loading_splash_visual" in " ".join(record_matched_keywords(rec, "loading")).lower()
    ]
    splash_records.sort(
        key=lambda rec: (
            int(rec.get("frame_idx", 0) or 0),
            -max(
                record_category_score(rec, category)
                for category in ["BigWin", "Transition", "Feature game", "Feature Buy", "Result"]
            ),
            -float(rec.get("noise_score", 0.0) or 0.0),
        )
    )

    # 先保留開頭連續 loading 封面，避免被後段高分但不適合作代表圖的畫面排掉。
    for rec in splash_records[:min(3, k)]:
        keep_records.append(rec)
        keep_ids.add(id(rec))

    ranked_records = sorted(records, key=loading_keep_score, reverse=True)
    for rec in ranked_records:
        if len(keep_records) >= k:
            break
        if id(rec) in keep_ids:
            continue
        keep_records.append(rec)
        keep_ids.add(id(rec))

    remove_records = [rec for rec in records if id(rec) not in keep_ids]
    return keep_records, remove_records


def top_k_for_category(category):
    if category in ["Transition", "Result", "loading"]:
        if category == "Transition":
            return TOP_K_TRANSITION
        if category == "Result":
            return TOP_K_RESULT
        if category == "loading":
            return TOP_K_LOADING
        return TOP_K_SHORT_EVENTS
    if category == "BigWin":
        return TOP_K_BIGWIN
    if category == "Help":
        return TOP_K_HELP
    if category == "Feature Buy":
        return TOP_K_FEATURE_BUY
    return TOP_K_DEFAULT


def move_records_to_low_score(records, low_score_dir, category):
    trash_category_dir = os.path.join(low_score_dir, category)
    os.makedirs(trash_category_dir, exist_ok=True)

    for rec in records:
        src = rec["save_path"]
        if os.path.exists(src):
            dst = os.path.join(trash_category_dir, os.path.basename(src))
            try:
                shutil.move(src, dst)
            except Exception as e:
                print(f"移動失敗: {src} -> {dst} | {e}")


def record_text_joined(rec):
    return " ".join(normalize_text(text) for text in record_text_items(rec))


def has_record_pp_free_spins_left(rec):
    joined = record_text_joined(rec)
    compact = joined.replace(" ", "")
    if "freespinsleft" in compact or "freespinleft" in compact:
        return True
    return (
        has_any(joined, ["free spins", "free spin", "freespins", "freespin"])
        and "left" in joined
        and bool(re.search(r"\b\d{1,3}\b", joined))
    )


def has_record_feature_text(rec):
    joined = record_text_joined(rec)
    compact = joined.replace(" ", "")
    if has_any_pattern(joined, [
        r"free\s*(game|spin|spins)\s*\d{1,3}\s*/\s*\d{1,3}",
        r"free\s*(game|games|spin|spins)\s*\d{1,3}\s*(of|f)\s*\d{1,3}",
        r"\d{1,3}\s*/\s*\d{1,3}\s*free\s*(game|spin|spins)",
    ]):
        return True
    if re.search(r"free(game|games|spin|spins)\d{1,3}(of|f)\d{1,3}", compact):
        return True
    return has_any(joined, [
        "remaining", "remaining free spin", "remaining free spins",
        "free spin remaining", "free spins remaining",
        "last free spin", "last free spins",
        "free spins left", "free game bonus",
    ])


def has_record_strong_feature_counter(rec):
    joined = record_text_joined(rec)
    compact = joined.replace(" ", "")
    if re.search(r"free(game|games|spin|spins)\d{1,3}(of|f)\d{1,3}", compact):
        return True
    if re.search(r"free(game|games|spin|spins)\d{1,3}/\d{1,3}", compact):
        return True
    if re.search(r"free(game|games|spin|spins)\d{2,4}", compact):
        return True
    return has_any_pattern(joined, [
        r"free\s*(game|spin|spins)\s*\d{1,3}\s*/\s*\d{1,3}",
        r"free\s*(game|games|spin|spins)\s*\d{1,3}\s*(of|f)\s*\d{1,3}",
        r"\d{1,3}\s*/\s*\d{1,3}\s*free\s*(game|spin|spins)",
        r"remaining\s*free\s*(spin|spins)\s*\d{1,3}",
        r"free\s*(spin|spins)\s*remaining\s*\d{1,3}",
    ])


def has_record_start_intro_text(rec):
    joined = record_text_joined(rec)
    return has_any(joined, [
        "start", "starting", "press start", "tap to start", "click to start",
        "begin", "enter",
    ])


def has_record_result_text(rec):
    joined = record_text_joined(rec)
    compact = joined.replace(" ", "")
    if has_any(joined, RESULT_STRONG_PHRASES):
        return True
    return "total" in compact and "win" in compact and bool(re.search(r"\d[\d,. ]{2,}", joined))


def has_record_base_text(rec):
    joined = record_text_joined(rec)
    return has_any(joined, [
        "balance", "total bets", "total bet", "extrabet", "extra bet",
        "bet", "auto", "turbo", "spin",
    ])


def reassign_record_category(rec, new_category):
    old_category = rec.get("category")
    if old_category == new_category:
        return False

    src = rec.get("save_path")
    if not src:
        rec["category"] = new_category
        return True

    video_dir = os.path.dirname(os.path.dirname(src))
    dst_dir = os.path.join(video_dir, new_category)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))

    if os.path.exists(src):
        try:
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.move(src, dst)
            rec["save_path"] = dst
        except Exception as e:
            print(f"分類修正移動失敗: {src} -> {dst} | {e}")
            return False
    else:
        rec["save_path"] = dst

    rec["category"] = new_category
    return True


def refine_base_feature_by_bottom_ui_clusters(saved_records):
    if not ENABLE_BOTTOM_UI_CLUSTER_REFINEMENT:
        return

    feature_record_count = sum(1 for rec in saved_records if rec.get("category") == "Feature game")
    use_basegame_recovery = feature_record_count <= BOTTOM_UI_CLUSTER_LOW_FEATURE_COUNT
    candidates = [
        rec for rec in saved_records
        if (
            rec.get("category") in ["Basegame", "Feature game"]
            or (
                use_basegame_recovery
                and rec.get("category") in ["Basegame", "Transition"]
            )
        )
        and os.path.exists(rec.get("save_path", ""))
    ]
    if len(candidates) < BOTTOM_UI_CLUSTER_MIN_RECORDS:
        return

    feature_pairs = []
    for rec in candidates:
        feat = get_bottom_ui_color_feature(rec["save_path"])
        if feat is not None:
            feature_pairs.append((rec, feat))
    if len(feature_pairs) < BOTTOM_UI_CLUSTER_MIN_RECORDS:
        return

    recs = [rec for rec, _ in feature_pairs]
    feats = [feat for _, feat in feature_pairs]
    labels, centers = simple_kmeans(feats, k=2)
    if len(labels) == 0 or len(centers) < 2:
        return

    within = []
    for cid in range(len(centers)):
        member_indices = np.where(labels == cid)[0]
        if len(member_indices) == 0:
            within.append(0.0)
            continue
        within.append(float(np.mean([
            np.linalg.norm(feats[idx] - centers[cid])
            for idx in member_indices
        ])))
    separation = float(np.linalg.norm(centers[0] - centers[1]) / max(1e-6, np.mean(within) + 1e-6))
    if separation < BOTTOM_UI_CLUSTER_MIN_SEPARATION:
        return

    stats = []
    for cid in range(len(centers)):
        member_indices = np.where(labels == cid)[0]
        members = [recs[idx] for idx in member_indices]
        if not members:
            continue
        feature_text_hits = sum(1 for rec in members if has_record_feature_text(rec))
        strong_feature_counter_hits = sum(1 for rec in members if has_record_strong_feature_counter(rec))
        base_text_hits = sum(1 for rec in members if has_record_base_text(rec))
        feature_count = sum(1 for rec in members if rec.get("category") == "Feature game")
        base_count = sum(1 for rec in members if rec.get("category") == "Basegame")
        transition_count = sum(1 for rec in members if rec.get("category") == "Transition")
        avg_feature_ui = float(np.mean([rec.get("feature_ui_score", 0.0) for rec in members]))
        avg_base_ui = float(np.mean([rec.get("basegame_ui_score", 0.0) for rec in members]))
        feature_evidence = (
            strong_feature_counter_hits * 5.0
            + feature_text_hits * 2.0
            + feature_count * 1.4
            + max(0.0, avg_feature_ui - avg_base_ui) * 0.8
        )
        base_evidence = (
            base_count * 1.0
            + base_text_hits * 0.4
            + max(0.0, avg_base_ui - avg_feature_ui) * 0.8
        )
        stats.append({
            "cid": cid,
            "count": len(members),
            "feature_text_hits": feature_text_hits,
            "strong_feature_counter_hits": strong_feature_counter_hits,
            "base_text_hits": base_text_hits,
            "feature_count": feature_count,
            "base_count": base_count,
            "transition_count": transition_count,
            "avg_feature_ui": avg_feature_ui,
            "avg_base_ui": avg_base_ui,
            "feature_evidence": feature_evidence,
            "base_evidence": base_evidence,
        })

    if len(stats) < 2:
        return

    feature_stat = max(stats, key=lambda stat: stat["feature_evidence"])
    base_stat = max([stat for stat in stats if stat["cid"] != feature_stat["cid"]], key=lambda stat: stat["base_evidence"])
    if feature_stat["feature_evidence"] < BOTTOM_UI_CLUSTER_MIN_FEATURE_EVIDENCE:
        return
    if feature_stat["feature_evidence"] <= base_stat["feature_evidence"] + 0.5:
        return

    changed_to_feature = 0
    changed_to_base = 0
    for idx, rec in enumerate(recs):
        cid = int(labels[idx])
        if cid == feature_stat["cid"] and rec.get("category") in ["Basegame", "Transition"]:
            if (
                has_record_strong_feature_counter(rec)
                or rec.get("feature_ui_score", 0.0) >= FEATURE_UI_MIN_SCORE_FOR_KEEP * 0.75
            ):
                if reassign_record_category(rec, "Feature game"):
                    rec["bottom_ui_cluster_refined"] = "to_feature_game"
                    changed_to_feature += 1
        elif cid == base_stat["cid"] and rec.get("category") == "Feature game":
            if not has_record_feature_text(rec) and rec.get("basegame_ui_score", 0.0) >= BASEGAME_MIN_UI_SCORE_FOR_KEEP:
                if reassign_record_category(rec, "Basegame"):
                    rec["bottom_ui_cluster_refined"] = "to_basegame"
                    changed_to_base += 1

    if changed_to_feature or changed_to_base:
        print(
            "\n[Bottom UI Cluster] 依影片內底部 UI 色彩分群修正 "
            f"Basegame/Feature game：to_feature={changed_to_feature}, "
            f"to_base={changed_to_base}, separation={separation:.2f}"
        )


def refine_transition_feature_counter_records(saved_records):
    changed = 0
    for rec in saved_records:
        if rec.get("category") != "Transition":
            continue
        if not has_record_strong_feature_counter(rec):
            continue
        if has_record_start_intro_text(rec) or has_record_result_text(rec):
            continue
        if reassign_record_category(rec, "Feature game"):
            rec["transition_feature_counter_refined"] = True
            rec["top_score"] = max(float(rec.get("top_score", 0.0)), 10.0)
            changed += 1

    if changed:
        print(f"\n[Feature Counter Rescue] Transition -> Feature game：{changed} 張")


def keep_selected_images(saved_records, low_score_dir=None):
    if low_score_dir is None:
        low_score_dir = os.path.join(OUTPUT_DIR, "low_score")
    os.makedirs(low_score_dir, exist_ok=True)

    refine_transition_feature_counter_records(saved_records)
    refine_base_feature_by_bottom_ui_clusters(saved_records)

    category_map = defaultdict(list)
    for rec in saved_records:
        category_map[rec["category"]].append(rec)

    for category, records in category_map.items():
        if category == "Basegame":
            keep_records, remove_records = select_basegame_ui_images(
                records,
                cluster_count=VISUAL_CLUSTER_COUNT,
                keep_per_cluster=VISUAL_KEEP_PER_CLUSTER
            )
            print(
                f"\n[{category}] Basegame UI 優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "Feature game":
            keep_records, remove_records = select_feature_ui_images(
                records,
                cluster_count=VISUAL_CLUSTER_COUNT,
                keep_per_cluster=VISUAL_KEEP_PER_CLUSTER
            )
            print(
                f"\n[{category}] Remaining Free Spin UI 優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "Transition":
            keep_records, remove_records = select_transition_images(records)
            print(
                f"\n[{category}] 轉場品質分優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "BigWin":
            keep_records, remove_records = select_bigwin_images(records)
            print(
                f"\n[{category}] Big/Mega/Total Win + 分數訊號優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "Help":
            keep_records, remove_records = select_help_images(records)
            print(
                f"\n[{category}] 深色說明頁 + OCR 內容去重取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "loading":
            keep_records, remove_records = select_loading_images(records)
            print(
                f"\n[{category}] loading 封面優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category in VISUAL_CLUSTER_CATEGORIES:
            cluster_count = BIGWIN_VISUAL_CLUSTER_COUNT if category == "BigWin" else VISUAL_CLUSTER_COUNT
            keep_per_cluster = BIGWIN_VISUAL_KEEP_PER_CLUSTER if category == "BigWin" else VISUAL_KEEP_PER_CLUSTER
            keep_records, remove_records = select_visual_cluster_images(
                records,
                cluster_count=cluster_count,
                keep_per_cluster=keep_per_cluster,
                drop_low_score_majority_cluster=category in DROP_LOW_SCORE_MAJORITY_CLUSTER_CATEGORIES
            )
            print(
                f"\n[{category}] 視覺分群 {cluster_count} 群，每群 {keep_per_cluster} 張；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        else:
            records.sort(key=lambda x: x["top_score"], reverse=True)
            k = top_k_for_category(category)
            keep_records = records[:k]
            remove_records = records[k:]
            print(f"\n[{category}] top_score 保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score")

        move_records_to_low_score(remove_records, low_score_dir, category)


# =========================
# 主流程
# =========================
def process_video(video_path, ocr_engine, video_output_dir, csv_path):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    video_file_prefix = safe_short_name(video_name, max_len=36)
    video_debug_dir = os.path.join(video_output_dir, "_debug")

    detected_roi = None
    if AUTO_DETECT_ROI:
        detected_roi = auto_detect_game_area(video_path, debug_dir=video_debug_dir)

    if detected_roi:
        roi_x, roi_y, roi_w, roi_h = detected_roi
        print(f"[{video_name}] Auto ROI: x={roi_x}, y={roi_y}, w={roi_w}, h={roi_h}")
    else:
        roi_x, roi_y, roi_w, roi_h = DEFAULT_ROI_X, DEFAULT_ROI_Y, DEFAULT_ROI_W, DEFAULT_ROI_H
        print(f"[{video_name}] 使用 fallback ROI: x={roi_x}, y={roi_y}, w={roi_w}, h={roi_h}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"無法開啟影片: {video_path}")
        return []

    frame_idx = 0
    saved_count = 0
    last_sampled_roi = None
    last_processed_frame_idx = None
    help_dense_until_frame = -1
    transition_dense_until_frame = -1
    feature_dense_until_frame = -1
    saved_records = []

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"[{video_name}] 影片讀取結束。")
            break

        help_dense_active = frame_idx <= help_dense_until_frame
        transition_dense_active = frame_idx <= transition_dense_until_frame
        feature_dense_active = frame_idx <= feature_dense_until_frame
        dense_active = help_dense_active or transition_dense_active or feature_dense_active
        dense_step_hit = dense_active and frame_idx % DENSE_SAMPLE_STEP == 0

        if frame_idx % FRAME_INTERVAL != 0 and not dense_step_hit:
            frame_idx += 1
            continue

        H, W = frame.shape[:2]
        x = max(0, min(roi_x, W - 1))
        y = max(0, min(roi_y, H - 1))
        w = max(1, min(roi_w, W - x))
        h = max(1, min(roi_h, H - y))

        cropped = frame[y:y + h, x:x + w]
        if cropped.size == 0:
            print(f"[{video_name}] frame {frame_idx}: ROI 擷取失敗")
            frame_idx += 1
            continue

        diff_score = frame_diff_score(last_sampled_roi, cropped)

        force_sample = (
            last_processed_frame_idx is None
            or frame_idx - last_processed_frame_idx >= FORCE_SAMPLE_INTERVAL_FRAMES
            or help_dense_active
            or transition_dense_active
            or feature_dense_active
        )

        if last_sampled_roi is not None and diff_score < DIFF_THRESHOLD and not force_sample:
            print(f"[{video_name}] frame {frame_idx} 跳過 | diff={diff_score:.2f}")
            frame_idx += 1
            continue

        if force_sample and last_sampled_roi is not None and diff_score < DIFF_THRESHOLD:
            print(
                f"[{video_name}] frame {frame_idx} 強制取樣 | "
                f"diff={diff_score:.2f} | interval={FORCE_SAMPLE_INTERVAL_FRAMES}"
            )
        last_processed_frame_idx = frame_idx

        current_blur = blur_score(cropped)
        if ENABLE_BLUR_FILTER and current_blur < BLUR_THRESHOLD:
            print(f"[{video_name}] frame {frame_idx} 跳過模糊圖 | blur={current_blur:.2f} | diff={diff_score:.2f}")
            last_sampled_roi = cropped.copy()
            frame_idx += 1
            continue

        exposure_score, exposure_reasons = overexposure_score(cropped)
        if ENABLE_OVEREXPOSURE_FILTER and exposure_score >= OVEREXPOSURE_SCORE_THRESHOLD:
            print(
                f"[{video_name}] frame {frame_idx} 跳過爆光圖 | "
                f"exposure={exposure_score:.2f} | {', '.join(exposure_reasons)} | "
                f"blur={current_blur:.2f} | diff={diff_score:.2f}"
            )
            last_sampled_roi = cropped.copy()
            frame_idx += 1
            continue

        try:
            result = get_ocr_result(ocr_engine, cropped)
        except Exception as e:
            print(f"OCR 執行失敗, frame={frame_idx}, 錯誤: {e}")
            result = None

        ocr_items = extract_ocr_items(result)
        category, category_scores, matched_keywords, raw_texts, top_score = classify_frame(cropped, ocr_items, w, h)

        noise_score, noise_reasons = transition_noise_score(cropped)
        transition_keep_score, transition_keep_reasons = get_transition_keep_score(
            ocr_items, w, h, category_scores
        )
        if category == "Transition" and transition_keep_reasons:
            matched_keywords.setdefault("Transition", []).extend(
                f"{reason}:{transition_keep_score:.2f}" for reason in transition_keep_reasons
            )

        feature_ui_score = float(category_scores.get("FeatureUI", 0.0))
        basegame_ui_score = float(category_scores.get("BasegameUI", 0.0))
        bigwin_keep_signal_score = float(category_scores.get("BigWinKeep", 0.0))
        help_quality_score, help_quality_reasons = help_page_quality_score(cropped, ocr_items)
        help_tokens = help_text_tokens(ocr_items)
        help_paytable_score = help_paytable_signal_score(ocr_items)
        category_scores["HelpQuality"] = round(help_quality_score, 2)
        category_scores["HelpPaytable"] = round(help_paytable_score, 2)

        if category == "Help":
            web_help_roi = get_web_help_page_roi(frame)
            if web_help_roi:
                hx, hy, hw, hh = web_help_roi
                web_cropped = frame[hy:hy + hh, hx:hx + hw]
                if web_cropped.size > 0 and (hw > w * 1.35 or hh > h * 1.05):
                    try:
                        web_result = get_ocr_result(ocr_engine, web_cropped)
                    except Exception as e:
                        print(f"OCR 執行失敗, frame={frame_idx}, web help crop 錯誤: {e}")
                        web_result = None

                    web_ocr_items = extract_ocr_items(web_result)
                    (
                        web_category,
                        web_category_scores,
                        web_matched_keywords,
                        web_raw_texts,
                        web_top_score,
                    ) = classify_frame(web_cropped, web_ocr_items, hw, hh)
                    web_help_quality_score, web_help_quality_reasons = help_page_quality_score(
                        web_cropped, web_ocr_items
                    )
                    web_help_paytable_score = help_paytable_signal_score(web_ocr_items)

                    web_joined = " ".join(
                        normalize_text(text)
                        for _, text, score in web_ocr_items
                        if score >= SCORE_THRESHOLD
                    )
                    web_rules_help_like = is_rules_help_page_candidate(
                        web_joined,
                        web_ocr_items,
                        web_help_quality_score,
                        web_category_scores,
                        web_help_paytable_score,
                    )
                    web_help_like = (
                        web_category == "Help"
                        or has_help_signal(web_joined, web_ocr_items, hw, hh)
                        or web_rules_help_like
                    )
                    web_false_result_from_rules = (
                        web_category == "Result"
                        and web_rules_help_like
                        and web_help_quality_score >= 6.0
                    )

                    if (
                        web_help_like
                        and (
                            web_category not in ["Feature Buy", "BigWin", "Result", "loading"]
                            or web_false_result_from_rules
                        )
                    ):
                        x, y, w, h = hx, hy, hw, hh
                        cropped = web_cropped
                        ocr_items = web_ocr_items
                        category = "Help"
                        category_scores = web_category_scores
                        matched_keywords = web_matched_keywords
                        raw_texts = web_raw_texts
                        top_score = web_top_score
                        category_scores["Help"] = max(category_scores.get("Help", 0.0), 12.0)
                        matched_keywords.setdefault("Help", []).append("web_full_page_crop_forced")
                        current_blur = blur_score(cropped)
                        noise_score, noise_reasons = transition_noise_score(cropped)
                        transition_keep_score, transition_keep_reasons = get_transition_keep_score(
                            ocr_items, w, h, category_scores
                        )
                        feature_ui_score = float(category_scores.get("FeatureUI", 0.0))
                        basegame_ui_score = float(category_scores.get("BasegameUI", 0.0))
                        bigwin_keep_signal_score = float(category_scores.get("BigWinKeep", 0.0))
                        help_quality_score = web_help_quality_score
                        help_quality_reasons = web_help_quality_reasons + ["web_full_page_crop"]
                        help_tokens = help_text_tokens(ocr_items)
                        help_paytable_score = web_help_paytable_score
                        category_scores["HelpQuality"] = round(help_quality_score, 2)
                        category_scores["HelpPaytable"] = round(help_paytable_score, 2)

        if category == "Help" and help_quality_reasons:
            matched_keywords.setdefault("Help", []).extend(
                f"{reason}:{help_quality_score:.2f}" for reason in help_quality_reasons
            )
        if category == "Help":
            help_dense_until_frame = max(
                help_dense_until_frame,
                frame_idx + HELP_DENSE_SAMPLE_AFTER_FRAMES,
            )
            matched_keywords.setdefault("Help", []).append("help_dense_sampling_active")
        if category == "Transition":
            transition_dense_until_frame = max(
                transition_dense_until_frame,
                frame_idx + TRANSITION_DENSE_SAMPLE_AFTER_FRAMES,
            )
            matched_keywords.setdefault("Transition", []).append("transition_dense_sampling_active")
        if category == "Feature game":
            feature_dense_until_frame = max(
                feature_dense_until_frame,
                frame_idx + FEATURE_DENSE_SAMPLE_AFTER_FRAMES,
            )
            matched_keywords.setdefault("Feature game", []).append("feature_dense_sampling_active")
        feature_obstruction_score, feature_obstruction_reasons = feature_board_obstruction_score(cropped)
        category_scores["FeatureObstruction"] = round(feature_obstruction_score, 2)
        if category == "Feature game" and feature_obstruction_reasons:
            matched_keywords.setdefault("Feature game", []).extend(
                f"{reason}:{feature_obstruction_score:.2f}" for reason in feature_obstruction_reasons
            )
        final_joined = " ".join(
            normalize_text(text)
            for _, text, ocr_score in (ocr_items or [])
            if ocr_score >= SCORE_THRESHOLD
        )
        feature_active_score = float(category_scores.get("FeatureActive", 0.0))
        feature_subtype, feature_subtype_scores = detect_feature_subtype(final_joined)
        if category != "Feature game":
            feature_subtype = ""
        has_protected_feature_ui = feature_ui_score >= FEATURE_UI_MIN_SCORE_FOR_KEEP + NOISE_PROTECT_UI_MARGIN
        has_protected_feature_active = (
            category == "Feature game"
            and feature_active_score >= FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP
        )
        has_protected_basegame_ui = basegame_ui_score >= BASEGAME_MIN_UI_SCORE_FOR_KEEP + NOISE_PROTECT_UI_MARGIN
        should_skip_noise = category == "Other"
        if category == "Feature game" and not (has_protected_feature_ui or has_protected_feature_active):
            should_skip_noise = True
        if category == "Basegame" and not has_protected_basegame_ui:
            should_skip_noise = True

        if (
            ENABLE_TRANSITION_NOISE_FILTER
            and noise_score >= TRANSITION_NOISE_SCORE_THRESHOLD
            and category not in ["BigWin", "Result", "loading"]
            and should_skip_noise
        ):
            print(
                f"[{video_name}] frame {frame_idx} 跳過轉場殘影/雜訊圖 | "
                f"noise={noise_score:.2f} | {', '.join(noise_reasons)} | "
                f"category={category} | feature_ui={feature_ui_score:.2f} | basegame_ui={basegame_ui_score:.2f} | "
                f"blur={current_blur:.2f} | diff={diff_score:.2f}"
            )
            last_sampled_roi = cropped.copy()
            frame_idx += 1
            continue

        if ENABLE_TRANSITION_NOISE_FILTER and noise_score >= TRANSITION_NOISE_SCORE_THRESHOLD:
            matched_keywords.setdefault(category, []).append(f"kept_noisy_but_classifiable:{noise_score:.2f}")

        save_path = os.path.join(video_output_dir, category, f"{video_file_prefix}_frame_{frame_idx:06d}.jpg")
        if not imwrite_image(save_path, cropped):
            print(f"[{video_name}] frame {frame_idx}: 圖片寫入失敗，跳過這張")
            last_sampled_roi = cropped.copy()
            frame_idx += 1
            continue
        saved_count += 1

        saved_records.append({
            "category": category,
            "top_score": top_score,
            "basegame_ui_score": basegame_ui_score,
            "feature_ui_score": feature_ui_score,
            "feature_active_score": feature_active_score,
            "bigwin_keep_score": bigwin_keep_signal_score,
            "help_quality_score": help_quality_score,
            "help_paytable_score": help_paytable_score,
            "help_tokens": help_tokens,
            "feature_obstruction_score": feature_obstruction_score,
            "noise_score": noise_score,
            "transition_keep_score": transition_keep_score,
            "feature_subtype": feature_subtype,
            "feature_subtype_scores": feature_subtype_scores,
            "save_path": save_path,
            "frame_idx": frame_idx,
            "blur_score": current_blur,
            "raw_texts": raw_texts,
            "category_scores": dict(category_scores),
            "matched_keywords": dict(matched_keywords),
        })

        print(f"\n[{video_name}] frame {frame_idx} -> {category} | diff={diff_score:.2f} | blur={current_blur:.2f} | top_score={top_score:.2f}")
        print("OCR:")
        for box, text, score in ocr_items:
            print(f"  [box={box}] ('{text}', {score:.3f})")

        print("Category scores:")
        for cat in CATEGORY_NAMES:
            if cat in category_scores:
                print(f"  {cat}: {category_scores[cat]}")

        print("Matched keywords:")
        for cat, kws in matched_keywords.items():
            if kws:
                print(f"  {cat}: {', '.join(kws)}")

        append_csv_row(
            csv_path,
            [
                video_name,
                frame_idx,
                category,
                f"{diff_score:.2f}",
                f"{current_blur:.2f}",
                f"{top_score:.2f}",
                feature_subtype,
                str(feature_subtype_scores),
                str(raw_texts),
                str(category_scores),
                str(matched_keywords),
                f"({x},{y},{w},{h})",
                save_path,
            ]
        )

        last_sampled_roi = cropped.copy()
        frame_idx += 1

    cap.release()
    print(f"[{video_name}] 完成，總共儲存 {saved_count} 張圖")
    return saved_records


def generate_symbols_for_output(video_output_dir, debug=False):
    try:
        from . import generate_symbol_table as symbol_table_generator
    except ImportError:
        import generate_symbol_table as symbol_table_generator

    symbol_table_generator.process_video(
        Path(video_output_dir),
        api_key="",
        no_ai=True,
        debug=debug,
        icons_only=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Slot video frame classifier.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--video-id",
        default=None,
        metavar="ID",
        help=(
            "Process only the video whose filename stem matches ID.\n"
            "Examples:\n"
            "  --video-id 8        → matches 8.mp4 / 8.mov / …\n"
            "  --video-id lucky    → matches lucky.mp4\n"
            "(Omit to process all videos in input_videos/.)"
        ),
    )
    parser.add_argument(
        "--skip-symbols",
        action="store_true",
        help="Only classify video frames. Do not generate symbol_table output.",
    )
    parser.add_argument(
        "--symbol-debug",
        action="store_true",
        help="Save extra symbol detection debug images under symbol_table.",
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    video_list = get_video_list()
    if not video_list:
        print(f"No videos found. Put video files in: {INPUT_DIR}")
        return

    # ── Filter by --video-id if given ────────────────────────────────────────
    if args.video_id:
        target = args.video_id.strip()
        video_list = [
            p for p in video_list
            if os.path.splitext(os.path.basename(p))[0] == target
        ]
        if not video_list:
            print(f"No video found with id '{target}' in {INPUT_DIR}")
            return

    ocr_engine = init_ocr(OCR_LANG)
    print("OCR initialized.")
    print(f"Found {len(video_list)} video(s).")

    for video_path in video_list:
        if not os.path.exists(video_path):
            print(f"Video not found: {video_path}")
            continue

        video_output_dir = get_video_output_dir(video_path)
        video_csv_path = get_video_csv_path(video_output_dir)
        prepare_output_dirs(video_output_dir)
        write_csv_header(video_csv_path)

        print(f"\n=== Processing: {os.path.basename(video_path)} ===")
        print(f"Output folder: {video_output_dir}")

        records = process_video(video_path, ocr_engine, video_output_dir, video_csv_path)
        keep_selected_images(records, low_score_dir=os.path.join(video_output_dir, "low_score"))
        print(f"CSV saved: {video_csv_path}")
        if not args.skip_symbols:
            print("Generating symbol images...")
            generate_symbols_for_output(video_output_dir, debug=args.symbol_debug)
            print(f"Symbols saved: {os.path.join(video_output_dir, 'symbol_table', 'symbols')}")

    print(f"Output root: {OUTPUT_DIR}")
    print("Done.")

if __name__ == "__main__":
    main()
