import os

import cv2
import numpy as np

try:
    from .config import (
        AUTO_ROI_BROWSER_TOP_RATIO,
        AUTO_ROI_COLUMN_PADDING,
        AUTO_ROI_LANDSCAPE_MAX_HEIGHT_RATIO,
        AUTO_ROI_LANDSCAPE_MAX_WIDTH_RATIO,
        AUTO_ROI_LANDSCAPE_MIN_WIDTH_RATIO,
        AUTO_ROI_LANDSCAPE_PADDING,
        AUTO_ROI_MAX_WIDTH_RATIO,
        AUTO_ROI_MIN_AREA_RATIO,
        AUTO_ROI_MIN_WIDTH_RATIO,
        AUTO_ROI_MOTION_THRESHOLD,
        AUTO_ROI_MOTION_X_PADDING,
        AUTO_ROI_MOTION_Y_PADDING,
        AUTO_ROI_NATIVE_PORTRAIT_ASPECT_MAX,
        AUTO_ROI_NATIVE_PORTRAIT_MIN_WIDTH_RATIO,
        AUTO_ROI_PADDING,
        AUTO_ROI_SAMPLE_COUNT,
        AUTO_ROI_TIGHTEN_PORTRAIT_COLUMN,
        AUTO_ROI_TRIM_BROWSER_TOP,
        AUTO_ROI_USE_MOTION_BBOX_FOR_PORTRAIT,
        AUTO_ROI_WEB_HELP_TALL_RATIO,
        AUTO_ROI_WEB_HELP_WIDE_RATIO,
        MAX_ROI_AREA_RATIO,
        SAVE_ROI_DEBUG_IMAGE,
        WEB_HELP_FULL_PAGE_CROP,
        WEB_HELP_FULL_PAGE_MIN_ASPECT,
    )
except ImportError:
    from config import (
        AUTO_ROI_BROWSER_TOP_RATIO,
        AUTO_ROI_COLUMN_PADDING,
        AUTO_ROI_LANDSCAPE_MAX_HEIGHT_RATIO,
        AUTO_ROI_LANDSCAPE_MAX_WIDTH_RATIO,
        AUTO_ROI_LANDSCAPE_MIN_WIDTH_RATIO,
        AUTO_ROI_LANDSCAPE_PADDING,
        AUTO_ROI_MAX_WIDTH_RATIO,
        AUTO_ROI_MIN_AREA_RATIO,
        AUTO_ROI_MIN_WIDTH_RATIO,
        AUTO_ROI_MOTION_THRESHOLD,
        AUTO_ROI_MOTION_X_PADDING,
        AUTO_ROI_MOTION_Y_PADDING,
        AUTO_ROI_NATIVE_PORTRAIT_ASPECT_MAX,
        AUTO_ROI_NATIVE_PORTRAIT_MIN_WIDTH_RATIO,
        AUTO_ROI_PADDING,
        AUTO_ROI_SAMPLE_COUNT,
        AUTO_ROI_TIGHTEN_PORTRAIT_COLUMN,
        AUTO_ROI_TRIM_BROWSER_TOP,
        AUTO_ROI_USE_MOTION_BBOX_FOR_PORTRAIT,
        AUTO_ROI_WEB_HELP_TALL_RATIO,
        AUTO_ROI_WEB_HELP_WIDE_RATIO,
        MAX_ROI_AREA_RATIO,
        SAVE_ROI_DEBUG_IMAGE,
        WEB_HELP_FULL_PAGE_CROP,
        WEB_HELP_FULL_PAGE_MIN_ASPECT,
    )

try:
    from .video_io import imwrite_image, read_sample_frames
except ImportError:
    from video_io import imwrite_image, read_sample_frames


