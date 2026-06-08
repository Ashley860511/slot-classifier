"""Local symbol icon export and quality selection helpers."""

from __future__ import annotations

import json
import math
import os
import shutil
import time
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - handled by caller
    Image = None
    ImageDraw = None


def _image_metrics(img) -> dict[str, Any]:
    """Score one cropped icon candidate without using AI."""
    if Image is None:
        return {"score": 0.0, "reason": "pillow_missing"}

    rgba = img.convert("RGBA")
    w, h = rgba.size
    if w <= 0 or h <= 0:
        return {"score": 0.0, "reason": "empty"}

    try:
        import cv2
        import numpy as np

        arr = np.array(rgba, dtype=np.uint8)
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3]
        bright = rgb.mean(axis=2)
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        mask = (alpha > 8) & (((chroma > 18) & (bright > 28)) | (bright > 85))

        if int(mask.sum()) < 18:
            return {"score": 0.0, "reason": "blank"}

        ys, xs = np.where(mask)
        x1, x2 = int(xs.min()), int(xs.max())
        y1, y2 = int(ys.min()), int(ys.max())
        bbox_w = x2 - x1 + 1
        bbox_h = y2 - y1 + 1

        margin = max(2, int(min(w, h) * 0.035))
        touch_left = x1 <= margin
        touch_top = y1 <= margin
        touch_right = x2 >= w - 1 - margin
        touch_bottom = y2 >= h - 1 - margin
        edge_touches = sum((touch_left, touch_top, touch_right, touch_bottom))

        content_ratio = float(mask.sum()) / float(w * h)
        bbox_fill = float(mask.sum()) / float(max(1, bbox_w * bbox_h))
        yellow_fill = (
            (alpha > 8)
            & (rgb[:, :, 0] > 180)
            & (rgb[:, :, 1] > 140)
            & (rgb[:, :, 2] < 80)
            & (chroma > 80)
        )
        white_fill = (alpha > 8) & (bright > 170) & (chroma < 55)
        red_fill = (
            (alpha > 8)
            & (rgb[:, :, 0] > 130)
            & (rgb[:, :, 1] < 120)
            & (rgb[:, :, 2] < 120)
            & (chroma > 45)
        )
        size_score = min(1.0, min(w, h) / 88.0)
        edge_score = max(0.0, 1.0 - edge_touches * 0.24)

        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sharp_score = min(1.0, sharpness / 520.0)

        component_mask = mask.astype(np.uint8) * 255
        num, _labels, stats, _centroids = cv2.connectedComponentsWithStats(component_mask, 8)
        sizeable_components = 0
        for i in range(1, num):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area >= max(14, int(mask.sum() * 0.025)):
                sizeable_components += 1
        fragment_penalty = max(0.0, min(0.22, (sizeable_components - 3) * 0.055))

        area_score = min(1.0, content_ratio / 0.34) * 0.55 + min(1.0, bbox_fill / 0.45) * 0.45
        score = (
            size_score * 0.24
            + edge_score * 0.34
            + sharp_score * 0.18
            + area_score * 0.24
            - fragment_penalty
        )

        return {
            "score": round(max(0.0, min(1.0, score)), 4),
            "width": w,
            "height": h,
            "content_ratio": round(content_ratio, 4),
            "bbox": [x1, y1, bbox_w, bbox_h],
            "edge_touches": edge_touches,
            "sharpness": round(sharpness, 2),
            "components": sizeable_components,
            "yellow_fill_ratio": round(float(yellow_fill.mean()), 4),
            "white_fill_ratio": round(float(white_fill.mean()), 4),
            "red_fill_ratio": round(float(red_fill.mean()), 4),
        }
    except Exception as exc:
        return {
            "score": round(min(1.0, min(w, h) / 96.0), 4),
            "width": w,
            "height": h,
            "reason": f"basic_score:{exc}",
        }


def _reject_text_only_candidate(img) -> tuple[bool, str]:
    """Reject payout numbers / text fragments before writing icon exports."""
    try:
        import numpy as np
    except Exception:
        return False, "no_numpy"

    rgba = img.convert("RGBA")
    w, h = rgba.size
    if w < 22 or h < 22:
        return True, "too_small"

    arr = np.array(rgba, dtype=np.uint8)
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3] > 8
    bright = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)

    fg = alpha & ((bright > 58) | (chroma > 28))
    colourful = alpha & (bright > 45) & (chroma > 35)
    white_text = alpha & (bright > 125) & (chroma < 45)
    yellow_text = alpha & (
        (rgb[:, :, 0] > 130) & (rgb[:, :, 1] > 100) &
        (rgb[:, :, 2] < 120) & (chroma > 35)
    )
    red_art = alpha & (rgb[:, :, 0] > 115) & (rgb[:, :, 1] < 105) & (rgb[:, :, 2] < 115) & (chroma > 38)
    blue_art = alpha & (rgb[:, :, 2] > 105) & (rgb[:, :, 0] < 130) & (chroma > 38)
    green_art = alpha & (rgb[:, :, 1] > 105) & (rgb[:, :, 0] < 145) & (chroma > 38)

    fg_ratio = float(fg.mean())
    colourful_ratio = float(colourful.mean())
    text_ratio = float((white_text | yellow_text).mean())
    yellow_ratio = float(yellow_text.mean())
    non_yellow_art_ratio = float((red_art | blue_art | green_art).mean())
    aspect = w / max(h, 1)
    dense_letter_badge = (
        min(w, h) >= 64
        and aspect <= 1.45
        and fg_ratio >= 0.45
        and colourful_ratio >= 0.10
        and text_ratio >= 0.10
    )

    if fg_ratio < 0.055:
        return True, "empty_or_text_sliver"
    if text_ratio > 0.045 and non_yellow_art_ratio < 0.050 and fg_ratio < 0.22:
        return True, "payout_text_only"
    if (
        not dense_letter_badge
        and yellow_ratio > 0.030
        and non_yellow_art_ratio < 0.030
        and colourful_ratio < 0.18
    ):
        return True, "yellow_number_only"
    if aspect > 1.35 and h <= 54 and text_ratio > 0.030 and non_yellow_art_ratio < 0.045:
        return True, "payout_number_strip"

    return False, "ok"


