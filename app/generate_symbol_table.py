#!/usr/bin/env python3
"""
generate_symbol_table.py - local symbol icon extractor.

For each classified video in project/output/<id>/, reads Help/Paytable screenshots,
finds likely paytable pages with local image features + OCR, uses OpenCV to crop
symbol icons, then writes local icon candidate folders for later review/reporting.
Claude/API usage is opt-in only via --with-ai.

Usage:
    python generate_symbol_table.py                       # local icon export for all videos
    python generate_symbol_table.py --video-id 9          # local icon export for one video
    python generate_symbol_table.py --debug               # also save intermediate debug images
    python generate_symbol_table.py --with-ai --api-key sk-...  # legacy Claude + HTML path
    python generate_symbol_table.py --output-root PATH    # custom output root
"""

import argparse
import base64
import html
import io
import json
import os
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None  # Pillow not installed; cropping will be skipped

from symbol_table.debug_io import safe_save_debug_image, safe_write_debug_text
from symbol_table.paths import (
    collect_all_help_images,
    collect_basegame_images,
    collect_help_images,
    collect_paytable_scan_images,
)
from symbol_table.paytable_detector import (
    find_paytable_pages,
    find_paytable_pages_local,
    write_paytable_candidates_debug,
)
from symbol_table.icon_export import export_icon_crops

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PACKAGE_ROOT / "project" / "output"

# Minimum pixel size for a cropped symbol to be considered usable.
# If the crop is smaller than this, we flag it for Basegame fallback.
MIN_SYMBOL_SIZE = 60   # pixels (width or height)

