import csv
import hashlib
import os
import re

import cv2
import numpy as np

try:
    from .config import CATEGORIES, INPUT_DIR, OUTPUT_DIR, SINGLE_VIDEO_NAME, VIDEO_EXTENSIONS
except ImportError:
    from config import CATEGORIES, INPUT_DIR, OUTPUT_DIR, SINGLE_VIDEO_NAME, VIDEO_EXTENSIONS


def get_video_list():
    os.makedirs(INPUT_DIR, exist_ok=True)
    if SINGLE_VIDEO_NAME:
        return [os.path.join(INPUT_DIR, SINGLE_VIDEO_NAME)]

    return sorted([
        os.path.join(INPUT_DIR, f)
        for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(VIDEO_EXTENSIONS)
    ])


def safe_short_name(name, max_len=52):
    safe_name = re.sub(r'[<>:"/\\|?*]+', "_", str(name))
    safe_name = re.sub(r"\s+", " ", safe_name).strip(" .")
    if not safe_name:
        safe_name = "video"

    if len(safe_name) <= max_len:
        return safe_name

    digest = hashlib.sha1(str(name).encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"{safe_name[:max_len - 9].rstrip()}_{digest}"


def safe_folder_name(name):
    return safe_short_name(name, max_len=52)


def get_video_output_dir(video_path):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(OUTPUT_DIR, safe_folder_name(video_name))


def get_video_csv_path(video_output_dir):
    return os.path.join(video_output_dir, "classification_result.csv")


def imread_image(path):
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_image(path, image):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ext = os.path.splitext(path)[1] or ".jpg"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        return False
    try:
        with open(path, "wb") as f:
            f.write(encoded.tobytes())
        return True
    except Exception as e:
        try:
            if cv2.imwrite(path, image):
                return True
        except Exception:
            pass
        print(f"寫入圖片失敗: {path} | {e}")
        return False


def read_sample_frames(video_path, sample_count=80):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []

    indices = np.linspace(0, max(0, total - 1), min(sample_count, total)).astype(int)
    frames = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)

    cap.release()
    return frames


def write_csv_header(csv_path):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "video_name", "frame_idx", "final_category", "diff_score",
                "blur_score", "top_score", "feature_subtype", "feature_subtype_scores",
                "ocr_items", "category_scores", "matched_keywords", "roi", "save_path",
                "confidence_level", "confidence_score",
            ])


def append_csv_row(csv_path, row):
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def prepare_output_dirs(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for cat in CATEGORIES + ["low_score"]:
        os.makedirs(os.path.join(output_dir, cat), exist_ok=True)