def _is_trusted_pp_paytable_crop_info(info: dict[str, Any]) -> bool:
    """Known PP web paytable supplemental boxes are trusted symbol crops."""
    source_page = str(info.get("source_page_path") or "").lower()
    if "low_score" in source_page:
        return False
    box = info.get("source_box") or []
    if len(box) != 4:
        return False
    try:
        x, y, w, h = [int(v) for v in box]
    except (TypeError, ValueError):
        return False
    def near(value, targets, tolerance=8):
        return any(abs(value - target) <= tolerance for target in targets)

    page2_multiplier = near(x, [72, 232, 390, 544], tolerance=16) and near(y, [216], tolerance=10) and 146 <= w <= 168 and 100 <= h <= 126
    return page2_multiplier


def _reject_low_quality_icon(metrics: dict[str, Any]) -> tuple[bool, str]:
    """Reject numeric scraps and clipped fragments after local quality scoring."""
    score = float(metrics.get("score", 0.0) or 0.0)
    w = int(metrics.get("width", 0) or 0)
    h = int(metrics.get("height", 0) or 0)
    content_ratio = float(metrics.get("content_ratio", 0.0) or 0.0)
    edge_touches = int(metrics.get("edge_touches", 0) or 0)
    yellow_fill_ratio = float(metrics.get("yellow_fill_ratio", 0.0) or 0.0)
    white_fill_ratio = float(metrics.get("white_fill_ratio", 0.0) or 0.0)
    red_fill_ratio = float(metrics.get("red_fill_ratio", 0.0) or 0.0)
    coloured_fill_ratio = yellow_fill_ratio + white_fill_ratio + red_fill_ratio

    if content_ratio < 0.085:
        return True, "low_content_text_scrap"
    if score < 0.52:
        return True, "low_quality_fragment"
    # Post-processing intentionally trims dark paytable backgrounds tightly.
    # Treat edge contact as clipping only when the crop still has lots of empty
    # margin; compact, high-content icon crops often touch all four edges but
    # are complete artwork.
    if edge_touches >= 3 and content_ratio < 0.55:
        if content_ratio >= 0.40 and coloured_fill_ratio >= 0.045 and min(w, h) >= 70:
            return False, "ok_coloured_edge_icon"
        return True, "clipped_fragment"
    if min(w, h) < 42:
        return True, "too_thin_fragment"
    if w < 48 and h > 70 and score < 0.86:
        return True, "vertical_fragment"
    if h < 46 and score < 0.86:
        if h >= 40 and content_ratio >= 0.50 and coloured_fill_ratio >= 0.045:
            return False, "ok_coloured_short_icon"
        return True, "horizontal_fragment"

    return False, "ok"


def _reject_final_symbol_candidate(metrics: dict[str, Any]) -> tuple[bool, str]:
    """
    Stricter filter for the final symbols/ folder.

    icon_candidates/ is intentionally broad for debugging.  The final folder is
    used as downstream input, so keep only crops that look like a standalone
    icon instead of payout text, reel screenshots, or clipped fragments.
    """
    score = float(metrics.get("score", 0.0) or 0.0)
    w = int(metrics.get("width", 0) or 0)
    h = int(metrics.get("height", 0) or 0)
    content_ratio = float(metrics.get("content_ratio", 0.0) or 0.0)
    edge_touches = int(metrics.get("edge_touches", 0) or 0)
    components = int(metrics.get("components", 0) or 0)
    yellow_fill_ratio = float(metrics.get("yellow_fill_ratio", 0.0) or 0.0)
    white_fill_ratio = float(metrics.get("white_fill_ratio", 0.0) or 0.0)
    red_fill_ratio = float(metrics.get("red_fill_ratio", 0.0) or 0.0)
    coloured_fill_ratio = yellow_fill_ratio + white_fill_ratio + red_fill_ratio
    bbox = metrics.get("bbox") or [0, 0, 0, 0]
    bbox_x = float(bbox[0] or 0)
    bbox_y = float(bbox[1] or 0)
    bbox_w = float(bbox[2] or 0)
    bbox_h = float(bbox[3] or 0)
    aspect = bbox_w / max(1.0, bbox_h)
    crop_aspect = w / max(1.0, h)

    if score < 0.60:
        return True, "final_low_score"
    if coloured_fill_ratio < 0.012 and content_ratio < 0.18 and max(w, h) <= 72:
        return True, "final_text_number_fragment"
    if content_ratio < 0.105:
        if score >= 0.74 and max(w, h) >= 95 and min(w, h) >= 45:
            return False, "ok_large_low_content_symbol"
        return True, "final_low_content"
    if min(w, h) < 50:
        if min(w, h) >= 40 and content_ratio >= 0.45 and coloured_fill_ratio >= 0.045:
            return False, "ok_coloured_small_icon"
        return True, "final_too_small"
    if aspect < 0.32 or aspect > 2.45:
        return True, "final_bad_aspect"
    if bbox_x > w * 0.42 or bbox_y > h * 0.40:
        return True, "final_partial_symbol"
    if (
        yellow_fill_ratio > 0.060
        and white_fill_ratio > 0.015
        and red_fill_ratio < 0.010
        and content_ratio > 0.50
    ):
        return True, "final_question_overlay"
    is_coloured_full_icon = (
        red_fill_ratio > 0.025
        or yellow_fill_ratio > 0.025
        or white_fill_ratio > 0.014
    )
    if edge_touches >= 3 and content_ratio > 0.60 and not is_coloured_full_icon:
        if score >= 0.56 and min(w, h) >= 42:
            return False, "ok_full_bleed_symbol"
        return True, "final_full_rect_fragment"
    if edge_touches >= 3 and content_ratio < 0.50:
        if content_ratio >= 0.40 and coloured_fill_ratio >= 0.045 and min(w, h) >= 70:
            return False, "ok_coloured_edge_icon"
        return True, "final_likely_clipped"
    if edge_touches >= 2 and score < 0.82 and not is_coloured_full_icon:
        return True, "final_edge_clipped"
    if components >= 9 and content_ratio < 0.22:
        return True, "final_noisy_fragment"
    if (
        bbox_h <= 45
        and content_ratio < 0.18
        and coloured_fill_ratio < 0.022
        and score < 0.92
    ):
        return True, "final_thin_symbol_fragment"
    if (
        bbox_h <= 50
        and content_ratio < 0.24
        and coloured_fill_ratio < 0.018
        and score < 0.90
    ):
        return True, "final_low_art_symbol_fragment"
    return False, "ok"


