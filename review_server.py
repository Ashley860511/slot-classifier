"""
review_server.py — 地端 review 本機伺服器

用法：
  python review_server.py --video-id WildTrain
  # 然後開瀏覽器：http://localhost:8765

只依賴 Python 標準庫，無需安裝額外套件。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# apply_corrections 模組與本檔案同目錄
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from apply_corrections import apply_corrections  # noqa: E402

PORT = 8765
_VIDEO_ID: str = ""
_OUTPUT_DIR: str = ""


class ReviewHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")

        if path == "" or path == "/":
            self._redirect("/review")
            return

        if path == "/review":
            self._serve_review_html()
            return

        if path == "/status":
            self._json_response(200, {"ok": True, "video_id": _VIDEO_ID, "port": PORT})
            return

        self._text_response(404, "Not Found")

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")

        if path == "/api/apply-corrections":
            self._handle_apply_corrections()
            return

        if path == "/api/save-symbol":
            self._handle_save_symbol()
            return

        if path == "/api/sync-report-meta":
            self._handle_sync_report_meta()
            return

        if path == "/api/save-report":
            self._handle_save_report()
            return

        self._text_response(404, "Not Found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── private helpers ──────────────────────────────────────────────────────

    def _redirect(self, location: str):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _serve_review_html(self):
        html_path = os.path.join(_OUTPUT_DIR, "review.html")
        if not os.path.exists(html_path):
            self._text_response(404, f"review.html not found at {html_path}")
            return
        with open(html_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_apply_corrections(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            self._json_response(400, {"ok": False, "error": f"JSON 解析失敗：{e}"})
            return

        # 若 payload 沒有 output_dir，補上伺服器已知的 output_dir
        if not payload.get("output_dir"):
            payload["output_dir"] = _OUTPUT_DIR

        try:
            summary = apply_corrections(payload)
            self._json_response(200, {"ok": True, **summary})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _handle_save_report(self):
        """接收完整 HTML，覆寫 report.html。"""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            self._json_response(400, {"ok": False, "error": f"JSON 解析失敗：{e}"})
            return

        output_dir = payload.get("output_dir") or _OUTPUT_DIR
        html_content = payload.get("html", "")

        if not html_content:
            self._json_response(400, {"ok": False, "error": "缺少 html 內容"})
            return
        if not os.path.isdir(output_dir):
            self._json_response(400, {"ok": False, "error": f"找不到 output_dir：{output_dir}"})
            return

        report_path = os.path.join(output_dir, "report.html")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"[Report] 已儲存：{report_path}")
            self._json_response(200, {"ok": True, "path": report_path})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _handle_sync_report_meta(self):
        """接收 report.html 編輯後的 meta，更新 tags.json 與 assets.json。"""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            self._json_response(400, {"ok": False, "error": f"JSON 解析失敗：{e}"})
            return

        output_dir = payload.get("output_dir") or _OUTPUT_DIR
        if not os.path.isdir(output_dir):
            self._json_response(400, {"ok": False, "error": f"找不到 output_dir：{output_dir}"})
            return

        updated = []

        # ── 更新 tags.json ──────────────────────────────────────────────────
        tags_path = os.path.join(output_dir, "tags.json")
        if os.path.exists(tags_path):
            try:
                with open(tags_path, "r", encoding="utf-8") as f:
                    tags = json.load(f)
                changed = False
                for field in ("game", "developer", "reel_format", "payways", "max_win"):
                    if field in payload and payload[field] != "":
                        if tags.get(field) != payload[field]:
                            tags[field] = payload[field]
                            changed = True
                if changed:
                    with open(tags_path, "w", encoding="utf-8") as f:
                        json.dump(tags, f, ensure_ascii=False, indent=2)
                    updated.append("tags.json")
                    print(f"[Sync] tags.json 已更新")
            except Exception as e:
                print(f"[Sync] tags.json 更新失敗：{e}")

        # ── 更新 assets.json ────────────────────────────────────────────────
        assets_path = os.path.join(output_dir, "assets.json")
        if os.path.exists(assets_path):
            try:
                with open(assets_path, "r", encoding="utf-8") as f:
                    assets = json.load(f)
                changed = False
                for field in ("game", "cover"):
                    if field in payload and payload[field] != "":
                        if assets.get(field) != payload[field]:
                            assets[field] = payload[field]
                            changed = True
                if changed:
                    with open(assets_path, "w", encoding="utf-8") as f:
                        json.dump(assets, f, ensure_ascii=False, indent=2)
                    updated.append("assets.json")
                    print(f"[Sync] assets.json 已更新")
            except Exception as e:
                print(f"[Sync] assets.json 更新失敗：{e}")

        self._json_response(200, {"ok": True, "updated": updated})

    def _handle_save_symbol(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            self._json_response(400, {"ok": False, "error": f"JSON 解析失敗：{e}"})
            return

        output_dir = payload.get("output_dir") or _OUTPUT_DIR
        image_b64  = payload.get("image_b64", "")
        label      = payload.get("label", "").strip()

        if not image_b64:
            self._json_response(400, {"ok": False, "error": "缺少 image_b64"})
            return

        symbols_dir = os.path.join(output_dir, "symbol_table", "symbols")
        os.makedirs(symbols_dir, exist_ok=True)

        # 找下一個可用的編號 symbol_manual_NNN.png
        existing = [
            f for f in os.listdir(symbols_dir)
            if re.match(r"symbol_manual_\d+", f)
        ]
        nums = []
        for f in existing:
            m = re.search(r"symbol_manual_(\d+)", f)
            if m:
                nums.append(int(m.group(1)))
        next_num = max(nums) + 1 if nums else 1
        suffix = f"_{label}" if label else ""
        filename = f"symbol_manual_{next_num:03d}{suffix}.png"
        out_path = os.path.join(symbols_dir, filename)

        try:
            img_bytes = base64.b64decode(image_b64)
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            print(f"[Symbol] 已儲存：{out_path}")
            self._json_response(200, {"ok": True, "filename": filename, "path": out_path})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _json_response(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _text_response(self, status: int, text: str):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    global _VIDEO_ID, _OUTPUT_DIR

    parser = argparse.ArgumentParser(description="地端 review 本機伺服器")
    parser.add_argument("--video-id", required=True, help="影片 ID，例如 WildTrain")
    parser.add_argument("--port", type=int, default=PORT, help=f"監聽埠（預設 {PORT}）")
    parser.add_argument(
        "--output-root",
        default=os.path.join(_HERE, "project", "output"),
        help="output 根目錄（預設 project/output/）",
    )
    args = parser.parse_args()

    _VIDEO_ID = args.video_id
    _OUTPUT_DIR = os.path.join(args.output_root, _VIDEO_ID)

    if not os.path.isdir(_OUTPUT_DIR):
        print(f"[錯誤] 找不到 output 目錄：{_OUTPUT_DIR}")
        sys.exit(1)

    html_path = os.path.join(_OUTPUT_DIR, "review.html")
    if not os.path.exists(html_path):
        print(f"[警告] review.html 尚未生成：{html_path}")
        print("       請先執行：python app/generate_review_page.py " + _OUTPUT_DIR)

    server = HTTPServer(("", args.port), ReviewHandler)
    print(f"[Review Server] video_id = {_VIDEO_ID}")
    print(f"[Review Server] output_dir = {_OUTPUT_DIR}")
    print(f"\n   Review server: http://localhost:{args.port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Review Server] 已停止")


if __name__ == "__main__":
    main()
