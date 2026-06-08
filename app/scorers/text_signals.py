import json
import os
import re

import numpy as np

try:
    from ..constants import (
        BIGWIN_STRONG_PHRASES,
        FEATURE_BUY_PHRASES,
        FEATURE_INTRO_PATTERNS,
        FEATURE_INTRO_PHRASES,
        FEATURE_RUNNING_PHRASES,
        HELP_PHRASES,
        LOADING_COVER_MARKETING_TERMS,
        LOADING_COVER_VENDOR_TERMS,
        LOADING_PHRASES,
        RESULT_STRONG_PHRASES,
        SCORE_THRESHOLD,
        TRANSITION_ACTION_PHRASES,
        TRANSITION_COVER_TERMS,
    )
except ImportError:
    from constants import (
        BIGWIN_STRONG_PHRASES,
        FEATURE_BUY_PHRASES,
        FEATURE_INTRO_PATTERNS,
        FEATURE_INTRO_PHRASES,
        FEATURE_RUNNING_PHRASES,
        HELP_PHRASES,
        LOADING_COVER_MARKETING_TERMS,
        LOADING_COVER_VENDOR_TERMS,
        LOADING_PHRASES,
        RESULT_STRONG_PHRASES,
        SCORE_THRESHOLD,
        TRANSITION_ACTION_PHRASES,
        TRANSITION_COVER_TERMS,
    )

# ---------------------------------------------------------------------------
# OCR corrections – loaded lazily from ocr_corrections.json; hard-coded dict
# is the fallback.
# ---------------------------------------------------------------------------
_OCR_CORRECTIONS = None

_HARDCODED_CORRECTIONS = {
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


def _load_ocr_corrections():
    global _OCR_CORRECTIONS
    if _OCR_CORRECTIONS is not None:
        return _OCR_CORRECTIONS

    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "ocr_corrections.json"),
        os.path.join(os.path.dirname(__file__), "..", "ocr_corrections.json"),
        os.path.join(os.path.dirname(__file__), "ocr_corrections.json"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    _OCR_CORRECTIONS = json.load(fh)
                return _OCR_CORRECTIONS
            except Exception:
                pass

    _OCR_CORRECTIONS = dict(_HARDCODED_CORRECTIONS)
    return _OCR_CORRECTIONS


def normalize_text(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    corrections = _load_ocr_corrections()
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


def has_loading_strong_signal(joined):
    return has_any(joined, LOADING_PHRASES)


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

    amount_hits = re.findall(r"\d[\d,. ]{2,}", joined)
    return len(amount_hits) >= 2