def _reject_portrait_fragment(rec: dict[str, Any]) -> tuple[bool, str]:
    """Drop partial logo fragments from portrait help pages after crop scoring."""
    crop_kind = str(rec.get("source_crop_kind") or "")
    size = rec.get("source_size") or []
    if not isinstance(size, (list, tuple)) or len(size) < 2:
        return False, "ok"
    source_w = int(size[0] or 0)
    source_h = int(size[1] or 0)
    if not (420 <= source_w <= 700 and source_h >= 760 and source_w / max(source_h, 1) <= 0.85):
        return False, "ok"

    metrics = rec.get("metrics") or {}
    w = int(metrics.get("width", 0) or 0)
    h = int(metrics.get("height", 0) or 0)
    edge_touches = int(metrics.get("edge_touches", 0) or 0)
    red_fill_ratio = float(metrics.get("red_fill_ratio", 0.0) or 0.0)
    white_fill_ratio = float(metrics.get("white_fill_ratio", 0.0) or 0.0)

    if crop_kind == "portrait_stacked_logo" and red_fill_ratio >= 0.10 and h < 95 and white_fill_ratio < 0.004:
        return True, "final_portrait_logo_fragment"
    if crop_kind == "legacy_full_page" and red_fill_ratio >= 0.05 and edge_touches >= 2:
        return True, "final_portrait_legacy_fragment"
    if crop_kind == "legacy_full_page" and edge_touches >= 4 and min(w, h) >= 60 and red_fill_ratio >= 0.035:
        return True, "final_portrait_legacy_fragment"
    return False, "ok"


def _allow_primary_paytable_low_score(rec: dict[str, Any], final_reason: str) -> bool:
    """Keep slightly low-scored crops from primary Help pages when they look like real art."""
    if final_reason != "final_low_score":
        return False

    source_page = str(rec.get("source_page_path") or "").lower()
    if "low_score" in source_page:
        return False

    if _is_large_full_page_source(rec):
        return False

    metrics = rec.get("metrics") or {}
    score = float(metrics.get("score", 0.0) or 0.0)
    w = int(metrics.get("width", 0) or 0)
    h = int(metrics.get("height", 0) or 0)
    content_ratio = float(metrics.get("content_ratio", 0.0) or 0.0)
    yellow_fill_ratio = float(metrics.get("yellow_fill_ratio", 0.0) or 0.0)
    white_fill_ratio = float(metrics.get("white_fill_ratio", 0.0) or 0.0)
    red_fill_ratio = float(metrics.get("red_fill_ratio", 0.0) or 0.0)
    coloured_fill_ratio = yellow_fill_ratio + white_fill_ratio + red_fill_ratio
    return (
        score >= 0.56
        and min(w, h) >= 45
        and content_ratio >= 0.16
        and coloured_fill_ratio >= 0.035
    )


def _allow_primary_paytable_edge_icon(info: dict[str, Any], metrics: dict[str, Any], reason: str) -> bool:
    """Allow real paytable artwork that only looks clipped because it fills the crop."""
    if reason not in {
        "clipped_fragment", "horizontal_fragment", "vertical_fragment",
        "final_likely_clipped", "final_edge_clipped", "final_full_rect_fragment",
    }:
        return False

    source_page = str(info.get("source_page_path") or "").lower()
    if "low_score" in source_page:
        return False

    if _is_large_full_page_source(info):
        return False

    score = float(metrics.get("score", 0.0) or 0.0)
    w = int(metrics.get("width", 0) or 0)
    h = int(metrics.get("height", 0) or 0)
    content_ratio = float(metrics.get("content_ratio", 0.0) or 0.0)
    yellow_fill_ratio = float(metrics.get("yellow_fill_ratio", 0.0) or 0.0)
    white_fill_ratio = float(metrics.get("white_fill_ratio", 0.0) or 0.0)
    red_fill_ratio = float(metrics.get("red_fill_ratio", 0.0) or 0.0)
    coloured_fill_ratio = yellow_fill_ratio + white_fill_ratio + red_fill_ratio
    return (
        score >= 0.55
        and min(w, h) >= 50
        and content_ratio >= 0.24
        and coloured_fill_ratio >= 0.030
    )


