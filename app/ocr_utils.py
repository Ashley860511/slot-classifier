import cv2
import numpy as np
from paddleocr import PaddleOCR

# OCR 輸入最大邊長（px）；超過此值會先縮圖再做 OCR，box 座標自動還原回原始比例
OCR_MAX_SIDE = 480


def init_ocr(lang):
    return PaddleOCR(
        lang=lang,
        use_angle_cls=False,   # slot 畫面文字均為橫式，跳過角度分類節省約 30% 時間
        cpu_threads=2,         # 限制 Paddle 佔用的核心數，避免吃滿全機 CPU
        show_log=False,        # 關閉大量 init log
    )


def get_ocr_result(ocr_engine, img):
    """OCR with auto downscale: 若輸入圖超過 OCR_MAX_SIDE，先縮圖再還原 box 座標。"""
    h, w = img.shape[:2]
    scale = min(1.0, OCR_MAX_SIDE / max(h, w, 1))

    if scale < 0.99:
        small = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))))
        raw = _run_ocr(ocr_engine, small)
        return _rescale_boxes(raw, 1.0 / scale)

    return _run_ocr(ocr_engine, img)


def _run_ocr(ocr_engine, img):
    if hasattr(ocr_engine, "predict"):
        return ocr_engine.predict(img)
    return ocr_engine.ocr(img)


def _rescale_boxes(result, factor):
    """將 OCR 結果中的 box 座標乘以 factor（還原縮圖前的比例）。"""
    if not result:
        return result

    # PaddleOCR 回傳格式可能是 [[box, (text, score)], ...] 或 [[[box,(text,score)], ...]]
    # 只處理最外層是 list of item 的情況
    def scale_item(item):
        try:
            box, info = item[0], item[1]
            scaled_box = [[pt[0] * factor, pt[1] * factor] for pt in box]
            return [scaled_box, info]
        except Exception:
            return item

    # 判斷是否有多餘的外層包裝
    if (
        len(result) == 1
        and isinstance(result[0], list)
        and result[0]
        and isinstance(result[0][0], list)
    ):
        return [[scale_item(item) for item in result[0]]]

    return [scale_item(item) for item in result]


def extract_ocr_items(result):
    items = []
    if not result:
        return items

    if len(result) == 1 and isinstance(result[0], list):
        maybe_inner = result[0]
        if maybe_inner and isinstance(maybe_inner[0], list):
            result = maybe_inner

    for item in result:
        try:
            if len(item) >= 2 and isinstance(item[1], (list, tuple)):
                box = item[0]
                text = str(item[1][0]).strip()
                score = float(item[1][1])
                items.append((box, text, score))
        except Exception:
            continue

    return items

