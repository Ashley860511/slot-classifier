"""
generate_review_page.py — 生成 review.html 審核頁面

用法：
  python generate_review_page.py project/output/WildTrain
  python generate_review_page.py project/output/WildTrain --all   # 包含高信心幀

頁面功能：
  - 只顯示 needs_review/ 下的截圖（低/中信心）
  - 以卡片形式顯示：截圖 + 預測類別 + 信心等級 + 競爭分數
  - 可按類別篩選，快速定位問題
  - 顯示各類別統計（高/中/低信心各幾張）
"""
from __future__ import annotations

import argparse
import ast
import base64
import csv
import json
import os
import sys
from pathlib import Path


CATEGORY_EMOJI = {
    "Basegame":     "🎰",
    "Feature game": "⭐",
    "Feature Buy":  "💰",
    "BigWin":       "🏆",
    "Transition":   "🔄",
    "Help":         "📖",
    "loading":      "⏳",
    "Result":       "🎉",
    "Other":        "❓",
}

CONFIDENCE_COLOR = {
    "high":   "#28a745",
    "medium": "#ffc107",
    "low":    "#dc3545",
}
CONFIDENCE_TEXT = {
    "high":   "高信心",
    "medium": "中信心",
    "low":    "低信心",
}


def img_to_base64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def load_csv_records(csv_path: str) -> list[dict]:
    records = []
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(dict(row))
    except Exception as e:
        print(f"[警告] 讀取 CSV 失敗：{e}")
    return records


def parse_category_scores(raw: str) -> dict:
    try:
        return ast.literal_eval(raw)
    except Exception:
        return {}


def build_review_cards(records: list[dict], output_dir: str, include_high: bool) -> list[dict]:
    """篩選需要審核的幀，附加顯示用資訊。"""
    cards = []
    for rec in records:
        conf = rec.get("confidence_level", "low")
        if conf == "high" and not include_high:
            continue

        save_path = rec.get("save_path", "")
        if not os.path.exists(save_path):
            # 嘗試從 needs_review/ 找
            fname = os.path.basename(save_path)
            category = rec.get("final_category", "")
            review_path = os.path.join(output_dir, "needs_review", category, fname)
            if not os.path.exists(review_path):
                continue
            save_path = review_path

        scores = parse_category_scores(rec.get("category_scores", "{}"))
        # 取前 3 競爭類別（排除輔助分數）
        main_cats = ["Basegame", "Feature game", "Feature Buy", "BigWin",
                     "Transition", "Help", "loading", "Result", "Other"]
        top_scores = sorted(
            [(c, float(scores.get(c, 0))) for c in main_cats],
            key=lambda x: x[1], reverse=True
        )[:3]

        cards.append({
            "frame_idx":   rec.get("frame_idx", "?"),
            "category":    rec.get("final_category", "?"),
            "conf_level":  conf,
            "conf_score":  rec.get("confidence_score", "0"),
            "top_score":   rec.get("top_score", "0"),
            "save_path":   save_path,
            "top_scores":  top_scores,
            "subtype":     rec.get("feature_subtype", ""),
        })
    return cards