def _allow_structured_paytable_crop(info: dict[str, Any], metrics: dict[str, Any], reason: str) -> bool:
    """Allow tight card/logo crops extracted from validated paytable pages."""
    if reason not in {
        "final_low_score", "final_edge_clipped", "final_likely_clipped",
        "final_full_rect_fragment", "final_too_small",
    }:
        return False
    crop_kind = str(info.get("source_crop_kind") or "")
    if crop_kind not in {"portrait_paytable_card", "portrait_stacked_logo"}:
        return False
    score = float(metrics.get("score", 0.0) or 0.0)
    w = int(metrics.get("width", 0) or 0)
    h = int(metrics.get("height", 0) or 0)
    content_ratio = float(metrics.get("content_ratio", 0.0) or 0.0)
    yellow_fill_ratio = float(metrics.get("yellow_fill_ratio", 0.0) or 0.0)
    white_fill_ratio = float(metrics.get("white_fill_ratio", 0.0) or 0.0)
    red_fill_ratio = float(metrics.get("red_fill_ratio", 0.0) or 0.0)
    coloured_fill_ratio = yellow_fill_ratio + white_fill_ratio + red_fill_ratio
    if crop_kind == "portrait_paytable_card":
        return (
            score >= 0.72
            and min(w, h) >= 42
            and content_ratio >= 0.38
        )
    return (
        score >= 0.48
        and min(w, h) >= 42
        and content_ratio >= 0.12
        and coloured_fill_ratio >= 0.018
    )


def _is_large_full_page_source(info: dict[str, Any]) -> bool:
    """Return True for full-page Help crops where edge allowances are risky."""
    size = info.get("source_size") or []
    if not isinstance(size, (list, tuple)) or len(size) < 2:
        return False
    try:
        source_w = int(size[0])
        source_h = int(size[1])
    except Exception:
        return False
    return source_w >= 950 and source_h >= 780


def _reject_payout_text_bleed(img) -> tuple[bool, str]:
    """Reject symbol crops that still include payout-number rows."""
    try:
        import numpy as np
    except Exception:
        return False, "no_numpy"

    rgba = img.convert("RGBA")
    w, h = rgba.size
    if w < 42 or h < 54:
        return False, "ok"

    arr = np.array(rgba, dtype=np.uint8)
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3] > 8
    bright = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    text_like = alpha & (
        ((bright > 125) & (chroma < 58))
        | ((rgb[:, :, 0] > 135) & (rgb[:, :, 1] > 105) & (rgb[:, :, 2] < 125) & (chroma > 28))
    )
    colourful_art = alpha & (bright > 45) & (chroma > 42)

    lower_start = int(h * 0.48)
    lower_text = float(text_like[lower_start:, :].mean())
    upper_art = float(colourful_art[:lower_start, :].mean())
    if lower_text < 0.035 or upper_art < 0.045:
        return False, "ok"

    row_text = text_like.mean(axis=1)
    row_art = colourful_art.mean(axis=1)
    active_rows = (
        (row_text[lower_start:] > max(0.055, float(row_text.mean() + row_text.std() * 0.45)))
        & (row_art[lower_start:] < 0.060)
    )
    run = 0
    for value in active_rows.tolist():
        run = run + 1 if value else 0
        if run >= 2:
            return True, "final_payout_text_bleed"
    return False, "ok"


