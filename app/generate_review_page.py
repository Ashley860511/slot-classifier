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
    ALL_CATEGORIES = [
        "Basegame", "Feature game", "Feature Buy", "BigWin",
        "Transition", "Result", "Help", "loading", "Other"
    ]

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

    # ── 分類選項 ─────────────────────────────────────────────────────────────
    cat_options = '<option value="">🔀 改分類...</option>\n'
    for cat in ALL_CATEGORIES:
        cat_options += f'        <option value="{cat}">{cat}</option>\n'

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

        # Escape save_path for use in HTML data attribute
        save_path_escaped = c["save_path"].replace('"', '&quot;').replace("'", "&#39;")
        frame_idx = c["frame_idx"]
        category = c["category"]
        category_escaped = category.replace('"', '&quot;').replace("'", "&#39;")

        card_html += f"""
      <div class="card" data-category="{category_escaped}" data-conf="{c['conf_level']}"
           data-frame-idx="{frame_idx}" data-save-path="{save_path_escaped}" data-original-category="{category_escaped}">
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
            {emoji} {category}{subtype_badge}
          </div>
          <div style="font-size:11px;color:#666;margin-bottom:6px">
            Frame {frame_idx} &nbsp;|&nbsp; top={float(c['top_score']):.1f}
          </div>
          {score_bars}
        </div>
        <div class="correction-bar" id="corr-{frame_idx}">
          <button class="btn-accept" onclick="setAction('{frame_idx}','accept',this)">&#x2705; 正確</button>
          <select class="cat-select" onchange="setReclassify('{frame_idx}',this)">
            {cat_options}
          </select>
          <button class="btn-exclude" onclick="setAction('{frame_idx}','exclude',this)">&#x1F5D1; 排除</button>
        </div>
        <div class="corr-status" id="status-{frame_idx}"></div>
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

    output_dir_escaped = output_dir.replace("\\", "\\\\").replace('"', '\\"')

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>審核頁面 — {video_name}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; background: #f5f7fa; color: #1a1a2e; padding-bottom: 64px; }}
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
  .correction-bar {{ display:flex; gap:6px; padding:8px 10px; border-top:1px solid #f0f0f0; align-items:center; }}
  .btn-accept {{ background:#e8f5e9; border:1px solid #c8e6c9; border-radius:4px; cursor:pointer; font-size:11px; padding:3px 8px; }}
  .btn-accept.active {{ background:#28a745; color:white; }}
  .btn-exclude {{ background:#fce4ec; border:1px solid #f8bbd0; border-radius:4px; cursor:pointer; font-size:11px; padding:3px 8px; }}
  .btn-exclude.active {{ background:#dc3545; color:white; }}
  .cat-select {{ font-size:11px; border:1px solid #ddd; border-radius:4px; padding:3px 4px; flex:1; }}
  .corr-status {{ font-size:10px; padding:0 10px 6px; color:#888; min-height:14px; }}
  #action-bar {{ position:fixed; bottom:0; left:0; right:0; background:#1a1a2e; color:white; padding:12px 24px; display:flex; gap:12px; align-items:center; z-index:100; }}
  #corr-counter {{ flex:1; font-size:14px; }}
  #action-bar button {{ background:#00c97a; border:none; border-radius:6px; color:#000; font-weight:bold; padding:8px 18px; cursor:pointer; font-size:13px; }}
  #action-bar button:first-of-type {{ background:#444; color:#eee; }}
</style>
</head>
<body>
<div class="header">
  <h1>&#x1F50D; 分類審核頁面 — {video_name}</h1>
  <p>共 {total} 張截圖需確認 &nbsp;|&nbsp; 高信心自動接受，只需審核中/低信心（{need_count} 張）</p>
</div>

<div class="summary">
  <table class="stat-table">
    <tr><th>類別</th><th style="color:#28a745">&#x1F7E2; 高信心</th>
        <th style="color:#ffc107">&#x1F7E1; 中信心</th><th style="color:#dc3545">&#x1F534; 低信心</th></tr>
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

<div id="action-bar">
  <span id="corr-counter">0 張待修正</span>
  <button onclick="previewCorrections()">&#x1F441; 預覽</button>
  <button onclick="applyCorrections()">&#x1F680; 套用所有修正</button>
</div>

<script>
const REVIEW_META = {{
  video_id: "{video_name}",
  output_dir: "{output_dir_escaped}",
}};

const corrections = {{}};

function setAction(frameIdx, action, btn) {{
  const card = btn.closest('.card');
  const savePath = card.dataset.savePath;
  const originalCategory = card.dataset.originalCategory;

  const acceptBtn = card.querySelector('.btn-accept');
  const excludeBtn = card.querySelector('.btn-exclude');
  const catSelect = card.querySelector('.cat-select');
  const statusEl = document.getElementById('status-' + frameIdx);

  acceptBtn.classList.remove('active');
  excludeBtn.classList.remove('active');

  if (corrections[frameIdx] && corrections[frameIdx].action === action) {{
    delete corrections[frameIdx];
    if (statusEl) statusEl.textContent = '';
    updateCounter();
    return;
  }}

  btn.classList.add('active');
  catSelect.value = '';

  if (action === 'accept') {{
    corrections[frameIdx] = {{ action: 'accept', save_path: savePath, original_category: originalCategory }};
    if (statusEl) statusEl.textContent = '已標記：正確';
  }} else if (action === 'exclude') {{
    corrections[frameIdx] = {{ action: 'exclude', frame_idx: parseInt(frameIdx), save_path: savePath, original_category: originalCategory }};
    if (statusEl) statusEl.textContent = '已標記：排除';
  }}
  updateCounter();
}}

function setReclassify(frameIdx, select) {{
  const newCat = select.value;
  const card = select.closest('.card');
  const savePath = card.dataset.savePath;
  const originalCategory = card.dataset.originalCategory;
  const statusEl = document.getElementById('status-' + frameIdx);
  const acceptBtn = card.querySelector('.btn-accept');
  const excludeBtn = card.querySelector('.btn-exclude');

  acceptBtn.classList.remove('active');
  excludeBtn.classList.remove('active');

  if (!newCat) {{
    delete corrections[frameIdx];
    if (statusEl) statusEl.textContent = '';
    updateCounter();
    return;
  }}

  corrections[frameIdx] = {{
    action: 'reclassify',
    frame_idx: parseInt(frameIdx),
    save_path: savePath,
    original_category: originalCategory,
    new_category: newCat,
  }};
  if (statusEl) statusEl.textContent = '已標記：改為 ' + newCat;
  updateCounter();
}}

function updateCounter() {{
  const toApply = Object.values(corrections).filter(c => c.action === 'exclude' || c.action === 'reclassify');
  document.getElementById('corr-counter').textContent = toApply.length + ' 張待修正';
}}

function previewCorrections() {{
  const toApply = Object.values(corrections).filter(c => c.action === 'exclude' || c.action === 'reclassify');
  if (toApply.length === 0) {{
    alert('目前沒有修正項目');
    return;
  }}
  let summary = '修正摘要（共 ' + toApply.length + ' 張）：\\n\\n';
  toApply.forEach(function(c) {{
    if (c.action === 'exclude') {{
      summary += '排除：' + c.save_path + '\\n';
    }} else if (c.action === 'reclassify') {{
      summary += '改分類：' + c.original_category + ' → ' + c.new_category + '\\n  ' + c.save_path + '\\n';
    }}
  }});
  alert(summary);
}}

function applyCorrections() {{
  const toApply = Object.values(corrections).filter(c => c.action === 'exclude' || c.action === 'reclassify');
  if (toApply.length === 0) {{
    alert('沒有修正項目');
    return;
  }}

  const payload = {{
    output_dir: REVIEW_META.output_dir,
    corrections: toApply,
  }};

  const isLocal = location.hostname === 'localhost' || location.hostname === '127.0.0.1';

  if (isLocal) {{
    fetch('/api/apply-corrections', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(payload),
    }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
      alert('&#x2705; 修正完成：' + JSON.stringify(data));
    }}).catch(function(e) {{ alert('錯誤：' + e); }});
  }} else {{
    const jsonStr = JSON.stringify(payload, null, 2);
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(jsonStr).then(function() {{
        alert('&#x2705; 修正 JSON 已複製到剪貼板！\\n\\n請在 chat 貼上：\\n「請套用這個修正清單」\\n然後把剪貼板的 JSON 貼上');
      }}).catch(function() {{
        prompt('請複製以下 JSON 並貼到 chat：', jsonStr);
      }});
    }} else {{
      prompt('請複製以下 JSON 並貼到 chat：', jsonStr);
    }}
  }}
}}

let currentCat = 'all', currentConf = 'all';
function filterCards(cat) {{
  currentCat = cat;
  document.querySelectorAll('.filter-btn').forEach(function(b) {{
    if (b.textContent.includes(cat) || (cat==='all' && b.textContent==='全部')) b.classList.add('active');
    else if (!['全部信心','中信心','低信心'].includes(b.textContent.trim())) b.classList.remove('active');
  }});
  applyFilter();
}}
function filterConf(conf) {{
  currentConf = conf;
  ['all','medium','low'].forEach(function(c) {{
    const el = document.getElementById('cf-' + c);
    if (el) el.classList.toggle('active', c === conf);
  }});
  applyFilter();
}}
function applyFilter() {{
  document.querySelectorAll('.card').forEach(function(card) {{
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

    print(f"\n[OK] 審核頁面已生成：{out_path}")


if __name__ == "__main__":
    main()
