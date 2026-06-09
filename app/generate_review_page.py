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


def load_symbol_images(output_dir: str) -> list[dict]:
    """載入 symbol_table/symbols/ 下所有 symbol 圖。"""
    symbols_dir = os.path.join(output_dir, "symbol_table", "symbols")
    if not os.path.isdir(symbols_dir):
        return []
    result = []
    for f in sorted(os.listdir(symbols_dir)):
        if not f.lower().endswith((".png", ".jpg")):
            continue
        path = os.path.join(symbols_dir, f)
        b64 = img_to_base64(path)
        if b64:
            result.append({"filename": f, "b64": b64})
    return result


def load_help_images(output_dir: str, max_each: int = 30) -> list[dict]:
    """載入 Help/ 和 low_score/Help/ 的截圖供補切使用。"""
    result = []
    seen: set[str] = set()
    dirs = [
        os.path.join(output_dir, "Help"),
        os.path.join(output_dir, "low_score", "Help"),
    ]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        files = sorted(f for f in os.listdir(d) if f.lower().endswith((".jpg", ".png")))
        for f in files[:max_each]:
            if f in seen:
                continue
            seen.add(f)
            path = os.path.join(d, f)
            b64 = img_to_base64(path)
            if b64:
                result.append({"filename": f, "b64": b64})
    return result