def _border_foreground_stats(img) -> dict[str, Any] | None:
    """
    Estimate real artwork foreground against the crop border colour.

    Full-page Help crops often have an opaque dark/purple background.  The basic
    alpha/brightness metrics then treat the whole crop as "content", which lets
    payout numbers and explanatory text survive.  Comparing pixels to the border
    colour gives a better signal for standalone symbol artwork.
    """
    try:
        import numpy as np
    except Exception:
        return None

    rgba = img.convert("RGBA")
    w, h = rgba.size
    if w < 24 or h < 24:
        return None

    arr = np.array(rgba, dtype=np.uint8)
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3] > 8
    border_w = max(3, min(w, h) // 12)
    border = np.concatenate([
        rgb[:border_w, :, :].reshape(-1, 3),
        rgb[-border_w:, :, :].reshape(-1, 3),
        rgb[:, :border_w, :].reshape(-1, 3),
        rgb[:, -border_w:, :].reshape(-1, 3),
    ])
    bg = np.median(border, axis=0)
    bg_bright = float(bg.mean())

    bright = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    foreground = alpha & (dist > 34) & ((chroma > 22) | (np.abs(bright - bg_bright) > 28))
    text_like = foreground & (
        ((bright > 125) & (chroma < 75))
        | ((rgb[:, :, 0] > 135) & (rgb[:, :, 1] > 105) & (rgb[:, :, 2] < 135) & (chroma > 25))
        | ((rgb[:, :, 1] > 120) & (rgb[:, :, 2] > 120) & (rgb[:, :, 0] < 135))
    )
    colourful = foreground & (chroma > 45) & (bright > 35)

    if int(foreground.sum()) <= 0:
        return {
            "foreground_ratio": 0.0,
            "text_ratio": 0.0,
            "colourful_ratio": 0.0,
            "bbox": [0, 0, 0, 0],
            "bbox_aspect": 0.0,
        }

    ys, xs = np.where(foreground)
    bbox = [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
    return {
        "foreground_ratio": float(foreground.mean()),
        "text_ratio": float(text_like.mean()),
        "colourful_ratio": float(colourful.mean()),
        "bbox": bbox,
        "bbox_aspect": bbox[2] / max(1.0, float(bbox[3])),
    }


def _reject_full_page_text_fragment(rec: dict[str, Any], img) -> tuple[bool, str]:
    """Reject labels/payout fragments from full-page or mobile-panel Help crops."""
    size = rec.get("source_size") or []
    if not isinstance(size, (list, tuple)) or len(size) < 2:
        return False, "ok"
    try:
        source_w = int(size[0])
        source_h = int(size[1])
    except Exception:
        return False, "ok"

    full_page_like = (
        (source_w >= 950 and source_h >= 780)
        or (source_h >= 850 and source_h >= source_w * 1.35)
        or (
            source_w >= 950
            and source_h >= 520
            and source_w >= source_h * 1.45
            and str(rec.get("source_crop_kind") or "") == "legacy_full_page"
        )
    )
    if not full_page_like:
        return False, "ok"

    stats = _border_foreground_stats(img)
    if not stats:
        return False, "ok"

    fg_ratio = float(stats["foreground_ratio"])
    text_ratio = float(stats["text_ratio"])
    colour_ratio = float(stats["colourful_ratio"])
    bbox = stats["bbox"]
    bbox_aspect = float(stats["bbox_aspect"])
    crop_aspect = img.width / max(1.0, float(img.height))
    try:
        import numpy as np
        arr = np.array(img.convert("RGB"), dtype=np.uint8)
        bright = arr.mean(axis=2)
        chroma = arr.max(axis=2) - arr.min(axis=2)
        white_tile_ratio = float(((bright > 145) & (chroma < 52)).mean())
    except Exception:
        white_tile_ratio = 0.0

    # Thin text rows such as "SYMBOL", "3 - 36.00", or explanatory sentences.
    if bbox[3] <= max(30, img.height * 0.45) and bbox_aspect >= 1.55 and text_ratio >= 0.035:
        return True, "final_full_page_text_row"
    if bbox_aspect >= 1.45 and fg_ratio < 0.09 and text_ratio >= 0.020:
        return True, "final_full_page_sparse_text_row"

    # Wide crops with a small icon plus adjacent sentence/label text.
    if crop_aspect >= 1.55 and text_ratio >= 0.09 and colour_ratio < 0.30:
        return True, "final_full_page_label_bleed"

    # Payout value blocks on dark Help backgrounds are mostly yellow/white text.
    # Run this before the tile-card allowance because a cropped payout panel can
    # otherwise look like a bright rectangular card.
    if text_ratio >= 0.24 and colour_ratio <= 0.12:
        return True, "final_full_page_text_dominant_panel"
    if text_ratio >= 0.14 and colour_ratio <= 0.14 and text_ratio >= colour_ratio * 1.25:
        return True, "final_full_page_payout_text_panel"

    is_full_tile_card = (
        0.55 <= crop_aspect <= 1.75
        and fg_ratio >= 0.30
        and white_tile_ratio >= 0.22
        and colour_ratio >= 0.030
        and bbox[2] >= img.width * 0.55
        and bbox[3] >= img.height * 0.55
    )
    if is_full_tile_card:
        return False, "ok_full_tile_card"

    if fg_ratio < 0.025 and crop_aspect >= 1.25:
        return True, "final_full_page_sparse_background_text"
    if fg_ratio < 0.055 and max(img.width, img.height) >= 140:
        return True, "final_full_page_background_fragment"

    # Low-art foreground dominated by text colours.  Real A/K/Q/J/10 symbols
    # have much denser colourful artwork, so this avoids removing letter icons.
    if fg_ratio < 0.22 and text_ratio >= 0.055 and text_ratio >= colour_ratio * 0.55:
        return True, "final_full_page_text_fragment"

    return False, "ok"


def _final_quality_rank(rec: dict[str, Any]) -> tuple[float, float, float, str]:
    """Rank final candidates by completeness first, then sharp local score."""
    metrics = rec.get("metrics") or {}
    score = float(rec.get("score", 0.0) or 0.0)
    w = float(metrics.get("width", 0) or 0)
    h = float(metrics.get("height", 0) or 0)
    content_ratio = float(metrics.get("content_ratio", 0.0) or 0.0)
    edge_touches = float(metrics.get("edge_touches", 0) or 0)
    bbox = metrics.get("bbox") or [0, 0, 0, 0]
    bbox_w = float(bbox[2] or 0)
    bbox_h = float(bbox[3] or 0)

    bbox_width_fill = bbox_w / max(1.0, w)
    bbox_height_fill = bbox_h / max(1.0, h)
    shape_fill = min(1.0, bbox_width_fill) * min(1.0, bbox_height_fill)
    enough_canvas = min(1.0, min(w, h) / 82.0)
    edge_penalty = min(0.35, edge_touches * 0.10)
    completeness = (
        shape_fill * 0.42
        + min(1.0, content_ratio / 0.42) * 0.24
        + enough_canvas * 0.20
        + score * 0.14
        - edge_penalty
    )
    if str(rec.get("source_crop_kind") or "") == "mahjong_tile":
        tile_h_bonus = min(1.0, h / 190.0) * 0.26
        tile_w_bonus = min(1.0, w / 180.0) * 0.10
        short_tile_penalty = 0.32 if h < 180 else 0.0
        completeness += tile_h_bonus + tile_w_bonus - short_tile_penalty
    return (completeness, score, content_ratio, str(rec.get("candidate_id", "")))


def _dhash(img) -> int:
    """Small perceptual hash used to group repeated crops of the same icon.

    Center-crops 20% of each edge before hashing so the hash reflects the
    symbol content rather than tile borders or background padding.  This
    prevents white-background mahjong tiles (發、中、白板、八萬…) from being
    collapsed into the same group just because their borders look identical.
    """
    if Image is None:
        return 0
    w, h = img.size
    cx0 = int(w * 0.20)
    cy0 = int(h * 0.20)
    cx1 = w - cx0
    cy1 = h - cy0
    if cx1 > cx0 and cy1 > cy0:
        img = img.crop((cx0, cy0, cx1, cy1))
    gray = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = list(gray.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | int(px[y * 9 + x] > px[y * 9 + x + 1])
    return bits


def _hamming(a: int, b: int) -> int:
    return int((a ^ b).bit_count())


def _icons_visually_same(path_a: str, path_b: str) -> bool:
    """
    Confirm two crops are truly the same symbol before grouping.

    The small dHash is intentionally fuzzy, but stylized card letters can collide
    (for example Q and a).  A lightweight pixel comparison prevents those false
    merges while still grouping near-identical repeated crops.
    """
    try:
        with Image.open(path_a) as img_a, Image.open(path_b) as img_b:
            a = img_a.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
            b = img_b.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
        import numpy as np

        # Compare only the center 60% to focus on symbol content, not borders
        arr_a = np.array(a, dtype=np.float32)
        arr_b = np.array(b, dtype=np.float32)
        s = 64
        c0, c1 = int(s * 0.20), int(s * 0.80)
        arr_a = arr_a[c0:c1, c0:c1]
        arr_b = arr_b[c0:c1, c0:c1]
        rgb_diff = float(np.mean(np.abs(arr_a[:, :, :3] - arr_b[:, :, :3])) / 255.0)
        alpha_diff = float(np.mean(np.abs(arr_a[:, :, 3] - arr_b[:, :, 3])) / 255.0)
        return rgb_diff <= 0.055 and alpha_diff <= 0.018
    except Exception:
        return False


def _icon_rgb_alpha_diff(path_a: str, path_b: str, size: int = 96) -> tuple[float, float] | None:
    try:
        with Image.open(path_a) as img_a, Image.open(path_b) as img_b:
            a = img_a.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
            b = img_b.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        import numpy as np

        arr_a = np.array(a, dtype=np.float32)
        arr_b = np.array(b, dtype=np.float32)
        rgb_diff = float(np.mean(np.abs(arr_a[:, :, :3] - arr_b[:, :, :3])) / 255.0)
        alpha_diff = float(np.mean(np.abs(arr_a[:, :, 3] - arr_b[:, :, 3])) / 255.0)
        return rgb_diff, alpha_diff
    except Exception:
        return None


def _records_visually_same(rec_a: dict[str, Any], rec_b: dict[str, Any]) -> bool:
    """
    Compare two final candidates with crop-kind awareness.

    Portrait/mobile paytables often render A/K/Q/9/10 on identical card
    backgrounds.  A loose whole-crop comparison then collapses different
    symbols into the same group.  Use a stricter threshold for those structured
    card crops while keeping the regular fuzzy grouping for other providers.
    """
    kind_a = str(rec_a.get("source_crop_kind") or "")
    kind_b = str(rec_b.get("source_crop_kind") or "")
    if kind_a == "portrait_paytable_card" and kind_b == "portrait_paytable_card":
        diffs = _icon_rgb_alpha_diff(rec_a["path"], rec_b["path"], size=96)
        if diffs is None:
            return False
        rgb_diff, alpha_diff = diffs
        return rgb_diff <= 0.014 and alpha_diff <= 0.018
    return _icons_visually_same(rec_a["path"], rec_b["path"])


def _save_icon(img, out_path: Path, max_side: int = 240) -> Path:
    """Save the crop at its natural aspect ratio without synthetic padding."""
    rgba = img.convert("RGBA")
    if max(rgba.size) > max_side:
        rgba.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        rgba.save(out_path, "PNG")
        return out_path
    except PermissionError:
        fallback = out_path.with_name(f"{out_path.stem}_{int(time.time())}{out_path.suffix}")
        try:
            rgba.save(fallback, "PNG")
            return fallback
        except PermissionError:
            export_root = Path.cwd() / "symbol_table_exports" / f"{out_path.parent.name}_{int(time.time())}"
            export_root.mkdir(parents=True, exist_ok=True)
            final_fallback = export_root / out_path.name
            rgba.save(final_fallback, "PNG")
            return final_fallback


def _prepare_output_dir(path: Path, *, clean: bool = False) -> Path:
    """Create an output folder, falling back to a timestamped sibling if needed."""
    def _is_writable_dir(candidate: Path) -> bool:
        try:
            probe = candidate / f"write_probe_{int(time.time())}.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def _try_mkdir(candidate: Path) -> Path | None:
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate if _is_writable_dir(candidate) else None
        except FileExistsError:
            return None
        except PermissionError:
            return None

    if path.exists() and clean:
        try:
            if path.is_dir() and _is_writable_dir(path):
                for child in path.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                return path
        except OSError:
            pass

    if path.exists():
        try:
            if not any(path.iterdir()) and _is_writable_dir(path):
                return path
        except PermissionError:
            pass
        base = path.with_name(f"{path.name}_{int(time.time())}")
        for idx in range(100):
            candidate = base if idx == 0 else base.with_name(f"{base.name}_{idx:02d}")
            made = _try_mkdir(candidate)
            if made is not None:
                return made
    else:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except PermissionError:
            pass

    fallback_base = Path.cwd() / "symbol_table_exports" / f"{path.name}_{int(time.time())}"
    for idx in range(100):
        candidate = fallback_base if idx == 0 else fallback_base.with_name(f"{fallback_base.name}_{idx:02d}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
        except PermissionError:
            continue

    fallback = Path.cwd() / "symbol_table_exports" / f"{path.name}_{int(time.time())}_last"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    except PermissionError:
        tmp_fallback = Path(os.environ.get("TEMP", str(Path.cwd()))) / f"{path.name}_{int(time.time())}"
        tmp_fallback.mkdir(parents=True, exist_ok=True)
        return tmp_fallback


def _write_contact_sheet(records: list[dict[str, Any]], out_path: Path, title: str) -> None:
    if Image is None or ImageDraw is None or not records:
        return
    thumb = 96
    label_h = 30
    cols = min(8, max(1, math.ceil(math.sqrt(len(records)))))
    rows = math.ceil(len(records) / cols)
    w = cols * 132 + 24
    h = rows * (thumb + label_h + 16) + 54
    sheet = Image.new("RGB", (w, h), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 10), title, fill=(30, 30, 30))
    for idx, rec in enumerate(records):
        x = 12 + (idx % cols) * 132
        y = 42 + (idx // cols) * (thumb + label_h + 16)
        try:
            icon = Image.open(rec["path"]).convert("RGBA")
            icon.thumbnail((thumb, thumb), Image.Resampling.LANCZOS)
            sheet.paste(
                icon,
                (x + (thumb - icon.width) // 2, y + (thumb - icon.height) // 2),
                icon,
            )
        except Exception:
            pass
        label = rec.get("label") or rec.get("candidate_id") or rec.get("final_id") or str(idx)
        draw.text((x, y + thumb + 3), label[:18], fill=(40, 40, 40))
        draw.text((x, y + thumb + 16), f"score {rec.get('score', 0):.2f}", fill=(90, 90, 90))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, "JPEG", quality=92)


def export_icon_crops(icon_images: list, symbol_table_dir: Path) -> dict[str, Any]:
    """
    Save every OpenCV icon crop and a locally selected best set.

    Output:
      symbol_table/icon_candidates/
      symbol_table/symbols/
      symbol_table/icon_export_metadata.json
    """
    if Image is None:
        return {"candidate_count": 0, "final_count": 0, "error": "pillow_missing"}

    candidates_dir = _prepare_output_dir(symbol_table_dir / "icon_candidates", clean=True)
    final_dir = _prepare_output_dir(symbol_table_dir / "symbols", clean=True)

    records: list[dict[str, Any]] = []
    for idx, img in enumerate(icon_images):
        trusted_pp_crop = _is_trusted_pp_paytable_crop_info(img.info)
        mahjong_tile_crop = str(img.info.get("source_crop_kind") or "") == "mahjong_tile"
        rejected, reject_reason = _reject_text_only_candidate(img)
        if rejected and mahjong_tile_crop and reject_reason in {"text_only", "flat_symbol_fragment", "small_text_fragment"}:
            rejected = False
            reject_reason = "ok_mahjong_tile_crop"
        if rejected:
            continue
        metrics = _image_metrics(img)
        rejected, quality_reason = _reject_low_quality_icon(metrics)
        if rejected and mahjong_tile_crop and quality_reason in {
            "low_score", "edge_clipped", "likely_clipped", "too_small",
        }:
            rejected = False
            quality_reason = "ok_mahjong_tile_crop"
        if rejected and _allow_primary_paytable_edge_icon(img.info, metrics, quality_reason):
            rejected = False
            quality_reason = "ok_primary_paytable_edge_icon"
        if rejected and not trusted_pp_crop:
            continue
        metrics["export_filter"] = reject_reason
        metrics["quality_filter"] = quality_reason
        score = float(metrics.get("score", 0.0))
        if trusted_pp_crop and score < 0.35:
            continue
        candidate_id = f"candidate_{idx:03d}"
        filename = f"{candidate_id}_score_{score:.2f}.png"
        out_path = candidates_dir / filename
        out_path = _save_icon(img, out_path)
        phash = _dhash(img)
        records.append({
            "candidate_id": candidate_id,
            "path": str(out_path),
            "score": score,
            "hash": f"{phash:016x}",
            "source_page_index": img.info.get("source_page_index"),
            "source_page_path": img.info.get("source_page_path"),
            "source_box_index": img.info.get("source_box_index"),
            "source_box": img.info.get("source_box"),
            "source_crop_box": img.info.get("source_crop_box"),
            "source_size": img.info.get("source_size"),
            "source_crop_kind": img.info.get("source_crop_kind"),
            "trusted_pp_paytable_crop": trusted_pp_crop,
            "metrics": metrics,
        })

    # Group visually similar crops; keep the highest-quality crop per group.
    # The broad candidate folder remains useful for inspection, while the final
    # symbols folder uses a stricter quality gate.
    final_pool = []
    for rec in records:
        final_rejected, final_reason = _reject_final_symbol_candidate(rec.get("metrics", {}))
        trusted_pp_crop = bool(rec.get("trusted_pp_paytable_crop"))
        mahjong_tile_crop = str(rec.get("source_crop_kind") or "") == "mahjong_tile"
        if mahjong_tile_crop:
            crop_box = rec.get("source_crop_box") or []
            if isinstance(crop_box, (list, tuple)) and len(crop_box) >= 2 and int(crop_box[1] or 0) <= 1:
                final_rejected = True
                final_reason = "final_mahjong_tile_source_edge_clipped"
        if final_rejected and mahjong_tile_crop and final_reason in {
            "final_low_score", "final_edge_clipped", "final_likely_clipped",
            "final_full_rect_fragment", "final_too_small",
        }:
            final_rejected = False
            final_reason = "ok_mahjong_tile_crop"
        if final_rejected and trusted_pp_crop and final_reason in {
            "final_low_score", "final_edge_clipped", "final_likely_clipped",
            "final_full_rect_fragment", "final_too_small",
        }:
            final_rejected = False
            final_reason = "ok_trusted_pp_paytable_crop"
        if final_rejected and _allow_primary_paytable_low_score(rec, final_reason):
            final_rejected = False
            final_reason = "ok_primary_paytable_low_score"
        if final_rejected and _allow_primary_paytable_edge_icon(rec, rec.get("metrics") or {}, final_reason):
            final_rejected = False
            final_reason = "ok_primary_paytable_edge_icon"
        if final_rejected and _allow_structured_paytable_crop(rec, rec.get("metrics") or {}, final_reason):
            final_rejected = False
            final_reason = "ok_structured_paytable_crop"
        if not final_rejected:
            try:
                with Image.open(rec["path"]) as rec_img:
                    bleed_rejected, bleed_reason = _reject_payout_text_bleed(rec_img)
                    if not bleed_rejected:
                        bleed_rejected, bleed_reason = _reject_full_page_text_fragment(rec, rec_img)
                    if not bleed_rejected:
                        bleed_rejected, bleed_reason = _reject_portrait_fragment(rec)
                    if bleed_rejected and mahjong_tile_crop and bleed_reason in {
                        "final_payout_text_bleed",
                        "final_full_page_text_dominant_panel",
                        "final_full_page_payout_text_panel",
                        "final_full_page_text_fragment",
                    }:
                        bleed_rejected = False
                        bleed_reason = "ok_mahjong_tile_crop"
                if bleed_rejected:
                    final_rejected = True
                    final_reason = bleed_reason
            except OSError:
                final_rejected = True
                final_reason = "final_unreadable"
        rec["final_filter"] = final_reason
        if not final_rejected:
            final_pool.append(rec)

    groups: list[dict[str, Any]] = []
    for rec in sorted(final_pool, key=_final_quality_rank, reverse=True):
        rec_hash = int(rec["hash"], 16)
        matched = None
        for group in groups:
            if (
                _hamming(rec_hash, int(group["hash"], 16)) <= 5
                and _records_visually_same(rec, group["best"])
            ):
                matched = group
                break
        if matched is None:
            groups.append({
                "group_id": len(groups),
                "hash": rec["hash"],
                "best": rec,
                "members": [rec["candidate_id"]],
            })
        else:
            matched["members"].append(rec["candidate_id"])

    final_records = []
    for group in sorted(groups, key=lambda g: g["best"].get("candidate_id", "")):
        best = group["best"]
        final_id = f"symbol_candidate_{group['group_id']:03d}"
        final_path = final_dir / f"{final_id}_from_{best['candidate_id']}_score_{best['score']:.2f}.png"
        with Image.open(best["path"]) as best_img:
            final_path = _save_icon(best_img.copy(), final_path)
        final_rec = {
            **best,
            "final_id": final_id,
            "path": str(final_path),
            "group_members": group["members"],
        }
        final_records.append(final_rec)

    metadata = {
        "candidate_count": len(records),
        "final_count": len(final_records),
        "candidates_dir": str(candidates_dir),
        "symbols_dir": str(final_dir),
        "final_icons_dir": str(final_dir),
        "candidates": records,
        "final_icons": final_records,
    }
    run_suffix = ""
    if final_dir.name.startswith("symbols_"):
        run_suffix = final_dir.name.removeprefix("symbols_")
    elif candidates_dir.name.startswith("icon_candidates_"):
        run_suffix = candidates_dir.name.removeprefix("icon_candidates_")

    metadata_path = symbol_table_dir / "icon_export_metadata.json"
    try:
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    except PermissionError:
        metadata_path = candidates_dir.parent / "icon_export_metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    if run_suffix:
        try:
            timestamped_metadata = candidates_dir.parent / f"icon_export_metadata_{run_suffix}.json"
            timestamped_metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    try:
        _write_contact_sheet(records, symbol_table_dir / "icon_candidates_contact_sheet.jpg", "All OpenCV icon candidates")
        _write_contact_sheet(final_records, symbol_table_dir / "final_icons_contact_sheet.jpg", "Local best icon candidates")
    except PermissionError:
        _write_contact_sheet(records, candidates_dir.parent / "icon_candidates_contact_sheet.jpg", "All OpenCV icon candidates")
        _write_contact_sheet(final_records, candidates_dir.parent / "final_icons_contact_sheet.jpg", "Local best icon candidates")
    if run_suffix:
        try:
            _write_contact_sheet(records, candidates_dir.parent / f"icon_candidates_contact_sheet_{run_suffix}.jpg", "All OpenCV icon candidates")
            _write_contact_sheet(final_records, candidates_dir.parent / f"final_icons_contact_sheet_{run_suffix}.jpg", "Local best icon candidates")
        except OSError:
            pass
    metadata["metadata_path"] = str(metadata_path)
    return metadata
