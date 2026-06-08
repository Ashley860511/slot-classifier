import ast
import os
import re
import shutil
from collections import defaultdict

import cv2
import numpy as np

try:
    from ..constants import (
        BASEGAME_FINAL_MAX_EXPOSURE_SCORE,
        BASEGAME_FINAL_MAX_NOISE_SCORE,
        BASEGAME_FINAL_MAX_OBSTRUCTION_SCORE,
        BASEGAME_KEEP_TOP_UI_RATIO,
        BASEGAME_MIN_UI_SCORE_FOR_KEEP,
        BIGWIN_EVENT_GAP_FRAMES,
        BIGWIN_KEEP_MIN_SCORE,
        BIGWIN_TIER_ORDER,
        BIGWIN_VISUAL_CLUSTER_COUNT,
        BIGWIN_VISUAL_KEEP_PER_CLUSTER,
        BOTTOM_UI_CLUSTER_LOW_FEATURE_COUNT,
        BOTTOM_UI_CLUSTER_MIN_FEATURE_EVIDENCE,
        BOTTOM_UI_CLUSTER_MIN_RECORDS,
        BOTTOM_UI_CLUSTER_MIN_SEPARATION,
        DROP_LOW_SCORE_MAJORITY_CLUSTER_CATEGORIES,
        ENABLE_BOTTOM_UI_CLUSTER_REFINEMENT,
        FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP,
        FEATURE_BOARD_OBSTRUCTION_THRESHOLD,
        FEATURE_UI_KEEP_TOP_RATIO,
        FEATURE_UI_MIN_SCORE_FOR_KEEP,
        HELP_EVENT_GAP_FRAMES,
        HELP_MAX_FINAL_PAGES,
        HELP_MIN_QUALITY_SCORE,
        HELP_PAYTABLE_KEEP_COUNT,
        HELP_PHRASES,
        HELP_RULE_TEXT_MIN_LONG_LINES,
        HELP_RULE_TEXT_MIN_LINES,
        HELP_RULE_TEXT_MIN_QUALITY_SCORE,
        HELP_RULE_TEXT_MIN_TOKENS,
        LOW_SCORE_MAJORITY_CLUSTER_RATIO,
        RESULT_STRONG_PHRASES,
        TOP_K_BIGWIN,
        TOP_K_DEFAULT,
        TOP_K_FEATURE_BUY,
        TOP_K_HELP,
        TOP_K_LOADING,
        TOP_K_RESULT,
        TOP_K_SHORT_EVENTS,
        TOP_K_TRANSITION,
        TRANSITION_EVENT_GAP_FRAMES,
        TRANSITION_NOISE_SCORE_THRESHOLD,
        VISUAL_CLUSTER_CATEGORIES,
        VISUAL_CLUSTER_COUNT,
        VISUAL_KEEP_PER_CLUSTER,
    )
except ImportError:
    from constants import (
        BASEGAME_FINAL_MAX_EXPOSURE_SCORE,
        BASEGAME_FINAL_MAX_NOISE_SCORE,
        BASEGAME_FINAL_MAX_OBSTRUCTION_SCORE,
        BASEGAME_KEEP_TOP_UI_RATIO,
        BASEGAME_MIN_UI_SCORE_FOR_KEEP,
        BIGWIN_EVENT_GAP_FRAMES,
        BIGWIN_KEEP_MIN_SCORE,
        BIGWIN_TIER_ORDER,
        BIGWIN_VISUAL_CLUSTER_COUNT,
        BIGWIN_VISUAL_KEEP_PER_CLUSTER,
        BOTTOM_UI_CLUSTER_LOW_FEATURE_COUNT,
        BOTTOM_UI_CLUSTER_MIN_FEATURE_EVIDENCE,
        BOTTOM_UI_CLUSTER_MIN_RECORDS,
        BOTTOM_UI_CLUSTER_MIN_SEPARATION,
        DROP_LOW_SCORE_MAJORITY_CLUSTER_CATEGORIES,
        ENABLE_BOTTOM_UI_CLUSTER_REFINEMENT,
        FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP,
        FEATURE_BOARD_OBSTRUCTION_THRESHOLD,
        FEATURE_UI_KEEP_TOP_RATIO,
        FEATURE_UI_MIN_SCORE_FOR_KEEP,
        HELP_EVENT_GAP_FRAMES,
        HELP_MAX_FINAL_PAGES,
        HELP_MIN_QUALITY_SCORE,
        HELP_PAYTABLE_KEEP_COUNT,
        HELP_PHRASES,
        HELP_RULE_TEXT_MIN_LONG_LINES,
        HELP_RULE_TEXT_MIN_LINES,
        HELP_RULE_TEXT_MIN_QUALITY_SCORE,
        HELP_RULE_TEXT_MIN_TOKENS,
        LOW_SCORE_MAJORITY_CLUSTER_RATIO,
        RESULT_STRONG_PHRASES,
        TOP_K_BIGWIN,
        TOP_K_DEFAULT,
        TOP_K_FEATURE_BUY,
        TOP_K_HELP,
        TOP_K_LOADING,
        TOP_K_RESULT,
        TOP_K_SHORT_EVENTS,
        TOP_K_TRANSITION,
        TRANSITION_EVENT_GAP_FRAMES,
        TRANSITION_NOISE_SCORE_THRESHOLD,
        VISUAL_CLUSTER_CATEGORIES,
        VISUAL_CLUSTER_COUNT,
        VISUAL_KEEP_PER_CLUSTER,
    )

try:
    from .text_signals import (
        normalize_text,
        has_any,
        has_any_pattern,
        has_feature_intro_signal,
        has_feature_running_signal,
    )
    from .visual_scores import (
        feature_reel_board_signal_score,
        overexposure_score,
    )
    from .help_scorer import (
        is_duplicate_help_record,
        help_paytable_signal_score,
    )
    from .bigwin_scorer import (
        bigwin_tier_key,
        bigwin_tier_label,
    )
except ImportError:
    from text_signals import (
        normalize_text,
        has_any,
        has_any_pattern,
        has_feature_intro_signal,
        has_feature_running_signal,
    )
    from visual_scores import (
        feature_reel_board_signal_score,
        overexposure_score,
    )
    from help_scorer import (
        is_duplicate_help_record,
        help_paytable_signal_score,
    )
    from bigwin_scorer import (
        bigwin_tier_key,
        bigwin_tier_label,
    )

try:
    from ..video_io import imread_image
except ImportError:
    from video_io import imread_image


# ---------------------------------------------------------------------------
# Record text helpers
# ---------------------------------------------------------------------------

