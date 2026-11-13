"""Link video keyframes to deck slides (single source of truth) and transcript to keyframes.

Frame -> slide matching combines
* text F1 between the frame's OCR text and the slide's text (robust to webcam overlays,
  letterboxing and footer differences), and
* perceptual-hash similarity of the images.
Then a deck-level vote picks the deck (and revision!) that was actually presented, so a
slide that exists identically in Rev A and Rev B is attributed to the right revision.
"""
from __future__ import annotations

from collections import defaultdict

from PIL import Image

from . import config as C
from . import db
from .dedup import _text_sim
from .util import hamming_hex


def match_keyframes(keyframes: list[dict]) -> dict:
    """keyframes: [{id, ocr_text, phash, is_slide}] -> {kf_id: (slide_id, score)} and chosen deck."""
    slides = db.q("""SELECT s.id, s.file_id, s.page_no, s.text, s.phash, s.content_id, f.name, f.revision,
                            COALESCE(src.governed, 1) AS governed
                     FROM slides s JOIN files f ON f.id=s.file_id LEFT JOIN sources src ON src.id=f.source_id""")
    if not slides or not keyframes:
        return {"links": {}, "deck": None}
    cand: dict[int, list[tuple[float, dict]]] = {}
    for k in keyframes:
        scored = []
        for s in slides:
            ts = _text_sim(k["ocr_text"] or "", s["text"] or "")
            vs = 1 - hamming_hex(k["phash"], s["phash"]) / 64
            score = 0.75 * ts + 0.25 * vs if (k["ocr_text"] and s["text"]) else vs * 0.9
            if score >= C.FRAME_MATCH_MIN * 0.8:
                scored.append((score, s))
        # Prefer higher score, then governed source-of-truth (SharePoint over personal OneDrive)
        scored.sort(key=lambda x: (-round(x[0], 4), -x[1]["governed"], len(x[1]["name"])))
        cand[k["id"]] = scored[:25]
    # deck vote: which file explains the recording best? (tiny bonus for governed source of truth)
    deck_score = defaultdict(float)
    deck_gov = {}
    for kid, sc in cand.items():
        seen = set()
        for score, s in sc:
            if s["file_id"] not in seen:
                deck_score[s["file_id"]] += score
                deck_gov[s["file_id"]] = s["governed"]
                seen.add(s["file_id"])
    deck = max(deck_score, key=lambda fid: (round(deck_score[fid], 3), deck_gov.get(fid, 0))) if deck_score else None
    links = {}
    for kid, sc in cand.items():
        if not sc:
            continue
        best_score = sc[0][0]
        pick = next(((score, s) for score, s in sc if s["file_id"] == deck and score >= best_score - 0.04), sc[0])
        if pick[0] >= C.FRAME_MATCH_MIN:
            links[kid] = (pick[1]["id"], round(pick[0], 3))
    return {"links": links, "deck": deck, "deck_scores": dict(deck_score)}


def keyframe_for_time(kfs: list[dict], t: float) -> int | None:
    best, best_d = None, 1e9
    for k in kfs:
        for a, b in k["intervals"]:
            if a <= t <= b:
                return k["id"]
            d = min(abs(t - a), abs(t - b))
            if d < best_d:
                best, best_d = k["id"], d
    return best


def dominant_colours(img: Image.Image, n: int = 4) -> list[str]:
    q = img.convert("RGB").resize((160, 90)).quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: n * 3]
    counts = sorted(q.getcolors(), reverse=True)
    out = []
    for _, idx in counts[:n]:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return out


def slide_prompt(img: Image.Image, ocr_res: dict) -> str:
    """A text prompt from which the slide can be recreated (by a human, python-pptx or an image model)."""
    lines = ocr_res.get("lines", [])
    title = ocr_res.get("title", "")
    body = [l for l in lines if l["text"] != title]
    cols = dominant_colours(img)
    w = img.width
    left = sum(1 for l in body if l["x"] < w * 0.5)
    layout = "two-column" if body and 0.3 < left / len(body) < 0.7 and len(body) > 6 else "single-column"
    import numpy as np

    g = np.asarray(img.convert("L").resize((96, 54)), dtype=np.float32)
    edges = (np.abs(np.diff(g, axis=1)) > 25).mean()
    visual = "contains a diagram/chart or picture" if edges > 0.06 and len(body) < 12 else "mostly text"
    out = [f"Create a 16:9 presentation slide ({layout}, {visual}).",
           f"Background colour {cols[0]}; accent colours {', '.join(cols[1:])}." if cols else "",
           f'Title: "{title}"' if title else "No title.",
           "Content, top to bottom:"]
    out += [f"- {l['text']}" for l in body[:30]]
    return "\n".join(x for x in out if x)
