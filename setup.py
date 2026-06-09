#!/usr/bin/env python3
"""
setup.py — Slot Classifier 一鍵環境建立腳本

使用方式（只需要系統有 Python 3.10）：
    python setup.py

做的事：
  1. 確認 Python 版本
  2. 建立 .venv 虛擬環境
  3. 安裝 requirements.txt 所有套件
  4. 驗證安裝結果
  5. 建立 project/input_videos/ 目錄
  6. 印出後續使用說明
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
VENV_DIR = HERE / ".venv"
REQ_FILE = HERE / "requirements.txt"

# ──────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────

def step(msg: str):
    print(f"\n{'─'*60}")
    print(f"  {msg}")
    print(f"{'─'*60}")

def ok(msg: str):
    print(f"  ✅ {msg}")

def warn(msg: str):
    print(f"  ⚠️  {msg}")

def fail(msg: str):
    print(f"  ❌ {msg}")

def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)

# ──────────────────────────────────────────────
# Step 1: Python 版本確認
# ──────────────────────────────────────────────

def check_python():
    step("Step 1 / 5 — 確認 Python 版本")
    major, minor = sys.version_info[:2]
    ver = f"{major}.{minor}"
    print(f"  Python 版本：{sys.version.split()[0]}")
    print(f"  執行路徑：{sys.executable}")

    if major != 3 or minor < 9:
        fail(f"需要 Python 3.9 以上（目前 {ver}）")
        fail("請安裝 Python 3.10：https://www.python.org/downloads/")
        sys.exit(1)

    if minor != 10:
        warn(f"建議使用 Python 3.10（目前 {ver}），其他版本可能與 PaddleOCR 有相容問題")
    else:
        ok(f"Python {ver} — 版本正確")

# ──────────────────────────────────────────────
# Step 2: 建立虛擬環境
# ──────────────────────────────────────────────

def create_venv():
    step("Step 2 / 5 — 建立虛擬環境 (.venv)")

    if VENV_DIR.exists():
        ok(".venv 已存在，跳過建立")
        return

    print(f"  建立中：{VENV_DIR}")
    result = run([sys.executable, "-m", "venv", str(VENV_DIR)])
    if result.returncode != 0:
        fail("虛擬環境建立失敗")
        sys.exit(1)
    ok(".venv 建立完成")

# ──────────────────────────────────────────────
# Step 3: 取得 venv Python 路徑
# ──────────────────────────────────────────────

def get_venv_python() -> Path:
    if platform.system() == "Windows":
        py = VENV_DIR / "Scripts" / "python.exe"
    else:
        py = VENV_DIR / "bin" / "python"

    if not py.exists():
        fail(f"找不到 venv Python：{py}")
        sys.exit(1)
    return py

# ──────────────────────────────────────────────
# Step 4: 安裝套件
# ──────────────────────────────────────────────

def install_packages(venv_python: Path):
    step("Step 3 / 5 — 安裝套件（約 5～15 分鐘）")

    if not REQ_FILE.exists():
        fail(f"找不到 requirements.txt：{REQ_FILE}")
        sys.exit(1)

    # 升級 pip
    print("  升級 pip...")
    run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("  安裝套件中（這需要一段時間，請耐心等待）...")
    result = run(
        [str(venv_python), "-m", "pip", "install", "-r", str(REQ_FILE)],
        capture_output=False,
    )

    if result.returncode != 0:
        fail("套件安裝失敗")
        print()
        print("  常見解決方式：")
        print("  1. 若路徑含中文或超長（Windows）→ 把專案移到 D:\\slot-classifier")
        print("  2. 網路問題 → 關閉 VPN 後重試")
        print("  3. 單獨安裝：")
        print("     pip install paddlepaddle==2.6.2")
        print("     pip install paddleocr==2.7.3")
        sys.exit(1)

    ok("套件安裝完成")

# ──────────────────────────────────────────────
# Step 5: 驗證環境
# ──────────────────────────────────────────────

def verify_env(venv_python: Path) -> bool:
    step("Step 4 / 5 — 驗證安裝結果")

    result = run(
        [str(venv_python), str(HERE / "check_environment.py")],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        fail("環境驗證失敗，請查看上方錯誤訊息")
        return False

    ok("環境驗證通過")
    return True

# ──────────────────────────────────────────────
# Step 5: 建立必要目錄
# ──────────────────────────────────────────────

def create_dirs():
    step("Step 5 / 5 — 建立目錄結構")

    dirs = [
        HERE / "project" / "input_videos",
        HERE / "project" / "output",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        ok(f"確認目錄：{d.relative_to(HERE)}")

# ──────────────────────────────────────────────
# 完成：印出後續說明
# ──────────────────────────────────────────────

def print_next_steps(venv_python: Path):
    is_windows = platform.system() == "Windows"
    py_path = ".venv\\Scripts\\python" if is_windows else ".venv/bin/python"
    bash_note = "（Windows 請用 Git Bash 或 WSL）" if is_windows else ""

    print()
    print("=" * 60)
    print("  ✅ 環境安裝完成！")
    print("=" * 60)
    print()
    print("  ── 後續操作方式 ──────────────────────────────────")
    print()
    print("  【方式 A】使用 Claude Code（需要 Node.js）")
    print("    1. npm install -g @anthropic/claude-code")
    print("    2. claude login")
    print(f"    3. cd {HERE}")
    print("       claude")
    print("    4. 輸入：幫我分析 WildTrain")
    print()
    print("  【方式 B】手動執行腳本 " + bash_note)
    print("    1. 把影片放到 project/input_videos/WildTrain.mp4")
    print("    2. bash classify_with_roi_confirm.sh --video-id WildTrain")
    print("    3. 瀏覽器確認 ROI → 回覆座標後繼續")
    print("    4. bash classify_with_roi_confirm.sh --video-id WildTrain --roi x,y,w,h")
    print("    5. 瀏覽器開啟 http://localhost:8765 進行人工審核")
    print()
    print("  ── 文件 ──────────────────────────────────────────")
    print("  README.md                       — 完整使用說明")
    print("  docs/onboarding_new_user.html   — 新使用者步驟指南")
    print("  docs/slot_classifier_usage_guide.html — 詳細操作說明")
    print()

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    print()
    print("=" * 60)
    print("  Slot Classifier — 環境安裝程式")
    print("=" * 60)
    print(f"  專案路徑：{HERE}")
    print(f"  作業系統：{platform.system()} {platform.release()}")

    check_python()
    create_venv()
    venv_python = get_venv_python()
    install_packages(venv_python)
    ok_env = verify_env(venv_python)
    create_dirs()
    print_next_steps(venv_python)

    if not ok_env:
        sys.exit(1)

if __name__ == "__main__":
    main()