def record_text_items(rec):
    texts = rec.get("raw_texts") or []
    if isinstance(texts, str):
        texts = [texts]

    clean_texts = []
    for item in texts:
        if isinstance(item, (list, tuple)) and item:
            clean_texts.append(str(item[0]))
        else:
            clean_texts.append(str(item))
    return clean_texts


def record_text_joined(rec):
    return " ".join(normalize_text(text) for text in record_text_items(rec))


def record_category_score(rec, category):
    scores = rec.get("category_scores") or {}
    if isinstance(scores, str):
        try:
            scores = ast.literal_eval(scores)
        except Exception:
            scores = {}
    try:
        return float(scores.get(category, 0.0))
    except Exception:
        return 0.0


def record_matched_keywords(rec, category):
    matched = rec.get("matched_keywords") or {}
    if isinstance(matched, str):
        try:
            matched = ast.literal_eval(matched)
        except Exception:
            matched = {}
    values = matched.get(category, [])
    if isinstance(values, str):
        values = [values]
    return [str(value) for value in values]


def has_record_pp_free_spins_left(rec):
    joined = record_text_joined(rec)
    compact = joined.replace(" ", "")
    if "freespinsleft" in compact or "freespinleft" in compact:
        return True
    return (
        has_any(joined, ["free spins", "free spin", "freespins", "freespin"])
        and "left" in joined
        and bool(re.search(r"\b\d{1,3}\b", joined))
    )


def has_record_feature_text(rec):
    joined = record_text_joined(rec)
    compact = joined.replace(" ", "")
    if has_any_pattern(joined, [
        r"free\s*(game|spin|spins)\s*\d{1,3}\s*/\s*\d{1,3}",
        r"free\s*(game|games|spin|spins)\s*\d{1,3}\s*(of|f)\s*\d{1,3}",
        r"\d{1,3}\s*/\s*\d{1,3}\s*free\s*(game|spin|spins)",
    ]):
        return True
    if re.search(r"free(game|games|spin|spins)\d{1,3}(of|f)\d{1,3}", compact):
        return True
    return has_any(joined, [
        "remaining", "remaining free spin", "remaining free spins",
        "free spin remaining", "free spins remaining",
        "last free spin", "last free spins",
        "free spins left", "free game bonus",
    ])


def has_record_strong_feature_counter(rec):
    joined = record_text_joined(rec)
    compact = joined.replace(" ", "")
    if re.search(r"free(game|games|spin|spins)\d{1,3}(of|f)\d{1,3}", compact):
        return True
    if re.search(r"free(game|games|spin|spins)\d{1,3}/\d{1,3}", compact):
        return True
    if re.search(r"free(game|games|spin|spins)\d{2,4}", compact):
        return True
    return has_any_pattern(joined, [
        r"free\s*(game|spin|spins)\s*\d{1,3}\s*/\s*\d{1,3}",
        r"free\s*(game|games|spin|spins)\s*\d{1,3}\s*(of|f)\s*\d{1,3}",
        r"\d{1,3}\s*/\s*\d{1,3}\s*free\s*(game|spin|spins)",
        r"remaining\s*free\s*(spin|spins)\s*\d{1,3}",
        r"free\s*(spin|spins)\s*remaining\s*\d{1,3}",
    ])


def has_record_free_spin_counter_over_reel_board(rec):
    joined = record_text_joined(rec)
    if not (
        has_any(joined, ["free spins", "free spin", "freespins", "freespin"])
        and bool(re.search(r"\b\d{1,3}\b", joined))
    ):
        return False
    if has_record_start_intro_text(rec) or has_record_result_text(rec):
        return False
    if has_any(joined, ["congratulations", "you have won", "you won", "press", "continue", "start"]):
        return False

    score = float((rec.get("category_scores") or {}).get("FeatureBoard", 0.0) or 0.0)
    if score >= 3.0:
        return True

    path = rec.get("save_path") or ""
    if not path or not os.path.exists(path):
        return False
    img = cv2.imread(path)
    if img is None:
        return False
    score, _reasons = feature_reel_board_signal_score(img)
    rec.setdefault("category_scores", {})["FeatureBoard"] = round(score, 2)
    return score >= 3.0


def has_record_start_intro_text(rec):
    joined = record_text_joined(rec)
    return has_any(joined, [
        "start", "starting", "press start", "tap to start", "click to start",
        "begin", "enter",
    ])


def has_record_result_text(rec):
    joined = record_text_joined(rec)
    compact = joined.replace(" ", "")
    if has_any(joined, RESULT_STRONG_PHRASES):
        return True
    return "total" in compact and "win" in compact and bool(re.search(r"\d[\d,. ]{2,}", joined))


def has_record_base_text(rec):
    joined = record_text_joined(rec)
    return has_any(joined, [
        "balance", "total bets", "total bet", "extrabet", "extra bet",
        "bet", "auto", "turbo", "spin",
    ])


def has_record_web_help_chrome(rec):
    joined = record_text_joined(rec)
    return has_any(joined, [
        "home figma", "notion", "chatgpt", "gitlab", "google chrome",
        "chrome", "pragmatic play",
    ]) and has_any(joined, ["page", "game rules", "information screen", "symbol"])


# ---------------------------------------------------------------------------
# Keep score functions
# ---------------------------------------------------------------------------

def basegame_keep_score(record):
    ui_score = float(record.get("basegame_ui_score", 0.0))
    blur = float(record.get("blur_score", 0.0))
    noise = float(record.get("noise_score", 0.0))
    top_score = float(record.get("top_score", 0.0))
    obstruction = float(record.get("feature_obstruction_score", 0.0))

    clear_score = min(3.0, blur / 900.0)
    noise_penalty = min(3.0, noise * 0.6)
    obstruction_penalty = min(8.0, obstruction * 1.4)

    score = ui_score * 2.0 + clear_score - noise_penalty - obstruction_penalty
    if top_score >= 8.0:
        score -= min(4.0, (top_score - 6.0) * 0.35)
    return score


def feature_keep_score(record):
    ui_score = float(record.get("feature_ui_score", 0.0))
    active_score = float(record.get("feature_active_score", 0.0))
    blur = float(record.get("blur_score", 0.0))
    noise = float(record.get("noise_score", 0.0))
    top_score = float(record.get("top_score", 0.0))
    obstruction = float(record.get("feature_obstruction_score", 0.0))
    help_quality = float(record.get("help_quality_score", 0.0))
    has_pp_counter = has_record_pp_free_spins_left(record)

    clear_score = min(2.5, blur / 1000.0)
    noise_penalty = min(3.0, noise * 0.55)
    if active_score >= FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP:
        obstruction_penalty = min(3.0, obstruction * 0.45)
    else:
        obstruction_penalty = min(8.0, obstruction * 1.8)
    score = (
        ui_score * 2.0
        + active_score * 1.6
        + clear_score
        - noise_penalty
        - obstruction_penalty
        + top_score * 0.05
    )
    if has_pp_counter:
        score += 28.0
    elif help_quality >= HELP_MIN_QUALITY_SCORE:
        score -= help_quality * 2.2
    return score


