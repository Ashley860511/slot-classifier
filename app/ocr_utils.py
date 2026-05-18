from paddleocr import PaddleOCR


def init_ocr(lang):
    return PaddleOCR(lang=lang)


def get_ocr_result(ocr_engine, img):
    if hasattr(ocr_engine, "predict"):
        return ocr_engine.predict(img)
    return ocr_engine.ocr(img)


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

