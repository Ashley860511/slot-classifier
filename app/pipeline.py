import json
import os
import shutil
from pathlib import Path

import cv2
import numpy as np

try:
    from .config import (
        AUTO_DETECT_ROI,
        DEFAULT_ROI_H,
        DEFAULT_ROI_W,
        DEFAULT_ROI_X,
        DEFAULT_ROI_Y,
        INPUT_DIR,
        OUTPUT_DIR,
        WEB_HELP_FULL_PAGE_MIN_ASPECT,
    )
except ImportError:
    from config import (
        AUTO_DETECT_ROI,
        DEFAULT_ROI_H,
        DEFAULT_ROI_W,
        DEFAULT_ROI_X,
        DEFAULT_ROI_Y,
        INPUT_DIR,
        OUTPUT_DIR,
        WEB_HELP_FULL_PAGE_MIN_ASPECT,
    )

try:
    from .auto_roi import auto_detect_game_area, get_web_help_page_roi
except ImportError:
    from auto_roi import auto_detect_game_area, get_web_help_page_roi

try:
    from .ocr_utils import extract_ocr_items, get_ocr_result, init_ocr
except ImportError:
    from ocr_utils import extract_ocr_items, get_ocr_result, init_ocr

try:
    from .video_io import (
        append_csv_row,
        get_video_csv_path,
        get_video_list,
        get_video_output_dir,
        imwrite_image,
        prepare_output_dirs,
        safe_short_name,
        write_csv_header,
    )
except ImportError:
    from video_io import (
        append_csv_row,
        get_video_csv_path,
        get_video_list,
        get_video_output_dir,
        imwrite_image,
        prepare_output_dirs,
        safe_short_name,
        write_csv_header,
    )

try:
    from .constants import (
        BLUR_THRESHOLD,
        CATEGORY_NAMES,
        DENSE_SAMPLE_STEP,
        DIFF_THRESHOLD,
        ENABLE_BLUR_FILTER,
        ENABLE_OVEREXPOSURE_FILTER,
        ENABLE_TRANSITION_NOISE_FILTER,
        FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP,
        FEATURE_DENSE_SAMPLE_AFTER_FRAMES,
        FEATURE_UI_MIN_SCORE_FOR_KEEP,
        FORCE_SAMPLE_INTERVAL_FRAMES,
        FRAME_INTERVAL,
        HELP_DENSE_SAMPLE_AFTER_FRAMES,
        BASEGAME_MIN_UI_SCORE_FOR_KEEP,
        NOISE_PROTECT_UI_MARGIN,
        OCR_LANG,
        OVEREXPOSURE_SCORE_THRESHOLD,
        SCORE_THRESHOLD,
        TRANSITION_DENSE_SAMPLE_AFTER_FRAMES,
        TRANSITION_NOISE_SCORE_THRESHOLD,
    )
except ImportError:
    from constants import (
        BLUR_THRESHOLD,
        CATEGORY_NAMES,
        DENSE_SAMPLE_STEP,
        DIFF_THRESHOLD,
        ENABLE_BLUR_FILTER,
        ENABLE_OVEREXPOSURE_FILTER,
        ENABLE_TRANSITION_NOISE_FILTER,
        FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP,
        FEATURE_DENSE_SAMPLE_AFTER_FRAMES,
        FEATURE_UI_MIN_SCORE_FOR_KEEP,
        FORCE_SAMPLE_INTERVAL_FRAMES,
        FRAME_INTERVAL,
        HELP_DENSE_SAMPLE_AFTER_FRAMES,
        BASEGAME_MIN_UI_SCORE_FOR_KEEP,
        NOISE_PROTECT_UI_MARGIN,
        OCR_LANG,
        OVEREXPOSURE_SCORE_THRESHOLD,
        SCORE_THRESHOLD,
        TRANSITION_DENSE_SAMPLE_AFTER_FRAMES,
        TRANSITION_NOISE_SCORE_THRESHOLD,
    )

try:
    from .scorers.classifier import (
        classify_frame,
        detect_feature_subtype,
        feature_active_signal_score,
        get_transition_keep_score,
    )
    from .scorers.text_signals import (
        has_any,
        has_help_signal,
        is_rules_help_page_candidate,
        normalize_text,
    )
    from .scorers.visual_scores import (
        blur_score,
        feature_board_obstruction_score,
        has_help_scroll_shell,
        overexposure_score,
        transition_noise_score,
    )
    from .scorers.help_scorer import (
        help_page_quality_score,
        help_paytable_signal_score,
        help_text_tokens,
    )
    from .scorers.selector import keep_selected_images
    from .scorers.confidence import calculate_confidence, needs_review, CONFIDENCE_HIGH
