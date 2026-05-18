#!/usr/bin/env python3
"""
test_opencv_detection.py

Standalone test: run dialog-crop + icon-detection on manually selected
paytable screenshots and save every intermediate image for inspection.

Usage:
    python test_opencv_detection.py
    python test_opencv_detection.py --input  path/to/paytable_folder
    python test_opencv_detection.py --output path/to/output_folder
    python test_opencv_detection.py --dark-threshold 55  # tweak detection
    python test_opencv_detection.py --row-threshold 0.25 # tweak row sensitivity
"""

import argparse
import sys
from pathlib import Path

# ── Try to import PIL / numpy ─────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow not installed. Run: pip install Pillow")

try:
    import numpy as np
except ImportError:
    sys.exit("numpy not installed. Run: pip install numpy")

# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_INPUT  = (
    r"C:\Users\ashleyli\Documents\Codex\2026-04-30"
    r"\files-mentioned-by-the-user-main"
    r"\slot_classifier_figma_share_package"
    r"\project\output\8\Help\help_paytable"
)
DEFAULT_OUTPUT = (
    r"C:\Users\ashleyli\Documents\Codex\2026-04-30"
    r"\files-mentioned-by-the-user-main"
    r"\slot_classifier_figma_share_package"
    r"\project\output\8\symbol_table\cv_test"
)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Dialog crop
# ══════════════════════════════════════════════════════════════════════════════

