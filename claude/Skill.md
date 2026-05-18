---
name: slot-report
description: >
  產生老虎機競品分析報告（report.html）。當使用者提到「競品報告」「slot report」
  「分析報告」「report.html」「老虎機分析」時立即使用。
  輸出單一 report.html 檔案，包含符號賠率表、玩法機制、遊戲流程圖三大段落，
  所有圖片與文字均可在瀏覽器內直接點選替換／編輯，無需重新執行腳本。
  若資料夾內已有 symbol_table/symbols/ 與分類截圖，一律自動填入。
---

# 老虎機競品分析報告 Skill

## 一、工作流程

1. **掃描資料夾**
   - 確認 `symbol_table/symbols/` 內的 PNG（`symbol_candidate_NNN_…png`）
   - 確認 `loading/`、`Basegame/`、`Transition/`、`Feature game/`、`BigWin/`、`Result/` 等子資料夾的截圖
   - 讀取 `classification_result.csv`（若存在）了解符號分類

2. **決定色彩主題**（見下表）

3. **依照本 Skill 的 HTML 樣板撰寫 `report.html`**，全部段落填入真實內容

4. **完成後用 Write 工具寫檔**，路徑為遊戲資料夾內的 `report.html`

---

## 二、色彩主題對照表

| 遊戲風格 | `--bg` | `--panel` | `--border` | `--gold-lt` | `--amber` |
|----------|--------|-----------|------------|-------------|-----------|
| 中式/財神（紅） | `#0e0508` | `#1c0a10` | `#8b2030` | `#f5c820` | `#e07030` |
| 足球/運動（綠） | `#050e07` | `#0a1c0d` | `#207840` | `#f0d020` | `#60d060` |
| Emoji/趣味（紫） | `#07050e` | `#140a1c` | `#7030a0` | `#f5c820` | `#c060e0` |
| 幸運/經典（粉紅）| `#0e0508` | `#1c0a0f` | `#c03065` | `#f5c820` | `#e04080` |
| 遊樂園/橙  | `#0e0805` | `#1c1408` | `#c06020` | `#f5c820` | `#e07020` |
| 奇幻/藍   | `#050810` | `#0a1020` | `#2050a0` | `#60c0ff` | `#4080e0` |
| 動物/棕   | `#0a0705` | `#18120a` | `#805020` | `#f5c820` | `#c08030` |

`--panel2` 通常比 `--panel` 深 `#060408`；`--border2` 比 `--border` 深約半階。

---

## 三、完整 HTML 樣板

> 以下樣板中，`PLACEHOLDER` 標示的位置需依遊戲填入真實內容。
> 段落結構**不可更動**，只替換文字與圖片路徑。