def render_html(cards: list[dict], output_dir: str, video_name: str) -> str:
    # ── 載入 symbol 與 Help 圖 ───────────────────────────────────────────────
    symbol_images = load_symbol_images(output_dir)
    help_images   = load_help_images(output_dir)
    output_dir_escaped = output_dir.replace("\\", "\\\\").replace('"', '\\"')

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
  /* Symbol Review */
  .sym-section {{ background:white; margin:24px 24px 0; padding:20px 24px;
                  border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,.08); }}
  .sym-section h2 {{ font-size:16px; margin:0 0 14px 0; color:#1a1a2e; }}
  #sym-grid {{ display:flex; flex-wrap:wrap; gap:10px; min-height:60px; }}
  .sym-thumb {{ width:90px; text-align:center; cursor:default; }}
  .sym-thumb img {{ width:90px; height:90px; object-fit:contain;
                    border:1px solid #e2e8f0; border-radius:6px; background:#f8f8f8; }}
  .help-thumb-section {{ margin-top:20px; }}
  .help-thumb-section h3 {{ font-size:14px; color:#555; margin:0 0 10px 0; }}
  #help-thumb-row {{ display:flex; gap:10px; overflow-x:auto; padding-bottom:8px; }}
  .help-thumb {{ width:160px; flex-shrink:0; text-align:center; cursor:pointer; }}
  .help-thumb img {{ width:160px; height:90px; object-fit:cover;
                     border:2px solid #e2e8f0; border-radius:6px; transition:.15s; }}
  .help-thumb:hover img {{ border-color:#2563eb; transform:scale(1.03); }}
  /* Crop modal */
  #crop-modal {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.7);
                 z-index:1000; align-items:center; justify-content:center; }}
  .crop-modal-inner {{ background:#1a1a2e; border-radius:10px; padding:16px;
                        max-width:95vw; max-height:95vh; display:flex; gap:16px;
                        flex-direction:column; overflow:hidden; }}
  .crop-modal-top {{ display:flex; gap:16px; overflow:hidden; flex:1; min-height:0; }}
  .crop-canvas-wrap {{ flex:1; overflow:auto; min-width:0; }}
  #crop-canvas {{ display:block; max-width:100%; cursor:crosshair; }}
  .crop-sidebar {{ width:200px; flex-shrink:0; display:flex; flex-direction:column; gap:10px; }}
  #crop-preview {{ display:none; flex-direction:column; gap:6px; align-items:center; }}
  #crop-preview img {{ max-width:180px; max-height:180px; object-fit:contain;
                        border:1px solid #444; border-radius:4px; background:#111; }}
  .crop-sidebar label {{ font-size:12px; color:#aaa; margin-bottom:2px; display:block; }}
  .crop-sidebar input {{ width:100%; box-sizing:border-box; background:#111;
                          border:1px solid #444; border-radius:4px; color:#eee;
                          font-size:13px; padding:5px 8px; }}
  .crop-modal-btns {{ display:flex; gap:8px; justify-content:flex-end; }}
  .btn-save-sym {{ background:linear-gradient(135deg,#00c97a,#00ff88); color:#000;
                   border:none; border-radius:6px; padding:9px 20px; font-size:14px;
                   font-weight:bold; cursor:pointer; }}
  .btn-save-sym:disabled {{ opacity:.4; cursor:not-allowed; }}
  .btn-cancel-modal {{ background:transparent; border:1px solid #555; color:#aaa;
                        border-radius:6px; padding:9px 16px; font-size:14px; cursor:pointer; }}
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

<!-- Symbol Review Section -->
<div class="sym-section">
  <h2>&#x1F3B0; Symbol 審核（{len(symbol_images)} 個已提取）</h2>
  <div id="sym-grid"></div>
  <div class="help-thumb-section">
    <h3>&#x1F4F8; 從 Help 截圖補切遺漏的 Symbol — 點擊縮圖開啟裁切工具</h3>
    <div id="help-thumb-row"></div>
  </div>
</div>

<!-- Crop Modal -->
<div id="crop-modal">
  <div class="crop-modal-inner">
    <div style="color:#7ecfff;font-size:14px;font-weight:bold">
      &#x1F3AF; 拖曳框選要裁出的 Symbol &nbsp;
      <span style="color:#888;font-weight:normal;font-size:12px">（可重複拖曳調整）</span>
    </div>
    <div class="crop-modal-top">
      <div class="crop-canvas-wrap">
        <canvas id="crop-canvas"></canvas>
      </div>
      <div class="crop-sidebar">
        <div id="crop-preview">
          <div style="font-size:12px;color:#aaa">預覽裁切結果</div>
          <img id="crop-preview-img" src="" alt="preview">
        </div>
        <div>
          <label>Symbol 名稱（選填）</label>
          <input id="crop-label" type="text" placeholder="例：8wan、scatter">
        </div>
        <div style="font-size:11px;color:#666;margin-top:4px">
          儲存後自動命名為<br>
          <code style="color:#aaa">symbol_manual_NNN.png</code>
        </div>
      </div>
    </div>
    <div class="crop-modal-btns">
      <button class="btn-cancel-modal" onclick="closeCropModal()">取消</button>
      <button class="btn-save-sym" id="sym-save-btn" onclick="saveSymbol()" disabled>
        &#x2705; 加入為 Symbol
      </button>
    </div>
  </div>
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

  // 同 saveSymbol：直接用絕對 URL，無論 file:// 或網路磁碟皆可連到本機 Server
  fetch('http://localhost:8765/api/apply-corrections', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(payload),
  }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
    alert('&#x2705; 修正完成：' + JSON.stringify(data));
  }}).catch(function() {{
    // Server 未啟動：fallback 複製 JSON 到剪貼板
    const jsonStr = JSON.stringify(payload, null, 2);
    const msg = '⚠️ 無法連到本機 Server（localhost:8765）\n已改為複製 JSON 到剪貼板。\n\n啟動 Server 後直接重試，或把 JSON 貼給 Claude 請他套用：\n  python review_server.py --video-id {影片名}';
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(jsonStr).then(function() {{
        alert(msg);
      }}).catch(function() {{
        prompt('請複製以下 JSON 並貼到 chat：', jsonStr);
      }});
    }} else {{
      prompt('請複製以下 JSON 並貼到 chat：', jsonStr);
    }}
  }});
}}

// ── Symbol Review ──────────────────────────────────────────────────────────

const SYMBOL_META = {{
  output_dir: "{output_dir_escaped}",
  symbols_dir: "{output_dir_escaped}\\\\symbol_table\\\\symbols",
}};

// 初始 symbol 清單（頁面載入時嵌入）
let symbolList = {json.dumps(symbol_images)};
// Help 截圖清單
const helpImages = {json.dumps(help_images)};

let cropState = null;  // {{ img, startX, startY, endX, endY, dragging }}
let activeHelpIdx = null;

function initSymbolReview() {{
  renderSymbolGrid();
  renderHelpThumbs();
}}

function renderSymbolGrid() {{
  const grid = document.getElementById('sym-grid');
  if (!grid) return;
  if (symbolList.length === 0) {{
    grid.innerHTML = '<p style="color:#888;font-size:13px">尚無 symbol — 從下方 Help 截圖補切</p>';
    return;
  }}
  grid.innerHTML = symbolList.map(function(s, i) {{
    return '<div class="sym-thumb" title="' + s.filename + '">'
         + '<img src="data:image/png;base64,' + s.b64 + '">'
         + '<div style="font-size:9px;color:#aaa;word-break:break-all;margin-top:3px">' + s.filename + '</div>'
         + '</div>';
  }}).join('');
}}

function renderHelpThumbs() {{
  const row = document.getElementById('help-thumb-row');
  if (!row) return;
  if (helpImages.length === 0) {{
    row.innerHTML = '<p style="color:#888;font-size:13px">找不到 Help 截圖</p>';
    return;
  }}
  row.innerHTML = helpImages.map(function(h, i) {{
    return '<div class="help-thumb" onclick="openCropModal(' + i + ')" title="' + h.filename + '">'
         + '<img src="data:image/jpeg;base64,' + h.b64 + '">'
         + '<div style="font-size:9px;color:#aaa;margin-top:3px">' + h.filename + '</div>'
         + '</div>';
  }}).join('');
}}

function openCropModal(idx) {{
  activeHelpIdx = idx;
  const modal = document.getElementById('crop-modal');
  const canvas = document.getElementById('crop-canvas');
  const img = new Image();
  img.onload = function() {{
    canvas.width  = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0);
    cropState = {{ img: img, startX:0, startY:0, endX:0, endY:0, dragging:false, drawn:false }};
    document.getElementById('crop-preview').style.display = 'none';
    document.getElementById('crop-label').value = '';
    document.getElementById('sym-save-btn').disabled = true;
  }};
  img.src = 'data:image/jpeg;base64,' + helpImages[idx].b64;
  modal.style.display = 'flex';
}}

function closeCropModal() {{
  document.getElementById('crop-modal').style.display = 'none';
  cropState = null;
  activeHelpIdx = null;
}}

function getCanvasPos(canvas, e) {{
  const r = canvas.getBoundingClientRect();
  const scaleX = canvas.width  / r.width;
  const scaleY = canvas.height / r.height;
  const clientX = e.touches ? e.touches[0].clientX : e.clientX;
  const clientY = e.touches ? e.touches[0].clientY : e.clientY;
  return {{ x: (clientX - r.left) * scaleX, y: (clientY - r.top) * scaleY }};
}}

function drawCropOverlay() {{
  if (!cropState || !cropState.drawn) return;
  const canvas = document.getElementById('crop-canvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(cropState.img, 0, 0);

  const x1 = Math.min(cropState.startX, cropState.endX);
  const y1 = Math.min(cropState.startY, cropState.endY);
  const w  = Math.abs(cropState.endX - cropState.startX);
  const h  = Math.abs(cropState.endY - cropState.startY);

  // 半透明遮罩
  ctx.fillStyle = 'rgba(0,0,0,0.45)';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.clearRect(x1, y1, w, h);
  ctx.drawImage(cropState.img, x1, y1, w, h, x1, y1, w, h);

  // 框線
  ctx.strokeStyle = '#00ff88';
  ctx.lineWidth = Math.max(2, canvas.width / 300);
  ctx.strokeRect(x1, y1, w, h);

  // 尺寸標籤
  ctx.font = 'bold ' + Math.max(14, canvas.width / 60) + 'px monospace';
  const label = Math.round(w) + ' x ' + Math.round(h);
  const tw = ctx.measureText(label).width;
  ctx.fillStyle = 'rgba(0,255,136,0.85)';
  ctx.fillRect(x1, y1 + h + 4, tw + 12, 22);
  ctx.fillStyle = '#000';
  ctx.fillText(label, x1 + 6, y1 + h + 20);

  updateCropPreview(x1, y1, w, h);
}}

function updateCropPreview(x1, y1, w, h) {{
  if (w < 10 || h < 10) return;
  const offscreen = document.createElement('canvas');
  offscreen.width  = w;
  offscreen.height = h;
  offscreen.getContext('2d').drawImage(cropState.img, x1, y1, w, h, 0, 0, w, h);
  const previewImg = document.getElementById('crop-preview-img');
  previewImg.src = offscreen.toDataURL('image/png');
  document.getElementById('crop-preview').style.display = 'flex';
  document.getElementById('sym-save-btn').disabled = false;
  cropState.cropB64 = offscreen.toDataURL('image/png').split(',')[1];
}}

(function setupCropCanvas() {{
  document.addEventListener('DOMContentLoaded', function() {{
    const canvas = document.getElementById('crop-canvas');
    if (!canvas) return;

    function onDown(e) {{
      if (!cropState) return;
      e.preventDefault();
      const p = getCanvasPos(canvas, e);
      cropState.startX = p.x; cropState.startY = p.y;
      cropState.endX   = p.x; cropState.endY   = p.y;
      cropState.dragging = true; cropState.drawn = true;
    }}
    function onMove(e) {{
      if (!cropState || !cropState.dragging) return;
      e.preventDefault();
      const p = getCanvasPos(canvas, e);
      cropState.endX = p.x; cropState.endY = p.y;
      drawCropOverlay();
    }}
    function onUp(e) {{
      if (!cropState) return;
      cropState.dragging = false;
      drawCropOverlay();
    }}
    canvas.addEventListener('mousedown',  onDown);
    canvas.addEventListener('mousemove',  onMove);
    canvas.addEventListener('mouseup',    onUp);
    canvas.addEventListener('touchstart', onDown, {{passive:false}});
    canvas.addEventListener('touchmove',  onMove, {{passive:false}});
    canvas.addEventListener('touchend',   onUp);

    initSymbolReview();
  }});
}})();

function saveSymbol() {{
  if (!cropState || !cropState.cropB64) return;
  const label = document.getElementById('crop-label').value.trim();
  const payload = {{
    output_dir: SYMBOL_META.output_dir,
    image_b64:  cropState.cropB64,
    label:      label,
  }};

  // 無論從 file:// 或網路磁碟開啟，review_server 都跑在本機 localhost:8765
  // 直接用絕對 URL POST，CORS 已設 *；只有 server 未啟動才 fallback 下載
  fetch('http://localhost:8765/api/save-symbol', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(payload),
  }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
    if (data.ok) {{
      symbolList.push({{ filename: data.filename, b64: cropState.cropB64 }});
      renderSymbolGrid();
      closeCropModal();
      alert('[OK] 已儲存到 symbol_table/symbols/：' + data.filename);
    }} else {{
      alert('[錯誤] ' + data.error);
    }}
  }}).catch(function() {{
    // Server 未啟動：fallback 下載，並提示啟動方式
    const a = document.createElement('a');
    const suffix = label ? '_' + label : '';
    a.download = 'symbol_manual' + suffix + '.png';
    a.href = 'data:image/png;base64,' + cropState.cropB64;
    a.click();
    alert('⚠️ 無法連到本機 Server（localhost:8765）\n\n已下載 PNG，請手動放到：\n  project/output/{影片名}/symbol_table/symbols/\n\n或先啟動 Server 再重試：\n  python review_server.py --video-id {影片名}');
    closeCropModal();
  }});
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