def render_html(cards: list[dict], output_dir: str, video_name: str) -> str:
    # 統計
    stats: dict[str, dict[str, int]] = {}
    for c in cards:
        cat = c["category"]
        lv  = c["conf_level"]
        stats.setdefault(cat, {"high": 0, "medium": 0, "low": 0})
        stats[cat][lv] = stats[cat].get(lv, 0) + 1

    total = len(cards)
    need_count = sum(1 for c in cards if c["conf_level"] != "high")

    # ── 統計列 ──────────────────────────────────────────────────────────────
    stat_rows = ""
    for cat, lv_counts in sorted(stats.items()):
        emoji = CATEGORY_EMOJI.get(cat, "")
        stat_rows += f"""
        <tr>
          <td>{emoji} {cat}</td>
          <td style="color:#28a745;font-weight:bold">{lv_counts.get('high',0)}</td>
          <td style="color:#ffc107;font-weight:bold">{lv_counts.get('medium',0)}</td>
          <td style="color:#dc3545;font-weight:bold">{lv_counts.get('low',0)}</td>
        </tr>"""

    # ── 卡片 ────────────────────────────────────────────────────────────────
    card_html = ""
    for c in cards:
        color  = CONFIDENCE_COLOR.get(c["conf_level"], "#aaa")
        label  = CONFIDENCE_TEXT.get(c["conf_level"], c["conf_level"])
        emoji  = CATEGORY_EMOJI.get(c["category"], "")
        img64  = img_to_base64(c["save_path"])
        img_src = f"data:image/jpeg;base64,{img64}" if img64 else ""

        score_bars = ""
        for cat_name, score_val in c["top_scores"]:
            bar_width = min(100, int(score_val * 4))
            bar_color = "#2563eb" if cat_name == c["category"] else "#94a3b8"
            score_bars += f"""
            <div style="margin:2px 0;font-size:11px">
              <span style="display:inline-block;width:90px;overflow:hidden;
                           text-overflow:ellipsis;white-space:nowrap">{cat_name}</span>
              <span style="display:inline-block;width:{bar_width}px;height:8px;
                           background:{bar_color};border-radius:2px;vertical-align:middle"></span>
              <span style="margin-left:4px;color:#555">{score_val:.1f}</span>
            </div>"""

        subtype_badge = f'<span style="font-size:10px;color:#888;margin-left:6px">{c["subtype"]}</span>' if c["subtype"] and c["subtype"] not in ("unknown_feature", "") else ""

        card_html += f"""
      <div class="card" data-category="{c['category']}" data-conf="{c['conf_level']}">
        <div style="position:relative">
          <img src="{img_src}" style="width:100%;height:160px;object-fit:cover;
               border-radius:6px 6px 0 0;background:#eee"
               onerror="this.style.display='none'">
          <span style="position:absolute;top:6px;right:6px;background:{color};
                       color:white;font-size:10px;padding:2px 7px;border-radius:10px;
                       font-weight:bold">{label}</span>
        </div>
        <div style="padding:8px 10px 10px">
          <div style="font-size:14px;font-weight:bold;margin-bottom:4px">
            {emoji} {c['category']}{subtype_badge}
          </div>
          <div style="font-size:11px;color:#666;margin-bottom:6px">
            Frame {c['frame_idx']} &nbsp;|&nbsp; top={float(c['top_score']):.1f}
          </div>
          {score_bars}
        </div>
      </div>"""

    # ── 類別篩選按鈕 ────────────────────────────────────────────────────────
    categories = sorted(set(c["category"] for c in cards))
    filter_btns = '<button class="filter-btn active" onclick="filterCards(\'all\')">全部</button>\n'
    for cat in categories:
        filter_btns += f'<button class="filter-btn" onclick="filterCards(\'{cat}\')">{CATEGORY_EMOJI.get(cat,"")} {cat}</button>\n'

    conf_filter = """
    <button class="filter-btn active" onclick="filterConf('all')" id="cf-all">全部信心</button>
    <button class="filter-btn" onclick="filterConf('medium')" id="cf-medium" style="color:#ffc107">中信心</button>
    <button class="filter-btn" onclick="filterConf('low')" id="cf-low" style="color:#dc3545">低信心</button>
    """

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>審核頁面 — {video_name}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; background: #f5f7fa; color: #1a1a2e; }}
  .header {{ background: #1a1a2e; color: white; padding: 18px 28px; }}
  .header h1 {{ margin: 0; font-size: 20px; }}
  .header p {{ margin: 4px 0 0; color: #aaa; font-size: 13px; }}
  .stat-table {{ border-collapse: collapse; font-size: 13px; }}
  .stat-table td, .stat-table th {{ padding: 4px 14px; border-bottom: 1px solid #e2e8f0; }}
  .stat-table th {{ color: #888; font-weight: normal; }}
  .toolbar {{ background: white; padding: 12px 24px; border-bottom: 1px solid #e2e8f0;
              display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
  .filter-btn {{ background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 16px;
                 padding: 4px 14px; font-size: 12px; cursor: pointer; }}
  .filter-btn.active {{ background: #1a1a2e; color: white; border-color: #1a1a2e; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr));
           gap: 14px; padding: 20px 24px; }}
  .card {{ background: white; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08);
           overflow: hidden; transition: transform .15s; }}
  .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.15); }}
  .summary {{ background: white; margin: 16px 24px 0; padding: 14px 20px;
              border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
</style>
</head>
<body>
<div class="header">
  <h1>🔍 分類審核頁面 — {video_name}</h1>
  <p>共 {total} 張截圖需確認 &nbsp;|&nbsp; 高信心自動接受，只需審核中/低信心（{need_count} 張）</p>
</div>

<div class="summary">
  <table class="stat-table">
    <tr><th>類別</th><th style="color:#28a745">🟢 高信心</th>
        <th style="color:#ffc107">🟡 中信心</th><th style="color:#dc3545">🔴 低信心</th></tr>
    {stat_rows}
  </table>
</div>

<div class="toolbar">
  {filter_btns}
  <span style="color:#ccc">|</span>
  {conf_filter}
</div>

<div class="grid" id="card-grid">
{card_html}
</div>

<script>
let currentCat = 'all', currentConf = 'all';
function filterCards(cat) {{
  currentCat = cat;
  document.querySelectorAll('.filter-btn').forEach(b => {{
    if (b.textContent.includes(cat) || (cat==='all' && b.textContent==='全部')) b.classList.add('active');
    else if (!['全部信心','中信心','低信心'].includes(b.textContent.trim())) b.classList.remove('active');
  }});
  applyFilter();
}}
function filterConf(conf) {{
  currentConf = conf;
  ['all','medium','low'].forEach(c => {{
    const el = document.getElementById('cf-' + c);
    if (el) el.classList.toggle('active', c === conf);
  }});
  applyFilter();
}}
function applyFilter() {{
  document.querySelectorAll('.card').forEach(card => {{
    const catMatch = currentCat === 'all' || card.dataset.category === currentCat;
    const confMatch = currentConf === 'all' || card.dataset.conf === currentConf;
    card.style.display = catMatch && confMatch ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="生成截圖審核 HTML 頁面")
    parser.add_argument("output_dir", help="分類輸出目錄，例如 project/output/WildTrain")
    parser.add_argument("--all", action="store_true", dest="include_high",
                        help="包含高信心幀（預設只顯示中/低信心）")
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    if not os.path.isdir(output_dir):
        print(f"[錯誤] 找不到目錄：{output_dir}")
        sys.exit(1)

    csv_files = list(Path(output_dir).glob("classification_result.csv"))
    if not csv_files:
        print(f"[錯誤] 找不到 classification_result.csv，請先執行分類")
        sys.exit(1)

    video_name = os.path.basename(output_dir)
    print(f"讀取 CSV：{csv_files[0]}")
    records = load_csv_records(str(csv_files[0]))
    print(f"共 {len(records)} 筆記錄")

    cards = build_review_cards(records, output_dir, args.include_high)
    print(f"需要審核：{len(cards)} 張")

    html = render_html(cards, output_dir, video_name)
    out_path = os.path.join(output_dir, "review.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 審核頁面已生成：{out_path}")
    print(f"   在 Windows 用瀏覽器開啟：\\\\34.80.93.119\\data\\user\\ashleyli\\competitive-survey-worker\\.claude\\skills\\project\\output\\{video_name}\\review.html")


if __name__ == "__main__":
    main()
