import os
import re

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

try:
    from ..constants import (
        BASEGAME_UI_MIN_SCORE,
        FEATURE_UI_MIN_SCORE_FOR_KEEP,
        HELP_PHRASES,
        MIN_CATEGORY_SCORE,
        SCORE_THRESHOLD,
        TRANSITION_ACTION_PHRASES,
    )
except ImportError:
    from constants import (
        BASEGAME_UI_MIN_SCORE,
        FEATURE_UI_MIN_SCORE_FOR_KEEP,
        HELP_PHRASES,
        MIN_CATEGORY_SCORE,
        SCORE_THRESHOLD,
        TRANSITION_ACTION_PHRASES,
    )

try:
    from .text_signals import (
        normalize_text,
        has_any,
        has_any_pattern,
        get_box_bounds,
        has_large_lower_start_button,
        has_large_result_layout,
        has_collect_button_signal,
        has_blocking_modal_signal,
        has_loading_strong_signal,
        has_loading_cover_text_signal,
        has_transition_cover_text_signal,
        has_feature_running_signal,
        has_feature_intro_signal,
        has_feature_buy_signal,
        has_help_signal,
        is_rules_help_page_candidate,
        has_explicit_basegame_control_signal,
        has_transition_strong_signal,
        has_result_strong_signal,
        has_inline_win_banner,
        has_large_center_payout_text,
        has_bigwin_strong_signal,
        has_pp_bigwin_title_signal,
        has_jackpot_meter_signal,
    )
    from .visual_scores import (
        get_basegame_ui_score,
        get_feature_ui_score,
        feature_reel_board_signal_score,
        has_brand_logo_splash_signal,
        has_large_center_payout_visual,
        has_loading_splash_signal,
    )
    from .help_scorer import help_paytable_signal_score
    from .bigwin_scorer import get_bigwin_keep_signal_score
except ImportError:
    from text_signals import (
        normalize_text,
        has_any,
        has_any_pattern,
        get_box_bounds,
        has_large_lower_start_button,
        has_large_result_layout,
        has_collect_button_signal,
        has_blocking_modal_signal,
        has_loading_strong_signal,
        has_loading_cover_text_signal,
        has_transition_cover_text_signal,
        has_feature_running_signal,
        has_feature_intro_signal,
        has_feature_buy_signal,
        has_help_signal,
        is_rules_help_page_candidate,
        has_explicit_basegame_control_signal,
        has_transition_strong_signal,
        has_result_strong_signal,
        has_inline_win_banner,
        has_large_center_payout_text,
        has_bigwin_strong_signal,
        has_pp_bigwin_title_signal,
        has_jackpot_meter_signal,
    )
    from visual_scores import (
        get_basegame_ui_score,
        get_feature_ui_score,
        feature_reel_board_signal_score,
        has_brand_logo_splash_signal,
        has_large_center_payout_visual,
        has_loading_splash_signal,
    )
    from help_scorer import help_paytable_signal_score
    from bigwin_scorer import get_bigwin_keep_signal_score

# ---------------------------------------------------------------------------
# CATEGORY_KEYWORDS – loaded from keywords.yaml; hard-coded dict is fallback.
# ---------------------------------------------------------------------------
_CATEGORY_KEYWORDS = None

_HARDCODED_CATEGORY_KEYWORDS = {
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
    "Basegame": {},
}


def _load_category_keywords():
    global _CATEGORY_KEYWORDS
    if _CATEGORY_KEYWORDS is not None:
        return _CATEGORY_KEYWORDS

    if not _YAML_AVAILABLE:
        _CATEGORY_KEYWORDS = dict(_HARDCODED_CATEGORY_KEYWORDS)
        return _CATEGORY_KEYWORDS

    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "keywords.yaml"),
        os.path.join(os.path.dirname(__file__), "..", "keywords.yaml"),
        os.path.join(os.path.dirname(__file__), "keywords.yaml"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if isinstance(data, dict):
                    _CATEGORY_KEYWORDS = data
                    return _CATEGORY_KEYWORDS
            except Exception:
                pass

    _CATEGORY_KEYWORDS = dict(_HARDCODED_CATEGORY_KEYWORDS)
    return _CATEGORY_KEYWORDS


def _get_feature_subtype_terms():
    try:
        from ..constants import FEATURE_SUBTYPE_TERMS
    except ImportError:
        from constants import FEATURE_SUBTYPE_TERMS
    return FEATURE_SUBTYPE_TERMS


def detect_feature_subtype(joined):
    FEATURE_SUBTYPE_TERMS = _get_feature_subtype_terms()
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


def feature_active_signal_score(joined, ocr_items=None, category_scores=None, help_quality_score=0.0):
    try:
        from ..constants import FEATURE_ACTIVE_TERMS, FEATURE_ACTIVE_INTERACTION_TERMS
    except ImportError:
        from constants import FEATURE_ACTIVE_TERMS, FEATURE_ACTIVE_INTERACTION_TERMS

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


def get_transition_keep_score(ocr_items, roi_w, roi_h, category_scores=None):
    try:
        from ..constants import BASEGAME_MIN_UI_SCORE_FOR_KEEP
    except ImportError:
        from constants import BASEGAME_MIN_UI_SCORE_FOR_KEEP

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
    CATEGORY_KEYWORDS = _load_category_keywords()

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

    feature_board_score, feature_board_reasons = feature_reel_board_signal_score(cropped)
    category_scores["FeatureBoard"] = round(feature_board_score, 2)
    if feature_board_reasons:
        matched_keywords.setdefault("Feature game", []).extend(feature_board_reasons)

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
    has_free_spin_counter_text = (
        has_any(joined, ["free spins", "free spin", "freespins", "freespin"])
        and bool(re.search(r"\b\d{1,3}\b", joined))
    )
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

    jackpot_pick_feature = (
        feature_subtype == "pick"
        and feature_board_score >= 3.0
        and has_any(joined, ["jackpot", "grand", "major", "minor", "mini"])
        and has_any(joined, ["please select", "select one", "pick", "choose"])
        and not has_help_page
        and not has_rules_help_page
    )
    if jackpot_pick_feature:
        category = "Feature game"
        top_score = max(top_score, feature_board_score, 12.0)
        category_scores["Feature game"] = max(category_scores.get("Feature game", 0.0), 12.0)
        category_scores["loading"] = min(category_scores.get("loading", 0.0), 2.0)
        matched_keywords.setdefault("Feature game", []).append(
            f"jackpot_pick_bonus:{feature_board_score:.2f}"
        )

    if (
        (has_loading_splash or has_loading_cover_text)
        and not has_transition_cover_text
        and not has_feature_buy_modal
        and not has_bigwin_overlay
        and not jackpot_pick_feature
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

    if (
        category == "Transition"
        and has_free_spin_counter_text
        and feature_board_score >= 3.0
        and not has_transition_cover_text
        and not has_start_intro
        and not has_feature_rule_intro
        and not has_transition_action_text
        and not has_real_result_layout
        and not has_total_win_label
    ):
        category = "Feature game"
        top_score = max(top_score, feature_board_score, feature_ui_score, 10.0)
        category_scores["Feature game"] = max(category_scores.get("Feature game", 0.0), 10.0)
        matched_keywords.setdefault("Feature game", []).append(
            f"free_spin_counter_over_reel_board:{feature_board_score:.2f}"
        )

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