def bigwin_keep_score(record):
    keep_signal = float(record.get("bigwin_keep_score", 0.0))
    top_score = float(record.get("top_score", 0.0))
    noise = float(record.get("noise_score", 0.0))
    blur = float(record.get("blur_score", 0.0))
    score = keep_signal * 2.0 + top_score + min(3.0, blur / 1200.0) - min(4.0, noise * 0.45)
    if keep_signal >= BIGWIN_KEEP_MIN_SCORE:
        score += 20.0
    return score


def loading_keep_score(rec):
    loading_score = record_category_score(rec, "loading")
    competing_score = max(
        record_category_score(rec, category)
        for category in ["BigWin", "Transition", "Feature game", "Feature Buy", "Result", "Basegame"]
    )
    loading_keywords = record_matched_keywords(rec, "loading")
    keyword_text = " ".join(loading_keywords).lower()
    frame_idx = int(rec.get("frame_idx", 0) or 0)

    score = loading_score * 2.0
    if "loading_splash_visual" in keyword_text:
        score += 14.0
    if "cover" in keyword_text or "splash" in keyword_text:
        score += 4.0
    if frame_idx <= 900:
        score += max(0.0, 9.0 - frame_idx / 120.0)

    score -= max(0.0, competing_score - loading_score) * 0.45
    score -= float(rec.get("feature_ui_score", 0.0) or 0.0) * 0.25
    score -= float(rec.get("basegame_ui_score", 0.0) or 0.0) * 0.15
    score -= max(0.0, float(rec.get("noise_score", 0.0) or 0.0) - 12.0) * 0.2
    return score


def top_k_for_category(category):
    if category in ["Transition", "Result", "loading"]:
        if category == "Transition":
            return TOP_K_TRANSITION
        if category == "Result":
            return TOP_K_RESULT
        if category == "loading":
            return TOP_K_LOADING
        return TOP_K_SHORT_EVENTS
    if category == "BigWin":
        return TOP_K_BIGWIN
    if category == "Help":
        return TOP_K_HELP
    if category == "Feature Buy":
        return TOP_K_FEATURE_BUY
    return TOP_K_DEFAULT


# ---------------------------------------------------------------------------
# Image feature / clustering
# ---------------------------------------------------------------------------

def get_image_feature(image_path):
    img = imread_image(image_path)
    if img is None:
        return None

    img = cv2.resize(img, (96, 96))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    hist = cv2.calcHist(
        [hsv],
        [0, 1, 2],
        None,
        [12, 8, 8],
        [0, 180, 0, 256, 0, 256]
    )
    hist = cv2.normalize(hist, hist).flatten()

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small_gray = cv2.resize(gray, (16, 16)).astype(np.float32).flatten() / 255.0

    return np.concatenate([hist.astype(np.float32), small_gray])


def get_bottom_ui_color_feature(image_path):
    img = imread_image(image_path)
    if img is None:
        return None

    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return None

    y1 = int(h * 0.55)
    y2 = int(h * 0.96)
    x1 = int(w * 0.04)
    x2 = int(w * 0.96)
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    roi = cv2.resize(roi, (128, 64))
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    hist = cv2.calcHist(
        [hsv],
        [0, 1, 2],
        None,
        [16, 5, 4],
        [0, 180, 0, 256, 0, 256]
    )
    hist = cv2.normalize(hist, hist).flatten().astype(np.float32)

    red = np.mean((((hue <= 10) | (hue >= 170)) & (sat >= 70) & (val >= 80)).astype(np.float32))
    pink = np.mean(((hue >= 145) & (hue <= 175) & (sat >= 55) & (val >= 90)).astype(np.float32))
    purple = np.mean(((hue >= 120) & (hue <= 160) & (sat >= 45) & (val >= 70)).astype(np.float32))
    blue = np.mean(((hue >= 88) & (hue <= 125) & (sat >= 45) & (val >= 70)).astype(np.float32))
    cyan = np.mean(((hue >= 75) & (hue <= 100) & (sat >= 45) & (val >= 80)).astype(np.float32))
    gold = np.mean(((hue >= 12) & (hue <= 38) & (sat >= 45) & (val >= 90)).astype(np.float32))
    green = np.mean(((hue >= 42) & (hue <= 82) & (sat >= 45) & (val >= 75)).astype(np.float32))
    dark = np.mean((val <= 70).astype(np.float32))
    bright = np.mean((val >= 210).astype(np.float32))
    high_sat = np.mean((sat >= 120).astype(np.float32))
    mean_sat = float(np.mean(sat) / 255.0)
    mean_val = float(np.mean(val) / 255.0)
    edge_ratio = float(np.mean(cv2.Canny(gray, 60, 140) > 0))
    small_gray = cv2.resize(gray, (16, 8)).astype(np.float32).flatten() / 255.0

    ratios = np.array([
        red, pink, purple, blue, cyan, gold, green, dark, bright,
        high_sat, mean_sat, mean_val, edge_ratio,
    ], dtype=np.float32)
    return np.concatenate([hist, ratios * 2.0, small_gray * 0.35])


def simple_kmeans(features, k=3, max_iter=30):
    n = len(features)
    if n == 0:
        return np.array([]), np.array([])

    k = min(k, n)
    X = np.asarray(features, dtype=np.float32)

    centers = [X[0]]
    while len(centers) < k:
        distances = np.min(
            np.stack([np.linalg.norm(X - c, axis=1) for c in centers], axis=1),
            axis=1
        )
        centers.append(X[int(np.argmax(distances))])

    centers = np.asarray(centers, dtype=np.float32)
    labels = np.zeros(n, dtype=np.int32)

    for _ in range(max_iter):
        dist = np.stack([np.linalg.norm(X - c, axis=1) for c in centers], axis=1)
        new_labels = np.argmin(dist, axis=1)

        if np.array_equal(labels, new_labels):
            break

        labels = new_labels
        for i in range(k):
            members = X[labels == i]
            if len(members) > 0:
                centers[i] = np.mean(members, axis=0)

    return labels, centers


