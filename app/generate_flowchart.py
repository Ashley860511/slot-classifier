#!/usr/bin/env python3
"""
generate_flowchart.py — AI-powered slot game flow diagram generator.

For each classified video in project/output/<id>/, reads category screenshots
and Help pages, asks Claude to analyse game mechanics AND determine the flow
architecture, then writes a self-contained HTML flowchart.

Usage:
    python generate_flowchart.py                      # all videos
    python generate_flowchart.py --video-id 0         # single video
    python generate_flowchart.py --no-ai              # images only, skip AI
    python generate_flowchart.py --api-key sk-...     # explicit API key
    python generate_flowchart.py --output-root PATH   # custom output root
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PACKAGE_ROOT / "project" / "output"

CATEGORIES = [
    "loading", "Basegame", "Feature Buy",
    "Feature game", "Transition", "BigWin", "Result", "Help", "Other",
]


# ─── Image helpers ────────────────────────────────────────────────────────────

def collect_images(video_dir: Path, max_per: int = 6) -> dict:
    """Return up to max_per images per category (sorted by name)."""
    out = {}
    for cat in CATEGORIES:
        d = video_dir / cat
        out[cat] = sorted(d.glob("*.jpg"))[:max_per] if d.exists() else []
    return out


def b64_encode(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode()


# ─── AI analysis ─────────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """\
You are analysing screenshots from a slot machine game to produce structured \
documentation of its mechanics and visual game flow.
Return ONLY valid JSON — no prose, no markdown fences, no extra keys.

Required schema (fill every field; use "" for unknown text, [] for unknown arrays):

{
  "game_name": "<best guess at the game title>",
  "game_theme": "<one-sentence visual theme>",

  "help_analysis": {
    "wild_symbol": "<wild symbol description or empty>",
    "scatter_symbol": "<scatter symbol description or empty>",
    "free_spins_trigger": "<what triggers free spins, or empty>",
    "free_spins_count": "<e.g. 10 free spins, or empty>",
    "retrigger": "<retrigger condition, or empty>",
    "special_features": ["<feature A>", "<feature B>"]
  },

  "states": {
    "<node_id>": "<2-3 line description of this game state>"
  },

  "flow_layout": {
    "rows": [
      {
        "label": "<row label, e.g. Base Game Path>",
        "dark": false,
        "nodes": [
          {
            "id": "<unique_snake_case_id>",
            "label": "<display label in flowchart>",
            "category": "<folder name: loading|Basegame|Feature Buy|Feature game|Transition|BigWin|Result|Other>",
            "img_index": 0,
            "img_count": 1,
            "optional": false,
            "trigger": "<always|random|paid|condition>",
            "state_key": "<id of matching entry in states dict>"
          }
        ]
      }
    ]
  }
}

━━━ RULES FOR flow_layout ━━━

1. ANALYSE the Help screenshots to determine the ACTUAL game architecture before
   deciding the layout. Do not assume a default structure.

2. TRADITIONAL game (has Free Spins triggered by Scatter):
   Use TWO rows:
   - Row 1 (dark:false): Loading → BaseGame → [FeatureBuy] → BigWin tiers
   - Row 2 (dark:true):  Transition → FreeGame → [Retrigger] → BigWin(FG) → Result

3. NON-TRADITIONAL game (3×3 grid, no Free Spins, Respin-based, etc.):
   Use ONE row containing only the states that actually exist.
   Example single row: Loading → BaseGame → [RespiUntilWin] → BigWin

4. Each BigWin TIER (BIG WIN, MEGA WIN, SUPER MEGA WIN, JUMBO WIN …) is a
   SEPARATE node in the TOP row, with img_index 0, 1, 2 … to pick distinct images.
   In the bottom Free Game row, BigWin(FG) is ONE node (img_index:0) only.

5. Mark optional:true for nodes that are randomly triggered, paid, or require
   specific symbol conditions. Use:
   - trigger:"random"    — randomly activated during base game
   - trigger:"paid"      — player pays to activate (Buy Feature)
   - trigger:"condition" — requires specific symbols/combos
   - trigger:"always"    — mandatory state always reached in a session

