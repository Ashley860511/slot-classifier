import re

try:
    from ..constants import BIGWIN_TIER_ORDER, SCORE_THRESHOLD
except ImportError:
    from constants import BIGWIN_TIER_ORDER, SCORE_THRESHOLD

try:
    from .text_signals import (
        normalize_text,
        has_any,
        has_bigwin_strong_signal,
        has_pp_bigwin_title_signal,
        has_jackpot_meter_signal,
        has_large_center_payout_text,
        has_large_result_layout,
        has_inline_win_banner,
        has_feature_running_signal,
    )
    from .visual_scores import has_large_center_payout_visual
except ImportError:
    from text_signals import (
        normalize_text,
        has_any,
        has_bigwin_strong_signal,
        has_pp_bigwin_title_signal,
        has_jackpot_meter_signal,
        has_large_center_payout_text,
        has_large_result_layout,
        has_inline_win_banner,
        has_feature_running_signal,
    )
    from visual_scores import has_large_center_payout_visual


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
    # Import here to avoid circular dependency
    try:
        from .selector import record_text_joined
    except ImportError:
        from selector import record_text_joined
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
