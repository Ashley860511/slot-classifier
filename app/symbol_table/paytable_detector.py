"""Paytable page detection using local OpenCV/OCR with optional Claude fallback."""

from __future__ import annotations

import base64
import html
import json
import os
import re
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - handled by caller in normal use
    Image = None

from .debug_io import safe_save_debug_image, safe_write_debug_text


PAYTABLE_CV_PREFILTER_MIN_SCORE = 2.0


_PAYTABLE_SCAN_PROMPT = """\
I will show you a batch of Help/Info page screenshots from a slot machine game.
For each page, classify it as EXACTLY ONE of:

- "symbol_paytable": the page primarily shows multiple slot symbol icons arranged
  as a payout/value table, with each icon paired with payout numbers or multiplier
  values.
- "other": rules text, feature explanation, feature buy dialog, loading splash,
  game screen, or any page that does not primarily show symbol payout values.

Return ONLY valid JSON - no prose. Example:
{"0": "symbol_paytable", "1": "other", "2": "other", "3": "symbol_paytable"}
"""


def _b64_encode(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode()


def find_paytable_pages(api_key: str, all_help_images: list[Path], batch_size: int = 8) -> list[Path]:
    """
    Claude Haiku fallback scan for paytable pages.

    The main pipeline uses local CV/OCR first. This remains available for cases
    where local OCR is not installed or a later run explicitly needs AI fallback.
    """
    try:
        import anthropic
    except ImportError:
        print("  anthropic package not installed - cannot scan for paytable pages.")
        return []

    client = anthropic.Anthropic(api_key=api_key)
    matches: list[Path] = []

    for batch_start in range(0, len(all_help_images), batch_size):
        batch = all_help_images[batch_start : batch_start + batch_size]

        content: list = [{"type": "text", "text": _PAYTABLE_SCAN_PROMPT}]
        for i, p in enumerate(batch):
            content.append({"type": "text", "text": f"Page {i}:"})
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": _b64_encode(p),
                },
            })

        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": content}],
        )

        raw = resp.content[0].text.strip()
        m = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        if not m:
            continue
        try:
            verdicts = json.loads(m.group())
        except json.JSONDecodeError:
            continue

        for page_idx_str, verdict in verdicts.items():
            if str(verdict).strip().lower() != "symbol_paytable":
                continue
            actual_idx = batch_start + int(page_idx_str)
            if actual_idx < len(all_help_images):
                matches.append(all_help_images[actual_idx])
                print(f"    [{actual_idx:3d}] {all_help_images[actual_idx].name} -> PAYTABLE OK")

    return matches