```html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>GAME_NAME — 競品分析報告</title>
<style>
:root {
  --bg:FILL; --panel:FILL; --panel2:FILL;
  --border:FILL; --border2:FILL;
  --gold:#c89010; --gold-lt:FILL; --amber:FILL;
  --text:#f8e8d5; --dim:#c09070; --dim2:#8a5040;
  --tag-bg:#1e0810;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;
     padding:24px 28px 80px;min-width:1050px;}

/* ── header ── */
.header{display:flex;gap:20px;align-items:flex-start;margin-bottom:24px;}
.header-img{width:200px;height:130px;object-fit:cover;border-radius:10px;
             border:2px solid var(--border);cursor:pointer;flex-shrink:0;}
.header-info h1{font-size:1.6rem;font-weight:900;color:var(--gold-lt);margin-bottom:4px;}
.header-sub{color:var(--dim);font-size:.85rem;margin-bottom:12px;}
.header-badges{display:flex;flex-wrap:wrap;gap:6px;}
.badge{padding:4px 12px;border-radius:20px;font-size:.72rem;font-weight:700;
       background:rgba(255,255,255,.06);border:1px solid var(--border2);color:var(--gold-lt);}
.badge.b-red{border-color:var(--border);color:#f08080;}

/* ── theme overview ── */
.theme-overview{display:flex;gap:20px;background:var(--panel);border:1.5px solid var(--border);
                border-radius:12px;padding:16px 20px;margin-bottom:20px;align-items:flex-start;}
.theme-text{flex:1;}
.theme-text h2{font-size:.85rem;font-weight:800;color:var(--gold-lt);margin-bottom:10px;
               text-transform:uppercase;letter-spacing:1px;}
.theme-text h2 span{color:var(--dim);font-weight:400;}
.theme-text p{font-size:.78rem;color:var(--dim);line-height:1.7;}
.stat-blocks{display:grid;grid-template-columns:1fr 1fr;gap:8px;min-width:200px;}
.stat-block{background:var(--panel2);border:1px solid var(--border2);border-radius:8px;
            padding:10px 12px;text-align:center;}
.sv{display:block;font-size:1.3rem;font-weight:900;color:var(--gold-lt);}
.sk{font-size:.62rem;color:var(--dim2);text-transform:uppercase;letter-spacing:.5px;}

/* ── nav ── */
.nav{display:flex;border-bottom:1.5px solid var(--border2);margin-bottom:20px;}
.nav a{padding:8px 18px;font-size:.75rem;font-weight:700;color:var(--dim);
       text-decoration:none;border-bottom:2px solid transparent;}
.nav a:hover{color:var(--gold-lt);border-bottom-color:var(--gold-lt);}

/* ── section ── */
.section{margin-bottom:28px;}
.section-title{font-size:.7rem;font-weight:800;text-transform:uppercase;letter-spacing:2px;
               color:var(--gold);margin-bottom:12px;}

/* ── symbol table ── */
.sym-outer{background:var(--panel);border:1.5px solid var(--border);border-radius:12px;padding:16px 20px;}
.sym-row{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-start;margin-bottom:10px;}
.sym-row:last-child{margin-bottom:0;}
.row-tag{font-size:8px;writing-mode:vertical-rl;text-orientation:mixed;color:var(--dim2);
         letter-spacing:1px;padding:4px 2px;border-right:1px solid var(--border2);
         margin-right:4px;min-height:60px;display:flex;align-items:center;}
.sym-cell{display:flex;flex-direction:column;align-items:center;padding:10px 7px 8px;
          border-radius:8px;min-width:84px;max-width:96px;background:var(--panel2);
          border:1px solid var(--border2);position:relative;}
.tier-badge{font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;margin-bottom:6px;}
.b-scatter{background:#3a2010;color:#f0c060;}
.b-wild   {background:#1a1030;color:#c080ff;}
.b-m1,.b-m2{background:#1a2010;color:#80e060;}
.b-m3,.b-m4,.b-m5{background:#102030;color:#60c0e0;}
.b-low,.b-l1,.b-l2,.b-l3{background:#181818;color:#a0a0a0;}
.sym-img-wrap{position:relative;width:68px;height:68px;margin-bottom:7px;
              overflow:hidden;border-radius:6px;}
.sym-img-wrap img{width:100%;height:100%;object-fit:contain;pointer-events:none;}
.sym-name{font-size:.7rem;font-weight:700;color:var(--text);text-align:center;margin-bottom:4px;}
.sym-note{font-size:.65rem;color:var(--dim);text-align:center;line-height:1.4;}
.pay-tbl{font-size:.67rem;border-collapse:collapse;width:100%;}
.pay-tbl td{padding:1px 3px;}
.pay-tbl td:first-child{color:var(--dim2);}
.pay-tbl td:last-child{color:var(--gold-lt);font-weight:700;text-align:right;}

/* ── edit mode: symbol hover ── */
body.edit-on .sym-img-wrap::after{content:'🔄';position:absolute;inset:0;z-index:10;
  display:flex;align-items:center;justify-content:center;font-size:20px;
  background:rgba(0,0,0,.4);border-radius:6px;opacity:0;transition:opacity .15s;pointer-events:none;}
body.edit-on .sym-img-wrap:hover::after{opacity:1;}
body.edit-on .sym-img-wrap{cursor:pointer;}

/* ── mechanics ── */
.mech-outer{background:var(--panel);border:1.5px solid var(--border);border-radius:12px;padding:16px 20px;}
.mech-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.mech-card{background:var(--panel2);border:1px solid var(--border2);border-radius:8px;padding:12px 14px;}
.mech-card h4{font-size:.72rem;font-weight:800;text-transform:uppercase;color:var(--amber);margin:0 0 6px;}
.mech-card p{font-size:.73rem;color:var(--dim);line-height:1.65;margin:0;}

/* ── flowchart ── */
.flow-outer{background:var(--panel);border:1.5px solid var(--border);border-radius:12px;padding:16px 20px;}
.flow-section-label{font-size:.65rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;
                    color:var(--dim2);margin-bottom:10px;padding-bottom:6px;
                    border-bottom:1px solid var(--border2);}
.flow-section-label.mt{margin-top:14px;}
.flow-divider{border:none;border-top:1px solid var(--border2);margin:16px 0 12px;}
.flow-row{display:flex;gap:0;align-items:flex-start;flex-wrap:nowrap;
          overflow-x:auto;padding-bottom:8px;}
.flow-arrow{color:var(--border);font-size:18px;display:flex;padding-top:28px;
            width:22px;align-items:flex-start;justify-content:center;flex-shrink:0;}
.node{display:flex;flex-direction:column;align-items:center;min-width:80px;max-width:96px;}
.node-thumb{width:80px;height:130px;border-radius:8px;overflow:hidden;
            cursor:pointer;position:relative;flex-shrink:0;}
.node-thumb img{width:100%;height:100%;object-fit:contain;}
.node-label{font-size:.7rem;font-weight:700;color:var(--text);margin-top:6px;text-align:center;}
.node-sub{font-size:.62rem;color:var(--dim);text-align:center;line-height:1.4;}
.node-tag{font-size:.58rem;font-weight:700;letter-spacing:.5px;padding:2px 6px;
          border-radius:8px;background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.15);
          color:var(--dim);margin-top:4px;text-align:center;}
/* node border colors */
.c-gold  {border:2px solid var(--gold);}
.c-red   {border:2px solid var(--border);}
.c-silver{border:2px solid #707070;}
.c-green {border:2px solid #30a040;}
.c-bw1   {border:2px solid #30a040;box-shadow:0 0 6px rgba(48,160,64,.35);}   /* BIG WIN   */
.c-bw2   {border:2px solid #8050d0;box-shadow:0 0 6px rgba(128,80,208,.35);}  /* SUPER WIN */
.c-bw3   {border:2px solid #c87010;box-shadow:0 0 6px rgba(200,112,16,.4);}   /* MEGA WIN  */
.c-result{border:2px solid var(--border2);}

/* edit mode: flowchart thumb hover */
body.edit-on .__img-wrap:not(.sym-img-wrap):hover::after{
  content:'🔄';position:absolute;inset:0;z-index:10;
  display:flex;align-items:center;justify-content:center;font-size:22px;
  background:rgba(0,0,0,.45);border-radius:6px;pointer-events:none;}
body.edit-on .header-img:hover{outline:3px solid var(--gold);cursor:pointer;}

/* ── fixed bottom buttons ── */
.edit-btn{position:fixed;bottom:24px;right:24px;z-index:999;background:var(--border);
          color:#fff;border:none;border-radius:24px;padding:9px 20px;font-size:.78rem;
          font-weight:700;cursor:pointer;letter-spacing:.5px;box-shadow:0 4px 16px rgba(0,0,0,.5);}
.edit-btn:hover{filter:brightness(1.2);}
.edit-btn.active{background:#40a060;}
.copy-btn{position:fixed;bottom:24px;right:160px;z-index:999;background:#285090;
          color:#fff;border:none;border-radius:24px;padding:9px 20px;font-size:.78rem;
          font-weight:700;cursor:pointer;letter-spacing:.5px;box-shadow:0 4px 16px rgba(0,0,0,.5);
          display:none;}
.copy-btn:hover{background:#3070c0;}
body.edit-on .copy-btn{display:block;}
</style>
</head>
<body>

<!-- ══ HEADER ══════════════════════════════════════════════════════════════ -->
<div class="header">
  <img class="header-img __img-wrap" src="loading/GAME_frame_XXXXXX.jpg" alt="GAME_NAME">
  <div class="header-info">
    <h1 class="__ed" contenteditable="false">GAME_NAME</h1>
    <div class="header-sub __ed" contenteditable="false">DEVELOPER｜THEME_DESCRIPTION</div>
    <div class="header-badges">
      <span class="badge __ed" contenteditable="false">REEL_FORMAT</span>
      <span class="badge b-red __ed" contenteditable="false">WAYS / LINES</span>
      <span class="badge __ed" contenteditable="false">CORE_MECHANIC</span>
    </div>
  </div>
</div>

<!-- ══ THEME OVERVIEW ════════════════════════════════════════════════════== -->
<div class="theme-overview">
  <div class="theme-text">
    <h2 class="__ed" contenteditable="false">遊戲概覽 <span>Game Overview</span></h2>
    <p class="__ed" contenteditable="false">GAME_DESCRIPTION（2-4 句，說明主題、核心機制、特色）</p>
  </div>
  <div class="stat-blocks">
    <div class="stat-block"><span class="sv __ed" contenteditable="false">STAT1</span><span class="sk">LABEL1</span></div>
    <div class="stat-block"><span class="sv __ed" contenteditable="false">STAT2</span><span class="sk">LABEL2</span></div>
    <div class="stat-block"><span class="sv __ed" contenteditable="false">STAT3</span><span class="sk">LABEL3</span></div>
    <div class="stat-block"><span class="sv __ed" contenteditable="false">STAT4</span><span class="sk">LABEL4</span></div>
  </div>
</div>

<!-- ══ NAV ══════════════════════════════════════════════════════════════=== -->
<nav class="nav">
  <a href="#symbols">符號賠率</a>
  <a href="#mechanics">玩法機制</a>
  <a href="#flowchart">流程圖</a>
</nav>

<!-- ══ SYMBOLS ══════════════════════════════════════════════════════════=== -->
<section class="section" id="symbols">
  <div class="section-title">符號賠率表</div>
  <div class="sym-outer">

    <div class="sym-row">
      <div class="row-tag">特殊</div>
      <div class="sym-cell">
        <span class="tier-badge b-scatter">Scatter</span>
        <div class="sym-img-wrap __img-wrap">
          <img src="symbol_table/symbols/SCATTER_FILE.png" alt="Scatter">
        </div>
        <div class="sym-name __ed" contenteditable="false">符號名稱</div>
        <div class="sym-note __ed" contenteditable="false">N 個觸發 Free Spins</div>
      </div>
      <div class="sym-cell">
        <span class="tier-badge b-wild">Wild</span>
        <div class="sym-img-wrap __img-wrap">
          <img src="symbol_table/symbols/WILD_FILE.png" alt="Wild">
        </div>
        <div class="sym-name __ed" contenteditable="false">Wild</div>
        <div class="sym-note __ed" contenteditable="false">代替所有普通符號</div>
      </div>
    </div>

    <div class="sym-row">
      <div class="row-tag">主力</div>
      <div class="sym-cell">
        <span class="tier-badge b-m1">M1</span>
        <div class="sym-img-wrap __img-wrap">
          <img src="symbol_table/symbols/M1_FILE.png" alt="M1">
        </div>
        <div class="sym-name __ed" contenteditable="false">符號名稱</div>
        <table class="pay-tbl">
          <tr><td>5×</td><td class="__ed" contenteditable="false">50×</td></tr>
          <tr><td>4×</td><td class="__ed" contenteditable="false">25×</td></tr>
          <tr><td>3×</td><td class="__ed" contenteditable="false">10×</td></tr>
        </table>
      </div>
    </div>

    <div class="sym-row">
      <div class="row-tag">低值</div>
    </div>

  </div>
</section>

<!-- ══ MECHANICS ═════════════════════════════════════════════════════════== -->
<section class="section" id="mechanics">
  <div class="section-title">玩法機制</div>
  <div class="mech-outer">
    <div class="mech-grid">
      <div class="mech-card">
        <h4>機制名稱 1</h4>
        <p class="__ed" contenteditable="false">說明文字…</p>
      </div>
      <div class="mech-card">
        <h4>機制名稱 2</h4>
        <p class="__ed" contenteditable="false">說明文字…</p>
      </div>
      <div class="mech-card">
        <h4>機制名稱 3</h4>
        <p class="__ed" contenteditable="false">說明文字…</p>
      </div>
      <div class="mech-card">
        <h4>機制名稱 4</h4>
        <p class="__ed" contenteditable="false">說明文字…</p>
      </div>
    </div>
  </div>
</section>

<!-- ══ FLOWCHART ══════════════════════════════════════════════════════════= -->
<section class="section" id="flowchart">
  <div class="section-title">遊戲流程圖</div>
  <div class="flow-outer">

    <div class="flow-section-label">MAIN FLOW — 主遊戲流程</div>
    <div class="flow-row">

      <div class="node">
        <div class="node-thumb c-gold __img-wrap">
          <img src="loading/GAME_frame_XXXXXX.jpg" alt="Loading">
        </div>
        <div class="node-label __ed" contenteditable="false">Loading</div>
        <div class="node-sub __ed" contenteditable="false">遊戲載入</div>
        <div class="node-tag __ed" contenteditable="false">LOADING</div>
      </div>
      <div class="flow-arrow">▶</div>

      <div class="node">
        <div class="node-thumb c-red __img-wrap">
          <img src="Basegame/GAME_frame_XXXXXX.jpg" alt="Base Game">
        </div>
        <div class="node-label __ed" contenteditable="false">Base Game</div>
        <div class="node-sub __ed" contenteditable="false">捲軸格式 / Ways</div>
        <div class="node-tag __ed" contenteditable="false">BASE</div>
      </div>
      <div class="flow-arrow">▶</div>

      <div class="node">
        <div class="node-thumb c-silver __img-wrap">
          <img src="Basegame/GAME_frame_XXXXXX.jpg" alt="Base Mechanic">
        </div>
        <div class="node-label __ed" contenteditable="false">基本特色名稱</div>
        <div class="node-sub __ed" contenteditable="false">特色說明</div>
        <div class="node-tag __ed" contenteditable="false">MECHANIC</div>
      </div>
      <div class="flow-arrow">▶</div>

      <div class="node">
        <div class="node-thumb c-gold __img-wrap">
          <img src="Transition/GAME_frame_XXXXXX.jpg" alt="Trigger">
        </div>
        <div class="node-label __ed" contenteditable="false">Scatter 觸發</div>
        <div class="node-sub __ed" contenteditable="false">N+ → Free Spins</div>
        <div class="node-tag __ed" contenteditable="false">TRIGGER</div>
      </div>

    </div>

    <hr class="flow-divider">
    <div class="flow-section-label mt">FREE SPINS FLOW — 免費旋轉流程</div>
    <div class="flow-row">

      <div class="node">
        <div class="node-thumb c-green __img-wrap">
          <img src="Transition/GAME_frame_XXXXXX.jpg" alt="FS Start">
        </div>
        <div class="node-label __ed" contenteditable="false">Free Spins 入場</div>
        <div class="node-sub __ed" contenteditable="false">初始倍率</div>
        <div class="node-tag __ed" contenteditable="false">FS START</div>
      </div>
      <div class="flow-arrow">▶</div>

      <div class="node">
        <div class="node-thumb c-green __img-wrap">
          <img src="Feature game/GAME_frame_XXXXXX.jpg" alt="Free Spins">
        </div>
        <div class="node-label __ed" contenteditable="false">Free Spins</div>
        <div class="node-sub __ed" contenteditable="false">特色說明</div>
        <div class="node-tag __ed" contenteditable="false">FREE SPIN</div>
      </div>
      <div class="flow-arrow">▶</div>

      <div class="node">
        <div class="node-thumb c-green __img-wrap">
          <img src="Feature game/GAME_frame_XXXXXX.jpg" alt="Chain">
        </div>
        <div class="node-label __ed" contenteditable="false">高倍率連鎖</div>
        <div class="node-sub __ed" contenteditable="false">倍率持續累加</div>
        <div class="node-tag __ed" contenteditable="false">CHAIN</div>
      </div>
      <div class="flow-arrow">▶</div>

      <div class="node">
        <div class="node-thumb c-bw1 __img-wrap">
          <img src="BigWin/GAME_frame_XXXXXX.jpg" alt="Big Win">
        </div>
        <div class="node-label __ed" contenteditable="false">Big Win</div>
        <div class="node-sub __ed" contenteditable="false"></div>
        <div class="node-tag __ed" contenteditable="false">BIG WIN</div>
      </div>
      <div class="flow-arrow">▶</div>

      <div class="node">
        <div class="node-thumb c-bw2 __img-wrap">
          <img src="BigWin/GAME_frame_XXXXXX.jpg" alt="Super Win">
        </div>
        <div class="node-label __ed" contenteditable="false">Super Win</div>
        <div class="node-sub __ed" contenteditable="false"></div>
        <div class="node-tag __ed" contenteditable="false">SUPER WIN</div>
      </div>
      <div class="flow-arrow">▶</div>

      <div class="node">
        <div class="node-thumb c-bw3 __img-wrap">
          <img src="BigWin/GAME_frame_XXXXXX.jpg" alt="Mega Win">
        </div>
        <div class="node-label __ed" contenteditable="false">Mega Win</div>
        <div class="node-sub __ed" contenteditable="false"></div>
        <div class="node-tag __ed" contenteditable="false">MEGA WIN</div>
      </div>
      <div class="flow-arrow">▶</div>

      <div class="node">
        <div class="node-thumb c-result __img-wrap">
          <img src="Result/GAME_frame_XXXXXX.jpg" alt="Result">
        </div>
        <div class="node-label __ed" contenteditable="false">結算</div>
        <div class="node-sub __ed" contenteditable="false">總獎金顯示</div>
        <div class="node-tag __ed" contenteditable="false">RESULT</div>
      </div>

    </div>

  </div>
</section>

<!-- ══ BUTTONS ══════════════════════════════════════════════════════════=== -->
<button class="edit-btn" onclick="toggleEdit(this)">✏️ 編輯模式</button>
<button class="copy-btn" onclick="copyHTML()">📋 複製 HTML</button>

<script>
function openPicker(targetImg) {
  var input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/*';
  input.onchange = function() {
    var file = this.files[0]; if (!file) return;
    var reader = new FileReader();
    reader.onload = function(ev) { targetImg.src = ev.target.result; };
    reader.readAsDataURL(file);
  };
  input.click();
}

function makeReplaceable() {
  document.querySelectorAll('.sym-cell').forEach(function(cell) {
    if (cell.dataset.rDone) return;
    cell.dataset.rDone = '1';
    cell.addEventListener('click', function(e) {
      if (!document.body.classList.contains('edit-on')) return;
      var wrap = e.target.closest('.sym-img-wrap');
      if (!wrap) return;
      var img = wrap.querySelector('img');
      if (!img) return;
      openPicker(img);
    });
  });

  document.querySelectorAll('.__img-wrap').forEach(function(wrap) {
    if (wrap.classList.contains('sym-img-wrap')) return;
    if (wrap.dataset.rDone) return;
    wrap.dataset.rDone = '1';
    wrap.addEventListener('click', function() {
      if (!document.body.classList.contains('edit-on')) return;
      var img = wrap.querySelector('img');
      if (!img) return;
      openPicker(img);
    });
  });

  document.querySelectorAll('.header-img').forEach(function(el) {
    if (el.dataset.rDone) return;
    el.dataset.rDone = '1';
    el.addEventListener('click', function() {
      if (!document.body.classList.contains('edit-on')) return;
      openPicker(el);
    });
  });
}

function toggleEdit(btn) {
  document.body.classList.toggle('edit-on');
  btn.classList.toggle('active');
  btn.textContent = document.body.classList.contains('edit-on')
    ? '✅ 完成編輯' : '✏️ 編輯模式';
  document.querySelectorAll('.__ed').forEach(function(el) {
    el.contentEditable = document.body.classList.contains('edit-on') ? 'true' : 'false';
  });
  makeReplaceable();
}

function copyHTML() {
  var html = '<!DOCTYPE html>\n' + document.documentElement.outerHTML;
  navigator.clipboard.writeText(html).then(function() {
    var btn = document.querySelector('.copy-btn');
    var orig = btn.textContent;
    btn.textContent = '✅ 已複製！';
    setTimeout(function() { btn.textContent = orig; }, 2000);
  });
}

document.addEventListener('DOMContentLoaded', makeReplaceable);
</script>

</body>
</html>
```

