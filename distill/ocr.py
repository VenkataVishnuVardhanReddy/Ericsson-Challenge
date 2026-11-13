"""OCR for slide frames (RapidOCR = PaddleOCR models on ONNX runtime, CPU, pip-only)."""
from __future__ import annotations

import numpy as np
from PIL import Image

_engine = None


def _get():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


def ocr(img: Image.Image, max_width: int = 1600) -> dict:
    """Return {'text', 'lines':[{text,box,score,h}], 'title'} in reading order."""
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)))
    arr = np.asarray(img.convert("RGB"))[:, :, ::-1]  # BGR
    try:
        res, _ = _get()(arr)
    except Exception:
        res = None
    lines = []
    for box, text, score in res or []:
        if float(score) < 0.5 or not text.strip():
            continue
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        lines.append({"text": text.strip(), "x": min(xs), "y": min(ys), "h": max(ys) - min(ys), "score": float(score)})
    # reading order: group into rows by y, then left to right
    lines.sort(key=lambda l: (round(l["y"] / max(8.0, l["h"] * 0.6)), l["x"]))
    text = "\n".join(l["text"] for l in lines)
    title = ""
    if lines:
        top = [l for l in lines if l["y"] < img.height * 0.35] or lines
        title = max(top, key=lambda l: l["h"])["text"]
    return {"text": text, "lines": lines, "title": title}


def slide_likeness(img: Image.Image, ocr_res: dict) -> float:
    """Heuristic 0..1: is this a slide/screen share (text, flat colours) or a camera image?"""
    small = np.asarray(img.convert("L").resize((160, 90)), dtype=np.float32)
    # slides have large flat areas -> many near-zero gradients
    gx = np.abs(np.diff(small, axis=1)).mean()
    gy = np.abs(np.diff(small, axis=0)).mean()
    flat = float(((np.abs(np.diff(small, axis=1)) < 2).mean()))
    chars = len(ocr_res.get("text", ""))
    score = 0.5 * min(1.0, chars / 60) + 0.5 * flat
    if gx + gy > 25:
        score *= 0.7
    return round(score, 3)