6. The "category" value MUST exactly match one of the classifier folder names:
   loading | Basegame | Feature Buy | Feature game | Transition | BigWin | Result | Other

   The "Other" folder contains frames the classifier could not confidently assign to a
   standard category. This often means a non-traditional feature game (e.g. picking
   bonus, penalty kick game, wheel spin) whose UI differs from conventional Free Spins.
   When "Other" screenshots show an in-game bonus mode, use category:"Other" for those
   nodes in flow_layout. Do NOT use "Feature game" for content that came from the Other
   folder — the renderer loads images by folder name.

━━━ EXAMPLES ━━━

Non-traditional 3×3 (Respin Until Win, no Free Game):
"flow_layout": {"rows": [{"label":"Base Game Path","dark":false,"nodes":[
  {"id":"loading","label":"Loading","category":"loading","img_index":0,"img_count":1,"optional":false,"trigger":"always","state_key":"loading"},
  {"id":"basegame","label":"Base Game","category":"Basegame","img_index":0,"img_count":2,"optional":false,"trigger":"always","state_key":"basegame"},
  {"id":"respin","label":"Respin Until Win","category":"Feature game","img_index":0,"img_count":1,"optional":true,"trigger":"random","state_key":"respin"},
  {"id":"bigwin","label":"Big Win","category":"BigWin","img_index":0,"img_count":1,"optional":false,"trigger":"condition","state_key":"bigwin"}
]}]}