def b64_encode(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode()


def b64_encode_pil(img) -> str:
    """Encode a PIL Image to base64 JPEG string."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return base64.standard_b64encode(buf.getvalue()).decode()

# ??? Icon detection (OpenCV ??no AI needed for coordinates) ???????????????????



def _box_overlap_ratio(a, b):
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    small = max(1, min(aw * ah, bw * bh))
    return inter / small


def _score_icon_box_for_art(dialog_img, box):
    """Score likely artwork boxes without over-favouring tight fragments."""
    try:
        import numpy as np
    except ImportError:
        return 0.0

    x, y, w, h = [int(v) for v in box]
    if w <= 0 or h <= 0:
        return 0.0
    W, H = dialog_img.size
    x = max(0, min(W - 1, x))
    y = max(0, min(H - 1, y))
    w = max(1, min(W - x, w))
    h = max(1, min(H - y, h))

    arr = np.array(dialog_img.convert("RGB"), dtype=np.float32)[y:y + h, x:x + w]
    if arr.size == 0:
        return 0.0
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    colorful = ((bright > 42) & (chroma > 38))
    color_ratio = float(colorful.mean())
    white_text = float(((bright > 135) & (chroma < 72)).mean())
    yellow_text = float(((arr[:, :, 0] > 130) & (arr[:, :, 1] > 92) & (arr[:, :, 2] < 135)).mean())
    aspect = w / max(h, 1)
    aspect_score = max(0.0, 1.0 - abs(aspect - 1.0) / 2.2)
    size_score = min(1.0, max(w, h) / 96.0)
    complete_size_bonus = min(0.55, (w * h) / 18000.0)
    text_penalty = white_text * 0.55 + yellow_text * 0.45
    return color_ratio * 2.25 + aspect_score * 0.28 + size_score * 0.24 + complete_size_bonus - text_penalty


def _dedupe_boxes(boxes, iou_threshold=0.42, image=None):
    """Merge near-duplicate icon boxes while keeping complete artwork boxes."""
    def area(b):
        return max(0, b[2]) * max(0, b[3])

    def iou(a, b):
        ax1, ay1, aw, ah = a
        bx1, by1, bw, bh = b
        ax2, ay2 = ax1 + aw, ay1 + ah
        bx2, by2 = bx1 + bw, by1 + bh
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        union = area(a) + area(b) - inter
        return inter / union if union else 0.0

    kept = []
    for box in sorted(boxes, key=area, reverse=True):
        if all(iou(box, old) < iou_threshold for old in kept):
            kept.append(box)
    return sorted(kept, key=lambda b: (b[1], b[0]))


def detect_mahjong_tile_boxes_in_dialog(dialog_img) -> list:
    """Detect full white mahjong-style symbol tiles before component splitting."""
    if Image is None:
        return []
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []

    arr = np.array(dialog_img.convert("RGB"), dtype=np.uint8)
    H, W = arr.shape[:2]
    if W < 900 or H < 500:
        return []

    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    white_tile = (bright > 145) & (chroma < 52)
    white_tile[: int(H * 0.10), :] = False
    white_tile[int(H * 0.94) :, :] = False
    white_tile = cv2.morphologyEx(
        white_tile.astype("uint8") * 255,
        cv2.MORPH_CLOSE,
        np.ones((5, 5), np.uint8),
        iterations=1,
    )

    num, _labels, stats, _centroids = cv2.connectedComponentsWithStats(white_tile, 8)
    boxes = []
    min_area = max(1400, int(W * H * 0.004))
    max_area = int(W * H * 0.055)
    for idx in range(1, num):
        x, y, w, h, area = [int(v) for v in stats[idx]]
        if area < min_area or area > max_area:
            continue
        if w < W * 0.045 or h < H * 0.070:
            continue
        if w > W * 0.24 or h > H * 0.28:
            continue
        aspect = w / max(h, 1)
        if not (0.58 <= aspect <= 2.15):
            continue

        crop = arr[y:y + h, x:x + w]
        crop_b = crop.mean(axis=2)
        crop_c = crop.max(axis=2) - crop.min(axis=2)
        white_ratio = float(((crop_b > 145) & (crop_c < 52)).mean())
        colour_ratio = float(((crop_c > 42) & (crop_b > 35)).mean())
        if white_ratio < 0.20 or colour_ratio < 0.015:
            continue

        pad = max(4, int(round(min(w, h) * 0.045)))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(W, x + w + pad)
        y2 = min(H, y + h + pad)
        boxes.append((x1, y1, x2 - x1, y2 - y1))

    boxes = _dedupe_boxes(boxes, iou_threshold=0.25, image=dialog_img)
    if len(boxes) >= 3:
        print(f"    Mahjong tile detector found {len(boxes)} full-tile candidates")
        return boxes
    return []


def _merge_stacked_symbol_boxes(boxes, image_w, image_h):
    """Merge vertically split symbol art, such as a bonus vessel plus its label."""
    merged = []
    for i, a in enumerate(boxes):
        ax, ay, aw, ah = [int(v) for v in a]
        if aw < image_w * 0.16 or ah < image_h * 0.055:
            continue
        for j, b in enumerate(boxes):
            if i == j:
                continue
            bx, by, bw, bh = [int(v) for v in b]
            if bw < image_w * 0.16 or bh < image_h * 0.045:
                continue
            top, bottom = (a, b) if ay <= by else (b, a)
            tx, ty, tw, th = [int(v) for v in top]
            bx, by, bw, bh = [int(v) for v in bottom]
            vertical_gap = by - (ty + th)
            if vertical_gap > max(10, int(min(th, bh) * 0.28)):
                continue
            overlap = max(0, min(tx + tw, bx + bw) - max(tx, bx))
            if overlap / float(max(1, min(tw, bw))) < 0.58:
                continue
            ux1 = min(tx, bx)
            uy1 = min(ty, by)
            ux2 = max(tx + tw, bx + bw)
            uy2 = max(ty + th, by + bh)
            uw, uh = ux2 - ux1, uy2 - uy1
            if uh > image_h * 0.34 or uw > image_w * 0.38:
                continue
            if uh < max(th, bh) * 1.10:
                continue
            merged.append((ux1, uy1, uw, uh))
    return merged


def _infer_portrait_paytable_card_boxes(boxes, image_w, image_h):
    """Infer missing low-saturation card boxes in mobile portrait paytables."""
    try:
        import numpy as np
    except ImportError:
        return []

    aspect = image_w / max(image_h, 1)
    if not (420 <= image_w <= 700 and image_h >= 760 and aspect <= 0.85):
        return []

    card_boxes = [
        tuple(int(v) for v in box)
        for box in boxes
        if is_portrait_paytable_card_box(box, image_w, image_h)
    ]
    if len(card_boxes) < 2:
        return []

    centers_x = sorted((x + w / 2.0) for x, _y, w, _h in card_boxes)
    clustered = []
    for cx in centers_x:
        if not clustered or abs(cx - clustered[-1][-1]) > image_w * 0.10:
            clustered.append([cx])
        else:
            clustered[-1].append(cx)
    col_centers = [sum(group) / len(group) for group in clustered]
    if len(col_centers) < 3:
        # NEZHA-style tables have three symbol columns; infer the third from
        # the observed spacing when one low-chroma card was missed.
        spacings = [
            col_centers[i + 1] - col_centers[i]
            for i in range(len(col_centers) - 1)
            if image_w * 0.12 <= col_centers[i + 1] - col_centers[i] <= image_w * 0.24
        ]
        step = float(np.median(spacings)) if spacings else image_w * 0.19
        while len(col_centers) < 3:
            left_candidate = col_centers[0] - step
            right_candidate = col_centers[-1] + step
            if left_candidate >= image_w * 0.22:
                col_centers.insert(0, left_candidate)
            elif right_candidate <= image_w * 0.86:
                col_centers.append(right_candidate)
            else:
                break
    col_centers = sorted(col_centers[:3])

    rows = []
    for box in card_boxes:
        x, y, w, h = box
        cy = y + h / 2.0
        matched = None
        for row in rows:
            if abs(cy - row["cy"]) <= image_h * 0.045:
                matched = row
                break
        if matched is None:
            rows.append({"cy": cy, "boxes": [box]})
        else:
            matched["boxes"].append(box)
            matched["cy"] = sum(b[1] + b[3] / 2.0 for b in matched["boxes"]) / len(matched["boxes"])

    inferred = []
    for row in rows:
        row_boxes = row["boxes"]
        if len(row_boxes) < 2:
            continue
        avg_w = int(round(sum(b[2] for b in row_boxes) / len(row_boxes)))
        avg_h = int(round(sum(b[3] for b in row_boxes) / len(row_boxes)))
        avg_cy = row["cy"]
        existing_centers = [b[0] + b[2] / 2.0 for b in row_boxes]
        for cx in col_centers:
            if any(abs(cx - old_cx) <= avg_w * 0.42 for old_cx in existing_centers):
                continue
            x = int(round(cx - avg_w / 2.0))
            y = int(round(avg_cy - avg_h / 2.0))
            if x < image_w * 0.08 or x + avg_w > image_w * 0.94:
                continue
            if y < image_h * 0.14 or y + avg_h > image_h * 0.80:
                continue
            inferred.append((max(0, x), max(0, y), min(avg_w, image_w - x), min(avg_h, image_h - y)))
    return inferred


def detect_icon_components_in_dialog(dialog_img) -> list:
    """
    Layout-agnostic symbol detector.

    Instead of assuming a two-column paytable, find independent colourful artwork
    components and reject pure text / payout-number fragments later.  This works
    better for web-style Help pages while still serving as a first pass for PG
    dialog paytables.
    """
    if Image is None:
        return []
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []

    try:
        arr = np.array(dialog_img.convert("RGB"), dtype=np.uint8)
        H, W = arr.shape[:2]
        bright = arr.mean(axis=2).astype(np.float32)
        chroma = (arr.max(axis=2) - arr.min(axis=2)).astype(np.float32)

        # Ignore browser/title bars and the very bottom navigation/footer area.
        y0 = int(H * 0.08)
        y1 = int(H * 0.92)

        # Colourful / high-contrast artwork mask.  Keep gold/red/blue/green art,
        # but avoid pale white body text when chroma is low.
        mask = (((chroma > 42) & (bright > 34)) |
                ((chroma > 28) & (bright > 92) & (bright < 245)))
        mask[:y0, :] = False
        mask[y1:, :] = False

        # Suppress long horizontal rule/paragraph text bands.  Symbols are compact;
        # paragraphs have many light pixels spanning a wide row range.
        light_text = (bright > 135) & (chroma < 70)
        row_density = light_text.mean(axis=1)
        text_rows = row_density > max(0.16, float(row_density.mean() + row_density.std() * 1.3))
        # Do not remove the whole row; only reduce low-chroma light text pixels.
        mask[text_rows, :] &= (chroma[text_rows, :] > 55)

        m = mask.astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)
        m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=1)

        num, labels, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        boxes = []
        min_area = max(45, int(W * H * 0.000035))
        max_area = int(W * H * 0.055)
        for i in range(1, num):
            x, y, w, h, area = [int(v) for v in stats[i]]
            if area < min_area or area > max_area:
                continue
            if w < max(10, int(W * 0.010)) or h < max(12, int(H * 0.014)):
                continue
            if w > W * 0.22 or h > H * 0.22:
                continue
            aspect = w / max(h, 1)
            if aspect < 0.28 or aspect > 2.75:
                continue

            crop_b = bright[y:y+h, x:x+w]
            crop_c = chroma[y:y+h, x:x+w]
            colourful_ratio = float(((crop_c > 38) & (crop_b > 38)).mean())
            white_ratio = float(((crop_b > 145) & (crop_c < 50)).mean())
            yellow_ratio = float(((arr[y:y+h, x:x+w, 0] > 130) &
                                  (arr[y:y+h, x:x+w, 1] > 95) &
                                  (arr[y:y+h, x:x+w, 2] < 105)).mean())
            fill_ratio = area / float(max(1, w * h))

            # Pure payout stacks are mostly yellow/white text with very little
            # multi-colour mass.  Keep gold symbols only when the crop still has
            # enough saturated artwork area.
            if colourful_ratio < 0.055 and white_ratio > 0.12:
                continue
            if yellow_ratio > 0.28 and colourful_ratio < 0.20 and fill_ratio < 0.36:
                continue
            if h > w * 1.8 and colourful_ratio < 0.17:
                continue

            # Multipart / low-chroma symbols (nori sushi, drums, props with
            # detached highlights) can be split into a component that is narrower
            # than the visible icon.  Keep extra horizontal context here; the
            # later payout-text cleanup removes nearby 6/5/4/3 value columns.
            pad_y = max(5, int(h * 0.22), int(min(w, h) * 0.18))
            pad_x = max(8, int(w * 0.45), int(h * 0.28), int(min(w, h) * 0.24))
            left = max(0, x - pad_x)
            top = max(0, y - pad_y)
            right = min(W, x + w + pad_x)
            bottom = min(H, y + h + pad_y)
            boxes.append((left, top, right - left, bottom - top))

        boxes = _dedupe_boxes(boxes, image=dialog_img)
        if boxes:
            print(f"    Component detector found {len(boxes)} icon candidates")
        return boxes
    except Exception as exc:
        print(f"    Component icon detection error: {exc}")
        return []


def detect_grid_icons_in_dialog(dialog_img) -> list:
    """
    Find symbol icon bounding boxes in a pre-cropped paytable dialog.

    Column detection: per-column std-dev ??colourful icon columns have high
    variance; text and dark backgrounds have low variance.

    Row detection: local-peak finding on the per-row brightness profile.
    Threshold-based region detection was replaced because the peaks were too
    narrow to pass a minimum-size filter reliably ??peaks only briefly exceed
    the mean-based threshold, giving above-threshold windows of ~30 px which
    is smaller than the typical icon row height.  Local maxima + valley
    boundaries solve this cleanly.

    Returns [(x, y, w, h), ...] sorted left->right, top->bottom.
    Returns [] if numpy is unavailable or detection fails.
    """
    if Image is None:
        return []
    try:
        import numpy as np
    except ImportError:
        return []

    try:
        arr  = np.array(dialog_img.convert("RGB"), dtype=np.float32)
        H, W = arr.shape[:2]
        bright = arr.mean(axis=2)           # (H, W)
        chroma = arr.max(axis=2) - arr.min(axis=2)

        # Skip title bar ??top ~12 % is the "Paytable" heading
        cs = int(H * 0.12)
        content = bright[cs:, :]            # (H-cs, W)
        CH = content.shape[0]

        def smooth(x, k):
            k = max(1, int(k))
            return np.convolve(x, np.ones(k) / k, mode="same")

        def find_groups(mask):
            groups, start = [], None
            for i, v in enumerate(mask.tolist()):
                if v and start is None:
                    start = i
                elif not v and start is not None:
                    groups.append((start, i - 1))
                    start = None
            if start is not None:
                groups.append((start, len(mask) - 1))
            return groups

        def estimate_icon_area_end():
            """
            Detect where the paytable's explanatory paragraph begins.

            Paytable symbol rows contain compact icon + payout clusters.  The
            rule section below them contains long white/gray text lines spanning
            much more of the dialog width.  We stop row-peak detection before
            that section so text fragments never become icon candidates.
            """
            light_text = (bright[cs:, :] > 138) & (chroma[cs:, :] < 62)
            row_text_density = smooth(light_text.mean(axis=1), max(3, CH // 70))

            # Avoid the title/header and upper paytable rows.  The notes usually
            # begin after the lower half of the dialog content.
            search_start = int(CH * 0.48)
            search_end = int(CH * 0.94)
            threshold = max(0.105, float(row_text_density.mean() +
                            row_text_density.std() * 1.15))

            run = 0
            min_run = max(3, int(CH * 0.012))
            for i in range(search_start, search_end):
                if row_text_density[i] > threshold:
                    run += 1
                    if run >= min_run:
                        cut = i - run + 1 - int(CH * 0.025)
                        return max(int(CH * 0.52), min(cut, int(CH * 0.85)))
                else:
                    run = 0
            return int(CH * 0.85)

        # ?? Column bands (std-dev: icons are colourful ??high variance) ??????
        col_std = content.std(axis=0)
        col_s   = smooth(col_std, W / 30)
        thr_c   = col_s.mean() + col_s.std() * 0.35
        c_grps  = find_groups(col_s > thr_c)
        c_grps  = [(s, e) for s, e in c_grps
                   if W * 0.06 <= (e - s) <= W * 0.30]
        c_grps.sort(key=lambda g: col_s[g[0]:g[1] + 1].sum(), reverse=True)
        raw_icon_cols = sorted(c_grps[:2], key=lambda g: g[0])

        # Narrow wide groups: slot paytables lay out [icon][payout text],
        # so a very wide group likely spans both.  Keep a slightly generous
        # icon band because scatter/wild framed art is often wider than a
        # square cell; text bleed is trimmed later by component cleanup.
        # Split at the local std-dev minimum within the group and keep
        # the left sub-range (the icon side).
        icon_cols = []
        icon_max_w = int(W * 0.22)
        icon_min_w = max(4, int(W * 0.06))
        for s, e in raw_icon_cols:
            gw = e - s + 1
            if gw <= icon_max_w:
                icon_cols.append((s, e))
            else:
                # Wide group: spans both the icon artwork and an adjacent text
                # label or payout-number column.
                # Find the deepest valley in the middle 60% of the group.
                margin = max(icon_min_w, gw // 5)
                seg    = col_s[s + margin : e - margin + 1]
                if len(seg) > 0:
                    split  = s + margin + int(np.argmin(seg))
                else:
                    split  = s + icon_max_w
                # Also cap at icon_max_w from the group start so that a
                # badly-placed argmin cannot pull in an entire payout column.
                # Any remaining text bleed is handled later by component cleanup.
                new_e = min(s + icon_max_w - 1,
                            max(s + icon_min_w, split - 1))
                icon_cols.append((s, new_e))

        if not icon_cols:
            print("    [detect] WARNING: icon column detection failed")
            return []

        # ?? Row detection via local-peak finding ?????????????????????????????
        # Use the ORIGINAL (possibly wide) icon_cols for row-brightness
        # sampling so that all icon content contributes to the row profile.
        # Column width normalization is applied separately below, only to the
        # crop coordinates, so it cannot accidentally drop row peaks.
        col_mask = np.zeros(W, dtype=bool)
        for s, e in icon_cols:
            col_mask[s : e + 1] = True

        row_bright = content[:, col_mask].mean(axis=1)
        row_s      = smooth(row_bright, max(1, CH // 50))

        min_dist   = max(4, int(CH * 0.06))
        min_height = row_s.mean()

        def find_local_peaks(profile, min_d, min_h):
            peaks = []
            n = len(profile)
            for i in range(1, n - 1):
                if profile[i] > profile[i - 1] and profile[i] > profile[i + 1]:
                    if profile[i] >= min_h:
                        if not peaks or (i - peaks[-1]) >= min_d:
                            peaks.append(i)
                        elif profile[i] > profile[peaks[-1]]:
                            peaks[-1] = i
            return peaks

        # Cap before the lower rule/paragraph section when present.
        icon_area_end = estimate_icon_area_end()
        peaks = find_local_peaks(row_s[:icon_area_end], min_dist, min_height)

        if not peaks:
            print("    [detect] WARNING: no icon row peaks found")
            return []

        # Convert peaks to (ys, ye) bounding boxes via valley boundaries
        r_grps = []
        for idx, p in enumerate(peaks):
            if idx > 0:
                prev_p   = peaks[idx - 1]
                valley_l = prev_p + int(np.argmin(row_s[prev_p : p + 1]))
            else:
                valley_l = max(0, p - min_dist // 2)

            if idx < len(peaks) - 1:
                next_p   = peaks[idx + 1]
                valley_r = p + int(np.argmin(row_s[p : next_p + 1]))
            else:
                valley_r = min(CH - 1, p + min_dist // 2)

            ys = valley_l + cs
            ye = valley_r + cs
            if (ye - ys) >= H * 0.03:
                r_grps.append((ys, ye))

        if not r_grps:
            print("    [detect] WARNING: no valid icon rows after valley split")
            return []

        # ?? Build grid ????????????????????????????????????????????????????????
        icons = []
        for (ys, ye) in r_grps:
            for (xs, xe) in icon_cols:
                icons.append((xs, ys, xe - xs + 1, ye - ys + 1))

        print(f"    Detected {len(icons)} icon regions "
              f"({len(r_grps)} rows x {len(icon_cols)} cols)")
        return icons

    except Exception as exc:
        print(f"    Icon detection error: {exc}")
        return []


def detect_pp_web_paytable_boxes(dialog_img) -> list:
    """Supplement fixed PP web paytable layouts after the modal has been cropped."""
    try:
        import numpy as np
    except ImportError:
        return []

    W, H = dialog_img.size
    aspect = W / max(H, 1)
    if not (680 <= W <= 920 and 430 <= H <= 620 and 1.25 <= aspect <= 1.75):
        return []

    arr = np.array(dialog_img.convert("RGB"), dtype=np.float32)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    dark_ratio = float(((bright < 95) & (chroma < 110)).mean())
    if dark_ratio < 0.60:
        return []

    def sx(x):
        return int(round(x * W / 776.0))

    def sy(y):
        return int(round(y * H / 522.0))

    def color_content_ratio(box):
        x, y, w, h = box
        x = max(0, min(W - 1, sx(x)))
        y = max(0, min(H - 1, sy(y)))
        w = max(1, min(W - x, sx(w)))
        h = max(1, min(H - y, sy(h)))
        crop = arr[y:y + h, x:x + w]
        if crop.size == 0:
            return 0.0
        cb = crop.mean(axis=2)
        cc = crop.max(axis=2) - crop.min(axis=2)
        return float(((cb > 45) & (cc > 38)).mean())

    page1_top_probe = [(74, 86, 132, 84), (234, 86, 132, 84), (394, 86, 132, 84), (554, 86, 132, 84)]
    # Page 1 has four small symbol artworks in the upper grid row; Page 2 has
    # only explanatory text in the same area.  The icons are dark under the
    # modal overlay, so the threshold must stay low.
    is_page1 = sum(1 for box in page1_top_probe if color_content_ratio(box) >= 0.025) >= 3

    boxes = []
    page2_probe = [(90, 216, 140, 112), (250, 216, 140, 112), (404, 216, 130, 112), (532, 216, 160, 112)]
    is_page2 = sum(1 for box in page2_probe if color_content_ratio(box) >= 0.060) >= 3

    if is_page1:
        # Page 1 layouts vary and the payout rows sit very close to artwork.
        # Let the component detector own most symbols, but add the bottom
        # Scatter logo because generic boxes often merge it with explanatory
        # text and then the final filter correctly rejects that wide crop.
        boxes.append((sx(260), sy(397), sx(100), sy(85)))
    elif is_page2:
        # Page 2: multiplier spheres include external golden wings.  Keep the
        # full wing span instead of only the colourful orb component.
        for x, w in [(72, 154), (232, 154), (390, 154), (544, 154)]:
            boxes.append((sx(x), sy(216), sx(w), sy(112)))
    else:
        return []

    clipped = []
    for x, y, w, h in boxes:
        x = max(0, min(W - 1, x))
        y = max(0, min(H - 1, y))
        w = max(1, min(W - x, w))
        h = max(1, min(H - y, h))
        clipped.append((x, y, w, h))
    return clipped


def is_pp_multiplier_paytable_box(box) -> bool:
    """Return True for supplemental PP page-2 multiplier symbol boxes."""
    _x, y, w, h = [int(v) for v in box]
    return 148 <= w <= 166 and 100 <= h <= 126 and 208 <= y <= 228


def is_pp_scatter_paytable_box(box) -> bool:
    """Return True for supplemental PP page-1 Scatter logo boxes."""
    x, y, w, h = [int(v) for v in box]
    return 245 <= x <= 275 and 390 <= y <= 410 and 85 <= w <= 115 and 75 <= h <= 96



def detect_icons_in_dialog(dialog_img) -> list:
    """
    Find symbol icon bounding boxes with a generic component-first strategy.

    Component detection handles web-style / non-PG help layouts.  The older
    grid detector remains as a fallback and?? path for compact two-column PG
    paytables where symbols are arranged in strict rows.
    """
    mahjong_tile_boxes = detect_mahjong_tile_boxes_in_dialog(dialog_img)
    if mahjong_tile_boxes:
        print(f"    Using {len(mahjong_tile_boxes)} mahjong tile candidates")
        return mahjong_tile_boxes

    component_boxes = detect_icon_components_in_dialog(dialog_img)
    grid_boxes = []

    # If the component pass finds too few symbols, or finds a suspiciously small
    # set, supplement it with the older grid detector.  This keeps Lucky Neko-like
    # layouts stable while improving web-style paytables.
    dialog_aspect = dialog_img.width / max(dialog_img.height, 1)
    if dialog_aspect < 0.85:
        grid_boxes = detect_grid_icons_in_dialog(dialog_img)
    elif len(component_boxes) < 8:
        grid_boxes = detect_grid_icons_in_dialog(dialog_img)
    elif len(component_boxes) < 16:
        # Add grid boxes too; dedupe removes overlap, and validation later drops
        # text / payout fragments.
        grid_boxes = detect_grid_icons_in_dialog(dialog_img)

    pp_web_boxes = detect_pp_web_paytable_boxes(dialog_img)
    if len(pp_web_boxes) >= 4 and all(is_pp_multiplier_paytable_box(b) for b in pp_web_boxes):
        boxes = _dedupe_boxes(pp_web_boxes, image=dialog_img)
        print(f"    Using {len(boxes)} PP multiplier icon candidates")
        return boxes

    boxes = _dedupe_boxes(component_boxes + grid_boxes + pp_web_boxes, image=dialog_img)
    stacked_boxes = _merge_stacked_symbol_boxes(boxes, dialog_img.width, dialog_img.height)
    if stacked_boxes:
        boxes = _dedupe_boxes(boxes + stacked_boxes, image=dialog_img)
    inferred_card_boxes = _infer_portrait_paytable_card_boxes(boxes, dialog_img.width, dialog_img.height)
    if inferred_card_boxes:
        boxes = _dedupe_boxes(boxes + inferred_card_boxes, image=dialog_img)

    if pp_web_boxes:
        covered = []
        forced = []
        for pp_box in pp_web_boxes:
            if is_pp_scatter_paytable_box(pp_box):
                forced.append(pp_box)
                continue
            if any(_box_overlap_ratio(pp_box, old) >= 0.58 for old in boxes):
                continue
            covered.append(pp_box)
        if covered:
            boxes = _dedupe_boxes(boxes + covered, image=dialog_img)
        for forced_box in forced:
            if forced_box not in boxes:
                boxes.append(forced_box)
    if boxes:
        print(f"    Using {len(boxes)} icon candidates after merge")
    return boxes

def tight_crop_content(img, bg_threshold=28, margin=3):
    """
    Remove dark/empty borders from a slot icon crop.

    Slot paytable dialogs have a very dark background (~20??8 brightness).
    This function trims any leading/trailing rows and columns whose mean
    brightness is at or below bg_threshold, then adds a small margin back.

    Returns the trimmed image, or the original if numpy is unavailable.
    """
    try:
        import numpy as np
    except ImportError:
        return img

    arr      = np.array(img.convert("RGB"), dtype=np.float32)
    bright   = arr.mean(axis=2)           # (H, W)
    row_mean = bright.mean(axis=1)        # (H,)
    col_mean = bright.mean(axis=0)        # (W,)

    content_r = np.where(row_mean > bg_threshold)[0]
    content_c = np.where(col_mean > bg_threshold)[0]

    if len(content_r) == 0 or len(content_c) == 0:
        return img   # nothing to trim ??return as-is

    y1 = max(0,          int(content_r[0])  - margin)
    y2 = min(img.height, int(content_r[-1]) + 1 + margin)
    x1 = max(0,          int(content_c[0])  - margin)
    x2 = min(img.width,  int(content_c[-1]) + 1 + margin)

    return img.crop((x1, y1, x2, y2))


def trim_icon_right(img, color_threshold=55, margin=6):
    """
    Trim the right side of an icon crop to remove adjacent text labels or
    payout-number columns that bleed into the detected icon column band.

    Strategy: slot icon artwork is highly colourful (gold, red, orange ??
    so its columns exhibit high inter-channel variance (R-G or G-B differs
    significantly across rows).  Adjacent columns ??whether white payout
    digits, styled text labels, or dark gaps ??all have much lower
    inter-channel variance than the icon itself.

    Empirically measured for this game type:
      ??Icon artwork columns:   colorfulness ??65??20  (very high)
      ??Styled text labels:     colorfulness ??35??0   (moderate)
      ??White payout digits:    colorfulness ??0??     (near-zero)
      ??threshold of 55 sits cleanly between icon art (??5) and text (??0),
        so only genuine icon pixels are "colorful" and the text on the right
        is excluded when trimming.

    Note: density-based filtering is NOT used here because decorative
    paytable frames often make density = 1.0 across the entire row,
    rendering density a non-discriminating criterion.

    Returns the trimmed image, or the original if numpy is unavailable or
    the image is already narrow.
    """
    try:
        import numpy as np
    except ImportError:
        return img

    if img.width < 16:
        return img

    arr  = np.array(img.convert("RGB"), dtype=np.float32)  # (H, W, 3)

    # Colorfulness: std of inter-channel differences across all rows in each col
    rg_std       = (arr[:, :, 0] - arr[:, :, 1]).std(axis=0)  # (W,)
    gb_std       = (arr[:, :, 1] - arr[:, :, 2]).std(axis=0)  # (W,)
    colorfulness = rg_std + gb_std                             # (W,)

    colorful_cols = np.where(colorfulness > color_threshold)[0]
    if len(colorful_cols) == 0:
        return img   # nothing qualifies ??return as-is

    right_bound = int(colorful_cols[-1]) + 1 + margin
    right_bound = min(right_bound, img.width)

    if right_bound < img.width - 2:
        return img.crop((0, 0, right_bound, img.height))
    return img


def trim_disconnected_right_noise(img, margin=8):
    """
    Remove detached text/number components to the right of a symbol crop.

    The wider initial crop preserves framed symbols, but can include payout
    digits or labels.  These are usually disconnected foreground components
    sitting to the right of the icon artwork, so keep components anchored in
    the left portion of the crop and discard the detached right-side residue.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return img

    if img.width < 36 or img.height < 24:
        return img

    arr = np.array(img.convert("RGB"), dtype=np.uint8)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    soft_low_chroma_art = (bright > 78) & (chroma > 10)
    mask = (((bright > 58) & (chroma > 18)) |
            soft_low_chroma_art |
            (chroma > 42) | (bright > 145)).astype(np.uint8)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)

    min_area = max(14, int(img.width * img.height * 0.0025))
    # Keep multipart, low-chroma symbols such as nori sushi or drums.  Their
    # right-side piece can look detached from the bright rice/drum head, so a
    # 50% anchor was too aggressive and cut valid artwork.
    anchor_limit = img.width * 0.68
    kept = []
    for i in range(1, num):
        x, y, w, h, area = stats[i]
        if area < min_area or w < 3 or h < 3:
            continue
        cx = x + w / 2
        if cx <= anchor_limit or x <= img.width * 0.32:
            kept.append((x, y, w, h, area))

    # If the heuristic would remove almost everything, keep the original crop.
    if not kept:
        return img

    x1 = max(0, min(k[0] for k in kept) - margin)
    y1 = max(0, min(k[1] for k in kept) - margin)
    x2 = min(img.width, max(k[0] + k[2] for k in kept) + margin)
    y2 = min(img.height, max(k[1] + k[3] for k in kept) + margin)

    if (x2 - x1) < 16 or (y2 - y1) < 16:
        return img
    return img.crop((x1, y1, x2, y2))


def trim_right_payout_column(img, margin=6):
    """
    Trim payout-number columns that sit to the right of an extracted symbol.

    Some web-style paytables place the symbol immediately next to a vertical
    payout list.  Connected-component detection can return a single wide region
    around both areas.  When the right side is mostly yellow numeric text, look
    for the first low-foreground vertical gap and crop there.
    """
    try:
        import numpy as np
    except ImportError:
        return img

    if img.width < 54 or img.height < 28:
        return img

    arr = np.array(img.convert("RGB"), dtype=np.float32)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    yellow_text = ((arr[:, :, 0] > 120) & (arr[:, :, 1] > 85) &
                   (arr[:, :, 2] < 140) & (chroma > 25))
    cream_text = ((bright > 105) & (bright < 245) & (chroma < 95))

    right = slice(int(img.width * 0.45), img.width)
    if float((yellow_text[:, right] | cream_text[:, right]).mean()) < 0.032:
        return img

    try:
        import cv2

        text_mask = (yellow_text | cream_text).astype("uint8")
        text_mask[:, :int(img.width * 0.55)] = 0
        n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(text_mask, 8)
        text_components = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if x < img.width * 0.54:
                continue
            if 3 <= area <= 190 and w <= 24 and h <= 28:
                text_components.append((int(x), int(y), int(w), int(h), int(area)))

        if len(text_components) >= 2:
            buckets = {}
            for comp in text_components:
                key = comp[0] // 14
                buckets.setdefault(key, []).append(comp)

            dense_groups = [group for group in buckets.values() if len(group) >= 2]
            if dense_groups:
                leftmost = min(comp[0] for group in dense_groups for comp in group)
                cut = max(20, leftmost - margin)
                # Only cut when there is actual colourful artwork to the left.
                left_art = ((chroma[:, :cut] > 42) & (bright[:, :cut] > 35)).mean()
                right_text = (yellow_text[:, cut:] | cream_text[:, cut:]).mean() if cut < img.width else 0.0
                if img.width * 0.46 <= cut < img.width - 6 and left_art > 0.045 and right_text > 0.018:
                    return img.crop((0, 0, cut, img.height))
    except Exception:
        pass

    fg = ((bright > 58) & (chroma > 22)) | ((bright > 78) & (chroma > 10)) | (chroma > 45) | (bright > 145)
    col_density = fg.mean(axis=0)
    if img.width >= 9:
        kernel = np.ones(5, dtype=np.float32) / 5.0
        col_density = np.convolve(col_density, kernel, mode="same")

    search_start = max(int(img.width * 0.32), 26)
    search_end = int(img.width * 0.82)
    low_thr = max(0.090, float(col_density.mean() * 0.22))
    min_run = max(3, int(img.width * 0.035))
    run = 0
    best_cut = None
    for x in range(search_start, search_end):
        if col_density[x] < low_thr:
            run += 1
            if run >= min_run:
                best_cut = x - run + 1
                break
        else:
            run = 0

    if best_cut is None:
        return img

    cut = max(20, best_cut + margin)
    # Avoid over-trimming genuinely wide framed symbols.
    if cut < img.width * 0.42:
        return img
    return img.crop((0, 0, cut, img.height))


def trim_right_text_components(img, margin=10):
    """
    More direct cleanup for crops where the symbol is correct but the right-side
    payout stack (6/5/4/3 or 80/40/etc.) remains inside the crop.

    The payout stack is usually a set of small detached white/yellow components
    in the right half.  Symbols such as sushi/drums can be multi-part, so this
    only cuts when the left side already contains enough colourful artwork.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return img

    if img.width < 62 or img.height < 34:
        return img

    arr = np.array(img.convert("RGB"), dtype=np.uint8)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)

    text_mask = (
        ((bright > 118) & (chroma < 62)) |
        ((arr[:, :, 0] > 120) & (arr[:, :, 1] > 86) & (arr[:, :, 2] < 145) & (chroma > 24))
    ).astype("uint8")
    text_mask[:, :int(img.width * 0.52)] = 0
    text_mask[:2, :] = 0
    text_mask[-2:, :] = 0

    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(text_mask, 8)
    text_components = []
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[i]]
        if x < img.width * 0.52:
            continue
        if 4 <= area <= 280 and 2 <= w <= 28 and 4 <= h <= 34:
            text_components.append((x, y, w, h, area))

    if len(text_components) < 2:
        return img

    # Require a vertical payout-like stack, not a single decorative highlight.
    by_col = {}
    for comp in text_components:
        by_col.setdefault(comp[0] // 16, []).append(comp)
    stack = max(by_col.values(), key=len)
    if len(stack) < 2:
        return img

    leftmost = min(c[0] for c in stack)
    cut = max(22, leftmost - margin)
    if cut < img.width * 0.46 or cut >= img.width - 6:
        return img

    left_art = (
        ((chroma[:, :cut] > 42) & (bright[:, :cut] > 35)) |
        ((bright[:, :cut] > 78) & (chroma[:, :cut] > 10))
    ).mean()
    right_text = text_mask[:, cut:].mean() if cut < img.width else 0.0
    if left_art < 0.040 or right_text < 0.014:
        return img

    return img.crop((0, 0, cut, img.height))


def trim_right_explanatory_text(img, margin=8):
    """
    Trim paragraph-style explanation text to the right of a framed symbol.

    PP paytables can show a large Scatter/Wild logo on the left followed by
    multi-line explanatory text.  The usual payout-column cleanup is tuned for
    compact number stacks, so add a separate paragraph detector that only cuts
    when the left side already contains strong colourful artwork.
    """
    try:
        import numpy as np
    except ImportError:
        return img

    if img.width < 86 or img.height < 48 or img.width < img.height * 0.95:
        return img

    arr = np.array(img.convert("RGB"), dtype=np.float32)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    text_like = (bright > 112) & (chroma < 70)
    art_like = (bright > 45) & (chroma > 45)

    left_art = float(art_like[:, :int(img.width * 0.48)].mean())
    right_text = float(text_like[:, int(img.width * 0.46):].mean())
    if left_art < 0.060 or right_text < 0.050:
        return img

    fg = ((bright > 55) & (chroma > 20)) | text_like | art_like
    col = fg.mean(axis=0)
    search_start = int(img.width * 0.34)
    search_end = int(img.width * 0.72)
    run = 0
    best_cut = None
    for x in range(search_start, search_end):
        if col[x] <= 0.060:
            run += 1
            if run >= max(3, int(img.width * 0.035)):
                best_cut = x - run + 1
                break
        else:
            run = 0

    if best_cut is None:
        return img

    cut = max(24, best_cut + margin)
    if cut < img.width * 0.38 or cut > img.width * 0.88:
        return img

    cropped = img.crop((0, 0, cut, img.height))
    if cropped.width < 40 or cropped.height < 40:
        return img
    return cropped


def trim_left_text_components(img):
    """Mirror the right-side text cleanup for scatter/payout text on the left."""
    try:
        import numpy as np
    except ImportError:
        np = None

    if np is not None and img.width >= 90 and img.height >= 50:
        arr = np.array(img.convert("RGBA"), dtype=np.uint8)
        rgb = arr[:, :, :3].astype(np.float32)
        alpha = arr[:, :, 3] > 8
        bright = rgb.mean(axis=2)
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        text_like = alpha & (
            ((bright > 118) & (chroma < 62)) |
            ((rgb[:, :, 0] > 120) & (rgb[:, :, 1] > 86) & (rgb[:, :, 2] < 145) & (chroma > 24))
        )
        art_like = alpha & (bright > 45) & (chroma > 42)
        left_text = float(text_like[:, :int(img.width * 0.45)].mean())
        right_art = float(art_like[:, int(img.width * 0.35):].mean())
        if left_text >= 0.030 and right_art >= 0.070:
            fg = alpha & ((bright > 58) | (chroma > 28))
            col = fg.mean(axis=0)
            for x in range(int(img.width * 0.22), int(img.width * 0.48)):
                if col[x] <= 0.035 and col[max(0, x - 8):x].mean() > 0.025 and col[x + 1:min(img.width, x + 9)].mean() > 0.12:
                    cut = min(img.width - 18, x + 3)
                    return img.crop((cut, 0, img.width, img.height))

    if Image is None or img.width < 54:
        return img
    mirrored = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    trimmed = trim_right_text_components(trim_right_payout_column(mirrored))
    if trimmed.size == mirrored.size:
        return img
    restored = trimmed.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if restored.width < img.width * 0.45 or restored.height < img.height * 0.80:
        return img
    return restored


def normalize_icon_crop(img, margin=8):
    """
    Tighten an icon candidate around visible artwork.

    The older row/column-mean crop works well when the candidate is mostly an
    icon, but it leaves too much dark dialog background around thin card
    symbols and payout-number fragments.  This pixel-mask crop is stricter:
    keep bright or colourful pixels, then add a small margin back.
    """
    try:
        import numpy as np
    except ImportError:
        return img

    arr = np.array(img.convert("RGB"), dtype=np.float32)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)

    mask = ((bright > 58) & (chroma > 18)) | ((bright > 78) & (chroma > 10)) | (chroma > 42) | (bright > 145)
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return img

    x1 = max(0, int(xs.min()) - margin)
    x2 = min(img.width, int(xs.max()) + 1 + margin)
    y1 = max(0, int(ys.min()) - margin)
    y2 = min(img.height, int(ys.max()) + 1 + margin)

    if (x2 - x1) < 8 or (y2 - y1) < 8:
        return img
    return img.crop((x1, y1, x2, y2))


def crop_to_main_artwork_component(img, margin=12):
    """
    Remove detached payout digits that sit above/beside a thin symbol.

    Single narrow symbols, such as a bowling pin, can be detected with nearby
    payout labels in the crop.  General right-side cleanup misses those labels
    because they are not a right column.  This keeps the dominant artwork
    component plus close neighbours, and drops small distant text components.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return img

    if img.width < 42 or img.height < 42:
        return img

    arr = np.array(img.convert("RGB"), dtype=np.uint8)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    mask = (
        ((bright > 55) & (chroma > 24)) |
        ((bright > 115) & (chroma > 10))
    ).astype("uint8")

    mask = cv2.morphologyEx(mask * 255, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    n, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    components = []
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[i]]
        if area < 18 or w < 3 or h < 4:
            continue
        comp_chroma = chroma[labels == i]
        comp_bright = bright[labels == i]
        colourful_ratio = float((comp_chroma > 34).mean()) if comp_chroma.size else 0.0
        score = area * (1.0 + colourful_ratio) + min(w, h) * 5.0 + float(comp_bright.mean()) * 0.05
        components.append({
            "box": (x, y, w, h),
            "area": area,
            "score": score,
            "colourful_ratio": colourful_ratio,
        })

    if len(components) < 2:
        return img

    main = max(components, key=lambda c: c["score"])
    mx, my, mw, mh = main["box"]
    main_area = max(1, int(main["area"]))
    expanded = (
        mx - max(10, int(mw * 0.45)),
        my - max(10, int(mh * 0.30)),
        mx + mw + max(10, int(mw * 0.45)),
        my + mh + max(10, int(mh * 0.30)),
    )

    keep = []
    dropped_area = 0
    for comp in components:
        x, y, w, h = comp["box"]
        cx, cy = x + w / 2.0, y + h / 2.0
        near_main = expanded[0] <= cx <= expanded[2] and expanded[1] <= cy <= expanded[3]
        substantial = comp["area"] >= main_area * 0.22 and comp["colourful_ratio"] >= 0.08
        if comp is main or near_main or substantial:
            keep.append(comp)
        else:
            dropped_area += comp["area"]

    if not keep or dropped_area < max(18, main_area * 0.03):
        return img

    x1 = max(0, min(c["box"][0] for c in keep) - margin)
    y1 = max(0, min(c["box"][1] for c in keep) - margin)
    x2 = min(img.width, max(c["box"][0] + c["box"][2] for c in keep) + margin)
    y2 = min(img.height, max(c["box"][1] + c["box"][3] for c in keep) + margin)
    if x2 - x1 < 22 or y2 - y1 < 22:
        return img
    return img.crop((x1, y1, x2, y2))


def validate_icon_candidate(img):
    """
    Return (ok, reason) for a pre-cropped icon candidate.

    This intentionally runs BEFORE Claude identification, so non-symbol crops
    (payout numbers, text labels, headers, empty dialog rows) do not consume the
    limited icon budget and push out real symbols.
    """
    try:
        import numpy as np
    except ImportError:
        return True, "no_numpy"

    w, h = img.size
    if w < 22 or h < 22:
        return False, "too_small"

    aspect = w / max(h, 1)
    if aspect < 0.38 or aspect > 2.25:
        return False, "bad_aspect"
    if w < 58 and h < 44 and aspect > 1.22:
        return False, "flat_symbol_fragment"

    arr = np.array(img.convert("RGB"), dtype=np.float32)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)

    fg = (bright > 58) | (chroma > 28)
    colourful = (bright > 45) & (chroma > 35)
    very_bright = bright > 170
    white_text = (bright > 125) & (chroma < 45)
    yellow_text = ((arr[:, :, 0] > 130) & (arr[:, :, 1] > 100) &
                   (arr[:, :, 2] < 110) & (chroma > 40))
    red_art = ((arr[:, :, 0] > 115) & (arr[:, :, 1] < 105) &
               (arr[:, :, 2] < 115) & (chroma > 38))
    blue_art = ((arr[:, :, 2] > 105) & (arr[:, :, 0] < 130) &
                (chroma > 38))
    green_art = ((arr[:, :, 1] > 105) & (arr[:, :, 0] < 145) &
                 (chroma > 38))

    area = float(w * h)
    fg_ratio = float(fg.mean())
    colourful_ratio = float(colourful.mean())
    bright_ratio = float(very_bright.mean())
    white_ratio = float(white_text.mean())
    yellow_ratio = float(yellow_text.mean())
    non_yellow_art_ratio = float((red_art | blue_art | green_art).mean())
    text_ratio = float((white_text | yellow_text).mean())
    dense_letter_badge = (
        min(w, h) >= 64
        and aspect <= 1.45
        and fg_ratio >= 0.45
        and colourful_ratio >= 0.10
        and white_ratio >= 0.10
    )

    # Mostly dark/empty candidates are usually row gaps or dialog background.
    if fg_ratio < 0.055:
        return False, "empty_or_text_sliver"

    # Low-chroma symbols such as sushi or dark props can be valid; only reject
    # truly weak fragments that have little color, little brightness, and little mass.
    if colourful_ratio < 0.010 and bright_ratio < 0.020 and fg_ratio < 0.070:
        return False, "low_colour"

    # Payout numbers are often gold/yellow text on a dark panel.  They can look
    # colourful enough to pass a simple chroma filter, but they lack the red /
    # blue / green hue variety present in actual slot symbols.
    if aspect > 1.42 and h <= 54 and fg_ratio < 0.16:
        if yellow_ratio > 0.025 or white_ratio > 0.030:
            return False, "payout_number_strip"
    if not dense_letter_badge and non_yellow_art_ratio < 0.040 and colourful_ratio < 0.28:
        if (
            yellow_ratio > 0.045
            or (aspect > 1.55 and bright_ratio > 0.035)
            or (aspect > 1.35 and h <= 48 and bright_ratio > 0.035)
        ):
            return False, "payout_number"

    # Pure payout values can survive as compact crops, especially when the text is
    # gold and sharp.  Reject low-art crops dominated by text-colour pixels.
    if text_ratio > 0.045 and non_yellow_art_ratio < 0.050 and fg_ratio < 0.22:
        return False, "payout_text_only"
    if (
        not dense_letter_badge
        and yellow_ratio > 0.030
        and non_yellow_art_ratio < 0.030
        and colourful_ratio < 0.18
    ):
        return False, "yellow_number_only"

    # Small payout digits can survive the yellow-text test because their crop is
    # normalized into a compact square.  Real low-card symbols are usually larger
    # and contain clearer red/blue/green artwork; tiny low-diversity pieces are
    # almost always payout columns or UI text.
    if min(w, h) <= 42 and max(w, h) <= 56:
        if non_yellow_art_ratio < 0.045 and colourful_ratio < 0.18:
            return False, "small_payout_text"

    # White headings ("Symbol Payout Values") and narrow yellow labels ("Wild
    # Symbol") can look like small icon crops after normalization.  They have a
    # high text-colour ratio but much less colourful artwork mass than real
    # symbols.
    if white_ratio > 0.14 and colourful_ratio < 0.08 and (w < 34 or h < 36 or aspect > 1.85):
        return False, "white_text_fragment"
    if w < 42 and h < 62 and colourful_ratio < 0.30:
        if bright_ratio > 0.08 or white_ratio > 0.08 or yellow_ratio > 0.035:
            return False, "small_text_fragment"

    # Header/label fragments often have very high foreground coverage but little
    # colour diversity, while symbol artwork has more varied chroma.
    colour_values = chroma[colourful]
    colour_spread = float(colour_values.std()) if colour_values.size else 0.0
    if fg_ratio > 0.42 and colourful_ratio < 0.10 and colour_spread < 18:
        return False, "text_block"

    # Payout values often form thin vertical stacks: plenty of bright pixels, but
    # not enough colourful icon mass after the crop has been normalized.
    if h > w * 1.55 and colourful_ratio < 0.12:
        return False, "payout_column"

    # Text labels such as "Symbol Values" are wide horizontal strips.
    if w > h * 1.85 and colourful_ratio < 0.12:
        return False, "text_label"

    return True, "ok"


