"""
confidence.py — 分類信心分數計算

三個等級：
  HIGH   (🟢) → 自動接受，不需人工審核
  MEDIUM (🟡) → 快速確認，大機率正確
  LOW    (🔴) → 需仔細審核，容易有誤

信心分數計算邏輯：
  - top_score：勝出類別的分數（越高越確定）
  - margin：第一名與第二名的分數差距（越大越確定）
  - category 特性：Basegame 是 fallback 類別，天生信心較低
"""

from __future__ import annotations

# 信心等級常數
CONFIDENCE_HIGH   = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW    = "low"

# 各等級對應的中文說明（用於 report）
CONFIDENCE_LABEL = {
    CONFIDENCE_HIGH:   "✅ 高信心",
    CONFIDENCE_MEDIUM: "⚠️  中信心",
    CONFIDENCE_LOW:    "❌ 低信心（需審核）",
}

# 各等級對應的 HTML 顏色
CONFIDENCE_COLOR = {
    CONFIDENCE_HIGH:   "#28a745",   # 綠
    CONFIDENCE_MEDIUM: "#ffc107",   # 黃
    CONFIDENCE_LOW:    "#dc3545",   # 紅
}


def calculate_confidence(
    final_category: str,
    top_score: float,
    category_scores: dict,
    matched_keywords: dict | None = None,
) -> tuple[str, float]:
    """
    計算分類信心等級。

    Returns:
        (level, score_0_to_1)
        level: "high" / "medium" / "low"
        score: 0.0 ~ 1.0，越高越確定
    """
    scores = sorted(
        [v for v in category_scores.values() if isinstance(v, (int, float))],
        reverse=True,
    )
    best   = float(scores[0]) if scores else 0.0
    second = float(scores[1]) if len(scores) > 1 else 0.0
    margin = best - second

    # ── 特殊信號：matched_keywords 裡有 priority_ 代表強規則命中 ─────
    priority_hit = False
    if matched_keywords:
        for kws in matched_keywords.values():
            if any("priority_" in str(kw) for kw in (kws or [])):
                priority_hit = True
                break

    # ── Basegame 是 fallback 類別，需要更嚴格的門檻 ──────────────────
    if final_category == "Basegame":
        basegame_ui = float(category_scores.get("BasegameUI", 0.0))
        if basegame_ui >= 4.0 and margin >= 3.0:
            level = CONFIDENCE_MEDIUM
        elif basegame_ui >= 2.5:
            level = CONFIDENCE_LOW
        else:
            level = CONFIDENCE_LOW
        raw = min(1.0, (basegame_ui * 0.1 + margin * 0.05))
        return level, round(raw, 3)

    # ── Other 通常代表 blocking modal 或 brand splash，中等信心 ────────
    if final_category == "Other":
        level = CONFIDENCE_MEDIUM if best >= 6.0 else CONFIDENCE_LOW
        return level, round(min(1.0, best * 0.05), 3)

    # ── 一般類別：用 top_score + margin + priority 判斷 ────────────────
    # 強信心：分高 + 領先多 + 有強規則命中
    if top_score >= 14.0 and margin >= 8.0:
        level = CONFIDENCE_HIGH
    elif top_score >= 14.0 and priority_hit:
        level = CONFIDENCE_HIGH
    elif top_score >= 10.0 and margin >= 5.0:
        level = CONFIDENCE_HIGH
    # 中等信心：分還可以但領先不多
    elif top_score >= 7.0 and margin >= 3.0:
        level = CONFIDENCE_MEDIUM
    elif top_score >= 10.0 and margin >= 2.0:
        level = CONFIDENCE_MEDIUM
    elif priority_hit and top_score >= 5.0:
        level = CONFIDENCE_MEDIUM
    # 低信心：分數低或第一名領先幅度小
    else:
        level = CONFIDENCE_LOW

    # 0~1 的連續分數（方便後續統計）
    raw = min(1.0, (top_score * 0.04 + margin * 0.03 + (0.15 if priority_hit else 0)))
    return level, round(raw, 3)


def needs_review(level: str) -> bool:
    """medium 和 low 都進 review queue。"""
    return level in (CONFIDENCE_MEDIUM, CONFIDENCE_LOW)