def select_visual_cluster_images(
    records,
    cluster_count=3,
    keep_per_cluster=3,
    drop_low_score_majority_cluster=False,
    keep_score_fn=None
):
    feature_pairs = []
    invalid_records = []

    for rec in records:
        feat = get_image_feature(rec["save_path"])
        if feat is None:
            invalid_records.append(rec)
        else:
            feature_pairs.append((rec, feat))

    if len(feature_pairs) <= cluster_count * keep_per_cluster:
        return [rec for rec, _ in feature_pairs], invalid_records

    recs = [rec for rec, _ in feature_pairs]
    feats = [feat for _, feat in feature_pairs]

    labels, centers = simple_kmeans(feats, k=cluster_count)
    if len(labels) == 0:
        return [], records

    keep_records = []
    keep_ids = set()
    dropped_cluster_ids = set()

    if drop_low_score_majority_cluster and len(centers) >= 2:
        cluster_stats = []
        max_size = 0
        for cid in range(len(centers)):
            member_indices = np.where(labels == cid)[0]
            size = int(len(member_indices))
            if size == 0:
                continue

            avg_score = float(np.mean([recs[idx].get("top_score", 0.0) for idx in member_indices]))
            max_size = max(max_size, size)
            cluster_stats.append((cid, size, avg_score))

        if cluster_stats and max_size > 0:
            majority_candidates = [
                stat for stat in cluster_stats
                if stat[1] >= max(1, int(max_size * LOW_SCORE_MAJORITY_CLUSTER_RATIO))
            ]
            if majority_candidates:
                drop_cid, drop_size, drop_avg_score = min(
                    majority_candidates,
                    key=lambda stat: (stat[2], -stat[1])
                )
                dropped_cluster_ids.add(drop_cid)
                print(
                    f"  drop low-score majority cluster: cluster={drop_cid}, "
                    f"count={drop_size}, avg_score={drop_avg_score:.2f}"
                )

    cluster_order = sorted(
        [cid for cid in range(len(centers)) if cid not in dropped_cluster_ids],
        key=lambda cid: int(np.sum(labels == cid)),
        reverse=True
    )

    for cid in cluster_order:
        member_indices = np.where(labels == cid)[0]
        if len(member_indices) == 0:
            continue

        center = centers[cid]
        ranked = []
        for idx in member_indices:
            dist = float(np.linalg.norm(feats[idx] - center))
            ranked.append((dist, idx))

        if keep_score_fn is None:
            ranked.sort(key=lambda x: x[0])
        else:
            ranked.sort(
                key=lambda x: (
                    keep_score_fn(recs[x[1]]),
                    -x[0],
                ),
                reverse=True
            )

        for _, idx in ranked[:keep_per_cluster]:
            rec = recs[idx]
            keep_records.append(rec)
            keep_ids.add(id(rec))

    remove_records = [
        rec for idx, rec in enumerate(recs)
        if id(rec) not in keep_ids or labels[idx] in dropped_cluster_ids
    ] + invalid_records
    return keep_records, remove_records


# ---------------------------------------------------------------------------
# Basegame helpers
# ---------------------------------------------------------------------------

def basegame_final_reject_reasons(rec):
    reasons = []
    joined = record_text_joined(rec)

    if has_record_feature_text(rec):
        reasons.append("feature_running_text")
    if has_feature_intro_signal(joined) and not has_record_base_text(rec):
        reasons.append("feature_intro_text")
    if has_record_result_text(rec):
        reasons.append("result_text")

    obstruction = float(rec.get("feature_obstruction_score", 0.0))
    noise = float(rec.get("noise_score", 0.0))
    if obstruction >= BASEGAME_FINAL_MAX_OBSTRUCTION_SCORE:
        reasons.append(f"board_obstructed:{obstruction:.2f}")
    if noise >= BASEGAME_FINAL_MAX_NOISE_SCORE and obstruction >= FEATURE_BOARD_OBSTRUCTION_THRESHOLD:
        reasons.append(f"noisy_overlay:{noise:.2f}")

    img = imread_image(rec.get("save_path", ""))
    if img is not None:
        exposure_score, _ = overexposure_score(img)
        if exposure_score >= BASEGAME_FINAL_MAX_EXPOSURE_SCORE and obstruction >= FEATURE_BOARD_OBSTRUCTION_THRESHOLD:
            reasons.append(f"overexposed_overlay:{exposure_score:.2f}")

    return reasons


def is_clean_basegame_final_candidate(rec):
    return not basegame_final_reject_reasons(rec)


# ---------------------------------------------------------------------------
# Help helpers
# ---------------------------------------------------------------------------

def help_rule_text_stats(rec):
    text_items = [
        normalize_text(text)
        for text in record_text_items(rec)
        if len(normalize_text(text)) >= 2
    ]
    joined = " ".join(text_items)
    token_count = len(set(joined.split()))
    long_line_count = sum(1 for text in text_items if len(text) >= 18)
    return {
        "line_count": len(text_items),
        "token_count": token_count,
        "long_line_count": long_line_count,
        "joined": joined,
    }


def is_plain_rule_help_record(rec):
    stats = help_rule_text_stats(rec)
    quality = float(rec.get("help_quality_score", 0.0))
    paytable_score = float(rec.get("help_paytable_score", 0.0))

    has_lots_of_text = (
        stats["line_count"] >= HELP_RULE_TEXT_MIN_LINES
        and (
            stats["token_count"] >= HELP_RULE_TEXT_MIN_TOKENS
            or stats["long_line_count"] >= HELP_RULE_TEXT_MIN_LONG_LINES
        )
    )
    has_help_context = (
        has_any(stats["joined"], HELP_PHRASES)
        or paytable_score >= 1.0
        or stats["long_line_count"] >= HELP_RULE_TEXT_MIN_LONG_LINES + 1
    )
    return (
        has_lots_of_text
        and has_help_context
        and quality >= HELP_RULE_TEXT_MIN_QUALITY_SCORE
    )


def help_rule_keep_score(rec):
    stats = help_rule_text_stats(rec)
    return (
        rec.get("help_quality_score", 0.0) * 1.2
        + rec.get("help_paytable_score", 0.0) * 2.0
        + stats["line_count"] * 0.8
        + stats["token_count"] * 0.15
        + stats["long_line_count"] * 1.0
        + rec.get("blur_score", 0.0) * 0.01
        - rec.get("noise_score", 0.0) * 0.6
    )


# ---------------------------------------------------------------------------
# Move records
# ---------------------------------------------------------------------------

def move_records_to_low_score(records, low_score_dir, category):
    trash_category_dir = os.path.join(low_score_dir, category)
    os.makedirs(trash_category_dir, exist_ok=True)

    for rec in records:
        src = rec["save_path"]
        if os.path.exists(src):
            dst = os.path.join(trash_category_dir, os.path.basename(src))
            try:
                shutil.move(src, dst)
            except Exception as e:
                print(f"移動失敗: {src} -> {dst} | {e}")