def icon_completeness_score(img) -> float:
    """
    Score how safe/complete a cropped icon looks.

    Higher is better.  The score is used after Claude identifies duplicates, so
    the final symbol table prefers crops that do not touch image borders and
    have a reasonable amount of visible artwork.
    """
    try:
        import numpy as np
    except ImportError:
        return float(img.width * img.height)

    arr = np.array(img.convert("RGB"), dtype=np.float32)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    mask = ((bright > 58) & (chroma > 18)) | ((bright > 78) & (chroma > 10)) | (chroma > 42) | (bright > 145)
    if not mask.any():
        return 0.0

    h, w = mask.shape
    ys, xs = np.where(mask)
    x_margin = min(int(xs.min()), int(w - 1 - xs.max()))
    y_margin = min(int(ys.min()), int(h - 1 - ys.max()))
    edge = max(2, round(min(w, h) * 0.06))
    edge_density = max(
        float(mask[:, :edge].mean()),
        float(mask[:, -edge:].mean()),
        float(mask[:edge, :].mean()),
        float(mask[-edge:, :].mean()),
    )

    artwork_area = float(mask.mean())
    size_score = min(float(w * h) / 9000.0, 1.4)
    margin_score = min((x_margin + y_margin) / 18.0, 1.0)
    edge_penalty = edge_density * 1.8
    return size_score + artwork_area + margin_score - edge_penalty


