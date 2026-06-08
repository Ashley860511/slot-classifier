import re

import cv2
import numpy as np

try:
    from ..constants import SCORE_THRESHOLD, BASEGAME_UI_MIN_SCORE, FEATURE_UI_MIN_SCORE_FOR_KEEP
except ImportError:
    from constants import SCORE_THRESHOLD, BASEGAME_UI_MIN_SCORE, FEATURE_UI_MIN_SCORE_FOR_KEEP

try:
    from .text_signals import (
        normalize_text,
        has_any,
        has_feature_running_signal,
        has_large_center_payout_text,
        has_loading_cover_text_signal,
        has_loading_strong_signal,
    )
except ImportError:
    from text_signals import (
        normalize_text,
        has_any,
        has_feature_running_signal,
        has_large_center_payout_text,
        has_loading_cover_text_signal,
        has_loading_strong_signal,
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

        from .text_signals import get_box_bounds
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


def feature_reel_board_signal_score(img):
    """Detect visible slot-board/reel geometry behind a free-spin counter."""
    if img is None or img.size == 0:
        return 0.0, []

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0, []

    roi = img[int(h * 0.12):int(h * 0.84), int(w * 0.18):int(w * 0.86)]
    if roi.size == 0:
        return 0.0, []

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    edges = cv2.Canny(gray, 55, 145)

    edge_ratio = float(np.mean(edges > 0))
    texture = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    colour_ratio = float(np.mean((sat >= 42) & (val >= 55)))

    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180.0,
        threshold=max(28, roi.shape[1] // 18),
        minLineLength=max(26, roi.shape[1] // 14),
        maxLineGap=max(8, roi.shape[1] // 42),
    )
    vertical_lines = 0
    horizontal_lines = 0
    if lines is not None:
        for line in lines[:, 0, :]:
            x1, y1, x2, y2 = [int(v) for v in line]
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            length = (dx * dx + dy * dy) ** 0.5
            if length < max(24, min(roi.shape[:2]) * 0.08):
                continue
            if dy >= dx * 1.8:
                vertical_lines += 1
            elif dx >= dy * 1.8:
                horizontal_lines += 1

    score = 0.0
    reasons = []
    if edge_ratio >= 0.050:
        score += 1.2
        reasons.append(f"board_edges:{edge_ratio:.3f}")
    if texture >= 520.0:
        score += 0.9
        reasons.append(f"board_texture:{texture:.0f}")
    if colour_ratio >= 0.30:
        score += 0.7
        reasons.append(f"board_colour:{colour_ratio:.2f}")
    if vertical_lines >= 3:
        score += 1.2
        reasons.append(f"vertical_reel_lines:{vertical_lines}")
    if horizontal_lines >= 2:
        score += 0.8
        reasons.append(f"horizontal_reel_lines:{horizontal_lines}")
    if vertical_lines >= 3 and horizontal_lines >= 2:
        score += 1.0
        reasons.append("reel_grid_geometry")

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


def feature_board_obstruction_score(img):
    if img is None or img.size == 0:
        return 0.0, []

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0, []

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


def has_large_center_payout_visual(img):
    if img is None or img.size == 0:
        return False

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return False

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
    has_jackpot_pick_screen = (
        has_any(joined, ["jackpot", "grand", "major", "minor", "mini"])
        and has_any(joined, ["please select", "select one", "pick", "choose"])
    )
    if has_jackpot_pick_screen:
        return False

    legal_or_vendor_terms = [
        "ver", "certified", "testlabs", "gaming", "institution", "regulations",
        "fair and just", "licensed", "license", "rights reserved", "pocket games soft",
        "pg soft", "omniplay", "omni play", "bmm", "mga", "ga ",
    ]
    has_legal_or_vendor = has_any(joined, legal_or_vendor_terms)
    if not has_legal_or_vendor:
        return False

    has_real_game_ui = has_any(joined, [
        "balance", "total bets", "total bet", "buy feature", "feature buy",
        "remaining", "total win", "collect", "jackpot", "grand", "major",
        "minor", "mini", "please select",
    ])
    cover_terms = [
        "get started", "win up to", "up to", "score a goal", "free games",
        "featuring", "licensed", "rights reserved",
    ]
    is_cover_like = has_any(joined, cover_terms)
    if has_real_game_ui and not is_cover_like:
        return False

    from .text_signals import get_box_bounds
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


def has_help_scroll_shell(img):
    if img is None or img.size == 0:
        return False

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return False

    center = img[int(h * 0.05):int(h * 0.92), int(w * 0.28):int(w * 0.72)]
    bottom = img[int(h * 0.86):int(h * 0.99), int(w * 0.28):int(w * 0.72)]
    if center.size == 0 or bottom.size == 0:
        return False

    center_hsv = cv2.cvtColor(center, cv2.COLOR_BGR2HSV)
    bottom_hsv = cv2.cvtColor(bottom, cv2.COLOR_BGR2HSV)
    center_sat = center_hsv[:, :, 1]
    center_val = center_hsv[:, :, 2]
    bottom_sat = bottom_hsv[:, :, 1]
    bottom_val = bottom_hsv[:, :, 2]

    dark_panel_ratio = float(np.mean((center_val <= 85) & (center_sat <= 110)))
    dark_bottom_ratio = float(np.mean((bottom_val <= 95) & (bottom_sat <= 115)))
    bright_button_ratio = float(np.mean((bottom_val >= 120) & (bottom_sat >= 80)))

    return (
        dark_panel_ratio >= 0.62
        and dark_bottom_ratio >= 0.48
        and bright_button_ratio >= 0.015
    )
