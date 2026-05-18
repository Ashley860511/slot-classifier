import argparse
import ast
import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

try:
    from ..config import OUTPUT_DIR
except ImportError:
    from config import OUTPUT_DIR


CATEGORIES = [
    "loading",
    "Basegame",
    "Transition",
    "Feature game",
    "Feature Buy",
    "BigWin",
    "Result",
    "Help",
]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IGNORE_TITLE_WORDS = {
    "chatgpt", "gitlab", "demogame", "home", "figma", "notion",
    "loading", "game", "pgsoft", "pocket", "games", "soft",
}

BIGWIN_TIERS = [
    ("super mega win", "Super Mega Win"),
    ("jumbo win", "Jumbo Win"),
    ("super win", "Super Win"),
    ("mega win", "Mega Win"),
    ("big win", "Big Win"),
    ("huge win", "Huge Win"),
    ("massive win", "Massive Win"),
    ("epic win", "Epic Win"),
]


def parse_obj(text, default):
    try:
        return ast.literal_eval(text)
    except Exception:
        return default


def normalize_text(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def image_files(folder):
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def load_rows(video_dir):
    csv_path = video_dir / "classification_result.csv"
    rows = []
    by_name = {}
    if not csv_path.exists():
        return rows, by_name
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
            save_name = Path(row.get("save_path", "")).name
            if save_name:
                by_name[save_name] = row
    return rows, by_name


def row_ocr_items(row):
    items = parse_obj(row.get("ocr_items", "[]"), [])
    normalized = []
    for item in items or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            text = str(item[0]).strip()
            try:
                score = float(item[1])
            except Exception:
                score = 0.0
            if text:
                normalized.append({"text": text, "score": score})
    return normalized


def row_text(row):
    return " ".join(item["text"] for item in row_ocr_items(row))


def collect_category_images(video_dir, rows_by_name):
    data = {}
    for category in CATEGORIES:
        entries = []
        for path in image_files(video_dir / category):
            row = rows_by_name.get(path.name, {})
            entries.append({
                "filename": path.name,
                "path": path,
                "relative_path": path.relative_to(video_dir).as_posix(),
                "ocr_text": row_text(row),
                "csv_category": row.get("final_category", category),
                "top_score": row.get("top_score", ""),
            })
        data[category] = entries
    return data


def infer_game_title(rows):
    candidates = []
    for row in rows[:80]:
        for item in row_ocr_items(row):
            raw = item["text"].strip()
            norm = normalize_text(raw)
            if not raw or len(raw) < 3:
                continue
            if any(word in norm for word in IGNORE_TITLE_WORDS):
                continue
            if re.search(r"\d", raw):
                continue
            if item["score"] < 0.65:
                continue
            candidates.append(raw)
    if not candidates:
        return "Unknown Game"
    return Counter(candidates).most_common(1)[0][0]


def detect_bigwin_tier(text):
    compact = normalize_text(text)
    compact_joined = compact.replace(" ", "")
    for phrase, label in BIGWIN_TIERS:
        key = phrase.replace(" ", "")
        if key in compact_joined:
            return label
    return "BigWin"


def unique_lines(texts, limit=30):
    seen = set()
    lines = []
    for text in texts:
        for part in re.split(r"[\n\r]+| {2,}", text):
            cleaned = re.sub(r"\s+", " ", str(part)).strip()
            key = normalize_text(cleaned)
            if len(key) < 4 or key in seen:
                continue
            seen.add(key)
            lines.append(cleaned)
            if len(lines) >= limit:
                return lines
    return lines


def infer_mechanics(category_data):
    all_help_text = " ".join(item["ocr_text"] for item in category_data.get("Help", []))
    all_feature_text = " ".join(item["ocr_text"] for item in category_data.get("Feature game", []))
    all_text = normalize_text(f"{all_help_text} {all_feature_text}")
    mechanics = []

    if "free spin" in all_text or "free game" in all_text:
        mechanics.append("Free game / free spins mode is present.")
    if "remaining" in all_text or "left" in all_text or "last free" in all_text:
        mechanics.append("Feature-game progress is shown with remaining/left/last spin UI.")
    if "multiplier" in all_text or re.search(r"x\s*\d+", all_text):
        mechanics.append("Multiplier mechanic is likely part of the feature or base flow.")
    if "wild" in all_text:
        mechanics.append("Wild symbols are important to the rules.")
    if "scatter" in all_text:
        mechanics.append("Scatter symbols are used as trigger or paytable symbols.")
    if "buy feature" in all_text or "feature buy" in all_text:
        mechanics.append("Feature Buy / Buy Feature entry is present.")
    if "paytable" in all_text or "payout" in all_text:
        mechanics.append("Help pages include paytable or payout explanation.")

    return mechanics


def build_analysis(video_dir):
    rows, rows_by_name = load_rows(video_dir)
    category_data = collect_category_images(video_dir, rows_by_name)

    bigwins = []
    for item in category_data.get("BigWin", []):
        tier = detect_bigwin_tier(item["ocr_text"])
        bigwins.append({**item, "tier": tier})

    help_lines = unique_lines(
        [item["ocr_text"] for item in category_data.get("Help", [])],
        limit=80,
    )

    analysis = {
        "video": video_dir.name,
        "game_title": infer_game_title(rows),
        "source": {
            "video_output_dir": str(video_dir),
            "csv": str(video_dir / "classification_result.csv"),
            "existing_flowchart": str(video_dir / "flowchart.html")
            if (video_dir / "flowchart.html").exists() else None,
        },
        "category_counts": {
            category: len(items)
            for category, items in category_data.items()
        },
        "representative_images": {
            category: [item["relative_path"] for item in items[:6]]
            for category, items in category_data.items()
        },
        "bigwin_tiers": [
            {
                "tier": item["tier"],
                "image": item["relative_path"],
                "ocr_text": item["ocr_text"],
            }
            for item in bigwins[:12]
        ],
        "help_text_lines": help_lines,
        "mechanics_summary": infer_mechanics(category_data),
    }
    return analysis


def write_json(video_dir, analysis):
    out = video_dir / "gameplay_analysis.json"
    out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_markdown(video_dir, analysis):
    out = video_dir / "gameplay_analysis.md"
    lines = [
        f"# {analysis['game_title']} Gameplay Analysis",
        "",
        f"- Video folder: `{analysis['video']}`",
        f"- Existing Claude flowchart: `{analysis['source']['existing_flowchart'] or 'none'}`",
        "",
        "## Category Counts",
        "",
    ]
    for category, count in analysis["category_counts"].items():
        lines.append(f"- {category}: {count}")

    lines.extend(["", "## Mechanics Summary", ""])
    for item in analysis["mechanics_summary"] or ["No automatic mechanics summary detected."]:
        lines.append(f"- {item}")

    lines.extend(["", "## BigWin Tiers", ""])
    for item in analysis["bigwin_tiers"]:
        lines.append(f"- {item['tier']}: `{item['image']}`")

    lines.extend(["", "## Help OCR Lines", ""])
    for line in analysis["help_text_lines"][:80]:
        lines.append(f"- {line}")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def image_tag(path, cls="thumb"):
    return f'<img class="{cls}" src="{html.escape(path)}" alt="">'


def write_html(video_dir, analysis):
    out = video_dir / "flowchart_auto.html"
    cards = []
    card_order = [
        ("loading", "Loading"),
        ("Basegame", "BaseGame"),
        ("Transition", "Transition"),
        ("Feature game", "FreeGame"),
        ("Feature Buy", "Feature Buy"),
        ("BigWin", "BigWin"),
        ("Result", "Result"),
        ("Help", "Help / Paytable"),
    ]
    reps = analysis["representative_images"]
    for key, label in card_order:
        imgs = reps.get(key, [])[:3]
        if not imgs:
            continue
        images_html = "\n".join(image_tag(path) for path in imgs)
        cards.append(f"""
        <section class="card">
          <h2>{html.escape(label)}</h2>
          <div class="images">{images_html}</div>
        </section>
        """)

    bigwin_rows = []
    for item in analysis["bigwin_tiers"][:6]:
        bigwin_rows.append(
            f'<li><b>{html.escape(item["tier"])}</b><br><code>{html.escape(item["image"])}</code></li>'
        )

    help_lines = "\n".join(
        f"<li>{html.escape(line)}</li>"
        for line in analysis["help_text_lines"][:24]
    )
    mechanics = "\n".join(
        f"<li>{html.escape(item)}</li>"
        for item in analysis["mechanics_summary"]
    )

    doc = f"""<!doctype html>
<html lang="zh-TW">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(analysis['game_title'])} Auto Flowchart</title>
  <style>
    body {{ margin: 0; padding: 28px; font-family: Arial, sans-serif; background: #f3f1ed; color: #252525; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 6px; font-size: 28px; }}
    .sub {{ color: #666; font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }}
    .card {{ background: #fff; border: 1px solid #ddd5ca; border-radius: 10px; padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,.05); }}
    .card h2 {{ margin: 0 0 10px; font-size: 15px; color: #157347; }}
    .images {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .thumb {{ width: 92px; height: 136px; object-fit: cover; border-radius: 6px; border: 1px solid #ddd; background: #eee; }}
    .panel {{ margin-top: 18px; background: #fff; border: 1px solid #ddd5ca; border-radius: 10px; padding: 16px; }}
    .panel h2 {{ margin: 0 0 10px; font-size: 17px; }}
    li {{ margin: 5px 0; line-height: 1.4; }}
    code {{ font-size: 11px; color: #555; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(analysis['game_title'])}</h1>
    <div class="sub">Auto-generated from classified screenshots and OCR. Existing Claude flowchart is preserved separately.</div>
  </header>
  <main>
    <div class="grid">
      {''.join(cards)}
    </div>
    <section class="panel">
      <h2>Mechanics Summary</h2>
      <ul>{mechanics or '<li>No automatic mechanics summary detected.</li>'}</ul>
    </section>
    <section class="panel">
      <h2>BigWin Candidates</h2>
      <ul>{''.join(bigwin_rows) or '<li>No BigWin images found.</li>'}</ul>
    </section>
    <section class="panel">
      <h2>Help OCR Highlights</h2>
      <ul>{help_lines or '<li>No Help OCR lines found.</li>'}</ul>
    </section>
  </main>
</body>
</html>
"""
    out.write_text(doc, encoding="utf-8")
    return out


def export_video(video_dir):
    analysis = build_analysis(video_dir)
    return {
        "json": write_json(video_dir, analysis),
        "markdown": write_markdown(video_dir, analysis),
        "html": write_html(video_dir, analysis),
    }


def discover_video_dirs(output_root, video=None):
    output_root = Path(output_root)
    if video is not None:
        target = output_root / str(video)
        return [target] if target.exists() else []
    return [
        path for path in sorted(output_root.iterdir(), key=lambda p: p.name)
        if path.is_dir() and (path / "classification_result.csv").exists()
    ]


def main():
    parser = argparse.ArgumentParser(description="Export gameplay analysis files from classified screenshot folders.")
    parser.add_argument("--output-root", default=OUTPUT_DIR, help="Root folder containing per-video output folders.")
    parser.add_argument("--video", default=None, help="Only export one video folder, e.g. 8.")
    args = parser.parse_args()

    video_dirs = discover_video_dirs(args.output_root, args.video)
    if not video_dirs:
        print("No video output folders found.")
        return

    for video_dir in video_dirs:
        outputs = export_video(video_dir)
        print(f"[{video_dir.name}] analysis exported")
        for kind, path in outputs.items():
            print(f"  {kind}: {path}")


if __name__ == "__main__":
    main()

