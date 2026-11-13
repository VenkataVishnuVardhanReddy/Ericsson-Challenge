"""Shared helpers: hashing, content-addressable store, ffmpeg, text normalisation."""
from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from .config import STORE_DIR


# --------------------------------------------------------------------------- hashing
def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


_ws = re.compile(r"\s+")
_nonword = re.compile(r"[^\w\s]", re.UNICODE)


def norm_text(t: str) -> str:
    """Normalise text so cosmetic differences (case, spacing, punctuation, ligatures) vanish."""
    t = unicodedata.normalize("NFKC", t or "").lower()
    t = _nonword.sub(" ", t)
    return _ws.sub(" ", t).strip()


def text_hash(t: str) -> str:
    return sha256_bytes(norm_text(t).encode("utf-8"))


# --------------------------------------------------------------------------- perceptual hashing
def dhash_gray(gray: np.ndarray, size: int = 8) -> int:
    """Difference hash of a grayscale uint8 image -> 64-bit int."""
    img = Image.fromarray(gray).resize((size + 1, size), Image.BILINEAR)
    a = np.asarray(img, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def phash_img(img: Image.Image) -> str:
    import imagehash

    return str(imagehash.phash(img.convert("L"), hash_size=8))


def hamming_hex(a: str | None, b: str | None) -> int:
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


# --------------------------------------------------------------------------- object store
def store_image(img: Image.Image, max_width: int, quality: int) -> tuple[str, int]:
    """Compress an image to WebP and store it content-addressed. Returns (hash, bytes)."""
    if img.width > max_width:
        h = round(img.height * max_width / img.width)
        img = img.resize((max_width, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "WEBP", quality=quality, method=6)
    data = buf.getvalue()
    key = sha256_bytes(data)
    p = object_path(key)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return key, len(data)


def object_path(key: str) -> Path:
    return STORE_DIR / key[:2] / f"{key[2:]}.webp"


# --------------------------------------------------------------------------- ffmpeg
@lru_cache
def ffmpeg_bin() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args: list[str], **kw) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", *args]
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def probe_video(path: str | Path) -> dict:
    """Duration / size / fps via OpenCV (no ffprobe needed)."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    dur = n / fps if fps else 0
    if dur <= 0:  # fall back to ffmpeg's banner
        p = subprocess.run([ffmpeg_bin(), "-i", str(path)], capture_output=True, text=True)
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
        if m:
            dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    return {"duration": dur, "fps": fps, "width": w, "height": h}


def fmt_ts(sec: float) -> str:
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def jdump(o) -> str:
    return json.dumps(o, ensure_ascii=False)


# --------------------------------------------------------------------------- Ericsson metadata
# Ericsson document numbers look like "1/1551-LZA 701 6001 Uen", "LME-12:001234 Uen",
# "2/0363-FGB 101 1234". Revisions look like "A", "B", "PA1", "R1A".
DOC_NO_RE = re.compile(
    r"\b(?:\d{1,4}/)?\d{2,5}(?:\s\d{1,3})?-[A-Z]{2,5}\s?\d{2,4}\s?\d{2,5}(?:/\d+)?(?:\s?U[a-z]{2})?\b"
    r"|\b[A-Z]{2,4}-\d{2}:\d{4,6}(?:\s?U[a-z]{2})?\b"
)
REV_RE = re.compile(
    r"(?:\b(?:Rev(?:ision)?\.?\s*[:\-_]?\s*)|[_\-]Rev\s*)([A-Z]{1,2}\d{0,2}|R\d[A-Z]|PA\d{1,2})\b"
    r"|\bU[a-z]{2}\s*\|\s*([A-Z]{1,2}\d{0,2}|R\d[A-Z]|PA\d{1,2})\s*\|",
    re.I,
)


def find_doc_number(text: str) -> str | None:
    m = DOC_NO_RE.search(text or "")
    return _ws.sub(" ", m.group(0)).strip() if m else None


def find_revision(text: str) -> str | None:
    m = REV_RE.search(text or "")
    return (m.group(1) or m.group(2)).upper() if m else None


_copy_suffix = re.compile(r"(\s*\(\d+\)|\s*-\s*copy(\s*\(\d+\))?|^copy of\s+|_copy\d*|\s+kopia)", re.I)


def canonical_name(name: str) -> str:
    """'Deck (1).pdf' / 'Copy of Deck.pdf' / 'Deck - Copy.pdf' -> 'deck.pdf'."""
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = _copy_suffix.sub("", stem).strip()
    return f"{stem}.{ext}".lower() if ext else stem.lower()