Traditional 5-reel with Free Spins and 3 BigWin tiers:
"flow_layout": {"rows": [
  {"label":"Base Game Path","dark":false,"nodes":[
    {"id":"loading","label":"Loading","category":"loading","img_index":0,"img_count":1,"optional":false,"trigger":"always","state_key":"loading"},
    {"id":"basegame","label":"Base Game","category":"Basegame","img_index":0,"img_count":2,"optional":false,"trigger":"always","state_key":"basegame"},
    {"id":"feature_buy","label":"Buy Feature","category":"Feature Buy","img_index":0,"img_count":1,"optional":true,"trigger":"paid","state_key":"feature_buy"},
    {"id":"bigwin_1","label":"BIG WIN","category":"BigWin","img_index":0,"img_count":1,"optional":false,"trigger":"condition","state_key":"bigwin_1"},
    {"id":"bigwin_2","label":"MEGA WIN","category":"BigWin","img_index":1,"img_count":1,"optional":false,"trigger":"condition","state_key":"bigwin_2"},
    {"id":"bigwin_3","label":"SUPER MEGA WIN","category":"BigWin","img_index":2,"img_count":1,"optional":false,"trigger":"condition","state_key":"bigwin_3"}
  ]},
  {"label":"Free Game Path","dark":true,"nodes":[
    {"id":"transition","label":"Transition","category":"Transition","img_index":0,"img_count":1,"optional":false,"trigger":"always","state_key":"transition"},
    {"id":"freegame","label":"Free Game","category":"Feature game","img_index":0,"img_count":2,"optional":false,"trigger":"always","state_key":"freegame"},
    {"id":"retrigger","label":"Retrigger","category":"Feature game","img_index":1,"img_count":1,"optional":true,"trigger":"condition","state_key":"retrigger"},
    {"id":"bigwin_fg","label":"Big Win (FG)","category":"BigWin","img_index":0,"img_count":1,"optional":false,"trigger":"condition","state_key":"bigwin_fg"},
    {"id":"result","label":"Total Win","category":"Result","img_index":0,"img_count":1,"optional":false,"trigger":"always","state_key":"result"}
  ]}
]}
"""


def analyse_with_claude(api_key: str, images: dict) -> dict:
    try:
        import anthropic
    except ImportError:
        print("  anthropic package not installed — run: pip install anthropic")
        return {}

    client = anthropic.Anthropic(api_key=api_key)
    content = [{"type": "text", "text": ANALYSIS_PROMPT}]

    send_order = [
        ("Help",         5),
        ("loading",      2),
        ("Basegame",     2),
        ("Feature Buy",  2),
        ("Transition",   2),
        ("Feature game", 3),
        ("Other",        4),
        ("BigWin",       4),
        ("Result",       1),
    ]

    for cat, limit in send_order:
        imgs = images.get(cat, [])[:limit]
        if not imgs:
            continue
        content.append({"type": "text", "text": f"── {cat} screenshots ──"})
        for p in imgs:
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
        print(f"  Warning: JSON parse failed ({exc}). Using empty data.")
        return {}


# ─── Fallback layout (no-AI mode) ────────────────────────────────────────────

def _build_fallback_layout(images: dict, ai_data: dict) -> dict:
    """
    Infer a basic flow_layout from which category folders contain images.
    Used when AI analysis is skipped or fails.
    """
    has = {cat: bool(imgs) for cat, imgs in images.items()}
    bw_imgs  = images.get("BigWin", [])
    bw_tiers = (ai_data.get("help_analysis") or {}).get("bigwin_tiers") or ["Big Win"]

    # ── Top row ───────────────────────────────────────────────────────────────
    top = []
    if has["loading"]:
        top.append({"id": "loading", "label": "Loading", "category": "loading",
                    "img_index": 0, "img_count": 1,
                    "optional": False, "trigger": "always", "state_key": "loading"})
    top.append({"id": "basegame", "label": "Base Game", "category": "Basegame",
                "img_index": 0, "img_count": 2,
                "optional": False, "trigger": "always", "state_key": "basegame"})
    if has["Feature Buy"]:
        top.append({"id": "feature_buy", "label": "Buy Feature", "category": "Feature Buy",
                    "img_index": 0, "img_count": 1,
                    "optional": True, "trigger": "paid", "state_key": "feature_buy"})

    # BigWin tiers in top row
    n_tiers = min(len(bw_tiers), max(1, len(bw_imgs)))
    for i, tier in enumerate(bw_tiers[:n_tiers]):
        top.append({"id": f"bigwin_{i+1}", "label": tier, "category": "BigWin",
                    "img_index": i, "img_count": 1,
                    "optional": False, "trigger": "condition", "state_key": f"bigwin_{i+1}"})

    rows = [{"label": "Base Game Path", "dark": False, "nodes": top}]

    # ── Bottom row (Feature game OR Other-based bonus) ───────────────────────
    has_feature = has["Feature game"] or has["Other"]
    feature_cat = "Feature game" if has["Feature game"] else "Other"
    feature_label = "Free Game" if has["Feature game"] else "Feature Game"

    if has_feature:
        btm = []
        if has["Transition"]:
            btm.append({"id": "transition", "label": "Transition", "category": "Transition",
                        "img_index": 0, "img_count": 1,
                        "optional": False, "trigger": "always", "state_key": "transition"})
        btm.append({"id": "featuregame", "label": feature_label, "category": feature_cat,
                    "img_index": 0, "img_count": 2,
                    "optional": False, "trigger": "always", "state_key": "featuregame"})
        if has["BigWin"]:
            btm.append({"id": "bigwin_fg", "label": "Big Win (FG)", "category": "BigWin",
                        "img_index": 0, "img_count": 1,
                        "optional": False, "trigger": "condition", "state_key": "bigwin_fg"})
        if has["Result"]:
            btm.append({"id": "result", "label": "Total Win", "category": "Result",
                        "img_index": 0, "img_count": 1,
                        "optional": False, "trigger": "always", "state_key": "result"})
        rows.append({"label": "Free Game Path", "dark": True, "nodes": btm})

    return {"rows": rows}


# ─── HTML CSS ─────────────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #e8e8e8;
  font-family: 'Segoe UI', Arial, sans-serif;
  padding: 28px 32px;
}
h1 { font-size: 20px; font-weight: 700; color: #222; margin-bottom: 4px; }
.subtitle { font-size: 12px; color: #999; margin-bottom: 22px; }

/* ── layout ── */
.diagram { display: flex; flex-direction: column; gap: 16px; min-width: 900px; }

.row-label {
  font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #aaa; margin-bottom: 4px; padding-left: 2px;
}
.flow-row {
  display: flex; flex-direction: row; align-items: flex-start;
  gap: 0; flex-wrap: nowrap; overflow-x: auto;
  padding: 14px 16px 14px;
  background: white;
  border-radius: 10px;
  border: 1.5px solid #e0e0e0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.flow-row.row-dark {
  background: #1e1e2e;
  border-color: #3a3a5c;
}

.arr-h {
  display: flex; align-items: center; padding-top: 24px;
  color: #bbb; font-size: 22px; width: 30px; flex-shrink: 0;
  justify-content: center;
}
.row-dark .arr-h { color: #555; }

/* ── nodes ── */
.node {
  background: white;
  border-radius: 10px;
  border: 1.5px solid #e0e0e0;
  padding: 10px 10px 12px;
  min-width: 136px;
  max-width: 180px;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
}
.node.optional { border-style: dashed; }
.node.purple { border-color: #b89edf; background: #f8f5ff; }
.node.blue   { border-color: #84b8df; background: #f4f9ff; }
.node.orange { border-color: #f0a060; background: #fff8f0; }
.node.gray   { border-color: #c8c8c8; background: #f8f8f8; }
.node.dark   { border-color: #3a3a5c; background: #252535; color: #ccc; }

.node-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.6px; color: #888;
  margin-bottom: 7px; padding-bottom: 5px;
  border-bottom: 1px solid #eee;
}
.node.purple .node-title { color: #7c5cbf; border-color: #ddd0f8; }
.node.blue   .node-title { color: #2a7fbf; border-color: #c0d8f0; }
.node.orange .node-title { color: #c06000; border-color: #f0d0a0; }
.node.dark   .node-title { color: #9090c0; border-color: #3a3a5c; }

.thumbs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.thumb  { width: 58px; height: 90px; object-fit: cover; border-radius: 5px; border: 1px solid #e0e0e0; }
.no-thumb {
  width: 58px; height: 90px; background: #f0f0f0; border-radius: 5px;
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; color: #ccc;
}

.desc { font-size: 10px; color: #666; line-height: 1.45; }
.node.dark .desc { color: #aaa; }
.desc ul { padding-left: 13px; }
.desc li { margin-bottom: 2px; }

.tag { display: inline-block; font-size: 9px; border-radius: 3px; padding: 1px 5px; margin: 1px 2px 2px 0; }
.t-orange { background: #fff0e0; color: #c06000; }
.t-purple { background: #f0ebff; color: #7c5cbf; }
.t-blue   { background: #e8f3ff; color: #2a7fbf; }
.t-gray   { background: #f0f0f0; color: #888; }

/* ── info panel ── */
.info-panel {
  background: white;
  border-radius: 10px;
  border: 1.5px solid #ddd;
  padding: 12px 16px;
  margin-bottom: 20px;
  display: flex; gap: 18px; align-items: flex-start; flex-wrap: wrap;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.info-section h3 { font-size: 11px; color: #7c5cbf; font-weight: 700; margin-bottom: 8px; }
.info-section p, .info-section li { font-size: 10px; color: #555; line-height: 1.55; }
.info-section ul { padding-left: 13px; }
.help-thumbs { display: flex; gap: 6px; flex-wrap: wrap; }
.help-thumb { width: 72px; height: 110px; object-fit: cover; border-radius: 5px; border: 1px solid #e0e0e0; }
"""


