"""
generate_roi_preview.py — auto ROI 偵測 + 生成瀏覽器預覽頁（帶互動調整框）

用法：
    python app/generate_roi_preview.py --video-id WildTrain

輸出：
    project/output/<VIDEO_ID>/_debug/auto_roi_preview.jpg
    project/output/<VIDEO_ID>/_debug/roi_adjust.html   ← 可在瀏覽器拖曳調整
    stdout 最後一行：ROI=x,y,w,h
"""
import argparse
import json
import os
import sys

# 讓 app/ 下的模組可以直接 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auto_roi import auto_detect_game_area
from config import DEFAULT_ROI_H, DEFAULT_ROI_W, DEFAULT_ROI_X, DEFAULT_ROI_Y, INPUT_DIR, OUTPUT_DIR
from video_io import get_video_list

# ── 互動式 ROI 調整頁面 HTML 模板 ──────────────────────────────
ROI_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>ROI 確認 — {video_id}</title>
<style>
body {{ margin:0; padding:12px; background:#1a1a2e; color:#eee;
        font-family:'Segoe UI',Arial,sans-serif; font-size:14px; }}
h1 {{ color:#7ecfff; font-size:17px; margin:0 0 10px 0; }}
#main {{ display:flex; gap:14px; align-items:flex-start; }}
#canvas-container {{ flex:1; min-width:0; background:#000; border:2px solid #444;
                     border-radius:6px; overflow:hidden; }}
canvas {{ display:block; width:100%; height:auto; cursor:crosshair; }}
#panel {{ width:270px; flex-shrink:0; }}
.card {{ background:#252540; border:1px solid #3a3a60; border-radius:6px;
         padding:12px; margin-bottom:10px; }}
.card-title {{ font-size:11px; color:#888; text-transform:uppercase;
               letter-spacing:.5px; margin-bottom:8px; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:7px; }}