def auto_crop_dialog(img: Image.Image, dark: int = 55) -> tuple:
    """
    Find the centered dark dialog panel and crop to it.
    Returns (cropped_Image, x_offset, y_offset).

    Problem this solves: many slot games have a dark background (shrine walls,
    night sky, etc.) that is also below the brightness threshold, causing the
    raw dark-pixel scan to return the full image width.  When the raw horizontal
    detection is implausibly wide we fall back to an aspect-ratio estimate:
    portrait slot dialogs are typically ~1.75× taller than they are wide, so we
    compute width from the already-detected height.
    """
    orig_w, orig_h = img.size
    gray = np.array(img.convert("L"), dtype=np.float32)

    MIN_COV = 0.12   # at least 12 % of rows/cols must be "dark"
    cx = orig_w // 2

    # ── Step 1: Vertical bounds — scan center column strip ───────────────────
    sw       = max(20, orig_w // 12)
    strip    = gray[:, cx - sw : cx + sw]
    row_mean = strip.mean(axis=1)
    dark_rows = np.where(row_mean < dark)[0]

    if len(dark_rows) < orig_h * MIN_COV:
        print(f"    [crop] vertical detection weak "
              f"({len(dark_rows)}/{orig_h} dark rows) — using centre fallback")
        y1, y2 = int(orig_h * 0.04), int(orig_h * 0.96)
    else:
        y1 = max(0,      int(dark_rows[0])  - 8)
        y2 = min(orig_h, int(dark_rows[-1]) + 8)

    # ── Step 2: Horizontal bounds — scan a row at mid-dialog height ──────────
    mid_y    = (y1 + y2) // 2
    row_slab = gray[max(0, mid_y - 8) : mid_y + 8, :]
    col_mean = row_slab.mean(axis=0)
    dark_cols = np.where(col_mean < dark)[0]

    if len(dark_cols) < orig_w * MIN_COV:
        print(f"    [crop] horizontal detection weak — using aspect-ratio estimate")
        raw_x1, raw_x2 = 0, orig_w   # will be replaced below
    else:
        raw_x1 = max(0,      int(dark_cols[0])  - 8)
        raw_x2 = min(orig_w, int(dark_cols[-1]) + 8)

    # ── Step 3: Width sanity — if too wide, background is also dark ──────────
    # Slot game backgrounds (shrines, night sky, etc.) often share the darkness
    # of the dialog panel, making the raw scan return the full image width.
    # Fix: estimate the dialog width from its height (portrait ratio ≈ 1.75:1).
    if (raw_x2 - raw_x1) > orig_w * 0.65:
        dialog_h = y2 - y1
        dialog_w = int(dialog_h / 1.75)
        x1 = max(0,      cx - dialog_w // 2)
        x2 = min(orig_w, cx + dialog_w // 2)
        print(f"    [crop] raw width {raw_x2 - raw_x1}px > 65 % of image "
              f"(dark background) → aspect-ratio estimate: {dialog_w}px wide")
    else:
        x1, x2 = raw_x1, raw_x2

    # ── Step 4: Final sanity ─────────────────────────────────────────────────
    if (x2 - x1) < orig_w * 0.12:
        print(f"    [crop] result too narrow — using centre fallback")
        x1, x2 = int(orig_w * 0.33), int(orig_w * 0.67)
    if (y2 - y1) < orig_h * 0.20:
        print(f"    [crop] result too short — using centre fallback")
        y1, y2 = int(orig_h * 0.04), int(orig_h * 0.96)

    print(f"    [crop] dialog bounds: x={x1}–{x2}, y={y1}–{y2}  "
          f"({x2-x1}×{y2-y1})")
    return img.crop((x1, y1, x2, y2)).copy(), x1, y1


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — Icon detection
# ══════════════════════════════════════════════════════════════════════════════

def detect_icons(dialog_img: Image.Image,
                 col_sigma: float = 0.35,
                 row_sigma: float = 0.25) -> list:
    """
    Find symbol icon bounding boxes inside the pre-cropped dialog.

    col_sigma  — column detection sensitivity (std-devs above mean)
    row_sigma  — unused legacy parameter; row detection now uses local-peak
                 finding, which is immune to the "peaks too narrow" problem
                 that plagued threshold-based row detection.

    Returns [(x, y, w, h), ...] sorted left->right, top->bottom.
    """
    arr    = np.array(dialog_img.convert("RGB"), dtype=np.float32)
    H, W   = arr.shape[:2]
    bright = arr.mean(axis=2)               # luminance (H, W)

    # Skip title bar (top ~12%)
    cs      = int(H * 0.12)
    content = bright[cs:, :]
    CH      = content.shape[0]             # content height

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

    # ── Column detection (std-dev = colourful icon columns) ──────────────────
    col_std = content.std(axis=0)
    col_s   = smooth(col_std, W / 30)
    thr_c   = col_s.mean() + col_s.std() * col_sigma
    c_grps  = find_groups(col_s > thr_c)
    c_grps  = [(s, e) for s, e in c_grps if W * 0.06 <= (e - s) <= W * 0.30]
    c_grps.sort(key=lambda g: col_s[g[0]:g[1]+1].sum(), reverse=True)
    raw_icon_cols = sorted(c_grps[:2], key=lambda g: g[0])

    # Narrow wide groups: [icon][payout text] layouts produce a wide group;
    # split at the local std-dev minimum and keep the left (icon) sub-range.
    icon_cols = []
    icon_max_w = int(W * 0.18)
    icon_min_w = max(4, int(W * 0.06))
    for s, e in raw_icon_cols:
        gw = e - s + 1
        if gw <= icon_max_w:
            icon_cols.append((s, e))
        else:
            margin = max(icon_min_w, gw // 5)
            seg    = col_s[s + margin : e - margin + 1]
            split  = (s + margin + int(np.argmin(seg))) if len(seg) > 0 else (s + icon_max_w)
            icon_cols.append((s, max(s + icon_min_w, split - 1)))

    print(f"    [detect] col_std mean={col_std.mean():.1f}  "
          f"std={col_std.std():.1f}  threshold={thr_c:.1f}")
    print(f"    [detect] {len(c_grps)} column group(s) above threshold, "
          f"kept top 2: {icon_cols}")

    if not icon_cols:
        print("    [detect] WARNING: no icon columns found")
        return []

    # ── Row detection via local-peak finding ─────────────────────────────────
    # Threshold-based "find above-threshold regions" fails here because the
    # brightness peaks are narrow — they only briefly exceed the threshold,
    # creating above-threshold windows that are too small to pass a size
    # filter.  Instead we find local maxima (one per icon row) and use the
    # valleys between adjacent peaks as row boundaries.
    col_mask = np.zeros(W, dtype=bool)
    for s, e in icon_cols:
        col_mask[s : e + 1] = True

    row_bright = content[:, col_mask].mean(axis=1)
    row_s      = smooth(row_bright, max(1, CH // 50))

    # Minimum distance between icon rows: slots rarely pack rows closer than
    # 6% of the content height.
    min_dist   = max(4, int(CH * 0.06))
    min_height = row_s.mean()              # peak must be above average

    def find_local_peaks(profile, min_d, min_h):
        """Strict local maxima with minimum spacing and minimum height."""
        peaks = []
        n = len(profile)
        for i in range(1, n - 1):
            if profile[i] > profile[i - 1] and profile[i] > profile[i + 1]:
                if profile[i] >= min_h:
                    if not peaks or (i - peaks[-1]) >= min_d:
                        peaks.append(i)
                    elif profile[i] > profile[peaks[-1]]:
                        peaks[-1] = i   # prefer taller of two close peaks
        return peaks

    # Only search the icon area — the last ~15% of content is usually a
    # footer (feature descriptions, footnotes) whose bright text creates
    # spurious peaks.  Capping at 85% of CH removes those false positives
    # without cutting off the last real icon row, which is always within
    # the first 83% of content for the paytable layouts we've seen.
    icon_area_end = int(CH * 0.85)
    peaks = find_local_peaks(row_s[:icon_area_end], min_dist, min_height)
    print(f"    [detect] row profile: mean={row_bright.mean():.1f}  "
          f"peaks found: {len(peaks)}")

    # Convert peaks -> (ys, ye) in full-image coordinates using valley bounds
    r_grps = []
    for idx, p in enumerate(peaks):
        # Left boundary: valley between previous peak and this one
        if idx > 0:
            prev_p = peaks[idx - 1]
            valley_l = prev_p + int(np.argmin(row_s[prev_p : p + 1]))
        else:
            valley_l = max(0, p - min_dist // 2)

        # Right boundary: valley between this peak and next one
        if idx < len(peaks) - 1:
            next_p = peaks[idx + 1]
            valley_r = p + int(np.argmin(row_s[p : next_p + 1]))
        else:
            valley_r = min(CH - 1, p + min_dist // 2)

        ys = valley_l + cs
        ye = valley_r + cs

        # Sanity: row must be at least 3% of full dialog height
        if (ye - ys) >= H * 0.03:
            r_grps.append((ys, ye))

    print(f"    [detect] {len(r_grps)} icon row(s) after valley splitting")

    if not r_grps:
        print("    [detect] WARNING: no icon rows found")
        return []

    # ── Build grid ────────────────────────────────────────────────────────────
    icons = []
    for (ys, ye) in r_grps:
        for (xs, xe) in icon_cols:
            icons.append((xs, ys, xe - xs + 1, ye - ys + 1))

    print(f"    [detect] OK {len(icons)} icons  "
          f"({len(r_grps)} rows x {len(icon_cols)} cols)")
    return icons


# ══════════════════════════════════════════════════════════════════════════════
# Visualisation helpers
# ══════════════════════════════════════════════════════════════════════════════

def draw_boxes(img: Image.Image, boxes: list,
               color=(255, 60, 60), width=3) -> Image.Image:
    vis  = img.copy().convert("RGB")
    draw = ImageDraw.Draw(vis)
    for i, (x, y, w, h) in enumerate(boxes):
        draw.rectangle([x, y, x + w, y + h], outline=color, width=width)
        draw.text((x + 4, y + 4), str(i), fill=(255, 255, 0))
    return vis


def save_profile_chart(profile: np.ndarray, threshold: float,
                        out_path: Path, title: str = ""):
    """Save a simple brightness-profile bar chart as a PNG."""
    W  = len(profile)
    H  = 200
    scale = H / (profile.max() + 1)
    canvas = Image.new("RGB", (W, H + 20), (20, 20, 30))
    draw   = ImageDraw.Draw(canvas)

    # Bars
    for x, v in enumerate(profile):
        bar_h = int(v * scale)
        col   = (80, 160, 255) if v < threshold else (255, 120, 60)
        draw.line([(x, H), (x, H - bar_h)], fill=col)

    # Threshold line
    thr_y = H - int(threshold * scale)
    draw.line([(0, thr_y), (W, thr_y)], fill=(255, 255, 80), width=1)
    draw.text((4, 2), title[:80], fill=(200, 200, 200))
    canvas.save(out_path, "PNG")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def run(input_dir: Path, output_dir: Path,
        dark: int, col_sigma: float, row_sigma: float):

    output_dir.mkdir(parents=True, exist_ok=True)
    images = sorted(input_dir.glob("*.jpg")) + sorted(input_dir.glob("*.png"))

    if not images:
        sys.exit(f"No images found in {input_dir}")

    print(f"\nInput  : {input_dir}  ({len(images)} images)")
    print(f"Output : {output_dir}")
    print(f"Params : dark={dark}  col_sigma={col_sigma}  row_sigma={row_sigma}\n")

    all_icon_count = 0

    for img_path in images:
        stem = img_path.stem
        print(f"─── {img_path.name} ──────────────────────────────────────────")

        orig = Image.open(img_path)
        print(f"    original size: {orig.width}×{orig.height}")

        # ── 1. Dialog crop ────────────────────────────────────────────────────
        dialog, x_off, y_off = auto_crop_dialog(orig, dark=dark)
        dialog.save(output_dir / f"{stem}_1_dialog.jpg", "JPEG", quality=92)
        print(f"    dialog saved  ({dialog.width}×{dialog.height})")

        # ── 2. Icon detection ─────────────────────────────────────────────────
        boxes = detect_icons(dialog, col_sigma=col_sigma, row_sigma=row_sigma)

        # Save annotated dialog
        vis = draw_boxes(dialog, boxes)
        vis.save(output_dir / f"{stem}_2_boxes.jpg", "JPEG", quality=92)
        print(f"    boxes saved   ({len(boxes)} boxes)")

        # ── 3. Profile charts (for tuning thresholds) ─────────────────────────
        arr    = np.array(dialog.convert("RGB"), dtype=np.float32)
        H, W   = arr.shape[:2]
        cs     = int(H * 0.12)
        content = arr[cs:, :].mean(axis=2)

        # Column std-dev profile
        col_std  = content.std(axis=0)
        k_c      = max(1, int(W / 30))
        col_s    = np.convolve(col_std, np.ones(k_c)/k_c, mode="same")
        thr_c    = col_s.mean() + col_s.std() * col_sigma
        save_profile_chart(col_s, thr_c,
                           output_dir / f"{stem}_3a_col_profile.png",
                           "Column std-dev (orange = above threshold)")

        # Row brightness profile
        col_mask = np.zeros(W, dtype=bool)
        if boxes:
            xs_all = sorted(set(b[0] for b in boxes))
            xe_all = sorted(set(b[0] + b[2] for b in boxes))
            for xs, xe in zip(xs_all, xe_all):
                col_mask[xs:xe] = True
        else:
            col_mask[W//8 : W*3//8] = True
            col_mask[W//2 : W*7//8] = True

        row_bright = content[:, col_mask].mean(axis=1)
        k_r        = max(1, int(H / 50))
        row_s      = np.convolve(row_bright, np.ones(k_r)/k_r, mode="same")
        thr_r      = row_s.mean() + row_s.std() * row_sigma
        save_profile_chart(row_s, thr_r,
                           output_dir / f"{stem}_3b_row_profile.png",
                           "Row brightness (orange = icon rows)")

        # ── 4. Save individual icon crops ─────────────────────────────────────
        pad = 4
        for i, (bx, by, bw, bh) in enumerate(boxes):
            x1 = max(0, bx - pad);  y1 = max(0, by - pad)
            x2 = min(dialog.width,  bx + bw + pad)
            y2 = min(dialog.height, by + bh + pad)
            icon = dialog.crop((x1, y1, x2, y2))
            icon.save(output_dir / f"{stem}_4_icon{i:02d}.jpg",
                      "JPEG", quality=92)

        all_icon_count += len(boxes)
        print()

    print(f"Done. {all_icon_count} icons extracted from {len(images)} image(s).")
    print(f"Results in: {output_dir}\n")
    print("Files per image:")
    print("  *_1_dialog.jpg     — auto-cropped dialog panel")
    print("  *_2_boxes.jpg      — dialog + red bounding boxes")
    print("  *_3a_col_profile   — column std-dev chart (for tuning col_sigma)")
    print("  *_3b_row_profile   — row brightness chart  (for tuning row_sigma)")
    print("  *_4_icon##.jpg     — individual extracted icons")
    print()
    print("If boxes are wrong, try adjusting:")
    print("  --col-sigma  (default 0.35, lower = detect more columns)")
    print("  --row-sigma  (default 0.25, lower = detect more rows)")
    print("  --dark       (default 55,   lower = stricter dialog crop)")


def main():
    p = argparse.ArgumentParser(
        description="OpenCV icon detection test — saves all intermediate images."
    )
    p.add_argument("--input",     default=DEFAULT_INPUT,
                   help="Folder with manually selected paytable screenshots")
    p.add_argument("--output",    default=DEFAULT_OUTPUT,
                   help="Folder to save debug images")
    p.add_argument("--dark",      type=int,   default=55,
                   help="Brightness threshold for dialog detection (default 55)")
    p.add_argument("--col-sigma", type=float, default=0.35,
                   help="Column detection sensitivity (default 0.35)")
    p.add_argument("--row-sigma", type=float, default=0.25,
                   help="Row detection sensitivity (default 0.25)")
    args = p.parse_args()

    run(
        input_dir  = Path(args.input),
        output_dir = Path(args.output),
        dark       = args.dark,
        col_sigma  = getattr(args, "col_sigma"),
        row_sigma  = getattr(args, "row_sigma"),
    )


if __name__ == "__main__":
    main()
