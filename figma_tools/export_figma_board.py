import argparse
import ast
import csv
import json
import re
import shutil
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PACKAGE_ROOT / "project" / "output"
DEFAULT_EXPORT_DIR = PACKAGE_ROOT / "figma_export"

COLUMNS = [
    {"key": "loading", "label": "LOADING", "count": 1},
    {"key": "Basegame", "label": "BaseGame", "count": 1},
    {"key": "Transition", "label": "Transition", "count": 1},
    {"key": "Feature game", "label": "FreeGame", "count": 1},
    {"key": "Feature Buy", "label": "BUY FEATURE", "count": 1},
    {"key": "Result", "label": "Result", "count": 1},
    {"key": "BigWin", "label": "BigWin I", "count": 1},
    {"key": "BigWin", "label": "BigWin II", "count": 1},
    {"key": "BigWin", "label": "BigWin III", "count": 1},
]

SINGLE_CATEGORY_SLOTS = {
    "loading": "loading",
    "Basegame": "basegame",
    "Transition": "transition",
    "Feature game": "featuregame",
    "Feature Buy": "featurebuy",
    "Result": "result",
}

CATEGORY_FOLDER_ALIASES = {
    "Feature Buy": ["FeatureBuy", "Feature Buy", "FeatrueBuy"],
}

BIGWIN_WORDS = [
    "big win", "bigwin", "mega win", "megawin", "super mega win", "supermegawin",
    "super win", "superwin", "superiwin", "jumbo win", "jumbowin", "jumbo loin",
    "huge win", "hugewin", "massive win", "massivewin", "epic win", "epicwin",
]

FEATURE_WORDS = [
    "remaining free spin", "remaining free spins", "free spin remaining",
    "free spins remaining", "last free spin", "last free spins",
]
LOADING_COVER_VENDOR_TERMS = [
    "pg soft", "pgsoft", "pocket games soft", "rights reserved",
    "licensed", "license", "certified", "mga", "bmm", "testlabs",
]
LOADING_COVER_MARKETING_TERMS = [
    "featuring", "free spin", "free spins", "wild symbol", "wild symbols",
    "multiplier", "multipliers", "loading game", "downloading",
]


def parse_obj(text, default):
    try:
        return ast.literal_eval(text)
    except Exception:
        return default