def right_payout_stack_score(img) -> float:
    """Estimate whether the crop still contains a right-side payout-number stack."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return 0.0

    if img.width < 58 or img.height < 34:
        return 0.0

    arr = np.array(img.convert("RGB"), dtype=np.uint8)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    text_mask = (
        ((bright > 118) & (chroma < 62)) |
        ((arr[:, :, 0] > 120) & (arr[:, :, 1] > 86) & (arr[:, :, 2] < 145) & (chroma > 24))
    ).astype("uint8")
    text_mask[:, :int(img.width * 0.52)] = 0
    text_mask[:2, :] = 0
    text_mask[-2:, :] = 0

    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(text_mask, 8)
    components = []
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[i]]
        if x < img.width * 0.52:
            continue
        if 4 <= area <= 300 and 2 <= w <= 30 and 4 <= h <= 36:
            components.append((x, y, w, h, area))

    if len(components) < 2:
        return 0.0

    buckets = {}
    for comp in components:
        buckets.setdefault(comp[0] // 16, []).append(comp)
    stack_len = max(len(group) for group in buckets.values())
    density = float(text_mask[:, int(img.width * 0.52):].mean())
    return stack_len + density * 20.0


def safe_trim_icon_step(before, after, *, min_area_ratio=0.42, score_tolerance=0.12):
    """
    Accept a cleanup crop only when it does not damage the symbol.

    Some symbols, such as drums or sushi, contain separated colourful parts.  The
    text/noise cleanup can mistake those detached parts for payout text and crop
    them away.  Keep the previous crop when the new crop loses too much area and
    does not improve the completeness score.
    """
    if after is before or after.size == before.size:
        return after

    before_area = max(1, before.width * before.height)
    after_area = max(1, after.width * after.height)
    area_ratio = after_area / before_area

    before_score = icon_completeness_score(before)
    after_score = icon_completeness_score(after)
    before_ok, _before_reason = validate_icon_candidate(before)
    after_ok, _after_reason = validate_icon_candidate(after)

    if after_ok and not before_ok:
        return after

    if after_ok and after.width < before.width * 0.78:
        # Right-payout cleanup is useful for crops that include a 6/5/4/3 value
        # column, but low-chroma multipart symbols such as drums or nori sushi can
        # also look like detached text.  Only accept an aggressive right cut when
        # the resulting crop still looks nearly as complete as the original.
        if right_payout_stack_score(before) >= 2.25 and after_score >= before_score - 0.35:
            return after

    # Tiny reductions are normal when removing dark borders.  Large reductions
    # should only be accepted if the crop quality clearly improves.
    if area_ratio < min_area_ratio and after_score <= before_score + score_tolerance:
        return before
    if after_score + score_tolerance < before_score and area_ratio < 0.72:
        return before

    return after


def safe_main_artwork_crop(before, after):
    """Accept main-artwork cleanup when it removes detached text but keeps a valid icon."""
    if after is before or after.size == before.size:
        return after

    after_ok, _after_reason = validate_icon_candidate(after)
    if not after_ok:
        return before

    before_ok, _before_reason = validate_icon_candidate(before)
    if not before_ok:
        return after

    before_score = icon_completeness_score(before)
    after_score = icon_completeness_score(after)
    before_area = max(1, before.width * before.height)
    after_area = max(1, after.width * after.height)
    area_ratio = after_area / before_area

    if area_ratio < 0.25:
        return before
    if after_score >= before_score - 0.30:
        return after
    return before


def crop_to_dominant_color_artwork(img, margin=18):
    """Crop around the dominant colourful artwork and drop nearby payout text."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return img

    if img.width < 42 or img.height < 42:
        return img

    arr = np.array(img.convert("RGB"), dtype=np.uint8)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    gold_art = (arr[:, :, 0] > 112) & (arr[:, :, 1] > 78) & (arr[:, :, 2] < 135)
    mask = (((bright > 38) & (chroma > 48)) | ((bright > 58) & gold_art)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)

    num, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    comps = []
    min_area = max(16, int(img.width * img.height * 0.0025))
    for i in range(1, num):
        x, y, w, h, area = [int(v) for v in stats[i]]
        if area < min_area or w < 5 or h < 5:
            continue
        if w > img.width * 0.92 and h < img.height * 0.28:
            continue
        comps.append((x, y, w, h, area, centroids[i]))

    if not comps:
        return img

    main = max(comps, key=lambda c: c[4])
    main_area = main[4]
    mcx, mcy = main[5]
    kept = []
    for comp in comps:
        x, y, w, h, area, centroid = comp
        cx, cy = centroid
        close = abs(cx - mcx) <= img.width * 0.48 and abs(cy - mcy) <= img.height * 0.44
        if area >= main_area * 0.10 or close:
            kept.append(comp)

    if not kept:
        return img

    x1 = max(0, min(c[0] for c in kept) - margin)
    y1 = max(0, min(c[1] for c in kept) - margin)
    x2 = min(img.width, max(c[0] + c[2] for c in kept) + margin)
    y2 = min(img.height, max(c[1] + c[3] for c in kept) + margin)

    if (x2 - x1) < 24 or (y2 - y1) < 24:
        return img
    if (x2 - x1) * (y2 - y1) > img.width * img.height * 0.92:
        return img
    return img.crop((x1, y1, x2, y2))


def trim_bottom_payout_text(img, margin=8):
    """
    Remove payout rows printed directly below a paytable symbol.

    PP web paytables place compact stacks such as "12-30 $100" immediately under
    the artwork.  Generic component crops can include both the symbol and that
    stack, so trim the lower text band when the upper portion still contains
    colourful art.
    """
    try:
        import numpy as np
    except ImportError:
        return img

    if img.width < 42 or img.height < 52:
        return img

    arr = np.array(img.convert("RGB"), dtype=np.float32)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    text_mask = ((bright > 118) & (chroma < 82)) | (
        (arr[:, :, 0] > 125) & (arr[:, :, 1] > 88) &
        (arr[:, :, 2] < 145) & (chroma > 22)
    )
    art_mask = (bright > 42) & (chroma > 38)

    lower_start = int(img.height * 0.42)
    lower_text = float(text_mask[lower_start:, :].mean())
    upper_art = float(art_mask[:max(lower_start, 1), :].mean())
    if lower_text < 0.030 or upper_art < 0.035:
        return img

    row_density = text_mask.mean(axis=1)
    art_density = art_mask.mean(axis=1)

    quiet_text_run = 0
    for y in range(lower_start, img.height):
        if row_density[y] >= 0.045 and art_density[y] <= 0.055:
            quiet_text_run += 1
            if quiet_text_run >= 2:
                cut = y - quiet_text_run + 1 - margin
                if img.height * 0.38 <= cut <= img.height * 0.84:
                    return img.crop((0, 0, img.width, max(24, int(cut))))
        else:
            quiet_text_run = 0

    threshold = max(0.070, float(row_density.mean() + row_density.std() * 0.55))
    run = 0
    min_run = max(2, int(img.height * 0.035))
    for y in range(lower_start, img.height):
        if row_density[y] >= threshold:
            run += 1
            if run >= min_run:
                cut = y - run + 1 - margin
                if img.height * 0.34 <= cut <= img.height * 0.78:
                    cropped = img.crop((0, 0, img.width, max(24, int(cut))))
                    return cropped
        else:
            run = 0

    return img


def expand_icon_crop_box(box, source_w, source_h):
    """
    Expand a detected artwork component into a source crop window.

    Component detection is intentionally tight around colourful pixels.  For
    paytables, that tight box is only a hint: crowns, rings, multiplier orbs,
    framed scatters, and letters often need surrounding pixels to avoid clipped
    edges.  Expand symmetrically from the component centre and let the later
    cleanup steps remove payout text or dark background.
    """
    bx, by, bw, bh = [int(v) for v in box]

    # Supplemental PP multiplier boxes are explicit symbol windows.  Keep a
    # small source-pixel cushion so glow and wings are not lost, but do not grow
    # into the explanatory text rows.
    if is_pp_multiplier_paytable_box((bx, by, bw, bh)):
        pad_x = max(6, int(round(bw * 0.08)))
        pad_y = max(4, int(round(bh * 0.04)))
        return (
            max(0, bx - pad_x),
            max(0, by - pad_y),
            min(source_w, bx + bw + pad_x),
            min(source_h, by + bh + pad_y),
        )

    cx = bx + bw / 2.0
    cy = by + bh / 2.0

    min_side = 74
    target_w = max(float(min_side), bw * 1.55, bh * 1.85)
    target_h = max(float(min_side), bh * 1.70, bw * 0.82)

    # Flat icons such as crowns are most likely to look cut in half vertically.
    if bw >= bh * 1.55:
        target_h = max(target_h, bh * 2.15, bw * 0.72)

    # Tall/slender icons need a little extra horizontal context for glow/frames.
    if bh >= bw * 1.45:
        target_w = max(target_w, bw * 2.05, bh * 0.92)

    # Avoid swallowing a whole paytable row when a detector already returned a
    # large framed symbol, but keep enough room for wide Wild/Scatter badges.
    target_w = min(target_w, max(float(min(source_w, 260)), bw * 2.35))
    target_h = min(target_h, max(float(min(source_h, 220)), bh * 2.35))

    x1 = int(round(cx - target_w / 2.0))
    y1 = int(round(cy - target_h / 2.0))
    x2 = int(round(cx + target_w / 2.0))
    y2 = int(round(cy + target_h / 2.0))

    if x1 < 0:
        x2 = min(source_w, x2 - x1)
        x1 = 0
    if y1 < 0:
        y2 = min(source_h, y2 - y1)
        y1 = 0
    if x2 > source_w:
        x1 = max(0, x1 - (x2 - source_w))
        x2 = source_w
    if y2 > source_h:
        y1 = max(0, y1 - (y2 - source_h))
        y2 = source_h

    if x2 <= x1 or y2 <= y1:
        return bx, by, min(source_w, bx + bw), min(source_h, by + bh)
    return x1, y1, x2, y2


