"""
apply_corrections.py — 套用 review 頁面匯出的修正清單

用法：
  python apply_corrections.py corrections.json
  python apply_corrections.py --json '{"video_id":"...","corrections":[...]}'
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys


def load_payload(args) -> dict:
    if args.json:
        return json.loads(args.json)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return json.load(f)
    raise ValueError("請提供 corrections.json 檔案路徑或 --json 字串")


def apply_corrections(payload: dict) -> dict:
    output_dir = payload.get("output_dir", "")
    corrections = payload.get("corrections", [])

    if not output_dir:
        raise ValueError("payload 缺少 output_dir")
    if not os.path.isdir(output_dir):
        raise FileNotFoundError(f"找不到 output_dir：{output_dir}")

    csv_path = os.path.join(output_dir, "classification_result.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"找不到 CSV：{csv_path}")

    # 讀取 CSV
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = [dict(row) for row in reader]

    # 建立 frame_idx → row 的索引（frame_idx 可能是字串）
    idx_map: dict[str, dict] = {}
    for row in rows:
        fidx = str(row.get("frame_idx", ""))
        idx_map[fidx] = row

    moved = 0
    skipped = 0
    errors = []

    for corr in corrections:
        action = corr.get("action")
        save_path = corr.get("save_path", "")
        frame_idx = str(corr.get("frame_idx", ""))
        new_category = corr.get("new_category", "")

        if action not in ("reclassify", "exclude"):
            continue

        if not os.path.exists(save_path):
            errors.append(f"檔案不存在，跳過：{save_path}")
            skipped += 1
            continue

        if action == "exclude":
            dest_dir = os.path.join(output_dir, "excluded")
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, os.path.basename(save_path))
            # 避免覆蓋同名檔案
            dest_path = _unique_path(dest_path)
            shutil.move(save_path, dest_path)
            # 更新 CSV
            if frame_idx in idx_map:
                idx_map[frame_idx]["final_category"] = "Excluded"
                idx_map[frame_idx]["save_path"] = dest_path
            moved += 1
            print(f"[排除] {os.path.basename(save_path)} → excluded/")

        elif action == "reclassify":
            if not new_category:
                errors.append(f"reclassify 缺少 new_category，跳過 frame_idx={frame_idx}")
                skipped += 1
                continue
            dest_dir = os.path.join(output_dir, new_category)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, os.path.basename(save_path))
            dest_path = _unique_path(dest_path)
            shutil.move(save_path, dest_path)
            # 更新 CSV
            if frame_idx in idx_map:
                idx_map[frame_idx]["final_category"] = new_category
                idx_map[frame_idx]["save_path"] = dest_path
            moved += 1
            orig_cat = corr.get("original_category", "?")
            print(f"[改分類] {os.path.basename(save_path)}: {orig_cat} → {new_category}")

    # 寫回 CSV
    if moved > 0:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[CSV] 已更新：{csv_path}")

    summary = {
        "moved": moved,
        "skipped": skipped,
        "errors": errors,
        "csv_updated": moved > 0,
    }
    return summary


def _unique_path(path: str) -> str:
    """若目標路徑已存在，加上數字後綴避免覆蓋。"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = f"{base}_{i}{ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def main():
    parser = argparse.ArgumentParser(description="套用 review 頁面匯出的修正清單")
    parser.add_argument("file", nargs="?", help="corrections.json 檔案路徑")
    parser.add_argument("--json", dest="json", metavar="JSON_STRING",
                        help="直接傳入 JSON 字串（from chat）")
    args = parser.parse_args()

    if not args.file and not args.json:
        parser.print_help()
        sys.exit(1)

    try:
        payload = load_payload(args)
    except Exception as e:
        print(f"[錯誤] 讀取 payload 失敗：{e}")
        sys.exit(1)

    try:
        summary = apply_corrections(payload)
    except Exception as e:
        print(f"[錯誤] 套用修正失敗：{e}")
        sys.exit(1)

    print("\n=== 執行摘要 ===")
    print(f"  已移動：{summary['moved']} 張")
    print(f"  已跳過：{summary['skipped']} 張")
    if summary["errors"]:
        print("  警告：")
        for err in summary["errors"]:
            print(f"    - {err}")
    if summary["csv_updated"]:
        print("  CSV 已更新")
    print("================")


if __name__ == "__main__":
    main()
