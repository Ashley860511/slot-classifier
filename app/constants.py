# =========================
# 取樣 / 分類設定
# =========================
FRAME_INTERVAL = 20
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