def reassign_record_category(rec, new_category):
    old_category = rec.get("category")
    if old_category == new_category:
        return False

    src = rec.get("save_path")
    if not src:
        rec["category"] = new_category
        return True

    video_dir = os.path.dirname(os.path.dirname(src))
    dst_dir = os.path.join(video_dir, new_category)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))

    if os.path.exists(src):
        try:
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.move(src, dst)
            rec["save_path"] = dst
        except Exception as e:
            print(f"分類修正移動失敗: {src} -> {dst} | {e}")
            return False
    else:
        rec["save_path"] = dst

    rec["category"] = new_category
    return True


# ---------------------------------------------------------------------------
# Category-specific selectors
# ---------------------------------------------------------------------------

def select_basegame_ui_images(records, cluster_count=3, keep_per_cluster=3):
    if not records:
        return [], []

    ranked_records = sorted(
        records,
        key=lambda rec: (
            rec.get("basegame_ui_score", 0.0),
            basegame_keep_score(rec),
            -rec.get("noise_score", 0.0),
            rec.get("blur_score", 0.0),
            -rec.get("top_score", 0.0),
        ),
        reverse=True
    )

    min_keep_pool = cluster_count * keep_per_cluster
    top_pool_count = max(min_keep_pool, int(np.ceil(len(ranked_records) * BASEGAME_KEEP_TOP_UI_RATIO)))
    top_pool_count = min(len(ranked_records), top_pool_count)

    candidates = [
        rec for rec in ranked_records[:top_pool_count]
        if rec.get("basegame_ui_score", 0.0) >= BASEGAME_MIN_UI_SCORE_FOR_KEEP
    ]
    rejected_candidates = []
    clean_candidates_for_final = []
    for rec in candidates:
        reject_reasons = basegame_final_reject_reasons(rec)
        if reject_reasons:
            rec.setdefault("basegame_final_reject_reasons", reject_reasons)
            rejected_candidates.append(rec)
        else:
            clean_candidates_for_final.append(rec)
    if clean_candidates_for_final:
        candidates = clean_candidates_for_final

    clean_candidates = [
        rec for rec in candidates
        if rec.get("noise_score", 0.0) < TRANSITION_NOISE_SCORE_THRESHOLD
    ]
    if len(clean_candidates) >= min_keep_pool:
        candidates = clean_candidates
    candidates = sorted(candidates, key=basegame_keep_score, reverse=True)
    if len(candidates) < min_keep_pool:
        fallback_candidates = [
            rec for rec in ranked_records[:min(top_pool_count, len(ranked_records))]
            if is_clean_basegame_final_candidate(rec)
        ]
        if fallback_candidates:
            candidates = fallback_candidates

    candidate_ids = {id(rec) for rec in candidates}
    rejected_ids = {id(rec) for rec in rejected_candidates} if clean_candidates_for_final else set()
    low_ui_records = [
        rec for rec in records
        if id(rec) not in candidate_ids or id(rec) in rejected_ids
    ]

    keep_records, cluster_remove_records = select_visual_cluster_images(
        candidates,
        cluster_count=cluster_count,
        keep_per_cluster=keep_per_cluster,
        drop_low_score_majority_cluster=False,
        keep_score_fn=basegame_keep_score
    )
    return keep_records, low_ui_records + cluster_remove_records


def select_feature_ui_images(records, cluster_count=3, keep_per_cluster=3):
    if not records:
        return [], []

    min_keep_pool = cluster_count * keep_per_cluster
    ranked_records = sorted(
        records,
        key=lambda rec: (
            1 if has_record_pp_free_spins_left(rec) else 0,
            rec.get("feature_active_score", 0.0),
            rec.get("feature_ui_score", 0.0),
            feature_keep_score(rec),
            -rec.get("noise_score", 0.0),
            rec.get("blur_score", 0.0),
            rec.get("top_score", 0.0),
        ),
        reverse=True
    )

    pp_counter_records = [
        rec for rec in ranked_records
        if has_record_pp_free_spins_left(rec)
        and rec.get("feature_obstruction_score", 0.0) < FEATURE_BOARD_OBSTRUCTION_THRESHOLD
    ]
    if len(pp_counter_records) >= min_keep_pool:
        candidates = sorted(pp_counter_records, key=feature_keep_score, reverse=True)
        keep_records = candidates[:min_keep_pool]
        keep_ids = {id(rec) for rec in keep_records}
        remove_records = [rec for rec in records if id(rec) not in keep_ids]
        return keep_records, remove_records

    top_pool_count = max(min_keep_pool, int(np.ceil(len(ranked_records) * FEATURE_UI_KEEP_TOP_RATIO)))
    top_pool_count = min(len(ranked_records), top_pool_count)

    candidates = [
        rec for rec in ranked_records[:top_pool_count]
        if (
            rec.get("feature_ui_score", 0.0) >= FEATURE_UI_MIN_SCORE_FOR_KEEP
            or rec.get("feature_active_score", 0.0) >= FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP
        )
    ]
    clean_candidates = [
        rec for rec in candidates
        if rec.get("noise_score", 0.0) < TRANSITION_NOISE_SCORE_THRESHOLD
    ]
    if len(clean_candidates) >= min_keep_pool:
        candidates = clean_candidates
    visible_board_candidates = [
        rec for rec in candidates
        if (
            rec.get("feature_obstruction_score", 0.0) < FEATURE_BOARD_OBSTRUCTION_THRESHOLD
            or rec.get("feature_active_score", 0.0) >= FEATURE_ACTIVE_MIN_SCORE_FOR_KEEP
        )
        and (
            has_record_pp_free_spins_left(rec)
            or rec.get("help_quality_score", 0.0) < HELP_MIN_QUALITY_SCORE
        )
    ]
    if len(visible_board_candidates) >= min_keep_pool:
        candidates = visible_board_candidates
    candidates = sorted(candidates, key=feature_keep_score, reverse=True)
    if len(candidates) < min_keep_pool:
        candidates = ranked_records[:min(top_pool_count, len(ranked_records))]

    candidate_ids = {id(rec) for rec in candidates}
    weak_ui_records = [rec for rec in records if id(rec) not in candidate_ids]

    keep_records, cluster_remove_records = select_visual_cluster_images(
        candidates,
        cluster_count=cluster_count,
        keep_per_cluster=keep_per_cluster,
        drop_low_score_majority_cluster=False,
        keep_score_fn=feature_keep_score
    )
    return keep_records, weak_ui_records + cluster_remove_records


