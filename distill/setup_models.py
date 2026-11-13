"""One-time download of all free, offline models (~400 MB). Run: python -m distill.setup_models"""
from __future__ import annotations

import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from . import config as C

GH = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEG_URL = f"{GH}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMB_URLS = [
    f"{GH}/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx",
    f"{GH}/speaker-recongition-models/nemo_en_titanet_small.onnx",
    f"{GH}/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
]


def _get(url: str, dst: Path) -> bool:
    try:
        print("  downloading", url)
        with urllib.request.urlopen(url, timeout=120) as r, open(dst, "wb") as f:
            shutil.copyfileobj(r, f)
        return dst.stat().st_size > 1000
    except Exception as e:
        print("   failed:", e)
        return False


def diarization():
    from .diarize import EMB_MODEL, SEG_MODEL

    SEG_MODEL.parent.mkdir(parents=True, exist_ok=True)
    if not SEG_MODEL.exists():
        with tempfile.TemporaryDirectory() as td:
            arc = Path(td) / "seg.tar.bz2"
            if _get(SEG_URL, arc):
                with tarfile.open(arc) as t:
                    t.extractall(td)
                m = next(Path(td).rglob("model.onnx"))
                shutil.copy(m, SEG_MODEL)
    if not EMB_MODEL.exists():
        for u in EMB_URLS:
            if _get(u, EMB_MODEL):
                break
    print("diarization models:", SEG_MODEL.exists(), EMB_MODEL.exists())


def whisper():
    from .transcribe import get_model

    get_model()
    print("whisper model ready:", C.WHISPER_MODEL)


def embeddings():
    import subprocess
    from .search import embedder

    dst = C.MODELS_DIR / "all-MiniLM-L6-v2"
    if not (dst / "model.safetensors").exists():
        dst.mkdir(parents=True, exist_ok=True)
        files = [
            "config.json", "config_sentence_transformers.json", "modules.json",
            "sentence_bert_config.json", "tokenizer.json", "tokenizer_config.json",
            "special_tokens_map.json", "vocab.txt", "model.safetensors", "1_Pooling/config.json",
        ]
        for f in files:
            p = dst / f
            p.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/{f}"
            subprocess.run(["curl.exe", "-4", "-sSL", "--retry", "3", "-o", str(p), url], check=True)
    embedder().encode(["warm up"])
    print("embedding model ready:", dst)


def ocr():
    from PIL import Image

    from .ocr import ocr as run

    run(Image.new("RGB", (200, 80), "white"))
    print("ocr ready")


if __name__ == "__main__":
    for step in (diarization, whisper, embeddings, ocr):
        try:
            step()
        except Exception as e:  # keep going; every component degrades gracefully
            print(f"!! {step.__name__} failed: {e}")