# ─── HTML building blocks ─────────────────────────────────────────────────────

def _thumbs_html(imgs: list, out_html: Path, n: int = 2) -> str:
    parts = ['<div class="thumbs">']
    shown = imgs[:n]
    if not shown:
        parts.append('<div class="no-thumb">—</div>')
    for p in shown:
        rel = os.path.relpath(str(p), str(out_html.parent)).replace("\\", "/")
        parts.append(f'<img src="{rel}" class="thumb" loading="lazy" alt="">')
    parts.append("</div>")
    return "".join(parts)


def _tags(items: list, cls: str = "t-purple") -> str:
    return "".join(f'<span class="tag {cls}">{t}</span>' for t in items)


def _node(title: str, thumbs: str, desc: str, css_cls: str = "") -> str:
    c = f" {css_cls}" if css_cls else ""
    return (
        f'<div class="node{c}">'
        f'<div class="node-title">{title}</div>'
        f"{thumbs}"
        f'<div class="desc">{desc}</div>'
        "</div>"
    )


def _arr() -> str:
    return '<div class="arr-h">→</div>'


# ─── Flow renderer ────────────────────────────────────────────────────────────

_TRIGGER_TAG = {
    "random":    ("t-orange", "RANDOM"),
    "paid":      ("t-purple", "PAID"),
    "condition": ("t-blue",   "CONDITION"),
}