---

## 四、圖片路徑規則

| 用途 | 路徑格式 |
|------|----------|
| 符號圖 | `symbol_table/symbols/symbol_candidate_NNN_from_candidate_XXX_score_Y.YY.png` |
| 載入畫面 | `loading/GAME_frame_XXXXXX.jpg` |
| 主遊戲 | `Basegame/GAME_frame_XXXXXX.jpg` |
| 轉場／觸發 | `Transition/GAME_frame_XXXXXX.jpg` |
| 特色遊戲 | `Feature game/GAME_frame_XXXXXX.jpg` |
| 大獎 | `BigWin/GAME_frame_XXXXXX.jpg` |
| 結算 | `Result/GAME_frame_XXXXXX.jpg` |
| 功能購買 | `Feature Buy/GAME_frame_XXXXXX.jpg` |

**選圖原則**：
- Loading 節點：選 LOGO 清晰 + 玩法介紹文字 + 讀取進度條 **三者同時出現** 的影格
- BigWin 三階：從 BigWin/ 內選 3 個視覺差異大的影格（不同爆分效果）
- 若 BigWin/ 為空，省略三階大獎節點

---

## 五、可編輯功能說明

頁面右下角固定兩個按鈕（`position:fixed`，**不用 sticky toolbar**）：

- **✏️ 編輯模式** → 點擊進入編輯，所有 `.__ed` 元素變為 contenteditable，
  所有 `.__img-wrap` 在 hover 時顯示 🔄，點擊後開啟本機檔案選擇器替換圖片
- **📋 複製 HTML** → 編輯模式中出現，一鍵複製整份 HTML（含已替換的 base64 圖片）

### 重要：`data-r-done` 防重複綁定
JS 使用 `data-r-done="1"` 標記已綁定的元素，
確保多次切換編輯模式不會重複掛載事件。
**不要預先在 HTML 寫 `data-r-done`**（只讓 JS 設定）。

---

## 六、注意事項

1. **node-thumb 必須 80×130px + `object-fit:contain`**，截圖完整不裁切
2. **符號 sym-img-wrap 必須 68×68px + `object-fit:contain`**
3. **mech-card 必須用 `<h4>` + `<p>` 格式**（不用 div.mech-title / div.mech-body）
4. **stat-blocks 固定 4 格 2×2 grid**
5. **無 Free Spins 的遊戲**（如純 Respin）：刪除 `<hr class="flow-divider">` 與 Free Spins flow-row，主遊戲流程視需要增加特色節點
6. 每份報告色彩主題隨遊戲風格調整，結構/JS 維持完全一致