def select_transition_images(records):
    if not records:
        return [], []

    def transition_rank(rec):
        joined = record_text_joined(rec)
        has_free_spin_award = (
            has_any(joined, ["you have won", "you won", "congratulations"])
            and has_any(joined, ["free spins", "free spin", "freespins", "freespin"])
        )
        has_settings_help_text = has_any(joined, [
            "settings menu", "information screen", "game history",
            "skip screens option", "auto skips",
        ])
        return (
            1 if has_free_spin_award else 0,
            -1 if has_settings_help_text else 0,
            rec.get("transition_keep_score", rec.get("top_score", 0.0)),
            -rec.get("noise_score", 0.0),
            rec.get("top_score", 0.0),
        )

    k = top_k_for_category("Transition")
    groups = []
    current_group = []
    last_frame = None
    for rec in sorted(records, key=lambda item: int(item.get("frame_idx", 0) or 0)):
        frame = int(rec.get("frame_idx", 0) or 0)
        if current_group and last_frame is not None and frame - last_frame > TRANSITION_EVENT_GAP_FRAMES:
            groups.append(current_group)
            current_group = []
        current_group.append(rec)
        last_frame = frame
    if current_group:
        groups.append(current_group)

    keep_records = []
    keep_ids = set()
    event_picks = [max(group, key=transition_rank) for group in groups]
    event_picks.sort(key=transition_rank, reverse=True)
    for rec in event_picks:
        if len(keep_records) >= k:
            break
        keep_records.append(rec)
        keep_ids.add(id(rec))

    remaining = [rec for rec in records if id(rec) not in keep_ids]
    remaining.sort(key=transition_rank, reverse=True)
    for rec in remaining:
        if len(keep_records) >= k:
            break
        keep_records.append(rec)
        keep_ids.add(id(rec))

    remove_records = [rec for rec in records if id(rec) not in keep_ids]
    return keep_records, remove_records


def select_bigwin_images(records):
    if not records:
        return [], []

    qualified_records = [
        rec for rec in records
        if (
            float(rec.get("bigwin_keep_score", 0.0)) >= BIGWIN_KEEP_MIN_SCORE
            or float(rec.get("top_score", 0.0)) >= 6.0
            or bigwin_tier_key(rec)
        )
    ]
    weak_records = [
        rec for rec in records
        if (
            float(rec.get("bigwin_keep_score", 0.0)) < BIGWIN_KEEP_MIN_SCORE
            and float(rec.get("top_score", 0.0)) < 6.0
            and not bigwin_tier_key(rec)
        )
    ]

    if not qualified_records:
        return [], records

    keep_limit = top_k_for_category("BigWin")
    keep_records = []
    keep_ids = set()

    def pick_best_bigwin_record(bucket):
        return max(
            bucket,
            key=lambda rec: (
                bigwin_keep_score(rec),
                rec.get("blur_score", 0.0),
                -rec.get("noise_score", 0.0),
                rec.get("top_score", 0.0),
            )
        )

    def split_bigwin_event_groups(bucket):
        sorted_bucket = sorted(bucket, key=lambda rec: int(rec.get("frame_idx", 0) or 0))
        groups = []
        current_group = []
        last_frame = None
        for rec in sorted_bucket:
            frame = int(rec.get("frame_idx", 0) or 0)
            if current_group and last_frame is not None and frame - last_frame > BIGWIN_EVENT_GAP_FRAMES:
                groups.append(current_group)
                current_group = []
            current_group.append(rec)
            last_frame = frame
        if current_group:
            groups.append(current_group)
        return groups

    tier_buckets = defaultdict(list)
    unlabeled_records = []
    for rec in qualified_records:
        tier = bigwin_tier_key(rec)
        if tier:
            tier_buckets[tier].append(rec)
        else:
            unlabeled_records.append(rec)

    if not tier_buckets.get("big_win"):
        labeled_frames = [
            int(rec.get("frame_idx", 0))
            for rec in qualified_records
            if bigwin_tier_key(rec)
        ]
        if labeled_frames:
            first_labeled_frame = min(labeled_frames)
            inferred_bigwin_records = [
                rec for rec in unlabeled_records
                if int(rec.get("frame_idx", 0)) < first_labeled_frame
                and (
                    float(rec.get("bigwin_keep_score", 0.0)) >= 4.0
                    or float(rec.get("top_score", 0.0)) >= 6.0
                )
            ]
            if inferred_bigwin_records:
                tier_buckets["big_win"].extend(inferred_bigwin_records)
                for rec in inferred_bigwin_records:
                    rec["bigwin_tier"] = "big_win"
                    rec["bigwin_tier_label"] = bigwin_tier_label("big_win")
                    rec.setdefault("matched_keywords", [])

    event_picks = []
    for tier in BIGWIN_TIER_ORDER:
        bucket = tier_buckets.get(tier, [])
        if not bucket:
            continue

        for event_group in split_bigwin_event_groups(bucket):
            pick = pick_best_bigwin_record(event_group)
            event_picks.append((tier, pick))

    event_picks.sort(
        key=lambda item: (
            BIGWIN_TIER_ORDER.index(item[0]) if item[0] in BIGWIN_TIER_ORDER else 999,
            int(item[1].get("frame_idx", 0) or 0),
        )
    )
    for tier, pick in event_picks:
        keep_records.append(pick)
        keep_ids.add(id(pick))
        pick["bigwin_tier"] = tier
        pick["bigwin_tier_label"] = bigwin_tier_label(tier)
        if len(keep_records) >= keep_limit:
            break

    remaining_candidates = [
        rec for rec in qualified_records
        if id(rec) not in keep_ids
    ]
    remaining_candidates.sort(
        key=lambda rec: (
            bigwin_keep_score(rec),
            rec.get("blur_score", 0.0),
            -rec.get("noise_score", 0.0),
        ),
        reverse=True
    )

    for rec in remaining_candidates:
        if len(keep_records) >= keep_limit:
            break
        keep_records.append(rec)
        keep_ids.add(id(rec))

    remove_records = [
        rec for rec in records
        if id(rec) not in keep_ids
    ]

    tier_summary = [
        f"{bigwin_tier_label(tier)}={len(tier_buckets.get(tier, []))}"
        for tier in BIGWIN_TIER_ORDER
        if tier_buckets.get(tier)
    ]
    if tier_summary:
        print("  BigWin OCR tiers: " + ", ".join(tier_summary))

    return keep_records, remove_records