except ImportError:
    from scorers.classifier import (
        classify_frame,
        detect_feature_subtype,
        feature_active_signal_score,
        get_transition_keep_score,
    )
    from scorers.text_signals import (
        has_any,
        has_help_signal,
        is_rules_help_page_candidate,
        normalize_text,
    )
    from scorers.visual_scores import (
        blur_score,
        feature_board_obstruction_score,
        has_help_scroll_shell,
        overexposure_score,
        transition_noise_score,
    )
    from scorers.help_scorer import (
        help_page_quality_score,
        help_paytable_signal_score,
        help_text_tokens,
    )
    from scorers.selector import keep_selected_images
    from scorers.confidence import calculate_confidence, needs_review, CONFIDENCE_HIGH


# ---------------------------------------------------------------------------
# OCR cache helpers
# ---------------------------------------------------------------------------

def _load_ocr_cache(cache_path):
    """Load OCR cache from JSON file. Returns a dict keyed by frame_idx string."""
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        # Convert lists back to the expected format: list of [box_as_ndarray, text, score]
        cache = {}
        for key, items in raw.items():
            converted = []
            for item in items:
                box, text, score = item
                converted.append((np.array(box, dtype=float), text, float(score)))
            cache[key] = converted
        return cache
    except Exception as e:
        print(f"[OCR cache] 無法載入快取 {cache_path}: {e}")
        return {}


