import os
import re

import cv2
import numpy as np

try:
    from ..constants import (
        HELP_DEDUP_JACCARD_THRESHOLD,
        HELP_VISUAL_DEDUP_MAX_MAD,
        HELP_VISUAL_DEDUP_MIN_HIST_CORR,
        SCORE_THRESHOLD,
    )
except ImportError:
    from constants import (
        HELP_DEDUP_JACCARD_THRESHOLD,
        HELP_VISUAL_DEDUP_MAX_MAD,
        HELP_VISUAL_DEDUP_MIN_HIST_CORR,
        SCORE_THRESHOLD,
    )

try:
    from .text_signals import normalize_text, has_any, get_box_bounds
except ImportError:
    from text_signals import normalize_text, has_any, get_box_bounds

try:
    from ..video_io import imread_image
except ImportError:
    from video_io import imread_image


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

    if paytable_title and (full_pay_count >= 3 or payout_pair_count >= 4):
        return 3.0
    if paytable_title and numeric_value_count >= 8 and symbol_table_terms >= 1:
        return 2.5
    if paytable_title and numeric_value_count >= 12:
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
