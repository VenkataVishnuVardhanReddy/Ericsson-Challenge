# Distill — Enterprise Data Storage Optimization

> **Ericsson Build Hackathon 2026 — "Data Storage Optimization" Challenge**  
> **Core Result:** Ericsson's files got **98.3% smaller**, and nothing important was lost. All 12 sample files were processed and verified with exact mathematical integrity.

---

## 1. Executive Summary: What We Proved

Across the 12 provided Ericsson enterprise files (including three multi-gigabyte meeting recordings, presentation decks with multiple revisions, and personal employee OneDrive folders):

- **Original Archive Size:** **1.45 GB** (1,556,024,836 bytes)
- **Optimized Archive Size:** **24.9 MB** (26,087,879 bytes)
- **Storage Space Freed:** **98.3% space saved**
- **Retention Verification:**
  - **95.8% to 99.7%** on-screen character match across recorded meeting presentations
  - **90.0% to 100.0%** visual perceptual match (pixel comparison, no OCR) against original video frames
  - **98.9%** slide OCR word recall against official PowerPoint reference decks
  - **100%** spoken audio transcribed with speaker attribution (who said what, when)
- **Mathematical Exactness:** Every byte saved is accounted for in a waterfall formula that sums down to the exact byte:  
  `1,556,024,836 B - 1,522,715,191 B (videos) - 3,772,216 B (duplicates) - 3,449,550 B (slides) = 26,087,879 B`

---

## 2. The 5 Storage Levels for Meeting Recordings

Users choose the level that matches the age and regulatory need of their recordings:

| Level | Plain English Name | Storage Footprint | What is Preserved |
|---|---|---|---|
| **Level 1** | **Original** | **100%** (1.1 GB) | The untouched original video file (kept byte-identical). |
| **Level 2** | **Smaller video** | **~15%** (~160 MB) | Playable video re-encoded at 5 fps H.264 (quality setting 32, max 1280 px). |
| **Level 3** | **Audio + slides + text** | **~2.2%** (~24 MB) | Full Opus speech audio (16 kbps) + crisp slide pictures (WebP) + searchable transcript. |
| **Level 4** | **Slides + text** | **~0.7%** (~7.5 MB) | Clean slide pictures (WebP) + complete timestamped transcript + speaker attribution. |
| **Level 5** | **Text + links** | **~0.1%** (~1.2 MB) | Slide pictures that exist in official decks become links; transcript preserved. |

---

## 3. "Was Anything Lost?" Verification Method

To prove to evaluators that critical knowledge was not discarded, Distill implements an automated moment-by-moment verification protocol:

1. **20 Evenly Spaced Moments:** For every video, frames are sampled at `t = duration * (i + 0.5) / 20`.
2. **Text Retention Check:** Compares original video frame OCR against preserved slide text using character-level sequence matching (`SequenceMatcher(autojunk=False)` with &ge; 90% fuzzy similarity window).
   - *Result on 88-minute Tech Concept recording:* **95.8%** of visible on-screen text verified preserved.
   - *Result on GraalVM technical presentation:* **99.7%** of visible on-screen text verified preserved.
3. **Visual Pixel Match (No OCR):** Compares original video frame against kept slide picture using perceptual hashing (`pHash` distance &le; 12 on 320 px grayscale, with presenter webcam motion masked).
   - *Result:* **90.0% to 100.0%** visual match.
4. **Official Slide OCR Accuracy:** Compares kept slide pictures against official PowerPoint deck slide text, excluding speaker notes and boilerplate headers/footers.
   - *Result:* **98.9%** word recall across 36 checked slides.

---

## 4. Document Policy: "Git for Slides"

Organizations frequently re-upload presentation decks with minor edits, creating duplicate sprawl:

- **SharePoint Governance:** Official documents in SharePoint remain **100% byte-identical** in their original format (`policy: "original kept"`).
- **Exact Duplicates in Personal Drives:** Exact copies in OneDrive become zero-byte reference pointers to the governed SharePoint version (`policy: "duplicate → reference"`).
- **Version Revision Control (Delta Storage):**
  - **SD-WAN Rev B (File 5):** Kept intact in SharePoint (28 slides, 3.5 MB).
  - **SD-WAN Rev A (File 11):** Stored as a delta (`policy: "revision → delta"`). Only the **3 modified slides** are saved; the other **22 identical slides** point directly to the primary deck in Content Addressable Storage (CAS). Total storage: **92 KB** instead of 3.46 MB (**97.3% space saved**).

---

## 5. Beyond the Brief: Interactive Features

1. **Savings Projection Sliders (Overview Page):**
   - Enterprise scale calculator allowing evaluators to adjust:
     - TB of meeting recordings (default 10 TB)
     - % older than 1 year (default 60%)
     - Storage cost €/TB/month (default €20)
     - Carbon footprint kg CO₂/TB/year (default 40 kg)
   - Projects live capacity freed (e.g. 5.9 TB), annual cost avoided (€1,426/yr), and tonnes of CO₂ eliminated (0.24 tonnes/yr).
2. **Slide Life Story Panel:**
   - Evaluators can click any slide thumbnail on document pages or video players to see everywhere that exact slide visual appears across company presentation decks and meeting video recordings with clickable timestamps.

---

## 6. How to Run

### Prerequisites
- Python 3.10+ (CPU-optimized, zero GPU required)
- Node.js 18+ & npm
- FFmpeg (in system PATH)

### 1. Run the Backend API Server
```powershell
# From Hackthon repository root
.\.venv\Scripts\python.exe -m uvicorn distill.app:app --host 127.0.0.1 --port 8000
```
Backend runs at `http://127.0.0.1:8000`.

### 2. Run the Next.js Frontend
```powershell
# In a second terminal
cd frontend
$env:PATH = "C:\Users\Vishnu\AppData\Local\Programs\nodejs;$env:PATH" # if node is not in global PATH
npm run dev
```
Open **http://localhost:3000** in your browser.

### 3. Verify Pitch Metrics Directly From DB
```powershell
# Run the standalone verification query tool
.\.venv\Scripts\python.exe scripts\pitch_numbers.py
```

---

## 7. Key API Endpoints

- `GET /api/overview` — Archive waterfall savings, per-source breakdown, and headline totals.
- `GET /api/files` — All 12 files with original bytes, size after, % saved, policy, and reason.
- `GET /api/files/{id}/stages` — 5 storage levels, progress stages, and processing details.
- `GET /api/files/{id}/integrity` — 20 sampled moments, text match %, visual match %, and slide recall.
- `GET /api/files/{id}/manifest` — Ordered slide manifest with "stored here" vs "shared with <deck>, page N".
- `GET /api/slides/{id}/appearances` — Slide life story across document decks and video recordings.
- `GET /api/duplicates` — Exact duplicate groups, version chains, and shared slide statistics.
- `GET /api/search?q={query}` — Full-text and semantic search across transcripts and slide text.
- `GET /api/offboard` — Departing employee folder audit against official SharePoint repositories.

---

## 8. Technology Stack

- **Backend:** FastAPI, SQLite (FTS5 + WAL mode), RapidOCR, Whisper Base (CPU int8), pyannote + WeSpeaker, ImageHash (pHash/dHash).
- **Frontend:** Next.js 15 (App Router), React 19, Tailwind CSS 3, Lucide Icons. Designed strictly in monochromatic high-contrast enterprise design system.
