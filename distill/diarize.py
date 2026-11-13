"""Speaker diarization ("who spoke when"), fully offline with sherpa-onnx.

Uses the pyannote-3.0 segmentation model + a speaker-embedding model, both ONNX (CPU).
If the models are not downloaded, diarization is skipped gracefully (single speaker).
Run `python -m distill.setup_models` once (needs internet) to fetch them (~40 MB).
"""
from __future__ import annotations

from pathlib import Path

from . import config as C

SEG_MODEL = C.MODELS_DIR / "diarization" / "segmentation.onnx"
EMB_MODEL = C.MODELS_DIR / "diarization" / "embedding.onnx"


def available() -> bool:
    return SEG_MODEL.exists() and EMB_MODEL.exists()


def diarize(audio, sample_rate: int = 16000, num_speakers: int = -1, threshold: float = 0.6) -> list[dict]:
    if not available():
        return []
    import sherpa_onnx
    import soundfile as sf
    from pathlib import Path

    if isinstance(audio, (str, Path)):
        a, sr = sf.read(str(audio), dtype="float32")
        if a.ndim > 1:
            a = a.mean(axis=1)
        audio = a

    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(SEG_MODEL)),
            num_threads=C.WHISPER_THREADS,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(EMB_MODEL), num_threads=C.WHISPER_THREADS),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=num_speakers, threshold=threshold),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not cfg.validate():
        return []
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
    if sd.sample_rate != sample_rate:
        raise ValueError("diarization expects 16 kHz audio")
    result = sd.process(audio).sort_by_start_time()
    # rename speakers in order of first appearance: Speaker 1, Speaker 2, ...
    order: dict[int, str] = {}
    turns = []
    for r in result:
        if r.speaker not in order:
            order[r.speaker] = f"Speaker {len(order) + 1}"
        turns.append({"start": float(r.start), "end": float(r.end), "speaker": order[r.speaker]})
    return turns


def voice_samples(audio, turns: list[dict], out_dir: Path, sr: int = 16000, seconds: float = 8.0) -> dict:
    """Save a short clean voice sample per speaker (enables speaker naming / future re-synthesis)."""
    import soundfile as sf

    out_dir.mkdir(parents=True, exist_ok=True)
    best: dict[str, dict] = {}
    for t in turns:
        d = t["end"] - t["start"]
        if d > best.get(t["speaker"], {}).get("d", 0):
            best[t["speaker"]] = {"d": d, **t}
    paths = {}
    for spk, t in best.items():
        a = audio[int(t["start"] * sr): int(min(t["end"], t["start"] + seconds) * sr)]
        p = out_dir / f"voice_{spk.replace(' ', '_').lower()}.wav"
        sf.write(p, a, sr)
        paths[spk] = p.name
    return paths
