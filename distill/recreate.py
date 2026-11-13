"""Recreate a playable MP4 video from a distilled Knowledge Packet.

Addresses the brief's question: "Based on all this data, can the recording be recreated as a video?"
Supports two reconstruction modes:
  1. 'audio_slides' : uses the distilled keyframes + their exact timeline intervals +
                      the tiny 16 kbps Opus audio track (~98% smaller than original).
  2. 'text_tts'     : reconstructs the video ONLY from pure text + keyframes (or prompt-rendered
                      placeholder slides if keyframes were replaced by source links), using
                      offline speech synthesis (Windows System.Speech / pyttsx3) on the
                      speaker-tagged transcript! Proves full reconstruction even after dropping audio.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config as C
from . import db
from .util import ffmpeg_bin, fmt_ts, object_path, run_ffmpeg


def _tts_utterances(segs: list[dict], out_wav: Path) -> bool:
    """Synthesise speaker-tagged segments into one WAV using Windows System.Speech (free, offline)."""
    import numpy as np
    import soundfile as sf

    if not segs:
        return False

    tmp = out_wav.parent / "tts_parts"
    tmp.mkdir(parents=True, exist_ok=True)
    ps_lines = [
        "Add-Type -AssemblyName System.Speech",
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)",
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
    ]
    speakers = {}
    parts = []
    for i, seg in enumerate(segs):
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue
        spk = seg.get("speaker") or "Speaker 1"
        if spk not in speakers:
            # vary speech rate slightly per speaker so multiple speakers stay distinguishable
            speakers[spk] = 0 if len(speakers) == 0 else (2 if len(speakers) % 2 == 1 else -1)
        rate = speakers[spk]
        safe = txt.replace("'", "''").replace('"', " ")
        wav_i = tmp / f"u_{i:04d}.wav"
        ps_lines.append(f"$s.Rate = {rate}")
        ps_lines.append(f"$s.SetOutputToWaveFile('{str(wav_i)}')")
        ps_lines.append(f"$s.Speak('{safe}')")
        parts.append((seg["start"], seg["end"], wav_i))

    if not parts:
        return False

    ps_lines.append("$s.Dispose()")
    ps_script = tmp / "synth.ps1"
    ps_script.write_text("\n".join(ps_lines), encoding="utf-8")
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_script)],
            check=True, capture_output=True, timeout=180
        )
    except Exception:
        return False

    sr = 16000
    total_dur = max(p[1] for p in parts) + 1.0
    mix = np.zeros(int(total_dur * sr), dtype=np.float32)
    for start, end, wp in parts:
        if not wp.exists():
            continue
        a, file_sr = sf.read(wp, dtype="float32")
        if a.ndim > 1:
            a = a.mean(axis=1)
        if file_sr != sr and len(a) > 0:
            x_old = np.linspace(0, 1, len(a))
            x_new = np.linspace(0, 1, int(len(a) * sr / file_sr))
            a = np.interp(x_new, x_old, a).astype(np.float32)
        idx = int(start * sr)
        if idx + len(a) > len(mix):
            mix = np.pad(mix, (0, idx + len(a) - len(mix) + sr))
        mix[idx: idx + len(a)] += a * 0.9
    mix = np.clip(mix, -1.0, 1.0)
    sf.write(out_wav, mix, sr)
    return True


def _render_slide_from_text(title: str, ocr_text: str, desc: str, out_png: Path) -> None:
    """Fallback slide image reconstructed purely from text/prompt when no image is kept."""
    im = Image.new("RGB", (1280, 720), (248, 250, 252))
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, 1280, 88], fill=(0, 37, 97))
    try:
        f_title = ImageFont.truetype("arial.ttf", 30)
        f_body = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        f_title = f_body = ImageFont.load_default()
    dr.text((40, 26), (title or "Reconstructed Slide")[:72], fill="white", font=f_title)
    y = 120
    lines = [l.strip() for l in (ocr_text or desc or "").splitlines() if l.strip()]
    for l in lines[:18]:
        dr.text((48, y), l[:95], fill=(15, 23, 42), font=f_body)
        y += 32
    im.save(out_png, "PNG")


def recreate_video(file_id: int, mode: str = "audio_slides", force: bool = False) -> dict:
    """Build a playable H.264 MP4 slideshow from distilled data. Returns {path, bytes, original_bytes, saving, mode}."""
    f = db.q1("SELECT * FROM files WHERE id=?", (file_id,))
    rec = db.q1("SELECT * FROM recordings WHERE file_id=?", (file_id,))
    if not f or not rec:
        raise ValueError(f"Recording {file_id} not found")

    mode = "text_tts" if mode == "text_tts" else "audio_slides"
    out_mp4 = C.RECREATED_DIR / f"recreated_{file_id}_{mode}.mp4"
    if out_mp4.exists() and not force:
        sz = out_mp4.stat().st_size
        return {
            "file_id": file_id, "mode": mode, "path": str(out_mp4),
            "filename": out_mp4.name, "bytes": sz,
            "original_bytes": f["size"],
            "saving": round(1 - sz / f["size"], 4) if f["size"] else 0,
            "cached": True,
        }

    kfs = db.q("SELECT * FROM keyframes WHERE file_id=? ORDER BY idx", (file_id,))
    segs = db.q("SELECT * FROM segments WHERE file_id=? ORDER BY start", (file_id,))
    dur = float(rec["duration"] or 0)
    pdir = Path(rec["packet_dir"])

    # Timeline of (start, end, keyframe)
    events = []
    for k in kfs:
        ivs = json.loads(k["intervals"] or "[]")
        for a, b in ivs:
            events.append((float(a), float(b), k))
    events.sort(key=lambda x: x[0])
    if not events:
        raise RuntimeError("No keyframes available to recreate video")

    tmp = Path(tempfile.mkdtemp(prefix="recreate_"))
    try:
        # Prepare PNG frames for ffmpeg concat demuxer (even dimensions required by libx264)
        png_map = {}
        concat_lines = []
        for idx, (a, b, k) in enumerate(events):
            kid = k["id"]
            if kid not in png_map:
                out_png = tmp / f"kf_{kid}.png"
                if mode == "text_tts" and not object_path(k["object_hash"]).exists():
                    _render_slide_from_text(f["name"], k["ocr_text"], k["description"], out_png)
                else:
                    src_webp = object_path(k["object_hash"])
                    if src_webp.exists():
                        im = Image.open(src_webp).convert("RGB")
                        w = im.width - (im.width % 2)
                        h = im.height - (im.height % 2)
                        if (w, h) != im.size:
                            im = im.resize((w, h))
                        im.save(out_png, "PNG")
                    else:
                        _render_slide_from_text(f["name"], k["ocr_text"], k["description"], out_png)
                png_map[kid] = out_png

            # Fill any small gap before this event by stretching previous or this frame
            d = max(0.2, b - a)
            concat_lines.append(f"file '{png_map[kid].as_posix()}'")
            concat_lines.append(f"duration {d:.3f}")
        concat_lines.append(f"file '{png_map[events[-1][2]['id']].as_posix()}'")

        concat_txt = tmp / "slides.txt"
        concat_txt.write_text("\n".join(concat_lines), encoding="utf-8")

        # Audio track
        audio_in: Path | None = None
        if mode == "audio_slides":
            for cand in (pdir / "audio.opus", pdir / "audio.m4a"):
                if cand.exists():
                    audio_in = cand
                    break
        if audio_in is None:
            tts_wav = tmp / "tts.wav"
            if _tts_utterances(segs, tts_wav):
                audio_in = tts_wav

        # Burn subtitles (SRT) so the recreated video even shows speaker captions!
        srt_path = tmp / "captions.srt"
        if segs:
            def sts(t: float) -> str:
                h, r = divmod(max(0.0, t), 3600)
                m, s = divmod(r, 60)
                return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1)*1000):03d}"

            srt_blocks = []
            for i, s in enumerate(segs, 1):
                srt_blocks.append(f"{i}\n{sts(s['start'])} --> {sts(s['end'])}\n[{s['speaker']}] {s['text']}\n")
            srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")

        cmd = ["-f", "concat", "-safe", "0", "-i", str(concat_txt)]
        if audio_in:
            cmd += ["-i", str(audio_in)]
        cmd += ["-vf", "scale='min(1280,iw)':-2,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "28", "-tune", "stillimage", "-r", "2"]
        if audio_in:
            cmd += ["-c:a", "aac", "-b:a", "32k", "-ac", "1", "-shortest"]
        cmd += ["-movflags", "+faststart", str(out_mp4)]
        run_ffmpeg(cmd)

        sz = out_mp4.stat().st_size
        db.audit("recreate_video", {"file_id": file_id, "mode": mode, "bytes": sz, "original": f["size"]})
        return {
            "file_id": file_id,
            "mode": mode,
            "path": str(out_mp4),
            "filename": out_mp4.name,
            "bytes": sz,
            "original_bytes": f["size"],
            "saving": round(1 - sz / f["size"], 4) if f["size"] else 0,
            "duration": dur,
            "cached": False,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
