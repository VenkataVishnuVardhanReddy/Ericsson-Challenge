# Distill — Data Storage Optimization & AI Knowledge Activation

Built for **Ericsson Build Hackathon 2026 (Karlskrona)**.
Free, 100% offline, CPU-only tool that shrinks meeting/training recordings by **~98–99.9%** without losing information, deduplicates PDFs/PPTXs down to the single slide (**"Git for Slides"**), links video frames to their source-of-truth decks, makes everything searchable and AI-ready, and guides safe employee offboarding cleanup.

---

## Quick Start

### 1. Start the Web Console
```powershell
.\.venv\Scripts\python.exe -m distill
```
Open **http://127.0.0.1:8000** in your browser.

### 2. Run on Synthetic Demo Data
Click **"▶ Ingest `sample_data/` (Demo)"** in the web UI, or regenerate synthetic test data anytime:
```powershell
.\.venv\Scripts\python.exe scripts\make_synthetic.py
```

### 3. Run the Automated End-to-End Test & Ground-Truth Benchmark
```powershell
.\.venv\Scripts\python.exe scripts\run_e2e_test.py
```

### 4. Run on Real Ericsson Sample Files (Hackathon Day!)
Place Ericsson's folders (e.g., SharePoint export, OneDrive folder, Ericsson Play videos, duplicate `(1).pdf` copies) in a folder or inside `sample_data/`, then either:
- Click **Ingest Folders** in the web UI and paste semicolon-separated folder paths, OR
- Drag/upload files directly via **⬆ Upload Files**.

> Tip: To use a stronger Whisper model (`small` instead of `base`) or force a language (`en` / `sv`), set environment variables before launching:
> ```powershell
> $env:DISTILL_WHISPER="small"
> .\.venv\Scripts\python.exe -m distill
> ```

---

## Architecture & Key Features

| Module | Purpose |
|---|---|
| [distill/keyframes.py](distill/keyframes.py) | Streams video at 1 fps, builds a live-motion activity mask (ignores presenter webcam tiles), merges bullet animations, detects revisited slides and live camera segments, stores WebP keyframes in CAS. |
| [distill/transcribe.py](distill/transcribe.py) | Offline `faster-whisper` (int8 CPU) with word timestamps + importer for Teams `.vtt` (`<v Name>`) and `.srt` transcripts + 16 kbps Opus speech compression. |
| [distill/diarize.py](distill/diarize.py) | Offline `sherpa-onnx` pyannote segmentation + speaker embeddings to cluster speakers and extract 8 s Opus voice samples. |
| [distill/ocr.py](distill/ocr.py) | RapidOCR (ONNX Runtime) in reading order + slide-likeness classifier. |
| [distill/documents.py](distill/documents.py) | Splits PDF/PPTX into slides, strips repeated deck boilerplate (footers/page numbers), extracts Ericsson doc numbers & revisions, computes per-slide `content_id` + perceptual `phash`. |
| [distill/linker.py](distill/linker.py) | Links video keyframes to canonical source-of-truth slides (`doc_number`, `revision`, `page_no`), binds spoken utterances to on-screen slides, generates slide-recreation prompts. |
| [distill/dedup.py](distill/dedup.py) | 5-level deduplication: SHA-256 exact copies, normalised text-hash re-exports, slide-level CAS sharing, revision version chains + red-box visual diffs, and trimmed/re-encoded video fingerprinting. |
| [distill/offboard.py](distill/offboard.py) | Scans leaver OneDrive vs governed SharePoint/Play: classifies `safe_delete`, `partial` (rescues only unique slides to a compact PDF), and `unique`; dry-run & reversible quarantine + audit trail. |
| [distill/search.py](distill/search.py) & [distill/ai.py](distill/ai.py) | Hybrid SQLite FTS5 (BM25) + MiniLM vector search (RRF), grounded Q&A (Ollama optional + offline extractive fallback), and PII-redacted JSONL/Markdown AI corpus export. |
| [distill/recreate.py](distill/recreate.py) | Recreates playable MP4s from distilled data (`audio_slides` mode or pure `text_tts` offline voice synthesis mode). |