def is_portrait_paytable_card_box(box, source_w, source_h):
    """Card-style paytables need tight source crops so payout tables stay out."""
    bx, by, bw, bh = [int(v) for v in box]
    aspect = source_w / max(source_h, 1)
    if not (420 <= source_w <= 700 and source_h >= 760 and aspect <= 0.85):
        return False
    if not (source_h * 0.16 <= by <= source_h * 0.76):
        return False
    if not (source_w * 0.18 <= bw <= source_w * 0.34):
        return False
    if not (source_h * 0.075 <= bh <= source_h * 0.19):
        return False
    box_aspect = bw / max(bh, 1)
    return 0.45 <= box_aspect <= 1.65


def is_portrait_stacked_logo_box(box, source_w, source_h):
    """Tall merged symbol logos in portrait dialogs, e.g. Bonus/Scatter badges."""
    bx, by, bw, bh = [int(v) for v in box]
    aspect = source_w / max(source_h, 1)
    if not (420 <= source_w <= 700 and source_h >= 760 and aspect <= 0.85):
        return False
    if not (source_h * 0.15 <= by <= source_h * 0.72):
        return False
    if not (source_w * 0.16 <= bw <= source_w * 0.40):
        return False
    if not (source_h * 0.16 <= bh <= source_h * 0.36):
        return False
    return bh >= bw * 1.70


def tight_paytable_card_crop_box(box, source_w, source_h):
    bx, by, bw, bh = [int(v) for v in box]
    pad_x = max(3, int(round(bw * 0.05)))
    pad_y = max(3, int(round(bh * 0.05)))
    return (
        max(0, bx - pad_x),
        max(0, by - pad_y),
        min(source_w, bx + bw + pad_x),
        min(source_h, by + bh + pad_y),
    )


def postprocess_portrait_paytable_card_crop(icon_img):
    """Keep the central symbol card from mobile portrait paytable rows."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return tight_crop_content(icon_img, bg_threshold=28, margin=3)

    arr = np.array(icon_img.convert("RGB"), dtype=np.uint8)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    white_text = (bright > 150) & (chroma < 45)
    mask = (bright > 28) & (chroma > 18) & ~white_text
    mask = cv2.morphologyEx(mask.astype("uint8") * 255, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)

    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    comps = []
    for idx in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[idx]]
        if area < max(90, icon_img.width * icon_img.height * 0.018):
            continue
        cx, cy = centroids[idx]
        if h < icon_img.height * 0.35 or w < icon_img.width * 0.18:
            continue
        # NEZHA-style rows sometimes include slivers of neighboring cards.
        # Prefer the sizeable component nearest the crop center.
        center_penalty = abs(cx - icon_img.width / 2.0) / max(icon_img.width, 1)
        comps.append((area * (1.0 - min(center_penalty, 0.45)), x, y, w, h))

    if not comps:
        return tight_crop_content(icon_img, bg_threshold=28, margin=3)

    _rank, x, y, w, h = max(comps, key=lambda item: item[0])
    margin = max(3, int(round(min(w, h) * 0.04)))
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(icon_img.width, x + w + margin)
    y2 = min(icon_img.height, y + h + margin)
    if x2 - x1 < 42 or y2 - y1 < 42:
        return tight_crop_content(icon_img, bg_threshold=28, margin=3)
    return icon_img.crop((x1, y1, x2, y2))


def postprocess_stacked_logo_crop(icon_img):
    """Crop a tall merged logo around the main colourful artwork."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return postprocess_icon_crop(icon_img)

    arr = np.array(icon_img.convert("RGB"), dtype=np.uint8)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    white_text = (bright > 150) & (chroma < 45)
    mask = (chroma > 35) & (bright > 45) & ~white_text
    mask = cv2.morphologyEx(mask.astype("uint8") * 255, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    comps = []
    for idx in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[idx]]
        if area < max(70, icon_img.width * icon_img.height * 0.004):
            continue
        cx, cy = centroids[idx]
        # Avoid browser/game UI fragments near the top/bottom edges.
        if not (icon_img.width * 0.16 <= cx <= icon_img.width * 0.84):
            continue
        if not (icon_img.height * 0.20 <= cy <= icon_img.height * 0.84):
            continue
        comps.append((x, y, w, h, area))

    if not comps:
        return postprocess_icon_crop(icon_img)

    largest = max(comps, key=lambda c: c[4])
    keep = [largest]
    lx, ly, lw, lh, la = largest
    for comp in comps:
        x, y, w, h, area = comp
        overlap = max(0, min(lx + lw, x + w) - max(lx, x))
        near_y = abs((y + h / 2.0) - (ly + lh / 2.0)) <= max(lh, h) * 0.85
        if comp is not largest and area >= la * 0.12 and overlap / float(max(1, min(lw, w))) >= 0.25 and near_y:
            keep.append(comp)

    margin = max(6, int(min(icon_img.width, icon_img.height) * 0.04))
    x1 = max(0, min(c[0] for c in keep) - margin)
    y1 = max(0, min(c[1] for c in keep) - margin)
    x2 = min(icon_img.width, max(c[0] + c[2] for c in keep) + margin)
    y2 = min(icon_img.height, max(c[1] + c[3] for c in keep) + margin)
    if x2 - x1 < 36 or y2 - y1 < 42:
        return postprocess_icon_crop(icon_img)
    return icon_img.crop((x1, y1, x2, y2))


def use_legacy_full_page_crop(source_w, source_h) -> bool:
    """Full-page and portrait mobile help screens need the older light padding."""
    aspect = source_w / max(source_h, 1)
    wide_full_page = source_w >= 1000 and aspect >= 1.35
    browser_panel_page = source_w >= 1000 and source_h >= 780
    portrait_mobile_panel = 420 <= source_w <= 700 and source_h >= 760 and aspect <= 0.85
    return wide_full_page or browser_panel_page or portrait_mobile_panel


def legacy_full_page_crop_box(box, source_w, source_h):
    """Old source-pixel crop strategy for full-page paytable/help layouts."""
    bx, by, bw, bh = [int(v) for v in box]
    pad = 10
    if bw >= bh * 1.18:
        # Full-page/PG-style detectors often return an entire symbol+payout row.
        # The symbol artwork is normally on the left side of that row, so keep
        # only that artwork window and let cleanup trim the remaining background.
        crop_w = max(56, min(bw, int(round(bh * 1.80))))
    else:
        crop_w = max(bw + 12, int(bh * 1.15), 56)
    x1 = max(0, bx - pad)
    y1 = max(0, by - pad)
    x2 = min(source_w, bx + crop_w + pad)
    y2 = min(source_h, by + bh + pad)
    if x2 <= x1 or y2 <= y1:
        return bx, by, min(source_w, bx + bw), min(source_h, by + bh)
    return x1, y1, x2, y2


def postprocess_icon_crop(icon_img, prefer_dominant_color_cleanup=False):
    """Clean one icon crop while protecting wide / multipart symbols."""
    icon_img = tight_crop_content(icon_img, bg_threshold=35)

    candidate = trim_bottom_payout_text(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.30, score_tolerance=0.55)

    candidate = trim_disconnected_right_noise(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.44)

    candidate = trim_right_payout_column(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.50)

    candidate = trim_right_text_components(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.48)

    candidate = trim_right_explanatory_text(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.42, score_tolerance=0.60)

    candidate = crop_to_main_artwork_component(icon_img, margin=12)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.32, score_tolerance=0.65)

    if prefer_dominant_color_cleanup:
        candidate = crop_to_dominant_color_artwork(icon_img, margin=18)
        icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.30, score_tolerance=0.70)

    candidate = normalize_icon_crop(icon_img, margin=22)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.62)

    candidate = crop_to_main_artwork_component(icon_img, margin=12)
    icon_img = safe_main_artwork_crop(icon_img, candidate)

    candidate = trim_bottom_payout_text(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.30, score_tolerance=0.55)

    candidate = trim_right_text_components(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.54)

    candidate = trim_left_text_components(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.45)

    return icon_img


def crop_to_mahjong_tile_card(icon_img, margin=8):
    """Keep a whole white mahjong-style tile instead of only its inner artwork."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    if icon_img.width < 70 or icon_img.height < 70:
        return None

    arr = np.array(icon_img.convert("RGB"), dtype=np.uint8)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    white_tile = (bright > 145) & (chroma < 52)
    white_tile = cv2.morphologyEx(
        white_tile.astype("uint8") * 255,
        cv2.MORPH_CLOSE,
        np.ones((3, 3), np.uint8),
        iterations=1,
    )

    n, _labels, stats, centroids = cv2.connectedComponentsWithStats(white_tile, 8)
    comps = []
    for idx in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[idx]]
        if area < max(900, int(icon_img.width * icon_img.height * 0.08)):
            continue
        if w < 55 or h < 55:
            continue
        aspect = w / max(h, 1)
        if not (0.55 <= aspect <= 2.10):
            continue
        cx, cy = centroids[idx]
        center_penalty = (
            abs(cx - icon_img.width * 0.42) / max(icon_img.width, 1)
            + abs(cy - icon_img.height * 0.50) / max(icon_img.height, 1)
        )
        comps.append((area * (1.0 - min(center_penalty, 0.65)), x, y, w, h))

    if not comps:
        return None

    _score, x, y, w, h = max(comps, key=lambda item: item[0])
    pad = max(4, int(round(min(w, h) * 0.045)), int(margin))
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(icon_img.width, x + w + pad)
    y2 = min(icon_img.height, y + h + pad)
    if x2 - x1 < 64 or y2 - y1 < 64:
        return None
    return icon_img.crop((x1, y1, x2, y2))


def find_mahjong_tile_source_crop_box(source_img, box, margin=8):
    """Find the full white tile in the source image that contains a detected component."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    bx, by, bw, bh = [int(v) for v in box]
    cx = bx + bw / 2.0
    cy = by + bh / 2.0
    arr = np.array(source_img.convert("RGB"), dtype=np.uint8)
    bright = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    white_tile = (bright > 145) & (chroma < 52)
    white_tile = cv2.morphologyEx(
        white_tile.astype("uint8") * 255,
        cv2.MORPH_CLOSE,
        np.ones((3, 3), np.uint8),
        iterations=1,
    )

    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(white_tile, 8)
    candidates = []
    for idx in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[idx]]
        if area < max(900, int(source_img.width * source_img.height * 0.0025)):
            continue
        if w < 55 or h < 55:
            continue
        aspect = w / max(h, 1)
        if not (0.55 <= aspect <= 2.10):
            continue
        pad = max(8, int(round(min(w, h) * 0.10)))
        contains_center = (x - pad) <= cx <= (x + w + pad) and (y - pad) <= cy <= (y + h + pad)
        if not contains_center:
            continue
        overlap_x = max(0, min(x + w, bx + bw) - max(x, bx))
        overlap_y = max(0, min(y + h, by + bh) - max(y, by))
        overlap = overlap_x * overlap_y
        center_penalty = abs(cx - (x + w / 2.0)) / max(w, 1) + abs(cy - (y + h / 2.0)) / max(h, 1)
        candidates.append((overlap + area * (1.0 - min(center_penalty, 0.75)), x, y, w, h))

    if not candidates:
        return None

    _score, x, y, w, h = max(candidates, key=lambda item: item[0])
    pad = max(4, int(round(min(w, h) * 0.045)), int(margin))
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(source_img.width, x + w + pad)
    y2 = min(source_img.height, y + h + pad)
    if x2 - x1 < 64 or y2 - y1 < 64:
        return None
    return x1, y1, x2, y2


def postprocess_full_page_icon_crop(icon_img):
    """Conservative legacy cleanup for full-page help/paytable layouts."""
    tile = crop_to_mahjong_tile_card(icon_img)
    if tile is not None:
        return tile

    icon_img = tight_crop_content(icon_img, bg_threshold=35)

    candidate = trim_disconnected_right_noise(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.44)

    candidate = trim_right_payout_column(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.50)

    candidate = trim_right_text_components(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.48)

    candidate = trim_right_explanatory_text(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.42, score_tolerance=0.60)

    candidate = crop_to_main_artwork_component(icon_img, margin=12)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.32, score_tolerance=0.65)

    candidate = normalize_icon_crop(icon_img, margin=14)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.68)

    candidate = crop_to_main_artwork_component(icon_img, margin=12)
    icon_img = safe_main_artwork_crop(icon_img, candidate)

    candidate = trim_right_text_components(icon_img)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.54)
    return icon_img


def postprocess_pp_multiplier_crop(icon_img):
    """Keep PP multiplier orb wings intact; only trim empty dark border."""
    icon_img = tight_crop_content(icon_img, bg_threshold=24, margin=4)
    candidate = trim_disconnected_right_noise(icon_img, margin=4)
    icon_img = safe_trim_icon_step(icon_img, candidate, min_area_ratio=0.62, score_tolerance=0.55)
    return tight_crop_content(icon_img, bg_threshold=24, margin=2)