def longest_active_interval(projection, must_include_min, must_include_max, min_active_ratio=0.12, gap_tolerance=18):
    """
    從投影分布中找包含動態區間的主要活動區域。
    用 gap_tolerance 允許中間有少量空白，避免被 UI 線條切斷。
    """
    if projection.size == 0:
        return 0, 0

    max_val = float(np.max(projection))
    if max_val <= 0:
        return 0, projection.size - 1

    threshold = max_val * min_active_ratio
    active = projection >= threshold

    # 保證必須包含 motion bbox
    must_include_min = max(0, int(must_include_min))
    must_include_max = min(projection.size - 1, int(must_include_max))
    active[must_include_min:must_include_max + 1] = True

    # 填補小 gap
    filled = active.copy()
    last_true = None
    for i, v in enumerate(active):
        if v:
            if last_true is not None and i - last_true <= gap_tolerance:
                filled[last_true:i + 1] = True
            last_true = i

    idxs = np.where(filled)[0]
    if len(idxs) == 0:
        return 0, projection.size - 1

    return int(idxs[0]), int(idxs[-1])


def smooth_1d(values, kernel_size=15):
    if len(values) == 0:
        return values

    kernel_size = max(3, int(kernel_size))
    if kernel_size % 2 == 0:
        kernel_size += 1

    kernel = np.ones(kernel_size, dtype=np.float32) / kernel_size
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def largest_true_run(mask):
    best_start = None
    best_end = None
    current_start = None

    for idx, value in enumerate(mask):
        if value and current_start is None:
            current_start = idx
        elif not value and current_start is not None:
            end = idx - 1
            if best_start is None or end - current_start > best_end - best_start:
                best_start = current_start
                best_end = end
            current_start = None

    if current_start is not None:
        end = len(mask) - 1
        if best_start is None or end - current_start > best_end - best_start:
            best_start = current_start
            best_end = end

    return best_start, best_end