def _normalize_ocr_text(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9.$/%+\-\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def init_local_ocr():
    """Initialize PaddleOCR when available; return None if local OCR is unavailable."""
    try:
        from ocr_utils import init_ocr
        return init_ocr("en")
    except Exception as exc:
        print(f"  Local OCR unavailable for paytable scan: {exc}")
        return None


def local_ocr_items(ocr_engine, pil_img) -> list:
    if ocr_engine is None or pil_img is None:
        return []
    try:
        import numpy as np
        from ocr_utils import extract_ocr_items, get_ocr_result

        arr = np.array(pil_img.convert("RGB"))
        result = get_ocr_result(ocr_engine, arr)
        return extract_ocr_items(result)
    except Exception as exc:
        print(f"    [ocr] failed: {exc}")
        return []


def paytable_score_from_ocr(ocr_items) -> tuple[float, list[str]]:
    joined = " ".join(
        _normalize_ocr_text(text)
        for _box, text, score in (ocr_items or [])
        if score >= 0.45
    )
    reasons: list[str] = []
    score = 0.0

    if any(term in joined for term in [
        "symbol payout", "payout values", "symbol pays", "symbol pay",
        "symbols pay anywhere", "symbols pay", "same symbol",
    ]):
        score += 4.0
        reasons.append("symbol_payout_title")
    if any(term in joined for term in ["multiplier symbol", "multiplier symbols"]):
        score += 3.0
        reasons.append("multiplier_symbols")
    elif re.search(r"\bpay\s*table\b|\bpaytable\b", joined):
        score += 1.0
        reasons.append("paytable_word")
    if any(term in joined for term in ["wild symbol", "scatter symbol", "wild", "scatter"]):
        score += 1.5
        reasons.append("wild_scatter_terms")
    if any(term in joined for term in ["paylines", "pay lines", "ways", "full"]):
        score += 1.0
        reasons.append("payout_layout_terms")

    numeric_values = re.findall(r"\b\d{1,4}(?:[,.]\d+)?\b", joined)
    payout_pairs = re.findall(r"\b\d{1,3}\s*-\s*\d{1,4}(?:[,.]\d+)?\b", joined)
    full_values = re.findall(r"\bfull\s+\d{1,4}(?:[,.]\d+)?\b", joined)
    if len(numeric_values) >= 10:
        score += min(3.0, len(numeric_values) / 8.0)
        reasons.append(f"many_numbers:{len(numeric_values)}")
    if len(payout_pairs) >= 3:
        score += 3.0
        reasons.append(f"payout_pairs:{len(payout_pairs)}")
    if len(full_values) >= 2:
        score += 2.0
        reasons.append(f"full_values:{len(full_values)}")

    return score, reasons


def _has_game_rules_text(joined: str) -> bool:
    return any(term in joined for term in [
        "game rules", "tap to", "wallet balance", "bet amount", "auto spin",
        "turbo spin", "more settings", "game history", "sound on", "sound off",
    ])


def paytable_score_from_cv(dialog_img, detect_icon_components_in_dialog=None) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    if dialog_img is None:
        return score, reasons

    try:
        import numpy as np
    except Exception:
        return score, reasons

    arr = np.array(dialog_img.convert("RGB"))
    if arr.size == 0:
        return score, reasons

    arr_f = arr.astype(np.float32)
    val = arr_f.max(axis=2)
    sat = arr_f.max(axis=2) - arr_f.min(axis=2)
    dark_plain_ratio = float(np.mean((val <= 110) & (sat <= 105)))
    dark_ratio = float(np.mean(val <= 115))
    if dark_plain_ratio >= 0.30 or dark_ratio >= 0.42:
        score += 1.0
        reasons.append(f"dark_help_bg:{dark_plain_ratio:.2f}")

    component_boxes = []
    if detect_icon_components_in_dialog is not None:
        component_boxes = detect_icon_components_in_dialog(dialog_img)
    plausible_boxes = [
        b for b in component_boxes
        if 18 <= b[2] <= max(180, dialog_img.width * 0.25)
        and 18 <= b[3] <= max(180, dialog_img.height * 0.25)
    ]
    if len(plausible_boxes) >= 6:
        score += 3.0
        reasons.append(f"icon_components:{len(plausible_boxes)}")
    elif len(plausible_boxes) >= 3:
        score += 1.5
        reasons.append(f"some_icon_components:{len(plausible_boxes)}")

    chroma = arr.max(axis=2) - arr.min(axis=2)
    yellowish = ((arr[:, :, 0] > 120) & (arr[:, :, 1] > 85) & (arr[:, :, 2] < 155) & (chroma > 20))
    yellow_ratio = float(yellowish.mean())
    if yellow_ratio >= 0.012:
        score += 0.8
        reasons.append("yellow_payout_text")

    light_text = (val > 135) & (sat < 80)
    paragraph_rows = int(np.sum(light_text.mean(axis=1) > 0.16))
    if paragraph_rows >= max(24, int(dialog_img.height * 0.10)) and yellow_ratio < 0.020:
        score -= 2.0
        reasons.append("paragraph_rules_layout")

    return score, reasons


def _icon_component_count_from_reasons(reasons: list[str]) -> int:
    """Extract the local CV icon-count signal from paytable scan reasons."""
    for reason in reasons or []:
        m = re.search(r"(?:some_)?icon_components:(\d+)", str(reason))
        if m:
            return int(m.group(1))
    return 0


def is_local_paytable_page(
    img_path: Path,
    ocr_engine=None,
    debug_dir: Path | None = None,
    auto_crop_dialog=None,
    detect_icon_components_in_dialog=None,
):
    if Image is None:
        return False, 0.0, ["pillow_unavailable"]

    dialog_img = None
    if auto_crop_dialog is not None:
        dialog_img, _x, _y = auto_crop_dialog(img_path)
    source = dialog_img if dialog_img is not None else Image.open(img_path)

    cv_score, cv_reasons = paytable_score_from_cv(source, detect_icon_components_in_dialog)
    should_scan_symbol_explanation = (
        cv_score >= 1.6
        and "yellow_payout_text" in cv_reasons
        and any(str(reason).startswith("dark_help_bg") for reason in cv_reasons)
    )
    should_scan_sparse_table = (
        cv_score >= 0.5
        and any(str(reason).startswith("some_icon_components") for reason in cv_reasons)
        and any(str(reason).startswith("dark_help_bg") for reason in cv_reasons)
    )
    if cv_score < PAYTABLE_CV_PREFILTER_MIN_SCORE and not (should_scan_symbol_explanation or should_scan_sparse_table):
        reasons = [f"cv_prefilter_skip:{cv_score:.1f}"] + cv_reasons
        if debug_dir:
            safe_save_debug_image(source, debug_dir / f"cv_skip_{img_path.stem}.jpg", format="JPEG", quality=88)
        return False, cv_score, reasons

    if ocr_engine is None:
        # Local icon export should still work in environments where PaddleOCR is
        # not installed.  A strong CV-only page has a dark help/paytable panel,
        # many compact icon components, and yellow payout text.  This is less
        # precise than OCR, but much better than falling back to every Help page.
        ok = cv_score >= 4.6
        if debug_dir:
            label = "paytable_cv" if ok else "other_cv"
            safe_save_debug_image(source, debug_dir / f"{label}_{img_path.stem}.jpg", format="JPEG", quality=88)
        return ok, cv_score, ["cv_only"] + cv_reasons

    ocr_items = local_ocr_items(ocr_engine, source)
    ocr_score, ocr_reasons = paytable_score_from_ocr(ocr_items)
    total = ocr_score + cv_score

    joined = " ".join(
        _normalize_ocr_text(text)
        for _box, text, score in (ocr_items or [])
        if score >= 0.45
    )
    has_buy_modal = "buy feature" in joined or "feature buy" in joined or ("cost" in joined and "quantity" in joined)
    has_game_rules = _has_game_rules_text(joined)
    has_symbol_payout_title = any(term in joined for term in [
        "symbol payout", "payout values", "symbol pays", "symbol pay",
        "symbols pay anywhere", "symbols pay", "same symbol",
    ])
    has_multiplier_symbols = any(term in joined for term in ["multiplier symbol", "multiplier symbols"])
    has_symbol_terms = any(reason in ocr_reasons for reason in ("wild_scatter_terms", "multiplier_symbols"))
    has_yellow_symbol_text = any(reason == "yellow_payout_text" for reason in cv_reasons)
    has_paytable_word = bool(re.search(r"\bpay\s*table\b|\bpaytable\b", joined))
    has_values = any(
        str(reason).startswith(("many_numbers", "payout_pairs", "full_values"))
        for reason in ocr_reasons
    )
    icon_component_count = _icon_component_count_from_reasons(cv_reasons)
    ok = (
        not has_buy_modal
        and not (
            has_game_rules
            and not (has_symbol_payout_title or has_multiplier_symbols or has_paytable_word)
            and cv_score < 4.0
        )
        and (
            (has_symbol_payout_title and total >= 5.5)
            or (has_multiplier_symbols and total >= 4.8)
            or (has_paytable_word and ocr_score >= 4.0 and cv_score >= 3.0 and total >= 7.0)
            or (has_paytable_word and has_values and icon_component_count >= 8 and total >= 5.5)
            or (has_paytable_word and has_values and icon_component_count >= 4 and total >= 4.3)
            or (has_paytable_word and has_symbol_terms and has_yellow_symbol_text and total >= 4.0)
            or (ocr_score >= 4.0 and cv_score >= 3.0 and total >= 7.0)
        )
    )

    if debug_dir:
        label = "paytable" if ok else "other"
        safe_save_debug_image(source, debug_dir / f"{label}_{img_path.stem}.jpg", format="JPEG", quality=88)

    return ok, total, ocr_reasons + cv_reasons


def find_paytable_pages_local(
    all_help_images: list[Path],
    debug_dir: Path | None = None,
    auto_crop_dialog=None,
    detect_icon_components_in_dialog=None,
    max_pages: int = 10,
) -> list[Path]:
    """Detect paytable pages using local OCR + OpenCV, no API call."""
    if not all_help_images:
        return []

    ocr_engine = init_local_ocr()
    scored = []
    cv_skipped = 0
    ocr_scanned = 0
    for idx, p in enumerate(all_help_images):
        try:
            ok, score, reasons = is_local_paytable_page(
                p,
                ocr_engine,
                debug_dir,
                auto_crop_dialog=auto_crop_dialog,
                detect_icon_components_in_dialog=detect_icon_components_in_dialog,
            )
        except Exception as exc:
            print(f"    [{idx:3d}] {p.name} -> local scan failed: {exc}")
            continue
        if reasons and str(reasons[0]).startswith("cv_prefilter_skip"):
            cv_skipped += 1
        else:
            ocr_scanned += 1
        if ok:
            scored.append((score, idx, p, reasons))
            print(f"    [{idx:3d}] {p.name} -> PAYTABLE local score={score:.1f} ({', '.join(reasons[:4])})")

    print(
        f"  Paytable prefilter: CV skipped {cv_skipped}, "
        f"OCR scanned {ocr_scanned}/{len(all_help_images)}, candidates {len(scored)}"
    )

    page_limit = max(1, int(max_pages))

    def is_primary_help_page(item):
        parts = {part.lower() for part in item[2].parts}
        return "low_score" not in parts

    def is_strong_symbol_paytable(item):
        score, _idx, _path, reasons = item
        reason_text = " ".join(str(r) for r in (reasons or []))
        has_title = "symbol_payout_title" in reason_text or "paytable_word" in reason_text
        has_symbols = "wild_scatter_terms" in reason_text or "multiplier_symbols" in reason_text
        has_values = (
            "many_numbers" in reason_text
            or "payout_pairs" in reason_text
            or "full_values" in reason_text
        )
        return score >= 9.5 and has_title and has_symbols and has_values

    def is_strong_secondary_paytable(item):
        # low_score is valuable as a fallback, but it also contains transition
        # overlays and webpage fragments.  Require an explicit Paytable label
        # so PP rule pages such as "symbols pay anywhere" do not flood output.
        score, _idx, _path, reasons = item
        reason_text = " ".join(str(r) for r in (reasons or []))
        icon_component_count = _icon_component_count_from_reasons(reasons)
        has_values = (
            "many_numbers" in reason_text
            or "payout_pairs" in reason_text
            or "full_values" in reason_text
        )
        is_symbol_explanation = (
            "wild_scatter_terms" in reason_text
            and "yellow_payout_text" in reason_text
        )
        return (
            score >= 4.0
            and "paytable_word" in reason_text
            and (
                "wild_scatter_terms" in reason_text
                or "multiplier_symbols" in reason_text
                or icon_component_count >= 4
            )
            and (has_values or is_symbol_explanation)
        )

    def sample_sequence(items, limit):
        if limit <= 0 or not items:
            return []
        items = sorted(items, key=lambda item: item[1])
        if len(items) <= limit:
            return list(items)
        # Paytables often appear as a scroll sequence. Taking only the highest
        # scores over-selects repeated top pages and can miss later low-card
        # pages (Q/J/10/9). Sample across the whole detected sequence instead.
        step = (len(items) - 1) / float(limit - 1) if limit > 1 else 1.0
        indices = sorted(set(round(i * step) for i in range(limit)))
        return [items[i] for i in indices]

    def append_unique(target, items):
        seen = {item[2].resolve() for item in target}
        seen_names = {item[2].name for item in target}
        for item in items:
            path = item[2].resolve()
            # Prefer the final Help copy for identical filenames, but do not let
            # a low_score-only high-value paytable disappear from extraction.
            if path in seen:
                continue
            if item[2].name in seen_names and not is_strong_symbol_paytable(item):
                continue
            target.append(item)
            seen.add(path)
            seen_names.add(item[2].name)

    primary_scored = [item for item in scored if is_primary_help_page(item)]
    secondary_scored = [item for item in scored if not is_primary_help_page(item)]
    selected = []

    # Strong symbol-paytable pages should be preserved even when they live in
    # low_score/Help or when sequence sampling would otherwise skip them.
    strong_pages = sorted(
        [item for item in secondary_scored if is_strong_secondary_paytable(item)],
        key=lambda item: item[1],
    )
    secondary_limit = min(len(strong_pages), max(8, page_limit // 3)) if strong_pages else 0

    # Keep a chronological backbone from primary Help when available, but reserve
    # space for low_score paytable pages.  Otherwise final Help can occupy the
    # full cap and the fallback pages are scanned but discarded.
    primary_limit = max(0, page_limit - secondary_limit) if primary_scored else 0
    append_unique(selected, sample_sequence(primary_scored, primary_limit))
    append_unique(selected, sample_sequence(strong_pages, secondary_limit))

    if not selected:
        append_unique(selected, sample_sequence(scored, page_limit))

    selected = sorted(selected, key=lambda item: item[1])[:page_limit]
    return [p for _score, _idx, p, _reasons in selected]


def write_paytable_candidates_debug(video_dir: Path, scan_images: list[Path], selected_pages: list[Path]):
    selected = {p.resolve() for p in selected_pages}
    rows = []
    for p in scan_images:
        rel = os.path.relpath(p, video_dir)
        chosen = p.resolve() in selected
        rows.append(
            "<tr>"
            f"<td>{html.escape(rel)}</td>"
            f"<td>{'PAYTABLE' if chosen else ''}</td>"
            f"<td><img src=\"{html.escape(rel.replace(os.sep, '/'))}\" loading=\"lazy\"></td>"
            "</tr>"
        )
    out = video_dir / "symbol_table" / "paytable_candidates_debug.html"
    safe_write_debug_text(
        out,
        """
<!doctype html>
<meta charset="utf-8">
<style>
body{font-family:Arial,sans-serif;background:#f6f6f6;color:#222}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;vertical-align:top}
img{max-width:260px;max-height:220px}
td:nth-child(2){font-weight:bold;color:#07823a}
</style>
<h1>Paytable candidates debug</h1>
<table><tr><th>Image</th><th>Local decision</th><th>Preview</th></tr>
""" + "\n".join(rows) + "\n</table>\n",
    )
    print(f"  Paytable debug -> {out}")