def _save_ocr_cache(cache_path, cache):
    """Save OCR cache to JSON file. Converts numpy arrays to lists."""
    try:
        serializable = {}
        for key, items in cache.items():
            converted = []
            for item in items:
                box, text, score = item
                if hasattr(box, "tolist"):
                    box = box.tolist()
                converted.append([box, text, float(score)])
            serializable[key] = converted
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(serializable, fh, ensure_ascii=False)
    except Exception as e:
        print(f"[OCR cache] 無法儲存快取 {cache_path}: {e}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_video(video_path, ocr_engine, video_output_dir, csv_path, progress_callback=None):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    video_file_prefix = safe_short_name(video_name, max_len=36)
    video_debug_dir = os.path.join(video_output_dir, "_debug")

    # --- OCR cache setup ---
    ocr_cache_path = os.path.join(video_output_dir, "ocr_cache.json")
    ocr_cache = _load_ocr_cache(ocr_cache_path)
    cache_hits = 0
    cache_misses = 0

    detected_roi = None
    if AUTO_DETECT_ROI:
        detected_roi = auto_detect_game_area(video_path, debug_dir=video_debug_dir)

    if detected_roi:
        roi_x, roi_y, roi_w, roi_h = detected_roi
        print(f"[{video_name}] Auto ROI: x={roi_x}, y={roi_y}, w={roi_w}, h={roi_h}")
    else:
        roi_x, roi_y, roi_w, roi_h = DEFAULT_ROI_X, DEFAULT_ROI_Y, DEFAULT_ROI_W, DEFAULT_ROI_H
        print(f"[{video_name}] 使用 fallback ROI: x={roi_x}, y={roi_y}, w={roi_w}, h={roi_h}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"無法開啟影片: {video_path}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    last_progress_frame = -1

    def notify_video_progress(current_frame, stage="classify"):
        nonlocal last_progress_frame
        if not progress_callback:
            return
        if (
            current_frame != 0
            and total_frames > 0
            and current_frame < total_frames - 1
            and current_frame - last_progress_frame < max(30, FRAME_INTERVAL * 4)
        ):
            return
        last_progress_frame = current_frame
        progress_callback({
            "stage": stage,
            "video": video_name,
            "frame": int(max(0, current_frame)),
            "total_frames": int(max(0, total_frames)),
            "video_progress": (
                min(1.0, max(0.0, current_frame / float(total_frames)))
                if total_frames > 0 else 0.0
            ),
            "output_dir": video_output_dir,
        })

    frame_idx = 0
    saved_count = 0
    last_sampled_roi = None
    last_processed_frame_idx = None
    help_dense_until_frame = -1
    transition_dense_until_frame = -1
    feature_dense_until_frame = -1
    saved_records = []

    while True:
        notify_video_progress(frame_idx)
        ret, frame = cap.read()
        if not ret:
            print(f"[{video_name}] 影片讀取結束。")
            break

        help_dense_active = frame_idx <= help_dense_until_frame
        transition_dense_active = frame_idx <= transition_dense_until_frame
        feature_dense_active = frame_idx <= feature_dense_until_frame
        dense_active = help_dense_active or transition_dense_active or feature_dense_active
        dense_step_hit = dense_active and frame_idx % DENSE_SAMPLE_STEP == 0

        if frame_idx % FRAME_INTERVAL != 0 and not dense_step_hit:
            frame_idx += 1
            continue

        H, W = frame.shape[:2]
        x = max(0, min(roi_x, W - 1))
        y = max(0, min(roi_y, H - 1))
        w = max(1, min(roi_w, W - x))
        h = max(1, min(roi_h, H - y))

        cropped = frame[y:y + h, x:x + w]
        if cropped.size == 0:
            print(f"[{video_name}] frame {frame_idx}: ROI 擷取失敗")
            frame_idx += 1
            continue

        diff_score_val = _frame_diff_score(last_sampled_roi, cropped)

        force_sample = (
            last_processed_frame_idx is None
            or frame_idx - last_processed_frame_idx >= FORCE_SAMPLE_INTERVAL_FRAMES
            or help_dense_active
            or transition_dense_active
            or feature_dense_active
        )

        if last_sampled_roi is not None and diff_score_val < DIFF_THRESHOLD and not force_sample:
            print(f"[{video_name}] frame {frame_idx} 跳過 | diff={diff_score_val:.2f}")
            frame_idx += 1
            continue

        if force_sample and last_sampled_roi is not None and diff_score_val < DIFF_THRESHOLD:
            print(
                f"[{video_name}] frame {frame_idx} 強制取樣 | "
                f"diff={diff_score_val:.2f} | interval={FORCE_SAMPLE_INTERVAL_FRAMES}"
            )
        last_processed_frame_idx = frame_idx

        current_blur = blur_score(cropped)
        if ENABLE_BLUR_FILTER and current_blur < BLUR_THRESHOLD:
            print(f"[{video_name}] frame {frame_idx} 跳過模糊圖 | blur={current_blur:.2f} | diff={diff_score_val:.2f}")
            last_sampled_roi = cropped.copy()
            frame_idx += 1
            continue

        exposure_score_val, exposure_reasons = overexposure_score(cropped)
        # Transition / Feature intro animations are full-screen bright effects that
        # legitimately look overexposed (FS entry flash, win celebration).  During
        # dense-sampling windows we raise the threshold by +2 so the intro frame is
        # not lost entirely.  Pure white-flash frames (score >= threshold + 4) are
        # still skipped because they carry no visual information.
        _in_transition_dense = frame_idx <= transition_dense_until_frame
        _in_feature_dense    = frame_idx <= feature_dense_until_frame
        _overexp_threshold = (OVEREXPOSURE_SCORE_THRESHOLD + 2.0
                              if (_in_transition_dense or _in_feature_dense)
                              else OVEREXPOSURE_SCORE_THRESHOLD)
        if ENABLE_OVEREXPOSURE_FILTER and exposure_score_val >= _overexp_threshold:
            print(
                f"[{video_name}] frame {frame_idx} 跳過爆光圖 | "
                f"exposure={exposure_score_val:.2f} | {', '.join(exposure_reasons)} | "
                f"blur={current_blur:.2f} | diff={diff_score_val:.2f}"
            )
            last_sampled_roi = cropped.copy()
            frame_idx += 1
            continue

        # --- OCR with cache ---
        cache_key = f"frame_{frame_idx}"
        if cache_key in ocr_cache:
            ocr_items = ocr_cache[cache_key]
            cache_hits += 1
        else:
            try:
                result = get_ocr_result(ocr_engine, cropped)
            except Exception as e:
                print(f"OCR 執行失敗, frame={frame_idx}, 錯誤: {e}")
                result = None
            ocr_items = extract_ocr_items(result)
            ocr_cache[cache_key] = ocr_items
            cache_misses += 1

        category, category_scores, matched_keywords, raw_texts, top_score = classify_frame(cropped, ocr_items, w, h)

        noise_score_val, noise_reasons = transition_noise_score(cropped)
        transition_keep_score_val, transition_keep_reasons = get_transition_keep_score(
            ocr_items, w, h, category_scores
        )
        if category == "Transition" and transition_keep_reasons:
            matched_keywords.setdefault("Transition", []).extend(
                f"{reason}:{transition_keep_score_val:.2f}" for reason in transition_keep_reasons
            )

        feature_ui_score = float(category_scores.get("FeatureUI", 0.0))
        basegame_ui_score = float(category_scores.get("BasegameUI", 0.0))
        bigwin_keep_signal_score = float(category_scores.get("BigWinKeep", 0.0))
        help_quality_score, help_quality_reasons = help_page_quality_score(cropped, ocr_items)
        help_tokens = help_text_tokens(ocr_items)
        help_paytable_score = help_paytable_signal_score(ocr_items)
        category_scores["HelpQuality"] = round(help_quality_score, 2)
        category_scores["HelpPaytable"] = round(help_paytable_score, 2)

        if category == "Help":
            web_help_roi = get_web_help_page_roi(frame)
            if web_help_roi:
                hx, hy, hw, hh = web_help_roi
                web_cropped = frame[hy:hy + hh, hx:hx + hw]
                if web_cropped.size > 0 and (hw > w * 1.35 or hh > h * 1.05):
                    web_cache_key = f"frame_{frame_idx}_web"
                    if web_cache_key in ocr_cache:
                        web_ocr_items = ocr_cache[web_cache_key]
                        cache_hits += 1
                    else:
                        try:
                            web_result = get_ocr_result(ocr_engine, web_cropped)
                        except Exception as e:
                            print(f"OCR 執行失敗, frame={frame_idx}, web help crop 錯誤: {e}")
                            web_result = None
                        web_ocr_items = extract_ocr_items(web_result)
                        ocr_cache[web_cache_key] = web_ocr_items
                        cache_misses += 1

                    (
                        web_category,
                        web_category_scores,
                        web_matched_keywords,
                        web_raw_texts,
                        web_top_score,
                    ) = classify_frame(web_cropped, web_ocr_items, hw, hh)
                    web_help_quality_score, web_help_quality_reasons = help_page_quality_score(
                        web_cropped, web_ocr_items
                    )
                    web_help_paytable_score = help_paytable_signal_score(web_ocr_items)

                    web_joined = " ".join(
                        normalize_text(text)
                        for _, text, score in web_ocr_items
                        if score >= SCORE_THRESHOLD
                    )
                    web_rules_help_like = is_rules_help_page_candidate(
                        web_joined,
                        web_ocr_items,
                        web_help_quality_score,
                        web_category_scores,
                        web_help_paytable_score,
                    )
                    web_help_like = (
                        web_category == "Help"
                        or has_help_signal(web_joined, web_ocr_items, hw, hh)
                        or web_rules_help_like
                    )
                    _roi_is_portrait = w > 0 and h > 0 and (w / float(max(1, h))) <= 0.85
                    _frame_is_landscape = (frame.shape[1] / float(max(1, frame.shape[0]))) >= WEB_HELP_FULL_PAGE_MIN_ASPECT
                    # If the classifier already decided this is Help AND the ROI is a narrow
                    # portrait strip inside a landscape frame, trust the classification and
                    # always use the full-page crop — no secondary signal check needed.
                    # This fixes paytable-image pages that have few OCR keywords.
                    _help_already_classified = (category == "Help" and _roi_is_portrait and _frame_is_landscape)
                    force_web_help_crop = (
                        _roi_is_portrait
                        and _frame_is_landscape
                        and (
                            _help_already_classified
                            or help_quality_score >= 8.0
                            or help_paytable_score >= 2.0
                            or has_help_signal(
                                " ".join(
                                    normalize_text(text)
                                    for _, text, ocr_score in (ocr_items or [])
                                    if ocr_score >= SCORE_THRESHOLD
                                ),
                                ocr_items,
                                w,
                                h,
                            )
                        )
                        and web_help_quality_score >= 2.0
                    )
                    web_false_result_from_rules = (
                        web_category == "Result"
                        and web_rules_help_like
                        and web_help_quality_score >= 6.0
                    )

                    if (
                        (web_help_like or force_web_help_crop)
                        and (
                            web_category not in ["Feature Buy", "BigWin", "Result", "loading"]
                            or web_false_result_from_rules
                            or force_web_help_crop
                        )
                    ):
                        x, y, w, h = hx, hy, hw, hh
                        cropped = web_cropped
                        ocr_items = web_ocr_items
                        category = "Help"
                        category_scores = web_category_scores
                        matched_keywords = web_matched_keywords
                        raw_texts = web_raw_texts
                        top_score = web_top_score
                        category_scores["Help"] = max(category_scores.get("Help", 0.0), 12.0)
                        matched_keywords.setdefault("Help", []).append("web_full_page_crop_forced")
                        current_blur = blur_score(cropped)
                        noise_score_val, noise_reasons = transition_noise_score(cropped)
                        transition_keep_score_val, transition_keep_reasons = get_transition_keep_score(
                            ocr_items, w, h, category_scores
                        )
                        feature_ui_score = float(category_scores.get("FeatureUI", 0.0))
                        basegame_ui_score = float(category_scores.get("BasegameUI", 0.0))
                        bigwin_keep_signal_score = float(category_scores.get("BigWinKeep", 0.0))
                        help_quality_score = web_help_quality_score
                        help_quality_reasons = web_help_quality_reasons + ["web_full_page_crop"]
                        help_tokens = help_text_tokens(ocr_items)
                        help_paytable_score = web_help_paytable_score
                        category_scores["HelpQuality"] = round(help_quality_score, 2)
                        category_scores["HelpPaytable"] = round(help_paytable_score, 2)

        if category == "Help" and help_quality_reasons:
            matched_keywords.setdefault("Help", []).extend(
                f"{reason}:{help_quality_score:.2f}" for reason in help_quality_reasons
            )
        if category == "Help":
            help_dense_until_frame = max(
                help_dense_until_frame,
                frame_idx + HELP_DENSE_SAMPLE_AFTER_FRAMES,
            )
            matched_keywords.setdefault("Help", []).append("help_dense_sampling_active")
        elif has_help_scroll_shell(cropped) and help_quality_score >= 3.0:
            help_dense_until_frame = max(
                help_dense_until_frame,
                frame_idx + HELP_DENSE_SAMPLE_AFTER_FRAMES,
            )
            matched_keywords.setdefault(category, []).append("help_shell_dense_probe")
        if category == "Transition":
            transition_dense_until_frame = max(
                transition_dense_until_frame,
                frame_idx + TRANSITION_DENSE_SAMPLE_AFTER_FRAMES,
            )
            matched_keywords.setdefault("Transition", []).append("transition_dense_sampling_active")
        if category == "Feature game":
            feature_dense_until_frame = max(
                feature_dense_until_frame,
                frame_idx + FEATURE_DENSE_SAMPLE_AFTER_FRAMES,
            )
            matched_keywords.setdefault("Feature game", []).append("feature_dense_sampling_active")

        feature_obstruction_score_val, feature_obstruction_reasons = feature_board_obstruction_score(cropped)
        category_scores["FeatureObstruction"] = round(feature_obstruction_score_val, 2)
        if category == "Feature game" and feature_obstruction_reasons:
            matched_keywords.setdefault("Feature game", []).extend(
                f"{reason}:{feature_obstruction_score_val:.2f}" for reason in feature_obstruction_reasons
            )

        final_joined = " ".join(
            normalize_text(text)
            for _, text, ocr_score in (ocr_items or [])
            if ocr_score >= SCORE_THRESHOLD
        )
        feature_active_score = float(category_scores.get("FeatureActive", 0.0))
        feature_subtype, feature_subtype_scores = detect_feature_subtype(final_joined)
        if category != "Feature game":
            feature_subtype = ""
        has_protected_feature_ui = feature_ui_score >= FEATURE_UI_MIN_SCORE_FOR_KEEP + NOISE_PROTECT_UI_MARGIN
        has_protected_feature_active = (
            category == "Feature game"
            and feature_active_score >= FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP
        )
        has_protected_basegame_ui = basegame_ui_score >= BASEGAME_MIN_UI_SCORE_FOR_KEEP + NOISE_PROTECT_UI_MARGIN
        should_skip_noise = category == "Other"
        if category == "Feature game" and not (has_protected_feature_ui or has_protected_feature_active):
            should_skip_noise = True
        if category == "Basegame" and not has_protected_basegame_ui:
            should_skip_noise = True

        if (
            ENABLE_TRANSITION_NOISE_FILTER
            and noise_score_val >= TRANSITION_NOISE_SCORE_THRESHOLD
            and category not in ["BigWin", "Result", "loading"]
            and should_skip_noise
        ):
            print(
                f"[{video_name}] frame {frame_idx} 跳過轉場殘影/雜訊圖 | "
                f"noise={noise_score_val:.2f} | {', '.join(noise_reasons)} | "
                f"category={category} | feature_ui={feature_ui_score:.2f} | basegame_ui={basegame_ui_score:.2f} | "
                f"blur={current_blur:.2f} | diff={diff_score_val:.2f}"
            )
            last_sampled_roi = cropped.copy()
            frame_idx += 1
            continue

        if ENABLE_TRANSITION_NOISE_FILTER and noise_score_val >= TRANSITION_NOISE_SCORE_THRESHOLD:
            matched_keywords.setdefault(category, []).append(f"kept_noisy_but_classifiable:{noise_score_val:.2f}")

        save_path = os.path.join(video_output_dir, category, f"{video_file_prefix}_frame_{frame_idx:06d}.jpg")
        if not imwrite_image(save_path, cropped):
            print(f"[{video_name}] frame {frame_idx}: 圖片寫入失敗，跳過這張")
            last_sampled_roi = cropped.copy()
            frame_idx += 1
            continue
        saved_count += 1

        # ── 信心分數 ──────────────────────────────────────────────────
        conf_level, conf_score = calculate_confidence(
            category, top_score, category_scores, matched_keywords
        )
        if needs_review(conf_level):
            review_dir = os.path.join(video_output_dir, "needs_review", category)
            os.makedirs(review_dir, exist_ok=True)
            review_path = os.path.join(review_dir, os.path.basename(save_path))
            shutil.copy2(save_path, review_path)

        saved_records.append({
            "category": category,
            "top_score": top_score,
            "basegame_ui_score": basegame_ui_score,
            "feature_ui_score": feature_ui_score,
            "feature_active_score": feature_active_score,
            "bigwin_keep_score": bigwin_keep_signal_score,
            "help_quality_score": help_quality_score,
            "help_paytable_score": help_paytable_score,
            "help_tokens": help_tokens,
            "feature_obstruction_score": feature_obstruction_score_val,
            "noise_score": noise_score_val,
            "transition_keep_score": transition_keep_score_val,
            "feature_subtype": feature_subtype,
            "feature_subtype_scores": feature_subtype_scores,
            "save_path": save_path,
            "frame_idx": frame_idx,
            "blur_score": current_blur,
            "raw_texts": raw_texts,
            "category_scores": dict(category_scores),
            "matched_keywords": dict(matched_keywords),
            "confidence_level": conf_level,
            "confidence_score": conf_score,
        })

        print(f"\n[{video_name}] frame {frame_idx} -> {category} | diff={diff_score_val:.2f} | blur={current_blur:.2f} | top_score={top_score:.2f}")
        print("OCR:")
        for box, text, score in ocr_items:
            print(f"  [box={box}] ('{text}', {score:.3f})")

        print("Category scores:")
        for cat in CATEGORY_NAMES:
            if cat in category_scores:
                print(f"  {cat}: {category_scores[cat]}")

        print("Matched keywords:")
        for cat, kws in matched_keywords.items():
            if kws:
                print(f"  {cat}: {', '.join(kws)}")

        append_csv_row(
            csv_path,
            [
                video_name,
                frame_idx,
                category,
                f"{diff_score_val:.2f}",
                f"{current_blur:.2f}",
                f"{top_score:.2f}",
                feature_subtype,
                str(feature_subtype_scores),
                str(raw_texts),
                str(category_scores),
                str(matched_keywords),
                f"({x},{y},{w},{h})",
                save_path,
                conf_level,
                f"{conf_score:.3f}",
            ]
        )

        last_sampled_roi = cropped.copy()
        frame_idx += 1

    cap.release()
    # Save OCR cache
    _save_ocr_cache(ocr_cache_path, ocr_cache)
    print(f"[{video_name}] OCR cache: hits={cache_hits}, misses={cache_misses}, saved to {ocr_cache_path}")
    notify_video_progress(total_frames or frame_idx, stage="classify_done")
    print(f"[{video_name}] 完成，總共儲存 {saved_count} 張圖")
    return saved_records


def _frame_diff_score(img1, img2):
    """Simple frame difference helper (avoid importing from visual_scores to keep pipeline light)."""
    if img1 is None or img2 is None:
        return 0.0
    if img1.shape != img2.shape:
        return 0.0
    diff = cv2.absdiff(img1, img2)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    return float(np.mean(diff_gray))


def generate_symbols_for_output(video_output_dir, debug=False):
    try:
        from . import generate_symbol_table as symbol_table_generator
    except ImportError:
        import generate_symbol_table as symbol_table_generator

    symbol_table_generator.process_video(
        Path(video_output_dir),
        api_key="",
        no_ai=True,
        debug=debug,
        icons_only=True,
    )


def get_video_output_dir_for_root(video_path, output_root):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(output_root, safe_short_name(video_name, max_len=52))


def run_classifier(
    video_paths=None,
    video_id=None,
    output_root=OUTPUT_DIR,
    skip_symbols=False,
    symbol_debug=False,
    progress_callback=None,
):
    def notify(stage, message, current=0, total=0, output_dir=None, percent=None):
        if progress_callback:
            progress_callback({
                "stage": stage,
                "message": message,
                "current": current,
                "total": total,
                "output_dir": output_dir,
                "percent": percent,
            })

    os.makedirs(output_root, exist_ok=True)

    if video_paths is None:
        video_list = get_video_list()
    else:
        video_list = [str(path) for path in video_paths]

    if video_id:
        target = str(video_id).strip()
        video_list = [
            path for path in video_list
            if os.path.splitext(os.path.basename(path))[0] == target
        ]

    if not video_list:
        notify("error", f"No videos found. Put video files in: {INPUT_DIR}")
        return []

    notify("ocr", "Initializing OCR...", 0, len(video_list), percent=0.0)
    ocr_engine = init_ocr(OCR_LANG)
    print("OCR initialized.")
    print(f"Found {len(video_list)} video(s).")

    outputs = []
    total = len(video_list)
    for index, video_path in enumerate(video_list, start=1):
        if not os.path.exists(video_path):
            print(f"Video not found: {video_path}")
            notify("missing", f"Video not found: {video_path}", index, total)
            continue

        video_output_dir = get_video_output_dir_for_root(video_path, output_root)
        video_csv_path = get_video_csv_path(video_output_dir)
        prepare_output_dirs(video_output_dir)
        write_csv_header(video_csv_path)

        print(f"\n=== Processing: {os.path.basename(video_path)} ===")
        print(f"Output folder: {video_output_dir}")
        video_base = ((index - 1) / float(max(1, total))) * 100.0
        video_span = (1.0 / float(max(1, total))) * 100.0

        notify(
            "classify",
            f"Classifying {os.path.basename(video_path)}",
            index,
            total,
            video_output_dir,
            percent=video_base,
        )

        def video_progress_callback(event):
            video_progress = float(event.get("video_progress", 0.0) or 0.0)
            percent = video_base + video_span * min(0.88, video_progress * 0.88)
            frame = int(event.get("frame", 0) or 0)
            total_frames = int(event.get("total_frames", 0) or 0)
            frame_text = (
                f" frame {frame}/{total_frames}" if total_frames > 0 else ""
            )
            notify(
                event.get("stage", "classify"),
                f"Classifying {os.path.basename(video_path)}{frame_text}",
                index,
                total,
                video_output_dir,
                percent=percent,
            )

        records = process_video(
            video_path,
            ocr_engine,
            video_output_dir,
            video_csv_path,
            progress_callback=video_progress_callback,
        )

        notify(
            "filter",
            f"Selecting final images for {os.path.basename(video_path)}",
            index,
            total,
            video_output_dir,
            percent=video_base + video_span * 0.90,
        )
        keep_selected_images(records, low_score_dir=os.path.join(video_output_dir, "low_score"))
        print(f"CSV saved: {video_csv_path}")

        if not skip_symbols:
            notify(
                "symbols",
                f"Generating symbols for {os.path.basename(video_path)}",
                index,
                total,
                video_output_dir,
                percent=video_base + video_span * 0.94,
            )
            print("Generating symbol images...")
            generate_symbols_for_output(video_output_dir, debug=symbol_debug)
            print(f"Symbols saved: {os.path.join(video_output_dir, 'symbol_table', 'symbols')}")

        outputs.append(video_output_dir)

    notify("done", f"Done. Output root: {output_root}", total, total, percent=100.0)
    print(f"Output root: {output_root}")
    print("Done.")
    return outputs