def normalize_text(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    compact = text.replace(" ", "")
    aliases = {
        "bigwin": "big win",
        "megawin": "mega win",
        "megawiy": "mega win",
        "megawily": "mega win",
        "megawiry": "mega win",
        "supermegawin": "super mega win",
        "superiwin": "super win",
        "jumbowin": "jumbo win",
        "jumboloin": "jumbo win",
        "freespin": "free spin",
        "freespins": "free spins",
    }
    extra = [value for key, value in aliases.items() if key in compact]
    if extra:
        text = f"{text} {' '.join(extra)}"
    return text


def normalize_phrase(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ocr_joined_text(row):
    items = parse_obj(row.get("ocr_items", "[]"), [])
    parts = []
    for item in items or []:
        if isinstance(item, (list, tuple)) and item:
            parts.append(str(item[0]))
        else:
            parts.append(str(item))
    return normalize_text(" ".join(parts))


def compact_contains(text, phrases):
    compact = text.replace(" ", "")
    return any(normalize_phrase(p).replace(" ", "") in compact for p in phrases)


def is_bigwin_text(text):
    return compact_contains(text, BIGWIN_WORDS)


def is_loading_cover_text(text):
    compact = text.replace(" ", "")
    has_vendor_footer = compact_contains(text, LOADING_COVER_VENDOR_TERMS)
    if not has_vendor_footer:
        return False

    has_loading_text = compact_contains(text, [
        "loading", "loading game", "downloading", "download over", "download over wi fi",
    ])
    has_cover_marketing = compact_contains(text, LOADING_COVER_MARKETING_TERMS)
    has_rules_or_paytable = compact_contains(text, [
        "paytable", "pay table", "payout values", "game rules", "how to play",
        "during any spin", "during any spins", "scatter symbol", "reels",
    ])
    return (has_loading_text or has_cover_marketing or "rightsreserved" in compact) and not has_rules_or_paytable


def bigwin_tier(text):
    compact = text.replace(" ", "")
    if "supermegawin" in compact or ("super" in compact and "mega" in compact and "win" in compact):
        return 4
    if "jumbowin" in compact or "jumbo" in compact:
        return 3
    if "megawin" in compact or "mega" in compact:
        return 2
    if "superwin" in compact or "super" in compact:
        return 1
    return 0


def score_dict(row):
    parsed = parse_obj(row.get("category_scores", "{}"), {})
    return parsed if isinstance(parsed, dict) else {}


def find_image(video_dir, save_path):
    direct = Path(save_path)
    if direct.exists():
        return direct

    name = direct.name
    if not name:
        return None

    matches = [
        path for path in video_dir.rglob(name)
        if "_debug" not in path.parts and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    if not matches:
        return None

    # Prefer final folders over low_score when both exist.
    matches.sort(key=lambda p: ("low_score" in p.parts, len(p.parts)))
    return matches[0]


def float_value(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def frame_index(path):
    match = re.search(r"_frame_(\d+)", path.name)
    if not match:
        return 10**12
    return int(match.group(1))


def loading_cover_rank(text):
    if compact_contains(text, ["loading game"]):
        return 0
    if compact_contains(text, ["loading", "downloading", "download over", "download over wi fi"]):
        return 1
    if is_loading_cover_text(text):
        return 2
    return 3


def representative_score(row, image_path, category, text):
    scores = score_dict(row)
    top = float_value(row.get("top_score"))
    blur = float_value(row.get("blur_score"))
    base_ui = float_value(scores.get("BasegameUI"))
    feature_ui = float_value(scores.get("FeatureUI"))
    bigwin_keep = float_value(scores.get("BigWinKeep"))
    feature_obstruction = float_value(scores.get("FeatureObstruction"))

    low_score_penalty = 6.0 if "low_score" in image_path.parts else 0.0
    score = top + min(6.0, blur / 700.0) - low_score_penalty

    if category == "Basegame":
        score += base_ui * 5.0
        if compact_contains(text, FEATURE_WORDS):
            score -= 10.0
        if is_bigwin_text(text):
            score -= 30.0
    elif category == "loading":
        if is_loading_cover_text(text):
            score += 40.0
    elif category == "Feature game":
        score += feature_ui * 6.0
        score -= feature_obstruction * 4.0
        if is_bigwin_text(text):
            score -= 40.0
    elif category == "BigWin":
        score += bigwin_keep * 4.0
        score += bigwin_tier(text) * 6.0
        if not is_bigwin_text(text):
            # Manual review may move a correct BigWin from low_score into the final
            # BigWin folder even when OCR missed the label. Trust final folders more
            # than CSV text for the Figma research board.
            score -= 6.0 if image_path.parent.name == "BigWin" else 40.0
    elif category == "Transition":
        score += float_value(scores.get("Transition")) * 0.35
    elif category == "Feature Buy":
        score += float_value(scores.get("Feature Buy")) * 0.6
        if compact_contains(text, FEATURE_WORDS):
            score -= 8.0
    elif category == "Help":
        score += float_value(scores.get("Help")) * 0.6
        score += float_value(scores.get("HelpQuality")) * 0.4
    elif category == "Result":
        score += float_value(scores.get("Result")) * 0.5
    elif category == "loading":
        score += float_value(scores.get("loading")) * 0.5

    return round(score, 3)


def load_csv_rows_by_name(video_dir):
    csv_path = video_dir / "classification_result.csv"
    if not csv_path.exists():
        return {}

    rows = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            save_path = Path(row.get("save_path", ""))
            if save_path.name:
                rows[save_path.name] = row
    return rows


def image_files(folder):
    if not folder.exists():
        return []
    return sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )


def category_folders(video_dir, category):
    names = CATEGORY_FOLDER_ALIASES.get(category, [category])
    folders = []
    for name in names:
        folder = video_dir / name
        if folder.exists():
            folders.append(folder)
    return folders


def load_video_candidates(video_dir):
    rows_by_name = load_csv_rows_by_name(video_dir)
    candidates = []
    seen = set()

    for category in SINGLE_CATEGORY_SLOTS.keys():
        paths = []
        for folder in category_folders(video_dir, category):
            paths.extend(image_files(folder))
        if not paths:
            for folder_name in CATEGORY_FOLDER_ALIASES.get(category, [category]):
                paths.extend(image_files(video_dir / "low_score" / folder_name))

        for image_path in paths:
            if image_path.name in seen:
                continue
            seen.add(image_path.name)
            row = rows_by_name.get(image_path.name, {})
            text = ocr_joined_text(row)
            candidates.append({
                "row": row,
                "image_path": image_path,
                "category": category,
                "text": text,
            })

    for folder in [video_dir / "Help", video_dir / "low_score" / "Help"]:
        for image_path in image_files(folder):
            if image_path.name in seen:
                continue
            row = rows_by_name.get(image_path.name, {})
            text = ocr_joined_text(row)
            if not is_loading_cover_text(text):
                continue
            seen.add(image_path.name)
            candidates.append({
                "row": row,
                "image_path": image_path,
                "category": "loading",
                "text": text,
            })

    for image_path in image_files(video_dir / "BigWin"):
        if image_path.name in seen:
            continue
        seen.add(image_path.name)
        row = rows_by_name.get(image_path.name, {})
        candidates.append({
            "row": row,
            "image_path": image_path,
            "category": "BigWin",
            "text": ocr_joined_text(row),
        })

    return candidates


def choose_one(candidates, category):
    pool = [item for item in candidates if item["category"] == category]
    if category == "Feature game":
        pool = [item for item in pool if not is_bigwin_text(item["text"])]
    if not pool:
        return None
    if category == "loading":
        pool.sort(
            key=lambda item: (
                not is_loading_cover_text(item["text"]),
                loading_cover_rank(item["text"]),
                frame_index(item["image_path"]),
                -representative_score(item["row"], item["image_path"], category, item["text"]),
            )
        )
        return pool[0]
    pool.sort(
        key=lambda item: representative_score(item["row"], item["image_path"], category, item["text"]),
        reverse=True,
    )
    return pool[0]


def choose_bigwins(candidates, limit=3):
    pool = [
        item for item in candidates
        if item["category"] == "BigWin" or (item["category"] != "Other" and is_bigwin_text(item["text"]))
    ]
    pool.sort(
        key=lambda item: (
            bigwin_tier(item["text"]),
            representative_score(item["row"], item["image_path"], "BigWin", item["text"]),
        ),
        reverse=True,
    )

    picks = []
    used_tiers = set()
    used_names = set()
    for item in pool:
        tier = bigwin_tier(item["text"])
        if tier in used_tiers and len(used_tiers) < limit:
            continue
        if item["image_path"].name in used_names:
            continue
        picks.append(item)
        used_tiers.add(tier)
        used_names.add(item["image_path"].name)
        if len(picks) >= limit:
            return picks

    for item in pool:
        if len(picks) >= limit:
            break
        if item["image_path"].name in used_names:
            continue
        picks.append(item)
        used_names.add(item["image_path"].name)
    return picks


def copy_item(item, export_images_dir, video_name, slot_key):
    suffix = item["image_path"].suffix.lower() or ".jpg"
    safe_video = re.sub(r"[^a-zA-Z0-9_-]+", "_", video_name)
    safe_slot = re.sub(r"[^a-zA-Z0-9_-]+", "_", slot_key)
    filename = f"video_{safe_video}_{safe_slot}{suffix}"
    dst = export_images_dir / filename
    shutil.copy2(item["image_path"], dst)
    return f"images/{filename}"


def build_export(output_root, export_dir):
    export_images_dir = export_dir / "images"
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_images_dir.mkdir(parents=True, exist_ok=True)

    video_dirs = [
        path for path in sorted(output_root.iterdir(), key=lambda p: p.name)
        if path.is_dir() and (path / "classification_result.csv").exists()
    ]

    manifest_videos = []
    for video_dir in video_dirs:
        candidates = load_video_candidates(video_dir)
        item_map = {}
        debug_selection = {}

        for category, slot_key in SINGLE_CATEGORY_SLOTS.items():
            chosen = choose_one(candidates, category)
            if not chosen:
                continue
            item_map[slot_key] = {
                "src": copy_item(chosen, export_images_dir, video_dir.name, slot_key),
                "source": str(chosen["image_path"]),
                "score": representative_score(chosen["row"], chosen["image_path"], category, chosen["text"]),
            }
            debug_selection[slot_key] = item_map[slot_key]

        bigwins = []
        for idx, chosen in enumerate(choose_bigwins(candidates, limit=3), start=1):
            slot_key = f"bigwin_{idx}"
            bigwins.append({
                "src": copy_item(chosen, export_images_dir, video_dir.name, slot_key),
                "source": str(chosen["image_path"]),
                "tier": bigwin_tier(chosen["text"]),
                "score": representative_score(chosen["row"], chosen["image_path"], "BigWin", chosen["text"]),
            })
        item_map["bigwins"] = bigwins
        debug_selection["bigwins"] = bigwins

        manifest_videos.append({
            "id": video_dir.name,
            "label": f"Video {video_dir.name}",
            "items": item_map,
        })

    manifest = {
        "title": "Slot Game Screen Research Board",
        "subtitle": "Auto-selected classified screenshots for art production research. Other is omitted.",
        "columns": [
            {"key": "loading", "label": "LOADING"},
            {"key": "basegame", "label": "BaseGame"},
            {"key": "transition", "label": "Transition"},
            {"key": "featuregame", "label": "FreeGame"},
            {"key": "featurebuy", "label": "BUY FEATURE"},
            {"key": "result", "label": "Result"},
            {"key": "bigwin_1", "label": "BigWin I"},
            {"key": "bigwin_2", "label": "BigWin II"},
            {"key": "bigwin_3", "label": "BigWin III"},
        ],
        "videos": manifest_videos,
        "layout": {
            "thumbWidth": 180,
            "thumbHeight": 270,
            "columnGap": 70,
            "rowGap": 90,
        },
    }

    (export_dir / "figma_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    instructions = (
        "# Figma import package\n\n"
        "1. Open Figma or FigJam.\n"
        "2. Run the local plugin in `figma_plugin`.\n"
        "3. Choose this whole `figma_export` folder when prompted.\n"
        "4. The plugin reads `figma_manifest.json` and places each image as a separate editable node.\n"
    )
    (export_dir / "README.md").write_text(instructions, encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Export classified slot screenshots for the Figma research-board plugin.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Folder containing per-video classification output.")
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR), help="Destination folder for manifest and copied images.")
    args = parser.parse_args()

    manifest = build_export(Path(args.output_root), Path(args.export_dir))
    export_dir = Path(args.export_dir)
    print(f"Exported {len(manifest['videos'])} video rows.")
    print(f"Manifest: {export_dir / 'figma_manifest.json'}")
    print(f"Images:   {export_dir / 'images'}")


if __name__ == "__main__":
    main()