def auto_crop_dialog(img_path: Path):
    """
    Detect and crop the centered dark dialog panel from a full Help screenshot.

    Slot game Help pages show a dark rounded dialog in the CENTER of the frame,
    surrounded by the blurred game background.  Sending the full screenshot to
    Claude makes coordinate estimation unreliable because the 'interesting' area
    is only ~35% of the image width.  Pre-cropping to just the dialog gives
    Claude a clean, focused image and dramatically improves coordinate accuracy.

    Detection strategy:
      1. Scan the center column strip for rows with very dark mean brightness.
      2. Scan a mid-height row for dark columns to find horizontal bounds.
      3. If the detected width covers > 65% of the image (game background is
         also dark ??e.g. shrine walls, night sky) estimate the dialog width
         from its height using a portrait aspect ratio (~1.75:1).
      4. Final sanity checks before returning.

    Returns (cropped_PIL_Image, x_offset, y_offset).
    If PIL or numpy are unavailable, returns (None, 0, 0).
    """
    if Image is None:
        return None, 0, 0
    try:
        import numpy as np

        img    = Image.open(img_path)
        orig_w, orig_h = img.size
        gray   = np.array(img.convert("L"), dtype=np.float32)
        rgb    = np.array(img.convert("RGB"), dtype=np.float32)

        def find_web_help_modal():
            """Crop wide PP web help overlays before generic dark-bg fallback."""
            if orig_w < orig_h * 1.35:
                return None

            bright = gray
            chroma = rgb.max(axis=2) - rgb.min(axis=2)
            dark_panel = (bright < 72) & (chroma < 95)

            y_scan1 = int(orig_h * 0.22)
            y_scan2 = int(orig_h * 0.72)
            if y_scan2 <= y_scan1:
                return None

            col_coverage = dark_panel[y_scan1:y_scan2, :].mean(axis=0)

            def groups_from_mask(mask, min_len):
                groups = []
                start = None
                for idx, value in enumerate(mask.tolist()):
                    if value and start is None:
                        start = idx
                    elif not value and start is not None:
                        if idx - start >= min_len:
                            groups.append((start, idx - 1))
                        start = None
                if start is not None and len(mask) - start >= min_len:
                    groups.append((start, len(mask) - 1))
                return groups

            col_groups = groups_from_mask(col_coverage > 0.35, max(40, int(orig_w * 0.06)))
            center_x = orig_w / 2.0
            modal_group = None
            for start, end in col_groups:
                width = end - start + 1
                if width < orig_w * 0.25 or width > orig_w * 0.72:
                    continue
                if start <= center_x <= end or abs((start + end) / 2.0 - center_x) < orig_w * 0.16:
                    modal_group = (start, end)
                    break
            if modal_group is None:
                return None

            mx1, mx2 = modal_group
            row_coverage = dark_panel[:, mx1:mx2 + 1].mean(axis=1)
            row_mask = row_coverage > 0.45
            row_mask[:int(orig_h * 0.18)] = False
            row_mask[int(orig_h * 0.76):] = False
            row_groups = groups_from_mask(row_mask, max(24, int(orig_h * 0.035)))
            if not row_groups:
                return None

            my1 = min(g[0] for g in row_groups)
            my2 = max(g[1] for g in row_groups)
            if (my2 - my1 + 1) < orig_h * 0.24:
                return None

            # PP web pages can show the game's left Buy/Bet rail beside the
            # help dialog.  The rail is also dark, so the broad center scan can
            # absorb it.  Refine the crop from the dialog title/header band,
            # where the real modal forms one centered dark rectangle.
            modal_h = my2 - my1 + 1
            header_y1 = min(my2, my1 + max(16, int(modal_h * 0.10)))
            header_y2 = min(my2 + 1, my1 + max(42, int(modal_h * 0.30)))
            header_cov = dark_panel[header_y1:header_y2, :].mean(axis=0)
            header_groups = groups_from_mask(header_cov > 0.45, max(40, int(orig_w * 0.05)))
            refined = None
            for start, end in header_groups:
                width = end - start + 1
                if width < orig_w * 0.25 or width > orig_w * 0.62:
                    continue
                if start <= center_x <= end or abs((start + end) / 2.0 - center_x) < orig_w * 0.16:
                    refined = (start, end)
                    break
            if refined is not None:
                mx1, mx2 = refined

            pad_x = max(4, int(orig_w * 0.004))
            pad_y = max(4, int(orig_h * 0.006))
            crop_w = mx2 - mx1 + 1 + pad_x * 2
            crop_h = my2 - my1 + 1 + pad_y * 2
            if crop_w / max(crop_h, 1) < 1.15:
                return None
            return (
                max(0, mx1 - pad_x),
                max(0, my1 - pad_y),
                min(orig_w, mx2 + 1 + pad_x),
                min(orig_h, my2 + 1 + pad_y),
            )

        web_modal = find_web_help_modal()
        if web_modal is not None:
            x1, y1, x2, y2 = web_modal
            cropped = img.crop((x1, y1, x2, y2)).copy()
            img.close()
            return cropped, x1, y1

        DARK    = 55    # brightness ceiling for dialog background pixels
        MIN_COV = 0.12  # minimum fraction of image that must be "dark"
        cx      = orig_w // 2

        # ?? Step 1: Vertical bounds ??scan center column strip ????????????????
        sw        = max(20, orig_w // 12)
        col_strip = gray[:, cx - sw : cx + sw]
        row_mean  = col_strip.mean(axis=1)
        dark_rows = np.where(row_mean < DARK)[0]

        if len(dark_rows) < orig_h * MIN_COV:
            y1, y2 = int(orig_h * 0.04), int(orig_h * 0.96)
        else:
            y1 = max(0,      int(dark_rows[0])  - 8)
            y2 = min(orig_h, int(dark_rows[-1]) + 8)

        # ?? Step 2: Horizontal bounds ??scan a row at mid-dialog height ???????
        mid_y     = (y1 + y2) // 2
        row_slab  = gray[max(0, mid_y - 8) : mid_y + 8, :]
        col_mean  = row_slab.mean(axis=0)
        dark_cols = np.where(col_mean < DARK)[0]

        if len(dark_cols) < orig_w * MIN_COV:
            raw_x1, raw_x2 = 0, orig_w
        else:
            raw_x1 = max(0,      int(dark_cols[0])  - 8)
            raw_x2 = min(orig_w, int(dark_cols[-1]) + 8)

        # ?? Step 3: If width too wide, background is also dark ????????????????
        # Many slot games have dark backgrounds (shrine walls, night sky, etc.)
        # that pass the brightness threshold, causing raw detection to span the
        # full image.  Portrait slot dialogs are ~1.75x taller than wide, so we
        # can estimate the dialog width from its already-detected height.
        if (raw_x2 - raw_x1) > orig_w * 0.65:
            dialog_h = y2 - y1
            dialog_w = int(dialog_h / 1.75)
            portrait_x1 = max(0,      cx - dialog_w // 2)
            portrait_x2 = min(orig_w, cx + dialog_w // 2)

            # Web-style Help pages are not centered portrait dialogs; the rules
            # and symbol tables can span the whole browser content area.  In
            # those cases the side areas outside the estimated portrait crop are
            # mostly dark page background, not bright blurred game art.  Keep the
            # wide crop so left/right symbol columns are not cut off.
            side_mask = np.zeros_like(gray, dtype=bool)
            side_mask[y1:y2, raw_x1:raw_x2] = True
            side_mask[y1:y2, portrait_x1:portrait_x2] = False
            if side_mask.any():
                rgb = np.array(img.convert("RGB"), dtype=np.float32)
                side_bright = gray[side_mask]
                side_chroma = (rgb.max(axis=2) - rgb.min(axis=2))[side_mask]
                side_dark_ratio = float((side_bright < DARK).mean())
                side_colour_ratio = float(((side_chroma > 45) &
                                           (side_bright > 45) &
                                           (side_bright < 245)).mean())
            else:
                side_dark_ratio = 0.0
                side_colour_ratio = 1.0

            if side_dark_ratio > 0.88 and side_colour_ratio < 0.18:
                x1, x2 = raw_x1, raw_x2
            else:
                x1, x2 = portrait_x1, portrait_x2
        else:
            x1, x2 = raw_x1, raw_x2

        # ?? Step 4: Final sanity ??????????????????????????????????????????????
        if (x2 - x1) < orig_w * 0.12:
            x1, x2 = int(orig_w * 0.33), int(orig_w * 0.67)
        if (y2 - y1) < orig_h * 0.20:
            y1, y2 = int(orig_h * 0.04), int(orig_h * 0.96)

        cropped = img.crop((x1, y1, x2, y2)).copy()
        img.close()
        return cropped, x1, y1

    except Exception as exc:
        print(f"    Dialog auto-crop failed ({exc}); using full image")
        try:
            img.close()
        except Exception:
            pass
        return None, 0, 0


# ??? AI prompt ????????????????????????????????????????????????????????????????

SYMBOL_ANALYSIS_PROMPT = """\
You are analysing Help / Paytable screenshots from a slot machine game.
Your task is to identify EVERY symbol shown and extract structured data.
Return ONLY valid JSON ??no prose, no markdown fences, no extra keys.

Required schema:

{
  "game_name": "<best guess at the game title>",
  "grid": "<e.g. 3x3, 5x3, 6x5>",
  "currency_unit": "<e.g. x bet, coins, credits>",

  "symbols": [
    {
      "id":          "<unique snake_case id, e.g. scatter, wild, m1, low_a>",
      "tier":        "<scatter | wild | M1 | M2 | M3 | M4 | M5 | low>",
      "label":       "<display name, e.g. Scatter, Wild, Revolver, A>",
      "description": "<1-sentence visual description of the symbol artwork>",
      "payout": {
        "3": <number or null>,
        "4": <number or null>,
        "5": <number or null>,
        "6": <number or null>
      },
      "help_crop": {
        "page_index": <0-based index of which Help screenshot this symbol appears on>,
        "x": <left pixel>,
        "y": <top pixel>,
        "w": <width in pixels>,
        "h": <height in pixels>
      },
      "notes": "<any special rule, e.g. only on reel 3, stacked, expanding>"
    }
  ],

  "tier_order": ["scatter","wild","M1","M2","M3","M4","M5","low"],

  "design_notes": "<2-4 sentence analysis of the symbol set design: colour palette, style, hierarchy clarity>"
}

????RULES ????

1. Identify ALL symbols visible across ALL Help pages provided.
2. Assign tiers based on payout values (highest payout = M1).
   - Card symbols (A K Q J 10 9) ??tier "low" regardless of payout.
   - Scatter symbol ??tier "scatter".
   - Wild symbol ??tier "wild".
3. help_crop MUST enclose ONLY the symbol artwork icon itself.
   ??Do NOT include: the symbol name label, multiplier numbers (e.g. 6??0 5??0),
     row backgrounds, separators, or any text whatsoever.
   ??The paytable typically has a 2-column layout. Each column shows:
       [icon]  [multiplier numbers to the right]
     Your crop must cover the ICON SQUARE only ??stop before the numbers start.
   ??Typical icon size on a 1920-wide screenshot is 70??10 px wide and 70??10 px tall.
     On a 1280-wide screenshot it is roughly 55??5 px.
   ??The exact pixel dimensions of each screenshot are provided in the header before
     each image (e.g. "?? Help page 0 (1920?960) ??"). Use these to calibrate your
     coordinates ??do not guess or rescale.
4. If a symbol is partially cut off in the Help screenshots (e.g. near the edge),
   still include it and set "needs_fallback": true in the object.
5. payout values should be the multiplier or coin amount shown in the paytable.
   Use null if that match count is not listed.
6. Sort symbols array: scatter first, wild second, then M1?5, then low symbols.
"""


# ??? AI: identify pre-cropped icons ??????????????????????????????????????????

_IDENTIFY_ICONS_PROMPT = """\
I will send you individual icon images extracted from a slot machine paytable.
Icons are labelled Icon-0, Icon-1, ??in reading order (left->right, top->bottom).
They come from multiple paytable pages so there may be DUPLICATES of the same symbol.

Return ONLY valid JSON ??no prose, no markdown fences.

Schema:
{
  "game_name": "<best guess>",
  "grid":      "<e.g. 6x5>",
  "design_notes": "<2-3 sentence colour/style analysis>",
  "icons": [
    {
      "id":       <integer matching Icon-N>,
      "playable": <true = real game symbol artwork; false = UI fragment, text, numbers, header, or empty area>,
      "name":     "<display name if playable, e.g. Wild, Scatter, Drum, A; else 'skip'>",
      "tier":     "<scatter|wild|M1|M2|M3|M4|M5|low|skip>",
      "payout":   {"3":<n|null>,"4":<n|null>,"5":<n|null>,"6":<n|null>},
      "notes":    "<special rule or empty string>"
    }
  ]
}

Rules:
- playable: false  ?? tier MUST be "skip".  Use this for partial text labels,
  payout-number fragments, navigation buttons, empty/dark crops, or any crop
  that is clearly NOT a slot symbol icon.
- Card symbols (A K Q J 10 9) ??tier "low".
- Scatter ??"scatter", Wild ??"wild".
- Other symbols: rank by payout descending ??M1, M2, M3 ??
- Payout values are NOT visible in crops; leave them null.
  Main goal: correct identification and correct playable flag.
"""


def identify_icons_with_claude(api_key: str, icon_images: list) -> dict:
    """
    Send a list of pre-cropped symbol icon PIL Images to Claude for identification.
    Returns dict with game_name, icons list, design_notes.
    """
    try:
        import anthropic
    except ImportError:
        print("  anthropic not installed")
        return {}

    client  = anthropic.Anthropic(api_key=api_key)
    content = [{"type": "text", "text": _IDENTIFY_ICONS_PROMPT}]

    for i, icon_img in enumerate(icon_images):
        content.append({"type": "text", "text": f"Icon-{i}:"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": b64_encode_pil(icon_img)},
        })

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )

    raw = resp.content[0].text.strip()
    for fence in ("```json", "```"):
        if fence in raw:
            raw = raw.split(fence, 1)[1].rsplit("```", 1)[0].strip()
            break
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  Warning: JSON parse failed ({exc})")
        return {}


# ??? AI: symbol analysis (legacy ??used as fallback) ?????????????????????????

def analyse_symbols_with_claude(api_key: str, help_images: list,
                                dialog_crop_dir: Path = None) -> tuple:
    """
    Send Help screenshots to Claude and return (ai_data, source_images).

    Before sending, each image is auto-cropped to just the dialog panel so
    Claude receives a focused ~600px-wide image rather than the full 1920px
    screenshot.  This eliminates the coordinate drift caused by the blurred
    game background on either side of the panel.

    Returns:
        ai_data      ??dict with game_name, symbols, design_notes, ??
        source_imgs  ??list of PIL Images (one per page) used for the API call;
                       these are the pre-cropped dialogs, so Claude's (x,y,w,h)
                       coordinates are directly valid against them.
    """
    try:
        import anthropic
    except ImportError:
        print("  anthropic package not installed ??run: pip install anthropic")
        return {}, []

    client      = anthropic.Anthropic(api_key=api_key)
    source_imgs = []   # cropped PIL Images, parallel to help_images

    content = [{"type": "text", "text": SYMBOL_ANALYSIS_PROMPT}]
    for i, p in enumerate(help_images):
        cropped, x_off, y_off = auto_crop_dialog(p)

        if cropped is not None:
            cw, ch   = cropped.size
            dim_str  = f"{cw}?{ch} (dialog crop from {x_off},{y_off})"
            img_b64  = b64_encode_pil(cropped)
            source_imgs.append(cropped)
        else:
            # Fallback: full image
            if Image is not None:
                try:
                    full = Image.open(p)
                    cw, ch   = full.size
                    dim_str  = f"{cw}?{ch} (full image)"
                    img_b64  = b64_encode(p)
                    source_imgs.append(full)
                except Exception:
                    dim_str  = "unknown"
                    img_b64  = b64_encode(p)
                    source_imgs.append(None)
            else:
                dim_str  = "unknown"
                img_b64  = b64_encode(p)
                source_imgs.append(None)

        content.append({"type": "text",
                         "text": f"?? Help page {i} ({dim_str}) ??"})
        content.append({
            "type": "image",
            "source": {"type": "base64",
                       "media_type": "image/jpeg",
                       "data": img_b64},
        })

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )

    raw = resp.content[0].text.strip()
    for fence in ("```json", "```"):
        if fence in raw:
            raw = raw.split(fence, 1)[1].rsplit("```", 1)[0].strip()
            break

    try:
        return json.loads(raw), source_imgs
    except json.JSONDecodeError as exc:
        print(f"  Warning: JSON parse failed ({exc}). Returning empty data.")
        return {}, source_imgs


# ??? AI: basegame fallback ????????????????????????????????????????????????????

BASEGAME_FALLBACK_PROMPT = """\
You are looking for specific slot machine symbols in Basegame gameplay screenshots.
I will provide:
  1. A list of symbol descriptions I need clean crops of.
  2. Several Basegame frame screenshots.

For each required symbol, find the frame and grid cell where it appears most cleanly
(not spinning, not in a winning flash animation, largest size).

Return ONLY valid JSON ??no prose, no markdown fences.

Schema:
{
  "fallbacks": [
    {
      "symbol_id": "<id from the required list>",
      "frame_index": <0-based index of the best Basegame frame>,
      "x": <left pixel of the symbol cell>,
      "y": <top pixel>,
      "w": <width>,
      "h": <height>,
      "confidence": <0.0-1.0>
    }
  ]
}

If a symbol cannot be found at all, omit it from the fallbacks array.

Required symbols:
{SYMBOL_LIST}
"""


def find_basegame_fallbacks(api_key: str, missing_symbols: list,
                            basegame_images: list) -> dict:
    """
    Ask Claude to locate specific symbols within Basegame frames.
    Returns dict mapping symbol_id ??crop info.
    """
    if not missing_symbols or not basegame_images:
        return {}

    try:
        import anthropic
    except ImportError:
        return {}

    client = anthropic.Anthropic(api_key=api_key)

    sym_list = "\n".join(
        f"- id: {s['id']}, description: {s.get('description', s['label'])}"
        for s in missing_symbols
    )
    prompt = BASEGAME_FALLBACK_PROMPT.replace("{SYMBOL_LIST}", sym_list)

    content = [{"type": "text", "text": prompt}]
    for i, p in enumerate(basegame_images):
        content.append({"type": "text", "text": f"?? Basegame frame {i} ??"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64_encode(p),
            },
        })

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": content}],
    )

    raw = resp.content[0].text.strip()
    for fence in ("```json", "```"):
        if fence in raw:
            raw = raw.split(fence, 1)[1].rsplit("```", 1)[0].strip()
            break

    try:
        data = json.loads(raw)
        return {fb["symbol_id"]: fb for fb in data.get("fallbacks", [])}
    except json.JSONDecodeError:
        return {}