_CATEGORY_CSS = {
    "loading":      "gray",
    "Feature Buy":  "purple",
    "Feature game": "blue",
    "Transition":   "blue",
    "BigWin":       "orange",
    "Result":       "",
    "Basegame":     "",
    "Other":        "gray",
}


def _render_flow(flow_layout: dict, images: dict, states: dict, out_path: Path) -> str:
    """Render all rows in flow_layout to HTML string."""
    html_parts = []

    for row in flow_layout.get("rows", []):
        row_label   = row.get("label", "")
        dark        = row.get("dark", False)
        nodes_def   = row.get("nodes", [])

        node_parts = []
        for i, nd in enumerate(nodes_def):
            if i > 0:
                node_parts.append(_arr())

            node_id   = nd.get("id", f"node_{i}")
            label     = nd.get("label", node_id)
            category  = nd.get("category", "Basegame")
            img_idx   = nd.get("img_index", 0)
            img_cnt   = nd.get("img_count", 1)
            optional  = nd.get("optional", False)
            trigger   = nd.get("trigger", "always")
            state_key = nd.get("state_key", node_id)

            # Images
            cat_imgs  = images.get(category, [])
            node_imgs = cat_imgs[img_idx: img_idx + img_cnt]
            thumbs    = _thumbs_html(node_imgs, out_path, img_cnt)

            # Description from states dict
            desc = str(states.get(state_key) or "")

            # Prepend trigger badge (only for non-always)
            if trigger in _TRIGGER_TAG:
                cls, txt = _TRIGGER_TAG[trigger]
                badge = f'<span class="tag {cls}">{txt}</span>'
                desc  = (badge + "<br>" + desc) if desc else badge

            # CSS class: colour by category + optional dashed border
            base_css = _CATEGORY_CSS.get(category, "")
            if dark and not base_css:
                base_css = "dark"
            css_cls = (base_css + (" optional" if optional else "")).strip()

            node_parts.append(_node(label, thumbs, desc, css_cls))

        label_html  = f'<div class="row-label">{row_label}</div>' if row_label else ""
        row_cls     = "flow-row" + (" row-dark" if dark else "")
        row_html    = f'<div class="{row_cls}">' + "".join(node_parts) + "</div>"
        html_parts.append(label_html + row_html)

    return "\n".join(html_parts)


# ─── Main HTML builder ────────────────────────────────────────────────────────