def find_portrait_game_column(content_mask, edge_mask, current_x1, current_x2):
    """
    背景雲層/動畫也有 motion 時，原本投影會把 ROI 撐太寬。
    這裡改抓中心附近「垂直方向持續有高細節」的欄位，對直式手機 slot 畫面較穩。
    """
    h, w = content_mask.shape[:2]
    if w <= 0 or h <= 0:
        return None

    y_start = int(h * 0.07)
    y_end = int(h * 0.96)
    content_roi = content_mask[y_start:y_end, :]
    edge_roi = edge_mask[y_start:y_end, :]

    content_profile = np.mean(content_roi > 0, axis=0)
    edge_profile = np.mean(edge_roi > 0, axis=0)
    profile = smooth_1d(content_profile * 0.55 + edge_profile * 0.45, kernel_size=max(9, w // 45))

    if float(np.max(profile)) <= 0:
        return None

    # 優先選目前 ROI 中央附近的高細節區，避免左右背景熱氣球或雲層干擾。
    roi_center = (current_x1 + current_x2) / 2.0
    screen_center = w / 2.0
    expected_center = roi_center if abs(roi_center - screen_center) < w * 0.18 else screen_center

    threshold = max(float(np.percentile(profile, 72)), float(np.max(profile)) * 0.38)
    active = profile >= threshold

    max_width = int(w * AUTO_ROI_MAX_WIDTH_RATIO)
    min_width = int(w * AUTO_ROI_MIN_WIDTH_RATIO)
    search_pad = max(max_width, int((current_x2 - current_x1 + 1) * 0.65))
    search_left = max(0, int(expected_center - search_pad))
    search_right = min(w - 1, int(expected_center + search_pad))

    active[:search_left] = False
    active[search_right + 1:] = False

    run_start, run_end = largest_true_run(active)
    if run_start is None:
        return None

    # 若高細節 run 太窄，從峰值向外擴到合理的直式遊戲寬度。
    if run_end - run_start + 1 < min_width:
        peak = int(np.argmax(profile[search_left:search_right + 1]) + search_left)
        half_width = max(min_width // 2, int((current_x2 - current_x1 + 1) * 0.32))
        run_start = max(0, peak - half_width)
        run_end = min(w - 1, peak + half_width)

    if run_end - run_start + 1 > max_width:
        center = int(round((run_start + run_end) / 2))
        half_width = max_width // 2
        run_start = max(0, center - half_width)
        run_end = min(w - 1, center + half_width)

    pad = max(2, int(AUTO_ROI_COLUMN_PADDING))
    return max(0, run_start - pad), min(w - 1, run_end + pad)


def constrain_browser_portrait_box(x1, y1, x2, y2, frame_w, frame_h):
    """
    Keep a portrait mobile game centered inside a landscape browser capture.

    Some games have saturated animated side art outside the phone viewport.  The
    motion bbox then grows left/right and later symbol crops inherit that offset.
    When the detected portrait box is wider than a normal phone viewport, shrink
    it around the screen center while preserving the detected vertical extent.
    """
    if frame_w <= 0 or frame_h <= 0:
        return x1, y1, x2, y2
    if frame_w / float(max(1, frame_h)) <= 1.4:
        return x1, y1, x2, y2

    current_w = max(1, x2 - x1 + 1)
    current_h = max(1, y2 - y1 + 1)
    width_ratio = current_w / float(frame_w)
    if width_ratio <= AUTO_ROI_MAX_WIDTH_RATIO:
        return x1, y1, x2, y2

    min_w = max(1, int(round(frame_w * AUTO_ROI_MIN_WIDTH_RATIO)))
    max_w = max(min_w, int(round(frame_w * 0.32)))
    target_w = int(round(current_h * 0.48))
    target_w = max(min_w, min(max_w, target_w, current_w))
    if target_w >= current_w:
        return x1, y1, x2, y2

    motion_center = (x1 + x2) / 2.0
    screen_center = frame_w / 2.0
    if abs(motion_center - screen_center) <= frame_w * 0.16:
        center = screen_center * 0.82 + motion_center * 0.18
    else:
        center = motion_center

    nx1 = int(round(center - target_w / 2.0))
    nx1 = max(0, min(nx1, frame_w - target_w))
    return nx1, y1, nx1 + target_w - 1, y2


def refine_browser_portrait_top(frame, rx, ry, rw, rh):
    """
    Trim browser chrome/bookmark rows above a portrait game embedded in a wide capture.

    A fixed top ratio is fragile across Chrome layouts.  FortuneMahjong-style
    recordings can leave the bookmark bar inside the ROI, so use the first
    sustained saturated/dark row inside the detected portrait column as the
    actual game canvas top.
    """
    H, W = frame.shape[:2]
    if W <= 0 or H <= 0 or rw <= 0 or rh <= 0:
        return rx, ry, rw, rh
    if W / float(max(1, H)) <= 1.4:
        return rx, ry, rw, rh
    if rw / float(max(1, W)) > 0.45 or rh / float(max(1, H)) < 0.55:
        return rx, ry, rw, rh
    if ry >= int(round(H * 0.16)):
        return rx, ry, rw, rh

    x1 = max(0, int(rx + rw * 0.04))
    x2 = min(W, int(rx + rw * 0.96))
    y_start = max(0, int(ry))
    y_limit = min(H, int(max(ry + 1, min(ry + rh * 0.22, H * 0.22))))
    if x2 <= x1 or y_limit <= y_start + 4:
        return rx, ry, rw, rh

    roi = frame[y_start:y_limit, x1:x2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    saturated = (sat > 55) & (val > 45)
    dark_content = gray < 218
    row_score = saturated.mean(axis=1) * 0.70 + dark_content.mean(axis=1) * 0.30
    row_score = smooth_1d(row_score.astype(np.float32), kernel_size=7)

    threshold = max(0.18, float(np.percentile(row_score, 88)) * 0.55)
    active = row_score >= threshold
    min_run = max(3, int(round(H * 0.004)))
    for idx in range(0, max(0, len(active) - min_run + 1)):
        if bool(np.all(active[idx:idx + min_run])):
            new_ry = y_start + idx
            if new_ry > ry + 3:
                bottom = ry + rh
                ry = min(new_ry, H - 1)
                rh = max(1, bottom - ry)
            break

    return rx, ry, rw, rh


def find_landscape_game_box(content_mask, motion_box):
    h, w = content_mask.shape[:2]
    mx, my, mw, mh = motion_box
    if w <= 0 or h <= 0:
        return None

    x_projection = np.mean(content_mask, axis=0)
    y_projection = np.mean(content_mask, axis=1)

    x1, x2 = longest_active_interval(
        x_projection,
        mx,
        mx + mw,
        min_active_ratio=0.18,
        gap_tolerance=max(16, w // 35)
    )
    y1, y2 = longest_active_interval(
        y_projection,
        my,
        my + mh,
        min_active_ratio=0.14,
        gap_tolerance=max(12, h // 35)
    )

    # 橫式遊戲通常是置中的 iframe，下面可能接網站說明文字；高度若被吃太深，優先回到動態遊戲區。
    width_ratio = (x2 - x1 + 1) / float(w)
    height_ratio = (y2 - y1 + 1) / float(h)
    if (
        width_ratio < AUTO_ROI_LANDSCAPE_MIN_WIDTH_RATIO
        or width_ratio > AUTO_ROI_LANDSCAPE_MAX_WIDTH_RATIO
    ):
        x1, x2 = mx, mx + mw
    if height_ratio > AUTO_ROI_LANDSCAPE_MAX_HEIGHT_RATIO:
        y1, y2 = my, my + mh

    pad = max(3, int(AUTO_ROI_LANDSCAPE_PADDING * (w / 480.0)))
    x1 = max(0, int(x1) - pad)
    y1 = max(0, int(y1) - pad)
    x2 = min(w - 1, int(x2) + pad)
    y2 = min(h - 1, int(y2) + pad)

    return x1, y1, x2, y2


def motion_contour_game_score(contour, frame_w, frame_h):
    x, y, w, h = cv2.boundingRect(contour)
    area = max(float(cv2.contourArea(contour)), float(w * h))
    width_ratio = w / float(max(1, frame_w))
    height_ratio = h / float(max(1, frame_h))
    aspect = w / float(max(1, h))
    center_x = x + w / 2.0
    center_y = y + h / 2.0
    center_penalty = 1.0 - min(0.75, abs(center_x - frame_w / 2.0) / float(max(1, frame_w)))
    score = area * max(0.25, center_penalty)

    is_portrait_game = (
        AUTO_ROI_MIN_WIDTH_RATIO <= width_ratio <= 0.50
        and height_ratio >= 0.45
        and aspect <= 1.05
    )
    is_landscape_game = (
        AUTO_ROI_LANDSCAPE_MIN_WIDTH_RATIO <= width_ratio <= 0.72
        and height_ratio <= AUTO_ROI_LANDSCAPE_MAX_HEIGHT_RATIO + 0.08
        and aspect >= 1.10
    )
    is_web_help_page = (
        width_ratio >= AUTO_ROI_WEB_HELP_WIDE_RATIO
        and height_ratio >= AUTO_ROI_WEB_HELP_TALL_RATIO
        and center_y >= frame_h * 0.35
    )

    if is_portrait_game:
        score *= 3.0
    elif is_landscape_game:
        score *= 2.2
    elif is_web_help_page:
        score *= 0.18

    return score


def select_game_motion_contour(contours, frame_w, frame_h):
    if not contours:
        return None
    return max(contours, key=lambda cnt: motion_contour_game_score(cnt, frame_w, frame_h))


def get_web_help_page_roi(frame):
    if not WEB_HELP_FULL_PAGE_CROP:
        return None
    H, W = frame.shape[:2]
    if W / float(max(1, H)) < WEB_HELP_FULL_PAGE_MIN_ASPECT:
        return None
    top = int(round(H * AUTO_ROI_BROWSER_TOP_RATIO)) if AUTO_ROI_TRIM_BROWSER_TOP else 0
    top = max(0, min(top, H - 1))
    return 0, top, W, H - top


def auto_detect_game_area(video_path, debug_dir=None):
    """
    先用多幀差異找動畫區域，再搭配邊緣/飽和度投影往外擴到遊戲矩形。
    目標：保留遊戲本體 UI，但排除網頁背景、瀏覽器、說明文字。
    """
    frames = read_sample_frames(video_path, AUTO_ROI_SAMPLE_COUNT)
    if len(frames) < 2:
        return None

    H, W = frames[0].shape[:2]
    small_w = 480
    scale = small_w / W
    small_h = int(H * scale)

    small_frames = [cv2.resize(f, (small_w, small_h)) for f in frames]
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in small_frames]

    motion_acc = np.zeros((small_h, small_w), dtype=np.float32)
    for prev, curr in zip(grays[:-1], grays[1:]):
        diff = cv2.absdiff(prev, curr)
        motion_acc += diff.astype(np.float32)

    motion_map = motion_acc / max(1, len(grays) - 1)

    _, motion_mask = cv2.threshold(
        motion_map.astype(np.uint8),
        AUTO_ROI_MOTION_THRESHOLD,
        255,
        cv2.THRESH_BINARY
    )

    # 接合零碎動態：slot reel、閃光、按鈕動畫會被連成一塊
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_CLOSE, kernel)
    motion_mask = cv2.dilate(motion_mask, kernel, iterations=1)

    contours, _ = cv2.findContours(motion_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # 選最像遊戲本體的動態區；網頁式 Help 進出時會整頁變動，不能讓它拉歪遊戲 ROI。
    largest = select_game_motion_contour(contours, small_w, small_h)
    if largest is None:
        return None
    mx, my, mw, mh = cv2.boundingRect(largest)

    area_ratio = (mw * mh) / float(small_w * small_h)
    if area_ratio < AUTO_ROI_MIN_AREA_RATIO:
        return None

    # 用平均畫面抓邊緣與高飽和內容，輔助把靜態底部 UI / 上方 UI 納進來
    avg = np.mean(np.stack(small_frames).astype(np.float32), axis=0).astype(np.uint8)
    hsv = cv2.cvtColor(avg, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    gray_avg = cv2.cvtColor(avg, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray_avg, 60, 140)

    _, sat_mask = cv2.threshold(sat, 35, 255, cv2.THRESH_BINARY)

    content_mask = cv2.bitwise_or(edges, sat_mask)
    content_mask = cv2.bitwise_or(content_mask, motion_mask)
    content_mask = cv2.morphologyEx(
        content_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    )

    x_projection = np.mean(content_mask, axis=0)
    y_projection = np.mean(content_mask, axis=1)

    x1, x2 = longest_active_interval(
        x_projection,
        mx,
        mx + mw,
        min_active_ratio=0.10,
        gap_tolerance=20
    )
    y1, y2 = longest_active_interval(
        y_projection,
        my,
        my + mh,
        min_active_ratio=0.08,
        gap_tolerance=28
    )

    motion_width_ratio = mw / float(small_w)
    motion_height_ratio = mh / float(small_h)
    motion_aspect_ratio = mw / float(max(1, mh))
    motion_is_landscape_game = (
        motion_width_ratio >= AUTO_ROI_LANDSCAPE_MIN_WIDTH_RATIO
        and motion_aspect_ratio >= 1.15
        and (
            motion_height_ratio <= AUTO_ROI_LANDSCAPE_MAX_HEIGHT_RATIO
            or (
                motion_width_ratio >= 0.55
                and motion_height_ratio <= 0.86
            )
        )
    )
    motion_is_portrait_game = (
        AUTO_ROI_USE_MOTION_BBOX_FOR_PORTRAIT
        and motion_height_ratio >= 0.62
        and AUTO_ROI_MIN_WIDTH_RATIO <= motion_width_ratio <= 0.48
    )

    if motion_is_landscape_game:
        landscape_box = find_landscape_game_box(content_mask, (mx, my, mw, mh))
        if landscape_box:
            x1, y1, x2, y2 = landscape_box
    elif motion_is_portrait_game:
        x_extra = max(2, int(AUTO_ROI_MOTION_X_PADDING * scale))
        y_extra = max(2, int(AUTO_ROI_MOTION_Y_PADDING * scale))
        x1 = max(0, mx - x_extra)
        x2 = min(small_w - 1, mx + mw + x_extra)
        y1 = max(0, my - y_extra)
        y2 = min(small_h - 1, my + mh + y_extra)
        x1, y1, x2, y2 = constrain_browser_portrait_box(x1, y1, x2, y2, small_w, small_h)
    elif (
        AUTO_ROI_TIGHTEN_PORTRAIT_COLUMN
        and (
            motion_height_ratio >= 0.52
            or (
                motion_width_ratio >= AUTO_ROI_WEB_HELP_WIDE_RATIO
                and motion_height_ratio >= AUTO_ROI_WEB_HELP_TALL_RATIO
            )
        )
    ):
        portrait_column = find_portrait_game_column(content_mask, edges, x1, x2)
        if portrait_column:
            x1, x2 = portrait_column

    pad_small = max(4, int(AUTO_ROI_PADDING * scale))
    x1 = max(0, x1 - pad_small)
    y1 = max(0, y1 - pad_small)
    x2 = min(small_w - 1, x2 + pad_small)
    y2 = min(small_h - 1, y2 + pad_small)

    # 如果投影擴太大，回退到 motion bbox + 較大 padding，避免整個網頁被吃進去
    roi_area_ratio = ((x2 - x1 + 1) * (y2 - y1 + 1)) / float(small_w * small_h)
    if roi_area_ratio > MAX_ROI_AREA_RATIO:
        extra = int(80 * scale)
        x1 = max(0, mx - extra)
        y1 = max(0, my - extra)
        x2 = min(small_w - 1, mx + mw + extra)
        y2 = min(small_h - 1, my + mh + extra)

    # 轉回原解析度
    rx = int(round(x1 / scale))
    ry = int(round(y1 / scale))
    rw = int(round((x2 - x1 + 1) / scale))
    rh = int(round((y2 - y1 + 1) / scale))

    rx = max(0, min(rx, W - 1))
    ry = max(0, min(ry, H - 1))
    rw = max(1, min(rw, W - rx))
    rh = max(1, min(rh, H - ry))

    # 原始影片本身就是直式窄螢幕時，左右通常都是遊戲/規則頁本體；
    # motion bbox 偶爾只吃到某個動態符號，不能因此裁掉半個 paytable/help 頁。
    if (
        W / float(max(1, H)) <= AUTO_ROI_NATIVE_PORTRAIT_ASPECT_MAX
        and rw < int(W * AUTO_ROI_NATIVE_PORTRAIT_MIN_WIDTH_RATIO)
    ):
        center_x = rx + rw / 2.0
        target_w = min(W, int(round(W * AUTO_ROI_NATIVE_PORTRAIT_MIN_WIDTH_RATIO)))
        rx = int(round(center_x - target_w / 2.0))
        rx = max(0, min(rx, W - target_w))
        rw = target_w

    if AUTO_ROI_TRIM_BROWSER_TOP and W / float(H) > 1.4:
        browser_top = int(round(H * AUTO_ROI_BROWSER_TOP_RATIO))
        if ry < browser_top:
            bottom = ry + rh
            ry = min(browser_top, H - 1)
            rh = max(1, bottom - ry)

    rx, ry, rw, rh = refine_browser_portrait_top(
        frames[len(frames) // 2],
        rx,
        ry,
        rw,
        rh,
    )

    if debug_dir and SAVE_ROI_DEBUG_IMAGE:
        os.makedirs(debug_dir, exist_ok=True)
        debug = frames[len(frames) // 2].copy()
        cv2.rectangle(debug, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 3)
        imwrite_image(os.path.join(debug_dir, "auto_roi_preview.jpg"), debug)
        imwrite_image(os.path.join(debug_dir, "auto_roi_motion_mask.jpg"), cv2.resize(motion_mask, (W, H)))

    return rx, ry, rw, rh


# =========================
# OCR / 文字分類
# =========================
