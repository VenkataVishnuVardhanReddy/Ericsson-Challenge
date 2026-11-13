"""Speech-to-text (faster-whisper, CPU) and import of existing Teams/VTT/SRT transcripts."""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

from . import config as C
from .util import run_ffmpeg

_model = None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            C.WHISPER_MODEL, device="cpu", compute_type="int8",
            cpu_threads=C.WHISPER_THREADS, download_root=str(C.MODELS_DIR / "whisper"),
        )
    return _model


def extract_audio_wav(video: str, out_wav: str) -> str:
    run_ffmpeg(["-i", video, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out_wav])
    return out_wav


def encode_opus(src: str, out: str, bitrate: str = C.OPUS_BITRATE) -> int:
    """Speech-optimised Opus: ~7 MB per hour at 16 kbps and still clearly intelligible."""
    try:
        run_ffmpeg(["-i", src, "-vn", "-ac", "1", "-c:a", "libopus", "-b:a", bitrate,
                    "-application", "voip", out])
    except Exception:
        out = str(Path(out).with_suffix(".m4a"))
        run_ffmpeg(["-i", src, "-vn", "-ac", "1", "-c:a", "aac", "-b:a", "24k", out])
    return os.path.getsize(out)


def load_wav(path: str) -> np.ndarray:
    import soundfile as sf

    a, sr = sf.read(path, dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    return a


def transcribe(wav: str, progress=None, duration: float = 0) -> tuple[list[dict], dict]:
    """Return word-level timed words and info. Words: {start,end,word,prob}."""
    model = get_model()
    beam = int(os.environ.get("DISTILL_BEAM", 1))
    segs, info = model.transcribe(
        wav, language=C.WHISPER_LANGUAGE, vad_filter=True, word_timestamps=True,
        beam_size=beam, condition_on_previous_text=False,
    )
    words, seg_conf = [], []
    for s in segs:
        seg_conf.append(float(np.exp(s.avg_logprob)))
        for w in s.words or []:
            words.append({"start": float(w.start), "end": float(w.end), "word": w.word, "prob": float(w.probability)})
        if progress and duration:
            progress(min(1.0, s.end / duration))
    meta = {
        "language": info.language,
        "language_prob": round(float(info.language_probability), 3),
        "mean_confidence": round(float(np.mean([w["prob"] for w in words])) if words else 0.0, 3),
        "model": C.WHISPER_MODEL,
    }
    return words, meta


def words_to_segments(words: list[dict], turns: list[dict] | None, max_len: float = 18.0) -> list[dict]:
    """Group words into readable segments that break on speaker change, pauses and sentence ends."""
    def speaker_at(t: float) -> str:
        if not turns:
            return "Speaker 1"
        best, best_ov = None, 0.0
        for tr in turns:
            if tr["start"] <= t <= tr["end"]:
                return tr["speaker"]
            ov = -min(abs(t - tr["start"]), abs(t - tr["end"]))
            if best is None or ov > best_ov:
                best, best_ov = tr["speaker"], ov
        return best or "Speaker 1"

    out, cur = [], None
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        spk = speaker_at(mid)
        brk = (
            cur is None or spk != cur["speaker"] or w["start"] - cur["end"] > 1.2
            or (cur["end"] - cur["start"] > max_len)
            or (cur["end"] - cur["start"] > 6 and cur["text"].rstrip().endswith((".", "?", "!")))
        )
        if brk:
            if cur:
                out.append(cur)
            cur = {"start": w["start"], "end": w["end"], "speaker": spk, "text": "", "probs": []}
        cur["text"] += w["word"]
        cur["end"] = w["end"]
        cur["probs"].append(w["prob"])
    if cur:
        out.append(cur)
    for s in out:
        s["text"] = s["text"].strip()
        s["confidence"] = round(float(np.mean(s.pop("probs"))), 3)
    return out


# --------------------------------------------------------------------------- existing transcripts
_ts = r"(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}"
_cue = re.compile(rf"({_ts})\s*-->\s*({_ts})")
_voice = re.compile(r"<v\s+([^>]+)>(.*?)(?:</v>|$)", re.S)


def _sec(ts: str) -> float:
    parts = ts.replace(",", ".").split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def parse_subtitles(path: str) -> list[dict]:
    """Parse WebVTT (incl. Teams '<v Name>' speaker tags) or SRT into segments."""
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", text.replace("\r", ""))
    segs = []
    for b in blocks:
        m = _cue.search(b)
        if not m:
            continue
        body = b[m.end():].strip()
        spk = "Speaker 1"
        v = _voice.search(body)
        if v:
            spk, body = v.group(1).strip(), v.group(2)
        elif re.match(r"^[A-ZÅÄÖ][\w .'-]{1,40}:\s", body):
            spk, body = body.split(":", 1)
        body = re.sub(r"<[^>]+>", "", body).replace("\n", " ").strip()
        if body:
            segs.append({"start": _sec(m.group(1)), "end": _sec(m.group(3)), "speaker": spk.strip(),
                         "text": body, "confidence": 1.0})
    # merge consecutive cues of the same speaker into readable segments
    merged = []
    for s in segs:
        if merged and merged[-1]["speaker"] == s["speaker"] and s["start"] - merged[-1]["end"] < 1.5 \
                and merged[-1]["end"] - merged[-1]["start"] < 15:
            merged[-1]["text"] += " " + s["text"]
            merged[-1]["end"] = s["end"]
        else:
            merged.append(dict(s))
    return merged