def select_help_images(records):
    if not records:
        return [], []

    ranked_records = sorted(
        records,
        key=lambda rec: (
            help_rule_keep_score(rec),
            rec.get("help_quality_score", 0.0),
            rec.get("blur_score", 0.0),
            -rec.get("noise_score", 0.0),
            rec.get("top_score", 0.0),
        ),
        reverse=True
    )

    web_help_records = [
        rec for rec in ranked_records
        if has_record_web_help_chrome(rec) and is_plain_rule_help_record(rec)
    ]
    if len(web_help_records) >= 3:
        ranked_records = web_help_records
    else:
        grouped = []
        current_group = []
        last_frame = None
        for rec in sorted(ranked_records, key=lambda item: int(item.get("frame_idx", 0) or 0)):
            frame = int(rec.get("frame_idx", 0) or 0)
            if current_group and last_frame is not None and frame - last_frame > HELP_EVENT_GAP_FRAMES:
                grouped.append(current_group)
                current_group = []
            current_group.append(rec)
            last_frame = frame
        if current_group:
            grouped.append(current_group)
        if grouped:
            best_group = max(
                grouped,
                key=lambda group: (
                    sum(1 for rec in group if is_plain_rule_help_record(rec)),
                    sum(float(rec.get("help_quality_score", 0.0)) for rec in group) / max(1, len(group)),
                    len(group),
                )
            )
            ranked_records = sorted(
                best_group,
                key=lambda rec: (
                    help_rule_keep_score(rec),
                    rec.get("help_quality_score", 0.0),
                    rec.get("blur_score", 0.0),
                    -rec.get("noise_score", 0.0),
                    rec.get("top_score", 0.0),
                ),
                reverse=True
            )

    k = min(top_k_for_category("Help"), HELP_MAX_FINAL_PAGES, len(ranked_records))
    keep_records = []
    keep_ids = set()

    rule_text_records = [
        rec for rec in ranked_records
        if is_plain_rule_help_record(rec)
    ]

    for rec in rule_text_records:
        if len(keep_records) >= k:
            break
        if is_duplicate_help_record(rec, keep_records):
            continue
        keep_records.append(rec)
        keep_ids.add(id(rec))

    paytable_records = [
        rec for rec in ranked_records
        if rec.get("help_paytable_score", 0.0) >= 2.0
        and rec.get("help_quality_score", 0.0) >= HELP_RULE_TEXT_MIN_QUALITY_SCORE
        and id(rec) not in keep_ids
    ]
    paytable_records.sort(
        key=lambda rec: (
            rec.get("help_paytable_score", 0.0),
            help_rule_keep_score(rec),
            rec.get("help_quality_score", 0.0),
        ),
        reverse=True
    )
    paytable_added = 0
    paytable_limit = min(HELP_PAYTABLE_KEEP_COUNT, max(0, k - len(keep_records)))
    for rec in paytable_records:
        if paytable_added >= paytable_limit:
            break
        if is_duplicate_help_record(rec, keep_records):
            continue
        keep_records.append(rec)
        keep_ids.add(id(rec))
        paytable_added += 1

    if not keep_records and ranked_records:
        for rec in ranked_records:
            if len(keep_records) >= min(3, k):
                break
            if rec.get("help_quality_score", 0.0) < HELP_RULE_TEXT_MIN_QUALITY_SCORE:
                continue
            if is_duplicate_help_record(rec, keep_records):
                continue
            keep_records.append(rec)
            keep_ids.add(id(rec))

    remove_records = [rec for rec in records if id(rec) not in keep_ids]
    return keep_records, remove_records


def select_loading_images(records):
    if not records:
        return [], []

    k = top_k_for_category("loading")
    keep_records = []
    keep_ids = set()

    splash_records = [
        rec for rec in records
        if "loading_splash_visual" in " ".join(record_matched_keywords(rec, "loading")).lower()
    ]
    splash_records.sort(
        key=lambda rec: (
            int(rec.get("frame_idx", 0) or 0),
            -max(
                record_category_score(rec, category)
                for category in ["BigWin", "Transition", "Feature game", "Feature Buy", "Result"]
            ),
            -float(rec.get("noise_score", 0.0) or 0.0),
        )
    )

    for rec in splash_records[:min(3, k)]:
        keep_records.append(rec)
        keep_ids.add(id(rec))

    ranked_records = sorted(records, key=loading_keep_score, reverse=True)
    for rec in ranked_records:
        if len(keep_records) >= k:
            break
        if id(rec) in keep_ids:
            continue
        keep_records.append(rec)
        keep_ids.add(id(rec))

    remove_records = [rec for rec in records if id(rec) not in keep_ids]
    return keep_records, remove_records


# ---------------------------------------------------------------------------
# Refinement passes
# ---------------------------------------------------------------------------

def refine_transition_feature_counter_records(saved_records):
    changed = 0
    for rec in saved_records:
        if rec.get("category") != "Transition":
            continue
        if not (
            has_record_strong_feature_counter(rec)
            or has_record_free_spin_counter_over_reel_board(rec)
        ):
            continue
        if has_record_start_intro_text(rec) or has_record_result_text(rec):
            continue
        if reassign_record_category(rec, "Feature game"):
            rec["transition_feature_counter_refined"] = True
            rec["top_score"] = max(float(rec.get("top_score", 0.0)), 10.0)
            changed += 1

    if changed:
        print(f"\n[Feature Counter Rescue] Transition -> Feature game：{changed} 張")