def generate_html(video_dir: Path, ai_data: dict, out_path: Path):
    images = collect_images(video_dir)

    game_name   = ai_data.get("game_name")  or video_dir.name
    game_theme  = ai_data.get("game_theme") or ""
    h           = ai_data.get("help_analysis") or {}
    states      = ai_data.get("states")     or {}
    flow_layout = ai_data.get("flow_layout")

    # Fall back to auto-inferred layout if AI didn't provide one
    if not flow_layout or not flow_layout.get("rows"):
        flow_layout = _build_fallback_layout(images, ai_data)

    # ── Info panel ────────────────────────────────────────────────────────────
    help_thumbs_html = ""
    for p in images.get("Help", [])[:5]:
        rel = os.path.relpath(str(p), str(out_path.parent)).replace("\\", "/")
        help_thumbs_html += f'<img src="{rel}" class="help-thumb" loading="lazy" alt="">'

    mech_rows = []
    for key, label in [
        ("wild_symbol",       "Wild"),
        ("scatter_symbol",    "Scatter"),
        ("free_spins_trigger","Free spins trigger"),
        ("free_spins_count",  "Free spins"),
        ("retrigger",         "Retrigger"),
    ]:
        val = h.get(key, "")
        if val:
            mech_rows.append(f"<li><b>{label}:</b> {val}</li>")
    for feat in (h.get("special_features") or [])[:6]:
        mech_rows.append(f"<li>{feat}</li>")
    mech_html = "<ul>" + "".join(mech_rows) + "</ul>" if mech_rows else "<p>—</p>"

    info_panel = (
        '<div class="info-panel">'
        '<div class="info-section">'
        "<h3>Help / Paytable</h3>"
        f'<div class="help-thumbs">{help_thumbs_html}</div>'
        "</div>"
        '<div class="info-section" style="max-width:340px">'
        "<h3>Game Mechanics</h3>"
        f"{mech_html}"
        "</div>"
        "</div>"
    )

    # ── Flow diagram ──────────────────────────────────────────────────────────
    flow_html = _render_flow(flow_layout, images, states, out_path)

    # ── Compose final HTML ────────────────────────────────────────────────────
    sep = "　·　"
    subtitle = game_theme
    if game_theme:
        subtitle += sep
    subtitle += f"Video: {video_dir.name}"

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{game_name} — Game Flow</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{game_name}</h1>
<p class="subtitle">{subtitle}</p>
{info_panel}
<div class="diagram">
{flow_html}
</div>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    print(f"  Flowchart → {out_path}")


# ─── Entry point ──────────────────────────────────────────────────────────────

def find_video_dirs(root: Path) -> list:
    return [
        p for p in sorted(root.iterdir(), key=lambda x: x.name)
        if p.is_dir() and (p / "classification_result.csv").exists()
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Generate a slot game flow HTML diagram from classified screenshots."
    )
    parser.add_argument(
        "--output-root", default=str(DEFAULT_OUTPUT_ROOT),
        help="Root folder containing per-video classification output.",
    )
    parser.add_argument(
        "--video-id", default=None,
        help="Process only the video folder with this name, e.g. '0'.",
    )
    parser.add_argument(
        "--api-key", default=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="Anthropic API key (falls back to ANTHROPIC_API_KEY env var).",
    )
    parser.add_argument(
        "--no-ai", action="store_true",
        help="Skip Claude AI analysis; produce image-only flowchart.",
    )
    args = parser.parse_args()

    root = Path(args.output_root)
    if not root.exists():
        print(f"Output root not found: {root}")
        sys.exit(1)

    video_dirs = find_video_dirs(root)
    if args.video_id:
        video_dirs = [d for d in video_dirs if d.name == args.video_id]

    if not video_dirs:
        print("No classified video folders found (need classification_result.csv).")
        sys.exit(0)

    print(f"Found {len(video_dirs)} video folder(s).")

    for vdir in video_dirs:
        print(f"\n── {vdir.name} ──────────────────")
        images = collect_images(vdir)
        total_imgs = sum(len(v) for v in images.values())
        print(f"  Images: {total_imgs} across {sum(1 for v in images.values() if v)} categories")

        ai_data = {}
        if not args.no_ai:
            if not args.api_key:
                print("  No API key — skipping AI (use --api-key or ANTHROPIC_API_KEY).")
            else:
                print("  Calling Claude for game analysis...")
                ai_data = analyse_with_claude(args.api_key, images)
                if ai_data:
                    print(f"  Game:   {ai_data.get('game_name', '?')}")
                    print(f"  Theme:  {ai_data.get('game_theme', '?')}")
                    layout = ai_data.get("flow_layout", {})
                    n_rows  = len(layout.get("rows", []))
                    n_nodes = sum(len(r.get("nodes", [])) for r in layout.get("rows", []))
                    print(f"  Layout: {n_rows} row(s), {n_nodes} node(s)")

        out_path = vdir / "flowchart.html"
        generate_html(vdir, ai_data, out_path)

    print(f"\nDone. {len(video_dirs)} flowchart(s) generated.")


if __name__ == "__main__":
    main()
