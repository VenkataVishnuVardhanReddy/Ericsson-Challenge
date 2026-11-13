"""Central configuration for Distill.

All paths are relative to the project root so the whole tool can be zipped and moved.
Everything is tunable via environment variables so we can adjust thresholds live on
Ericsson's sample data without code changes.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DISTILL_DATA", ROOT / "data"))
STORE_DIR = DATA_DIR / "store"          # content-addressable object store (slides, frames)
PACKETS_DIR = DATA_DIR / "packets"      # one "knowledge packet" per recording
RECREATED_DIR = DATA_DIR / "recreated"  # videos rebuilt from distilled data
RESCUE_DIR = DATA_DIR / "rescued"       # unique slides rescued from leaver files
MODELS_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "distill.db"

for _d in (DATA_DIR, STORE_DIR, PACKETS_DIR, RECREATED_DIR, RESCUE_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---- Security: Allowed roots ----------------------------------------------
_allowed_env = os.environ.get("DISTILL_ALLOWED_ROOTS")
if _allowed_env:
    ALLOWED_ROOTS = [Path(p.strip()).resolve() for p in _allowed_env.split(";") if p.strip()]
else:
    ALLOWED_ROOTS = [(ROOT / "sample_data").resolve(), (DATA_DIR / "uploads").resolve()]


def is_allowed_path(path: Path | str) -> bool:
    try:
        resolved = Path(path).resolve()
        return any(resolved == root or root in resolved.parents for root in ALLOWED_ROOTS)
    except Exception:
        return False


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


# ---- Speech to text -------------------------------------------------------
WHISPER_MODEL = os.environ.get("DISTILL_WHISPER", "base")   # tiny|base|small|medium|large-v3
WHISPER_THREADS = _i("DISTILL_WHISPER_THREADS", os.cpu_count() or 4)
WHISPER_LANGUAGE = os.environ.get("DISTILL_LANG") or None   # None = auto detect

# ---- Keyframe extraction --------------------------------------------------
SAMPLE_FPS = _f("DISTILL_SAMPLE_FPS", 1.0)          # frames analysed per second of video
ANALYSIS_WIDTH = _i("DISTILL_ANALYSIS_WIDTH", 640)  # analysis resolution
CHANGE_THRESHOLD = _f("DISTILL_CHANGE_THR", 0.020)   # fraction of static pixels changed (>20 luma)
MIN_STABLE_SEC = _f("DISTILL_MIN_STABLE", 2.0)      # a screen must stay this long to be a keyframe
SAME_SLIDE_HAMMING = _i("DISTILL_SAME_SLIDE_HAM", 4)  # pHash distance helper for slide similarity
KEYFRAME_MAX_WIDTH = _i("DISTILL_KF_WIDTH", 1280)
KEYFRAME_WEBP_QUALITY = _i("DISTILL_KF_Q", 70)

# ---- Document dedup -------------------------------------------------------
SLIDE_RENDER_WIDTH = _i("DISTILL_SLIDE_W", 960)
IDENTICAL_HAMMING = _i("DISTILL_IDENT_HAM", 4)     # pHash distance for visually identical slides
NEAR_HAMMING = _i("DISTILL_NEAR_HAM", 14)          # pHash distance for "modified" slides
NEAR_TEXT_SIM = _f("DISTILL_NEAR_TEXT", 0.70)      # text similarity for "modified" slides
FRAME_MATCH_MIN = _f("DISTILL_FRAME_MATCH", 0.55)  # min score to link a video frame to a deck slide

# ---- Search ---------------------------------------------------------------
EMBED_MODEL = os.environ.get(
    "DISTILL_EMBED", "sentence-transformers/all-MiniLM-L6-v2"
)

# ---- Optional local LLM (free, via Ollama) --------------------------------
OLLAMA_URL = os.environ.get("DISTILL_OLLAMA", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("DISTILL_OLLAMA_MODEL", "qwen2.5:3b")

# ---- Audio tier -----------------------------------------------------------
OPUS_BITRATE = os.environ.get("DISTILL_OPUS_BITRATE", "16k")

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv"}
PDF_EXT = {".pdf"}
PPTX_EXT = {".pptx"}
TRANSCRIPT_EXT = {".vtt", ".srt"}