# ??? Symbol cropping ??????????????????????????????????????????????????????????

def crop_symbol(source, x: int, y: int,
                w: int, h: int, out_path: Path) -> bool:
    """
    Crop a symbol and save as PNG to out_path.

    `source` can be:
      - a Path / str  ??opened with PIL
      - a PIL Image   ??used directly (e.g. a pre-cropped dialog image)

    Returns True on success.
    """
    if Image is None:
        print("  Pillow not installed ??skipping crop. Run: pip install Pillow")
        return False

    try:
        if isinstance(source, (str, Path)):
            img = Image.open(source)
        else:
            img = source   # already a PIL Image
        # Add a small padding around the crop for visual breathing room
        padding = 4
        left   = max(0, x - padding)
        top    = max(0, y - padding)
        right  = min(img.width,  x + w + padding)
        bottom = min(img.height, y + h + padding)

        cropped = img.crop((left, top, right, bottom))

        # Resize to a standard display size while keeping aspect ratio
        target_size = 96  # px (square bounding box)
        cropped.thumbnail((target_size, target_size), Image.LANCZOS)

        # Place on a transparent square canvas
        canvas = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
        offset_x = (target_size - cropped.width)  // 2
        offset_y = (target_size - cropped.height) // 2
        if cropped.mode != "RGBA":
            cropped = cropped.convert("RGBA")
        canvas.paste(cropped, (offset_x, offset_y), cropped)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path, "PNG")
        return True

    except Exception as exc:
        print(f"  Crop failed for {out_path.name}: {exc}")
        return False


def is_crop_usable(out_path: Path) -> bool:
    """Return True if the saved symbol PNG is large enough to be usable."""
    if Image is None or not out_path.exists():
        return False
    try:
        img = Image.open(out_path)
        return img.width >= MIN_SYMBOL_SIZE and img.height >= MIN_SYMBOL_SIZE
    except Exception:
        return False