.field label {{ display:block; font-size:11px; color:#888; margin-bottom:3px; }}
.field input {{ width:100%; box-sizing:border-box; background:#111128;
               border:1px solid #444; border-radius:4px; color:#00ff88;
               font-size:15px; font-weight:bold; padding:5px 8px; font-family:monospace; }}
.field input:focus {{ outline:none; border-color:#00ff88; }}
.info-row {{ display:flex; justify-content:space-between; font-size:11px;
             color:#666; margin-top:6px; }}
.info-row b {{ color:#aaa; }}
.preset-btn {{ display:block; width:100%; box-sizing:border-box;
               background:#1a1a2e; border:1px solid #3a3a5a; border-radius:4px;
               color:#ccc; font-size:12px; padding:7px 10px; text-align:left;
               cursor:pointer; margin-bottom:5px; line-height:1.5; }}
.preset-btn:hover {{ border-color:#00ff88; color:#00ff88; }}
.preset-btn b {{ display:block; color:#eee; }}
.btn-main {{ display:block; width:100%; box-sizing:border-box; padding:11px;
             border:none; border-radius:6px; font-size:14px; font-weight:bold;
             cursor:pointer; margin-bottom:7px; }}
.btn-confirm {{ background:linear-gradient(135deg,#00c97a,#00ff88); color:#000; }}
.btn-reset {{ background:transparent; border:1px solid #555 !important; color:#999; }}
.cmd-box {{ background:#111128; border:1px solid #333; border-radius:4px;
            padding:8px 10px; font-family:monospace; font-size:12px; color:#00ff88;
            word-break:break-all; line-height:1.7; margin-bottom:6px; }}
.cmd-box .dim {{ color:#555; }}
.btn-copy {{ display:block; width:100%; box-sizing:border-box; background:#2a2a4a;
             border:1px solid #444; border-radius:4px; color:#ccc; font-size:12px;
             padding:6px; cursor:pointer; }}
#hint {{ font-size:12px; color:#00ff88; margin-top:6px; min-height:18px; }}
</style>
</head>
<body>
<h1>🎯 ROI 邊框確認 — {video_id}</h1>
<p style="color:#888;font-size:12px;margin:0 0 10px 0">拖曳綠框或邊角調整，確認後複製訊息貼回 chat</p>
<div id="main">
  <div id="canvas-container"><canvas id="c"></canvas></div>
  <div id="panel">
    <div class="card">
      <div class="card-title">ROI 座標（原始像素）</div>
      <div class="grid2">
        <div class="field"><label>X（左）</label><input id="ix" type="number" min="0"></div>
        <div class="field"><label>Y（上）</label><input id="iy" type="number" min="0"></div>
        <div class="field"><label>W（寬）</label><input id="iw" type="number" min="1"></div>
        <div class="field"><label>H（高）</label><input id="ih" type="number" min="1"></div>
      </div>
      <div class="info-row">
        <span>右：<b id="ix2">-</b></span>
        <span>下：<b id="iy2">-</b></span>
        <span>原始 {native_w}×{native_h}</span>
      </div>
    </div>
    <div class="card">
      <div class="card-title">快速 Preset</div>
      <button class="preset-btn" onclick="applyROI({auto_x},{auto_y},{auto_w},{auto_h})">
        <b>🤖 Auto ROI（偵測值）</b>x={auto_x}, y={auto_y}, w={auto_w}, h={auto_h}
      </button>
      <button class="preset-btn" onclick="applyROI({fb_x},{fb_y},{fb_w},{fb_h})">
        <b>📐 Config Fallback</b>x={fb_x}, y={fb_y}, w={fb_w}, h={fb_h}
      </button>
    </div>
    <div class="card">
      <div class="card-title">確認後執行指令</div>
      <div class="cmd-box">
        <span class="dim">cd slot-classifier</span><br>
        bash classify_with_roi_confirm.sh \<br>
        &nbsp;--video-id {video_id} \<br>
        &nbsp;<span id="cmd-roi">--roi {auto_x},{auto_y},{auto_w},{auto_h}</span>
      </div>
      <button class="btn-copy" id="btn-copy-cmd" onclick="copyCmd()">📋 複製指令</button>
    </div>
    <button class="btn-main btn-confirm" onclick="confirmAndCopy()">✅ 確認 ROI — 複製訊息貼到 chat</button>
    <button class="btn-main btn-reset" onclick="applyROI({auto_x},{auto_y},{auto_w},{auto_h})">↺ 重置為 Auto ROI</button>
    <div id="hint"></div>
  </div>
</div>
<script>
const NW={native_w}, NH={native_h};
const AUTO={{x:{auto_x},y:{auto_y},w:{auto_w},h:{auto_h}}};
const VIDEO_ID="{video_id}";
const HANDLE_R=7, MIN_SIZE=30;
let roi={{...AUTO}}, drag=null;

const canvas=document.getElementById('c');
const ctx=canvas.getContext('2d');
canvas.width=NW; canvas.height=NH;

const img=new Image();
img.onload=()=>draw();
img.onerror=()=>{{ ctx.fillStyle='#222'; ctx.fillRect(0,0,NW,NH);
  ctx.fillStyle='#f66'; ctx.font='36px sans-serif'; ctx.textAlign='center';
  ctx.fillText('圖片載入失敗',NW/2,NH/2); draw(); }};
img.src='{preview_img_name}';

function draw(){{
  ctx.clearRect(0,0,NW,NH);
  if(img.complete&&img.naturalWidth>0) ctx.drawImage(img,0,0,NW,NH);
  else {{ ctx.fillStyle='#111'; ctx.fillRect(0,0,NW,NH); }}
  ctx.fillStyle='rgba(0,0,0,0.45)'; ctx.fillRect(0,0,NW,NH);
  ctx.clearRect(roi.x,roi.y,roi.w,roi.h);
  if(img.complete&&img.naturalWidth>0)
    ctx.drawImage(img,roi.x,roi.y,roi.w,roi.h,roi.x,roi.y,roi.w,roi.h);
  ctx.strokeStyle='#00ff88'; ctx.lineWidth=3;
  ctx.strokeRect(roi.x,roi.y,roi.w,roi.h);
  const lbl=`${{Math.round(roi.w)}} × ${{Math.round(roi.h)}}`;
  ctx.font='bold 22px monospace';
  const tw=ctx.measureText(lbl).width;
  const lx=roi.x+(roi.w-tw)/2, ly=roi.y+roi.h-14;
  ctx.fillStyle='rgba(0,255,136,0.85)'; ctx.fillRect(lx-6,ly-20,tw+12,28);
  ctx.fillStyle='#000'; ctx.fillText(lbl,lx,ly);
  handles().forEach(h=>{{
    ctx.fillStyle='#00ff88'; ctx.strokeStyle='#1a1a2e'; ctx.lineWidth=2;
    ctx.beginPath(); ctx.rect(h.cx-HANDLE_R,h.cy-HANDLE_R,HANDLE_R*2,HANDLE_R*2);
    ctx.fill(); ctx.stroke();
  }});
  updateInputs();
}}
function handles(){{
  const {{x,y,w,h}}=roi;
  return [
    {{id:'tl',cx:x,cy:y}},{{id:'tc',cx:x+w/2,cy:y}},{{id:'tr',cx:x+w,cy:y}},
    {{id:'ml',cx:x,cy:y+h/2}},{{id:'mr',cx:x+w,cy:y+h/2}},
    {{id:'bl',cx:x,cy:y+h}},{{id:'bc',cx:x+w/2,cy:y+h}},{{id:'br',cx:x+w,cy:y+h}},
  ];
}}
function canvasPos(e){{
  const r=canvas.getBoundingClientRect();
  return {{x:(e.clientX-r.left)*NW/r.width, y:(e.clientY-r.top)*NH/r.height}};
}}
canvas.addEventListener('pointerdown',e=>{{
  const p=canvasPos(e);
  for(const h of handles()){{
    if(Math.abs(p.x-h.cx)<=HANDLE_R*2&&Math.abs(p.y-h.cy)<=HANDLE_R*2){{
      drag={{mode:h.id,sx:p.x,sy:p.y,startRoi:{{...roi}}}};
      canvas.setPointerCapture(e.pointerId); return;
    }}
  }}
  if(p.x>=roi.x&&p.x<=roi.x+roi.w&&p.y>=roi.y&&p.y<=roi.y+roi.h){{
    drag={{mode:'move',sx:p.x,sy:p.y,startRoi:{{...roi}}}};
    canvas.setPointerCapture(e.pointerId);
  }}
}});
canvas.addEventListener('pointermove',e=>{{
  if(!drag) return;
  const p=canvasPos(e), dx=p.x-drag.sx, dy=p.y-drag.sy, r=drag.startRoi;
  let {{x,y,w,h}}=r;
  if(drag.mode==='move'){{ x=r.x+dx; y=r.y+dy; }}
  else{{
    const m=drag.mode;
    if(m.includes('l')){{x=r.x+dx;w=r.w-dx;}} if(m.includes('r')) w=r.w+dx;
    if(m.includes('t')){{y=r.y+dy;h=r.h-dy;}} if(m.includes('b')) h=r.h+dy;
  }}
  if(w<MIN_SIZE){{if(drag.mode.includes('l'))x=r.x+r.w-MIN_SIZE;w=MIN_SIZE;}}
  if(h<MIN_SIZE){{if(drag.mode.includes('t'))y=r.y+r.h-MIN_SIZE;h=MIN_SIZE;}}
  x=Math.max(0,Math.min(x,NW-w)); y=Math.max(0,Math.min(y,NH-h));
  w=Math.min(w,NW-x); h=Math.min(h,NH-y);
  roi={{x,y,w,h}}; draw();
}});
canvas.addEventListener('pointerup',()=>{{ drag=null; }});

function updateInputs(){{
  document.getElementById('ix').value=Math.round(roi.x);
  document.getElementById('iy').value=Math.round(roi.y);
  document.getElementById('iw').value=Math.round(roi.w);
  document.getElementById('ih').value=Math.round(roi.h);
  document.getElementById('ix2').textContent=Math.round(roi.x+roi.w);
  document.getElementById('iy2').textContent=Math.round(roi.y+roi.h);
  document.getElementById('cmd-roi').textContent='--roi '+roiStr();
}}
['ix','iy','iw','ih'].forEach(id=>{{
  document.getElementById(id).addEventListener('change',()=>{{
    roi={{x:+document.getElementById('ix').value,y:+document.getElementById('iy').value,
         w:+document.getElementById('iw').value,h:+document.getElementById('ih').value}};
    draw();
  }});
}});
function roiStr(){{ return `${{Math.round(roi.x)}},${{Math.round(roi.y)}},${{Math.round(roi.w)}},${{Math.round(roi.h)}}`; }}
function applyROI(x,y,w,h){{ roi={{x,y,w,h}}; draw(); showHint('✅ 套用成功'); }}
function copyCmd(){{
  const cmd=`bash classify_with_roi_confirm.sh --video-id ${{VIDEO_ID}} --roi ${{roiStr()}}`;
  navigator.clipboard.writeText(cmd).then(()=>{{
    const b=document.getElementById('btn-copy-cmd');
    b.textContent='✅ 已複製'; setTimeout(()=>b.textContent='📋 複製指令',2000);
  }});
}}
function confirmAndCopy(){{
  const msg=`ROI 確認：${{roiStr()}}`;
  navigator.clipboard.writeText(msg).then(()=>{{
    showHint('✅ 已複製！貼到 chat 送出即可');
    alert(`ROI：${{roiStr()}}\\n\\n已複製：「${{msg}}」\\n\\n貼回 chat 送出即可`);
  }}).catch(()=>alert(`ROI：${{roiStr()}}\\n請手動貼到 chat：\\n${{msg}}`));
}}
function showHint(msg){{
  const el=document.getElementById('hint'); el.textContent=msg;
  setTimeout(()=>el.textContent='',2500);
}}
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Auto ROI 偵測 + 生成預覽頁")
    parser.add_argument("--video-id", required=True, metavar="ID")
    args = parser.parse_args()

    video_id = args.video_id.strip()

    # 找影片檔案
    import cv2
    video_path = None
    for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        candidate = os.path.join(INPUT_DIR, video_id + ext)
        if os.path.exists(candidate):
            video_path = candidate
            break

    if not video_path:
        print(f"[錯誤] 找不到影片：{INPUT_DIR}/{video_id}.*", file=sys.stderr)
        sys.exit(1)

    # 取得原始影像尺寸
    cap = cv2.VideoCapture(video_path)
    native_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    native_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    # debug 輸出目錄
    debug_dir = os.path.join(OUTPUT_DIR, video_id, "_debug")
    os.makedirs(debug_dir, exist_ok=True)

    # 執行 auto ROI
    print(f"[{video_id}] 偵測 Auto ROI...", flush=True)
    roi = auto_detect_game_area(video_path, debug_dir=debug_dir)

    if roi:
        rx, ry, rw, rh = roi
        print(f"[{video_id}] Auto ROI: x={rx}, y={ry}, w={rw}, h={rh}")
    else:
        print(f"[{video_id}] Auto ROI 偵測失敗，使用 fallback")
        rx, ry, rw, rh = DEFAULT_ROI_X, DEFAULT_ROI_Y, DEFAULT_ROI_W, DEFAULT_ROI_H

    # 生成 ROI 調整 HTML
    preview_img = "auto_roi_preview.jpg"
    html_path = os.path.join(debug_dir, "roi_adjust.html")
    html = ROI_HTML_TEMPLATE.format(
        video_id=video_id,
        native_w=native_w, native_h=native_h,
        auto_x=rx, auto_y=ry, auto_w=rw, auto_h=rh,
        fb_x=DEFAULT_ROI_X, fb_y=DEFAULT_ROI_Y,
        fb_w=DEFAULT_ROI_W, fb_h=DEFAULT_ROI_H,
        preview_img_name=preview_img,
    )
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[{video_id}] ROI 預覽頁：{html_path}")
    print(f"           Windows 開啟：\\\\server\\path\\{video_id}\\_debug\\roi_adjust.html")

    # 最後一行固定格式，供外層腳本解析
    print(f"ROI={rx},{ry},{rw},{rh}")


if __name__ == "__main__":
    main()