def refine_base_feature_by_bottom_ui_clusters(saved_records):
    if not ENABLE_BOTTOM_UI_CLUSTER_REFINEMENT:
        return

    feature_record_count = sum(1 for rec in saved_records if rec.get("category") == "Feature game")
    use_basegame_recovery = feature_record_count <= BOTTOM_UI_CLUSTER_LOW_FEATURE_COUNT
    candidates = [
        rec for rec in saved_records
        if (
            rec.get("category") in ["Basegame", "Feature game"]
            or (
                use_basegame_recovery
                and rec.get("category") in ["Basegame", "Transition"]
            )
        )
        and os.path.exists(rec.get("save_path", ""))
    ]
    if len(candidates) < BOTTOM_UI_CLUSTER_MIN_RECORDS:
        return

    feature_pairs = []
    for rec in candidates:
        feat = get_bottom_ui_color_feature(rec["save_path"])
        if feat is not None:
            feature_pairs.append((rec, feat))
    if len(feature_pairs) < BOTTOM_UI_CLUSTER_MIN_RECORDS:
        return

    recs = [rec for rec, _ in feature_pairs]
    feats = [feat for _, feat in feature_pairs]
    labels, centers = simple_kmeans(feats, k=2)
    if len(labels) == 0 or len(centers) < 2:
        return

    within = []
    for cid in range(len(centers)):
        member_indices = np.where(labels == cid)[0]
        if len(member_indices) == 0:
            within.append(0.0)
            continue
        within.append(float(np.mean([
            np.linalg.norm(feats[idx] - centers[cid])
            for idx in member_indices
        ])))
    separation = float(np.linalg.norm(centers[0] - centers[1]) / max(1e-6, np.mean(within) + 1e-6))
    if separation < BOTTOM_UI_CLUSTER_MIN_SEPARATION:
        return

    stats = []
    for cid in range(len(centers)):
        member_indices = np.where(labels == cid)[0]
        members = [recs[idx] for idx in member_indices]
        if not members:
            continue
        feature_text_hits = sum(1 for rec in members if has_record_feature_text(rec))
        strong_feature_counter_hits = sum(1 for rec in members if has_record_strong_feature_counter(rec))
        base_text_hits = sum(1 for rec in members if has_record_base_text(rec))
        feature_count = sum(1 for rec in members if rec.get("category") == "Feature game")
        base_count = sum(1 for rec in members if rec.get("category") == "Basegame")
        transition_count = sum(1 for rec in members if rec.get("category") == "Transition")
        avg_feature_ui = float(np.mean([rec.get("feature_ui_score", 0.0) for rec in members]))
        avg_base_ui = float(np.mean([rec.get("basegame_ui_score", 0.0) for rec in members]))
        feature_evidence = (
            strong_feature_counter_hits * 5.0
            + feature_text_hits * 2.0
            + feature_count * 1.4
            + max(0.0, avg_feature_ui - avg_base_ui) * 0.8
        )
        base_evidence = (
            base_count * 1.0
            + base_text_hits * 0.4
            + max(0.0, avg_base_ui - avg_feature_ui) * 0.8
        )
        stats.append({
            "cid": cid,
            "count": len(members),
            "feature_text_hits": feature_text_hits,
            "strong_feature_counter_hits": strong_feature_counter_hits,
            "base_text_hits": base_text_hits,
            "feature_count": feature_count,
            "base_count": base_count,
            "transition_count": transition_count,
            "avg_feature_ui": avg_feature_ui,
            "avg_base_ui": avg_base_ui,
            "feature_evidence": feature_evidence,
            "base_evidence": base_evidence,
        })

    if len(stats) < 2:
        return

    feature_stat = max(stats, key=lambda stat: stat["feature_evidence"])
    base_stat = max([stat for stat in stats if stat["cid"] != feature_stat["cid"]], key=lambda stat: stat["base_evidence"])
    if feature_stat["feature_evidence"] < BOTTOM_UI_CLUSTER_MIN_FEATURE_EVIDENCE:
        return
    if feature_stat["feature_evidence"] <= base_stat["feature_evidence"] + 0.5:
        return

    changed_to_feature = 0
    changed_to_base = 0
    for idx, rec in enumerate(recs):
        cid = int(labels[idx])
        if cid == feature_stat["cid"] and rec.get("category") in ["Basegame", "Transition"]:
            if (
                has_record_strong_feature_counter(rec)
                or rec.get("feature_ui_score", 0.0) >= FEATURE_UI_MIN_SCORE_FOR_KEEP * 0.75
            ):
                if reassign_record_category(rec, "Feature game"):
                    rec["bottom_ui_cluster_refined"] = "to_feature_game"
                    changed_to_feature += 1
        elif cid == base_stat["cid"] and rec.get("category") == "Feature game":
            if not has_record_feature_text(rec) and rec.get("basegame_ui_score", 0.0) >= BASEGAME_MIN_UI_SCORE_FOR_KEEP:
                if reassign_record_category(rec, "Basegame"):
                    rec["bottom_ui_cluster_refined"] = "to_basegame"
                    changed_to_base += 1

    if changed_to_feature or changed_to_base:
        print(
            "\n[Bottom UI Cluster] 依影片內底部 UI 色彩分群修正 "
            f"Basegame/Feature game：to_feature={changed_to_feature}, "
            f"to_base={changed_to_base}, separation={separation:.2f}"
        )


# ---------------------------------------------------------------------------
# Main entry point for post-processing
# ---------------------------------------------------------------------------

def keep_selected_images(saved_records, low_score_dir=None):
    try:
        from ..config import OUTPUT_DIR
    except ImportError:
        from config import OUTPUT_DIR

    if low_score_dir is None:
        low_score_dir = os.path.join(OUTPUT_DIR, "low_score")
    os.makedirs(low_score_dir, exist_ok=True)

    refine_transition_feature_counter_records(saved_records)
    refine_base_feature_by_bottom_ui_clusters(saved_records)

    category_map = defaultdict(list)
    for rec in saved_records:
        category_map[rec["category"]].append(rec)

    for category, records in category_map.items():
        if category == "Basegame":
            keep_records, remove_records = select_basegame_ui_images(
                records,
                cluster_count=VISUAL_CLUSTER_COUNT,
                keep_per_cluster=VISUAL_KEEP_PER_CLUSTER
            )
            print(
                f"\n[{category}] Basegame UI 優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "Feature game":
            keep_records, remove_records = select_feature_ui_images(
                records,
                cluster_count=VISUAL_CLUSTER_COUNT,
                keep_per_cluster=VISUAL_KEEP_PER_CLUSTER
            )
            print(
                f"\n[{category}] Remaining Free Spin UI 優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "Transition":
            keep_records, remove_records = select_transition_images(records)
            print(
                f"\n[{category}] 轉場品質分優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "BigWin":
            keep_records, remove_records = select_bigwin_images(records)
            print(
                f"\n[{category}] Big/Mega/Total Win + 分數訊號優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "Help":
            keep_records, remove_records = select_help_images(records)
            print(
                f"\n[{category}] 深色說明頁 + OCR 內容去重取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category == "loading":
            keep_records, remove_records = select_loading_images(records)
            print(
                f"\n[{category}] loading 封面優先取樣；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        elif category in VISUAL_CLUSTER_CATEGORIES:
            cluster_count = BIGWIN_VISUAL_CLUSTER_COUNT if category == "BigWin" else VISUAL_CLUSTER_COUNT
            keep_per_cluster = BIGWIN_VISUAL_KEEP_PER_CLUSTER if category == "BigWin" else VISUAL_KEEP_PER_CLUSTER
            keep_records, remove_records = select_visual_cluster_images(
                records,
                cluster_count=cluster_count,
                keep_per_cluster=keep_per_cluster,
                drop_low_score_majority_cluster=category in DROP_LOW_SCORE_MAJORITY_CLUSTER_CATEGORIES
            )
            print(
                f"\n[{category}] 視覺分群 {cluster_count} 群，每群 {keep_per_cluster} 張；"
                f"保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score"
            )
        else:
            records.sort(key=lambda x: x["top_score"], reverse=True)
            k = top_k_for_category(category)
            keep_records = records[:k]
            remove_records = records[k:]
            print(f"\n[{category}] top_score 保留 {len(keep_records)} 張，移動 {len(remove_records)} 張到 low_score")

        move_records_to_low_score(remove_records, low_score_dir, category)