# ??? HTML CSS ?????????????????????????????????????????????????????????????????

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #e8e8e8;
  font-family: 'Segoe UI', Arial, sans-serif;
  padding: 28px 32px;
}
h1 { font-size: 20px; font-weight: 700; color: #222; margin-bottom: 4px; }
.subtitle { font-size: 12px; color: #999; margin-bottom: 22px; }

/* ?? symbol table ?? */
.sym-table-wrap {
  background: white; border-radius: 10px;
  border: 1.5px solid #e0e0e0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 16px 20px; margin-bottom: 20px;
  overflow-x: auto;
}
.sym-table-wrap h2 {
  font-size: 11px; font-weight: 700; color: #7c5cbf;
  text-transform: uppercase; letter-spacing: 1px;
  margin-bottom: 14px;
}
table.sym-table {
  border-collapse: separate; border-spacing: 6px;
}
table.sym-table th {
  font-size: 9px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1px; color: #aaa;
  text-align: center; padding-bottom: 4px;
}
.sym-cell {
  background: #fafafa; border: 1.5px solid #eee;
  border-radius: 8px; padding: 8px 6px 6px;
  text-align: center; min-width: 90px;
  vertical-align: top;
}
.sym-cell.tier-scatter { border-color: #f0a060; background: #fff8f0; }
.sym-cell.tier-wild    { border-color: #b89edf; background: #f8f5ff; }
.sym-cell.tier-m1      { border-color: #e8c030; background: #fffce8; }
.sym-cell.tier-m2      { border-color: #d0c090; background: #fdfcf4; }
.sym-cell.tier-low     { border-color: #d8d8d8; background: #f8f8f8; }

.sym-img {
  width: 64px; height: 64px; object-fit: contain;
  display: block; margin: 0 auto 6px;
  image-rendering: -webkit-optimize-contrast;
}
.sym-img-missing {
  width: 64px; height: 64px; background: #f0f0f0;
  border-radius: 6px; display: flex; align-items: center;
  justify-content: center; font-size: 9px; color: #ccc;
  margin: 0 auto 6px;
}
.sym-label {
  font-size: 10px; font-weight: 700; color: #333;
  margin-bottom: 4px;
}
.sym-payout {
  font-size: 9px; color: #888; line-height: 1.6;
  white-space: nowrap;
}
.sym-note {
  font-size: 8px; color: #b04090; margin-top: 3px;
  line-height: 1.4;
}
.tier-badge {
  display: inline-block; font-size: 8px; font-weight: 700;
  border-radius: 3px; padding: 1px 4px; margin-bottom: 4px;
}
.b-scatter { background: #fff0e0; color: #c06000; }
.b-wild    { background: #f0ebff; color: #7c5cbf; }
.b-m1      { background: #fff8c0; color: #806000; }
.b-m2      { background: #f8f4e0; color: #807050; }
.b-low     { background: #f0f0f0; color: #888; }

/* ?? design notes ?? */
.design-notes {
  background: white; border-radius: 10px;
  border: 1.5px solid #e0e0e0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 14px 18px; margin-bottom: 20px;
}
.design-notes h2 {
  font-size: 11px; font-weight: 700; color: #7c5cbf;
  text-transform: uppercase; letter-spacing: 1px;
  margin-bottom: 8px;
}
.design-notes p { font-size: 10px; color: #555; line-height: 1.7; }

/* ?? help thumbnails ?? */
.help-strip {
  display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px;
}
.help-strip img {
  height: 120px; border-radius: 6px;
  border: 1px solid #e0e0e0;
  object-fit: cover;
}
"""


# ??? HTML builder ?????????????????????????????????????????????????????????????

_TIER_BADGE = {
    "scatter": ("b-scatter", "SCATTER"),
    "wild":    ("b-wild",    "WILD"),
    "M1":      ("b-m1",      "M1"),
    "M2":      ("b-m2",      "M2"),
    "M3":      ("b-m2",      "M3"),
    "M4":      ("b-low",     "M4"),
    "M5":      ("b-low",     "M5"),
    "low":     ("b-low",     "LOW"),
}

_TIER_CELL_CSS = {
    "scatter": "tier-scatter",
    "wild":    "tier-wild",
    "M1":      "tier-m1",
    "M2":      "tier-m2",
    "M3":      "tier-m2",
    "M4":      "tier-low",
    "M5":      "tier-low",
    "low":     "tier-low",
}


def _payout_html(payout: dict) -> str:
    lines = []
    for count in ("6", "5", "4", "3"):
        val = payout.get(count)
        if val is not None:
            lines.append(f"{count} ??{val}")
    return "<br>".join(lines) if lines else "-"


def _symbol_cell(sym: dict, sym_img_path: Path, out_path: Path) -> str:
    tier      = sym.get("tier", "low")
    label     = sym.get("label", sym["id"])
    payout    = sym.get("payout", {})
    note      = sym.get("notes", "")
    cell_css  = _TIER_CELL_CSS.get(tier, "tier-low")
    badge_cls, badge_txt = _TIER_BADGE.get(tier, ("b-low", tier.upper()))

    if sym_img_path and sym_img_path.exists():
        rel = os.path.relpath(str(sym_img_path), str(out_path.parent)).replace("\\", "/")
        img_html = f'<img class="sym-img" src="{rel}" alt="{label}">'
    else:
        img_html = f'<div class="sym-img-missing">?</div>'

    note_html = f'<div class="sym-note">{note}</div>' if note else ""

    return (
        f'<td><div class="sym-cell {cell_css}">'
        f'<div class="tier-badge {badge_cls}">{badge_txt}</div>'
        f'{img_html}'
        f'<div class="sym-label">{label}</div>'
        f'<div class="sym-payout">{_payout_html(payout)}</div>'
        f'{note_html}'
        f'</div></td>'
    )


def generate_html(video_dir: Path, ai_data: dict,
                  sym_img_dir: Path, out_path: Path):
    """Build and write symbol_table.html."""
    game_name    = ai_data.get("game_name") or video_dir.name
    grid         = ai_data.get("grid", "")
    symbols      = ai_data.get("symbols", [])
    design_notes = ai_data.get("design_notes", "")
    help_images  = collect_help_images(video_dir)

    # ?? Help strip ????????????????????????????????????????????????????????????
    help_strip_html = ""
    for p in help_images:
        rel = os.path.relpath(str(p), str(out_path.parent)).replace("\\", "/")
        help_strip_html += f'<img src="{rel}" alt="Help">'

    # ?? Group symbols into columns for the table ??????????????????????????????
    # Order: scatter, wild, M1, M2, M3, M4, M5, low (card symbols)
    tier_order   = ai_data.get("tier_order") or ["scatter","wild","M1","M2","M3","M4","M5","low"]
    tier_groups  = {t: [] for t in tier_order}
    for sym in symbols:
        t = sym.get("tier", "low")
        if t not in tier_groups:
            tier_groups[t] = []
        tier_groups[t].append(sym)

    # Build one row per tier group that has symbols
    rows_html = ""
    for tier in tier_order:
        syms = tier_groups.get(tier, [])
        if not syms:
            continue

        cells = ""
        for sym in syms:
            img_path = sym_img_dir / f"{sym['id']}.png"
            cells += _symbol_cell(sym, img_path, out_path)

        rows_html += (
            f'<tr><th style="text-align:left;padding-right:8px;'
            f'color:#aaa;font-size:9px;text-transform:uppercase;">'
            f'{tier}</th>{cells}</tr>'
        )

    table_html = (
        '<div class="sym-table-wrap">'
        '<h2>Symbol Paytable</h2>'
        f'<table class="sym-table"><tbody>{rows_html}</tbody></table>'
        '</div>'
    )

    # ?? Design notes panel ????????????????????????????????????????????????????
    design_html = ""
    if design_notes:
        design_html = (
            '<div class="design-notes">'
            '<h2>蝢???</h2>'
            f'<p>{design_notes}</p>'
            '</div>'
        )

    # ?? Fallback notice (no-AI mode) ??????????????????????????????????????????
    noai_notice = ""
    if not symbols:
        noai_notice = (
            '<div style="background:#fff8f0;border:1.5px solid #f0c890;'
            'border-radius:8px;padding:10px 14px;margin-bottom:16px;'
            'font-size:10px;color:#a06000;">'
            '<b>No AI data:</b> Symbol analysis requires an Anthropic API key. '
            'Run with <code>--api-key sk-...</code> to extract symbols automatically.'
            '</div>'
        )

    sep = "?繚?"
    subtitle = f"Grid: {grid}{sep}" if grid else ""
    subtitle += f"Video: {video_dir.name}"

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{game_name} ??Symbol Table</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{game_name}</h1>
<p class="subtitle">{subtitle}</p>
{noai_notice}
<div class="help-strip">{help_strip_html}</div>
{table_html}
{design_html}
</body>
</html>"""

    try:
        out_path.write_text(html, encoding="utf-8")
        final_path = out_path
    except PermissionError as exc:
        print(f"  Symbol table output is locked ({exc}); trying fallback filenames.")
        final_path = None
        for suffix in ["_new", "_new2", "_new3"]:
            fallback = out_path.with_name(f"{out_path.stem}{suffix}{out_path.suffix}")
            try:
                fallback.write_text(html, encoding="utf-8")
                final_path = fallback
                break
            except PermissionError:
                continue
        if final_path is None:
            import time
            fallback = out_path.with_name(f"{out_path.stem}_{int(time.time())}{out_path.suffix}")
            fallback.write_text(html, encoding="utf-8")
            final_path = fallback
    print(f"  Symbol table -> {final_path}")


# ??? Per-video pipeline ???????????????????????????????????????????????????????

def process_video(video_dir: Path, api_key: str, no_ai: bool, debug: bool = False,
                  icons_only: bool = False):
    print(f"\n=== {video_dir.name} ===")

    all_help_images  = collect_all_help_images(video_dir)
    paytable_scan_images = collect_paytable_scan_images(video_dir)
    thumb_images     = collect_help_images(video_dir)   # sampled subset for HTML thumbnails
    basegame_images  = collect_basegame_images(video_dir)
    print(f"  Help pages  : {len(all_help_images)} final, {len(paytable_scan_images)} scan candidates "
          f"({len(thumb_images)} thumbnails)")
    print(f"  BG frames   : {len(basegame_images)}")

    sym_img_dir = video_dir / "symbol_table" / "symbols"
    sym_img_dir.mkdir(parents=True, exist_ok=True)
    out_path = video_dir / "symbol_table" / "symbol_table.html"
    if icons_only and out_path.exists():
        try:
            out_path.unlink()
        except PermissionError:
            print(f"  Existing symbol_table.html is locked; leaving it untouched: {out_path}")

    # ?? Step 1: Detect paytable pages locally (OCR + OpenCV) ??????????????
    ai_data       = {}
    paytable_pages = []
    if paytable_scan_images:
        local_debug_dir = video_dir / "symbol_table" / "paytable_scan_debug" if debug else None
        print(f"  Stage 1: scanning {len(paytable_scan_images)} Help frames "
              f"for paytable pages (local OCR + OpenCV)...")
        paytable_pages = find_paytable_pages_local(
            paytable_scan_images,
            local_debug_dir,
            auto_crop_dialog=auto_crop_dialog,
            detect_icon_components_in_dialog=detect_icons_in_dialog,
            max_pages=72 if icons_only else 10,
        )

        if icons_only:
            # Keep icon extraction scoped to pages that actually look like
            # paytables.  Some Help pages contain gameplay examples or full reel
            # screenshots; merging every final Help frame here makes those
            # examples leak into the final symbol set as basegame-looking crops.
            paytable_pages = sorted(paytable_pages, key=lambda p: p.name)
        write_paytable_candidates_debug(video_dir, paytable_scan_images, paytable_pages)

    if not paytable_pages and not no_ai:
        if not api_key:
            print("  No API key; skipping Haiku fallback (use --api-key or ANTHROPIC_API_KEY).")
        elif not paytable_scan_images:
            print("  No Help images found; skipping paytable analysis.")
        else:
            print(f"  Local scan found no paytable pages; falling back to Haiku "
                  f"for {len(paytable_scan_images)} Help frames...")
            paytable_pages = find_paytable_pages(api_key, paytable_scan_images)

    if not paytable_pages:
        if icons_only:
            print("  No paytable pages detected; skipping icon export to avoid non-paytable crops.")
            paytable_pages = []
        else:
            print("  No paytable pages detected; falling back to sampled Help images.")
            paytable_pages = thumb_images

    # ?? Step 2: OpenCV icon detection (no AI for coordinates) ????????????????
    icon_entries = []
    debug_dir    = video_dir / "symbol_table" / "debug" if debug else None
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
    if Image is None:
        print("  Pillow is unavailable; cannot crop symbol icons.")
        return

    # In debug mode with --no-ai, fall back to the known paytable frame
    # (or sampled Help images) so we can inspect dialog crops and boxes.
    debug_pages = paytable_pages or (thumb_images if debug else [])

    # Collect local icon crops from paytable pages.  This used to run only
    # before Claude identification; now it is the primary output path.
    page_results = []   # [(icon_images_list, box_count, page_idx), ...]

    if debug_pages and (icons_only or not no_ai or debug):
        print("  Stage 2: detecting icon positions with OpenCV...")
        for pi, page_path in enumerate(debug_pages):
            dialog_img, _xoff, _yoff = auto_crop_dialog(page_path)
            source = dialog_img if dialog_img is not None else Image.open(page_path)

            # ?? Debug: save dialog crop ???????????????????????????????????????
            if debug_dir and Image is not None:
                if safe_save_debug_image(source, debug_dir / f"dialog_p{pi}.jpg", format="JPEG", quality=90):
                    print(f"    [debug] saved dialog_p{pi}.jpg  "
                          f"({source.width}?{source.height})")

            boxes = detect_icons_in_dialog(source)

            # ?? Debug: save annotated dialog with bounding boxes ??????????????
            if debug_dir and boxes and Image is not None:
                try:
                    from PIL import ImageDraw
                    vis = source.copy().convert("RGB")
                    draw = ImageDraw.Draw(vis)
                    for (bx, by, bw, bh) in boxes:
                        draw.rectangle([bx, by, bx + bw, by + bh],
                                       outline=(255, 80, 80), width=2)
                    if safe_save_debug_image(vis, debug_dir / f"boxes_p{pi}.jpg", format="JPEG", quality=90):
                        print(f"    [debug] saved boxes_p{pi}.jpg "
                              f"({len(boxes)} boxes)")
                except Exception as _e:
                    print(f"    [debug] annotation failed: {_e}")

            page_icons = []
            for bi, (bx, by, bw, bh) in enumerate(boxes):
                # Icons in paytable grids are often wider than a square cell
                # (scatter/wild frames, crowns, multiplier orbs, etc.).  Treat
                # the detected box as an artwork hint and expand around its
                # centre before cleanup trims payout text or empty background.
                use_full_page_crop = use_legacy_full_page_crop(source.width, source.height)
                used_mahjong_tile_crop = False
                if is_pp_scatter_paytable_box((bx, by, bw, bh)):
                    pad = 4
                    x1 = max(0, bx - pad)
                    y1 = max(0, by - pad)
                    x2 = min(source.width, bx + bw + pad)
                    y2 = min(source.height, by + bh + pad)
                elif is_portrait_paytable_card_box((bx, by, bw, bh), source.width, source.height):
                    x1, y1, x2, y2 = tight_paytable_card_crop_box(
                        (bx, by, bw, bh), source.width, source.height
                    )
                elif is_portrait_stacked_logo_box((bx, by, bw, bh), source.width, source.height):
                    x1, y1, x2, y2 = expand_icon_crop_box(
                        (bx, by, bw, bh), source.width, source.height
                    )
                elif use_full_page_crop:
                    tile_crop_box = find_mahjong_tile_source_crop_box(source, (bx, by, bw, bh))
                    if tile_crop_box:
                        x1, y1, x2, y2 = tile_crop_box
                        used_mahjong_tile_crop = True
                    else:
                        x1, y1, x2, y2 = legacy_full_page_crop_box(
                            (bx, by, bw, bh), source.width, source.height
                        )
                else:
                    x1, y1, x2, y2 = expand_icon_crop_box(
                        (bx, by, bw, bh), source.width, source.height
                    )
                icon_img = source.crop((x1, y1, x2, y2))
                source_crop_kind = "default"
                prefer_dominant_cleanup = (
                    680 <= source.width <= 920
                    and 430 <= source.height <= 620
                    and 1.25 <= source.width / max(source.height, 1) <= 1.75
                )

                # Post-process: remove dark empty borders and adjacent payout
                # text, while protecting multipart symbols from over-trimming.
                if is_pp_scatter_paytable_box((bx, by, bw, bh)):
                    source_crop_kind = "pp_scatter"
                    icon_img = tight_crop_content(icon_img, bg_threshold=24, margin=2)
                elif is_pp_multiplier_paytable_box((bx, by, bw, bh)):
                    source_crop_kind = "pp_multiplier"
                    icon_img = postprocess_pp_multiplier_crop(icon_img)
                elif is_portrait_paytable_card_box((bx, by, bw, bh), source.width, source.height):
                    source_crop_kind = "portrait_paytable_card"
                    icon_img = postprocess_portrait_paytable_card_crop(icon_img)
                elif is_portrait_stacked_logo_box((bx, by, bw, bh), source.width, source.height):
                    source_crop_kind = "portrait_stacked_logo"
                    icon_img = postprocess_stacked_logo_crop(icon_img)
                elif used_mahjong_tile_crop:
                    source_crop_kind = "mahjong_tile"
                    tile_img = crop_to_mahjong_tile_card(icon_img)
                    if tile_img is not None:
                        icon_img = tile_img
                    else:
                        icon_img = tight_crop_content(icon_img, bg_threshold=35, margin=3)
                elif use_full_page_crop:
                    source_crop_kind = "legacy_full_page"
                    icon_img = postprocess_full_page_icon_crop(icon_img)
                else:
                    icon_img = postprocess_icon_crop(
                        icon_img,
                        prefer_dominant_color_cleanup=prefer_dominant_cleanup,
                    )
                icon_img.info["source_page_index"] = pi
                icon_img.info["source_page_path"] = str(page_path)
                icon_img.info["source_box_index"] = bi
                icon_img.info["source_box"] = [bx, by, bw, bh]
                icon_img.info["source_crop_box"] = [x1, y1, x2 - x1, y2 - y1]
                icon_img.info["source_size"] = [source.width, source.height]
                icon_img.info["source_crop_kind"] = source_crop_kind

                ok, reject_reason = validate_icon_candidate(icon_img)
                if (
                    not ok
                    and source_crop_kind in {"portrait_paytable_card", "mahjong_tile"}
                    and reject_reason in {"text_block", "flat_symbol_fragment", "small_text_fragment"}
                    and icon_img.width >= 58
                    and icon_img.height >= 58
                ):
                    ok = True
                    icon_img.info["structured_validation_override"] = reject_reason
                if not ok:
                    if debug_dir:
                        icon_img.save(
                            debug_dir / f"reject_p{pi}_b{bi}_{reject_reason}.jpg",
                            "JPEG", quality=90)
                    print(f"    [reject] p{pi} b{bi}: {reject_reason}")
                    continue

                if debug_dir:
                    icon_img.save(
                        debug_dir / f"icon_p{pi}_b{bi}.jpg", "JPEG", quality=90)
                page_icons.append(icon_img)

            if page_icons:
                page_results.append((page_icons, len(boxes), pi))

        # Local export should be complete, not token-efficient: collect from all
        # detected paytable pages so lower-scroll symbols such as A/J/10 and
        # secondary food icons are not pushed out by earlier duplicate crops.
        if icons_only:
            selected_pages = sorted(page_results, key=lambda t: t[2])
            max_icons = 1200
        else:
            # AI identification still keeps a tighter budget because every crop
            # would be sent as an image input.
            selected_pages = sorted(
                [(imgs, n, pi) for imgs, n, pi in page_results
                 if n % 2 == 0 and n >= 8],
                key=lambda t: t[2]
            )
            if not selected_pages:
                selected_pages = sorted(page_results, key=lambda t: t[2])
            max_icons = 40

        icon_entries = []
        collected_by_page = {pi: 0 for _imgs, _n, pi in selected_pages}

        if icons_only:
            # Local export should cover the whole scrolled paytable, not just the
            # first high-density frames.  Round-robin across pages so lower rows
            # (J/10/nori sushi, etc.) enter the candidate pool before duplicates
            # from earlier scroll positions consume the full icon budget.
            max_page_icons = max((len(imgs) for imgs, _n, _pi in selected_pages), default=0)
            for icon_idx in range(max_page_icons):
                for imgs, _n, pi in selected_pages:
                    if icon_idx >= len(imgs):
                        continue
                    if len(icon_entries) >= max_icons:
                        break
                    icon_entries.append(imgs[icon_idx])
                    collected_by_page[pi] += 1
                if len(icon_entries) >= max_icons:
                    break
        else:
            for imgs, _n, pi in selected_pages:
                remaining = max_icons - len(icon_entries)
                if remaining <= 0:
                    break
                take = min(len(imgs), remaining)
                icon_entries.extend(imgs[:take])
                collected_by_page[pi] += take

        for _imgs, _n, pi in selected_pages:
            added = collected_by_page.get(pi, 0)
            if added:
                print(f"    [collect] page {pi}: added {added} "
                      f"icons (total so far: {len(icon_entries)})")

        if icon_entries:
            print(f"  Collected {len(icon_entries)} icons from "
                  f"{len(selected_pages)} paytable page(s)")
        else:
            print("  No icons extracted")

    if icon_entries:
        symbol_table_dir = video_dir / "symbol_table"
        export_meta = export_icon_crops(icon_entries, symbol_table_dir)
        print(f"  Icon crops -> {export_meta.get('candidates_dir')}")
        print(f"  Final symbols -> {export_meta.get('symbols_dir') or export_meta.get('final_icons_dir')} "
              f"({export_meta.get('final_count', 0)} selected)")

    if icons_only:
        print("  Icons-only mode: skipped Claude identification and symbol_table.html.")
        return

    # ?? Step 3: Claude identifies each extracted icon (Sonnet) ???????????????
    if icon_entries and not no_ai and api_key:
        print(f"  Stage 3: identifying {len(icon_entries)} icons (Sonnet)...")
        id_data = identify_icons_with_claude(api_key, icon_entries)

        if id_data:
            best_by_name = {}

            for entry in id_data.get("icons", []):
                if not entry.get("playable", True):
                    print(f"    [skip] Icon-{entry.get('id','?')}: "
                          f"{entry.get('name','?')} (not playable)")
                    continue
                tier = entry.get("tier", "low")
                if tier == "skip":
                    continue

                idx = entry.get("id", -1)
                name = (entry.get("name") or f"sym_{idx}").strip()
                if not name or name.lower() in ("skip", ""):
                    continue

                name_key = name.lower().strip()
                sym_id = re.sub(r"[^a-z0-9]+", "_",
                                name_key).strip("_") or f"sym_{idx}"
                crop_score = (icon_completeness_score(icon_entries[idx])
                              if 0 <= idx < len(icon_entries) else 0.0)

                record = {
                    "id":          sym_id,
                    "tier":        tier,
                    "label":       name,
                    "payout":      entry.get("payout", {}),
                    "notes":       entry.get("notes", ""),
                    "description": "",
                    "_icon_idx":   idx,
                    "_crop_score": crop_score,
                }

                prev = best_by_name.get(name_key)
                if prev is None or crop_score > prev.get("_crop_score", -999.0):
                    if prev is not None:
                        print(f"    [dedup] Icon-{idx}: '{name}' replaces "
                              f"lower-quality crop "
                              f"({crop_score:.1f} > {prev.get('_crop_score', 0):.1f})")
                    best_by_name[name_key] = record
                else:
                    print(f"    [dedup] Icon-{idx}: '{name}' lower-quality crop "
                          f"({crop_score:.1f} <= {prev.get('_crop_score', 0):.1f})")

            symbols = []
            for sym in best_by_name.values():
                idx = sym.pop("_icon_idx", -1)
                sym.pop("_crop_score", None)
                if 0 <= idx < len(icon_entries):
                    img_out = sym_img_dir / f"{sym['id']}.png"
                    crop_symbol(icon_entries[idx], 0, 0,
                                icon_entries[idx].width,
                                icon_entries[idx].height,
                                img_out)
                    ok_str = "OK" if img_out.exists() else "FAIL"
                    print(f"    {sym['id']} [{sym['tier']}]: {ok_str}")
                symbols.append(sym)
            ai_data = {
                "game_name":    id_data.get("game_name", ""),
                "grid":         id_data.get("grid", ""),
                "design_notes": id_data.get("design_notes", ""),
                "symbols":      symbols,
                "tier_order":   ["scatter","wild","M1","M2","M3","M4","M5","low"],
            }
            print(f"  Identified {len(symbols)} symbols: "
                  f"{ai_data.get('game_name', '?')}")

    # ?? Step 4: Generate HTML ?????????????????????????????????????????????????
    generate_html(video_dir, ai_data, sym_img_dir, out_path)


# ??? Entry point ??????????????????????????????????????????????????????????????

def find_video_dirs(root: Path) -> list:
    return [
        p for p in sorted(root.iterdir(), key=lambda x: x.name)
        if p.is_dir() and (p / "classification_result.csv").exists()
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Extract local symbol icon crops from Help/Paytable pages."
    )
    parser.add_argument(
        "--output-root", default=str(DEFAULT_OUTPUT_ROOT),
        help="Root folder containing per-video classification output.",
    )
    parser.add_argument(
        "--video-id", default=None,
        help="Process only this video folder name, e.g. '9'.",
    )
    parser.add_argument(
        "--api-key", default=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="Anthropic API key (falls back to ANTHROPIC_API_KEY env var).",
    )
    parser.add_argument(
        "--no-ai", action="store_true",
        help="Legacy compatibility flag. AI is already disabled unless --with-ai is set.",
    )
    parser.add_argument(
        "--icons-only", action="store_true",
        help="Extract and rank local symbol icon crops only; skip AI and HTML output.",
    )
    parser.add_argument(
        "--with-ai", action="store_true",
        help="Opt in to the legacy Claude identification and symbol_table.html generation path.",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Save intermediate images (dialog crops, bounding boxes, icon crops) "
             "to symbol_table/debug/ for inspection.",
    )
    args = parser.parse_args()

    if Image is None:
        print("Warning: Pillow not installed. Symbol cropping will be skipped.")
        print("         Run: pip install Pillow")

    root = Path(args.output_root)
    if not root.exists():
        print(f"Output root not found: {root}")
        sys.exit(1)

    video_dirs = find_video_dirs(root)
    if args.video_id:
        video_dirs = [d for d in video_dirs if d.name == args.video_id]

    if not video_dirs:
        print("No classified video folders found.")
        sys.exit(0)

    local_icons_only = True
    local_no_ai = True

    print(f"Found {len(video_dirs)} video folder(s).")
    print("Mode: local icon export only (no Claude/API, no symbol_table.html).")
    if args.with_ai:
        print("Note: --with-ai is currently disabled; Claude symbol_table.html generation was removed from the default workflow.")
    for vdir in video_dirs:
        process_video(vdir, api_key=args.api_key, no_ai=local_no_ai,
                      debug=args.debug, icons_only=local_icons_only)

    print(f"\nDone. {len(video_dirs)} icon crop set(s) generated.")


if __name__ == "__main__":
    main()
