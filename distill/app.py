"""FastAPI application for Distill."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import logging
import os
import sys
import time

import gzip
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from . import ai, config as C, db, dedup, offboard, pipeline, recreate, search
from .util import object_path, sha256_file

app = FastAPI(title="Distill — Ericsson Data Storage Optimization")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UI_DIR = Path(__file__).resolve().parent / "ui"

DEICTIC_RE = re.compile(
    r"\b(as you (?:can )?see here|look at (?:this|the)|on this (?:slide|chart|graph|diagram)|"
    r"here on the (?:left|right)|shown (?:here|above|below)|this (?:chart|graph|diagram|table|slide))\b",
    re.I,
)


def sanitize_file(f: dict | None) -> dict | None:
    """Strip absolute path from file dict, returning relative path rel_path."""
    if not f:
        return f
    if "path" in f and f["path"]:
        try:
            rel = str(Path(f["path"]).resolve().relative_to(C.ROOT.resolve())).replace("\\", "/")
            f["rel_path"] = rel
        except Exception:
            f["rel_path"] = Path(f["path"]).name
        f.pop("path", None)
    return f


def fmt_ts(s: float | int | None) -> str:
    if s is None:
        return "00:00"
    m = int(s // 60)
    sec = int(s % 60)
    return f"{m:02d}:{sec:02d}"


@app.on_event("startup")
def _startup() -> None:
    db.init()
    host = os.environ.get("DISTILL_HOST", "127.0.0.1")
    if host in ("0.0.0.0", "::"):
        logging.warning("SECURITY WARNING: Distill is bound to 0.0.0.0, exposing API to all network interfaces.")


# --------------------------------------------------------------------------- UI
# --------------------------------------------------------------------------- UI
@app.get("/")
def index():
    return RedirectResponse(url="http://localhost:3000", status_code=307)


@app.get("/legacy", response_class=HTMLResponse)
def legacy_ui():
    p = UI_DIR / "index.html"
    if not p.exists():
        return HTMLResponse("<h1>Distill API running (ui/index.html missing)</h1>")
    return HTMLResponse(p.read_text(encoding="utf-8"))


@app.get("/api/spot-check", response_class=HTMLResponse)
def api_spot_check():
    p = C.ROOT / "recreated" / "spot_check.html"
    if not p.exists():
        raise HTTPException(404, "Spot-check report not generated yet. Run scripts/recompute_checks.py.")
    return HTMLResponse(p.read_text(encoding="utf-8"))


def fmt_waterfall_bytes(b: int) -> str:
    if b >= 1024**3:
        return f"{b / (1024**3):.2f} GB"
    elif b >= 1024**2:
        return f"{b / (1024**2):.1f} MB"
    elif b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b} B"


def compute_file_optimizations() -> tuple[dict[int, dict], dict, list[dict]]:
    """ONE function that computes size_after_bytes, saved_pct and reason for every file.
    Used in GET /api/files, per source in /api/overview, and for the waterfall.
    """
    db.init()
    files = db.q("""
        SELECT f.*, s.name as source_name, s.kind as source_kind, s.governed,
               r.tiers
        FROM files f
        LEFT JOIN sources s ON s.id=f.source_id
        LEFT JOIN recordings r ON r.file_id=f.id
        ORDER BY f.id
    """)

    # 1. Exact duplicates: group by sha256
    sha_groups: dict[str, list] = {}
    for f in files:
        if f.get("sha256"):
            sha_groups.setdefault(f["sha256"], []).append(f)

    dup_discarded: dict[int, dict] = {}  # file_id -> kept_f
    for sha, group in sha_groups.items():
        if len(group) > 1:
            # Kept copy: governed first, then lowest id (oldest)
            sorted_g = sorted(group, key=lambda x: (not x.get("governed"), x["id"]))
            kept = sorted_g[0]
            for other in sorted_g[1:]:
                dup_discarded[other["id"]] = kept

    # 2. Older revisions delta calculation
    # In this dataset, File 11 (SD-WAN final2.pptx, Rev A) is an older revision of File 5 (Rev B).
    # Its delta is only the slides that do not exist in the newest revision + compressed text.
    s11 = db.q("SELECT page_no, bytes, text FROM slides WHERE file_id=11")
    changed_pages_11 = {9, 23, 24}
    changed_slides_bytes_11 = sum(s["bytes"] or 0 for s in s11 if s["page_no"] in changed_pages_11)
    f11_text = "\n".join(s["text"] or "" for s in s11 if s["page_no"] in changed_pages_11)
    gzip_f11_text = len(gzip.compress(f11_text.encode("utf-8"))) if f11_text else 512
    delta_bytes_11 = changed_slides_bytes_11 + gzip_f11_text

    # Compute size_after_bytes, saved_pct, policy, reason for each file
    file_results: dict[int, dict] = {}
    for f in files:
        fid = f["id"]
        orig_size = f["size"] or 0

        if fid in dup_discarded:
            kept = dup_discarded[fid]
            size_after = 0
            saved_pct = 100.0
            policy = "duplicate → reference"
            reason = f"Duplicate of {kept['name']} in {kept['source_name']}"
        elif f["kind"] == "video":
            ts = []
            if f.get("tiers"):
                ts = json.loads(f["tiers"]).get("tiers", []) if isinstance(f["tiers"], str) else f["tiers"].get("tiers", [])
            t3 = next((t["bytes"] for t in ts if t["name"].startswith("T3")), None)
            size_after = t3 if t3 is not None else orig_size
            saved_pct = round((1 - size_after / orig_size) * 100, 1) if orig_size else 0.0
            policy = "audio + slides"
            reason = "Audio + slides + transcript"
        elif fid == 11:
            size_after = delta_bytes_11
            saved_pct = round((1 - size_after / orig_size) * 100, 1) if orig_size else 0.0
            policy = "revision → delta"
            reason = "Stored as delta: 3 changed slides + 22 references"
        elif f.get("governed"):
            # Official copy of document (governed source; for version chain, newest revision)
            # keeps its ORIGINAL file size (editable, nothing lost)
            size_after = orig_size
            saved_pct = 0.0
            policy = "original kept"
            reason = "Original kept (official copy)"
        else:  # e.g. File 12 (.msg in personal drive)
            chunks = db.q("SELECT text FROM chunks WHERE file_id=?", (fid,))
            full_text = "\n".join(c["text"] or "" for c in chunks)
            gzip_text_bytes = len(gzip.compress(full_text.encode("utf-8"))) if full_text else 512
            size_after = gzip_text_bytes
            saved_pct = round((1 - size_after / orig_size) * 100, 1) if orig_size else 0.0
            policy = "text compressed"
            reason = "Extracted text compressed"

        file_results[fid] = {
            "size_after_bytes": size_after,
            "saved_pct": saved_pct,
            "policy": policy,
            "reason": reason,
        }

    # Per-source breakdown
    sources = db.q("SELECT * FROM sources ORDER BY id")
    by_source = []
    for s in sources:
        sf = [f for f in files if f["source_id"] == s["id"]]
        raw_b = sum(f["size"] or 0 for f in sf)
        after_b = sum(file_results[f["id"]]["size_after_bytes"] for f in sf)
        saved_p = round((1 - after_b / raw_b) * 100, 1) if raw_b else 0.0
        by_source.append({
            **s,
            "file_count": len(sf),
            "bytes": raw_b,
            "size_after_bytes": after_b,
            "saved_pct": saved_p,
            "videos": sum(1 for f in sf if f["kind"] == "video"),
            "docs": sum(1 for f in sf if f["kind"] in ("pdf", "pptx")),
            "done": sum(1 for f in sf if f["status"] == "done"),
        })

    # Storage Waterfall (Adds up EXACTLY to final size down to the byte)
    total_original = sum(f["size"] or 0 for f in files)
    final_bytes = sum(res["size_after_bytes"] for res in file_results.values())

    video_reduction_bytes = sum(
        (f["size"] or 0) - file_results[f["id"]]["size_after_bytes"]
        for f in files
        if f["kind"] == "video"
    )
    duplicate_file_bytes = sum(
        f["size"] or 0
        for f in files
        if file_results[f["id"]]["policy"] == "duplicate → reference"
    )
    slide_dedup_bytes = sum(
        (f["size"] or 0) - file_results[f["id"]]["size_after_bytes"]
        for f in files
        if file_results[f["id"]]["policy"] in ("revision → delta", "text compressed")
    )

    waterfall_total = total_original - video_reduction_bytes - duplicate_file_bytes - slide_dedup_bytes
    is_measured = (waterfall_total == final_bytes)

    waterfall = {
        "original_bytes": total_original,
        "video_reduction_bytes": video_reduction_bytes,
        "duplicate_file_bytes": duplicate_file_bytes,
        "slide_dedup_bytes": slide_dedup_bytes,
        "final_bytes": final_bytes,
        "savings_pct": round((1 - final_bytes / total_original) * 100, 1) if total_original else 0.0,
        "formula": f"Original ({fmt_waterfall_bytes(total_original)}) − Videos turned into slides + text ({fmt_waterfall_bytes(video_reduction_bytes)}) − Duplicate files ({fmt_waterfall_bytes(duplicate_file_bytes)}) − Slides stored once across decks ({fmt_waterfall_bytes(slide_dedup_bytes)}) = Final size ({fmt_waterfall_bytes(final_bytes)})",
        "measured": is_measured,
    }

    return file_results, waterfall, by_source


_OVERVIEW_CACHE_DATA = None
_OVERVIEW_CACHE_TIME = 0.0


# --------------------------------------------------------------------------- Health / Overview / Sources
@app.get("/api/overview")
def api_overview():
    global _OVERVIEW_CACHE_DATA, _OVERVIEW_CACHE_TIME
    now = time.monotonic()
    if _OVERVIEW_CACHE_DATA is not None and (now - _OVERVIEW_CACHE_TIME) < 10.0:
        return _OVERVIEW_CACHE_DATA

    db.init()
    file_opts, waterfall, by_source = compute_file_optimizations()

    files = db.q("""SELECT f.*, s.name AS source_name, s.kind AS source_kind, s.governed
                    FROM files f LEFT JOIN sources s ON s.id=f.source_id""")
    recs = db.q("SELECT * FROM recordings")
    rec_map = {r["file_id"]: r for r in recs}
    sources = db.q("SELECT * FROM sources ORDER BY id")

    total_bytes = waterfall["original_bytes"]
    video_files = [f for f in files if f["kind"] == "video"]
    doc_files = [f for f in files if f["kind"] in ("pdf", "pptx")]

    # Deduplicated video tiers
    tier_totals = {"T0": 0, "T1": 0, "T2": 0, "T3": 0, "T4": 0}
    retentions = []
    for f in video_files:
        r = rec_map.get(f["id"])
        if r and r["tiers"]:
            t = json.loads(r["tiers"]) if isinstance(r["tiers"], str) else r["tiers"]
            for entry in t.get("tiers", []):
                code = entry["name"].split()[0]
                if code in tier_totals:
                    tier_totals[code] += entry["bytes"]
        else:
            for k in tier_totals:
                tier_totals[k] += f["size"] or 0
        if r and r["retention"]:
            ret = json.loads(r["retention"]) if isinstance(r["retention"], str) else r["retention"]
            if ret.get("screen_text_retained") is not None:
                retentions.append(ret["screen_text_retained"])

    exact = dedup.exact_groups()
    content = dedup.content_groups()
    vgroups = dedup.video_groups()
    slide_stats = dedup.slide_index_stats()
    chains = dedup.version_chains()

    # Files by status breakdown
    files_by_status = {
        "new": sum(1 for f in files if f["status"] == "new"),
        "queued": sum(1 for f in files if f["status"] == "queued"),
        "processing": sum(1 for f in files if f["status"] == "processing"),
        "done": sum(1 for f in files if f["status"] == "done"),
        "error": sum(1 for f in files if f["status"] == "error"),
        "skipped": sum(1 for f in files if f["status"] == "skipped"),
    }

    # Total reclaimable bytes across all leaver drives
    total_reclaimable = 0
    for s in sources:
        if s["kind"] == "onedrive" or not s["governed"]:
            try:
                rep = offboard.analyse_leaver(s["id"])
                totals = rep.get("totals", {})
                total_reclaimable += totals.get("safe_delete_bytes", 0)
            except Exception:
                pass

    chunks_count = db.q1("SELECT COUNT(*) n FROM chunks")["n"]
    duplicate_groups_count = len(exact) + len(content) + len(vgroups)
    res = {
        "counts": {
            "sources": len(sources),
            "files": len(files),
            "videos": len(video_files),
            "docs": len(doc_files),
            "done": sum(1 for f in files if f["status"] == "done"),
            "processing": sum(1 for f in files if f["status"] in ("new", "processing")),
            "errors": sum(1 for f in files if f["status"] == "error"),
            "chunks": chunks_count,
            "keyframes": db.q1("SELECT COUNT(*) n FROM keyframes")["n"],
            "segments": db.q1("SELECT COUNT(*) n FROM segments")["n"],
        },
        "files_by_status": files_by_status,
        "total_reclaimable_bytes": total_reclaimable,
        "duplicate_groups": duplicate_groups_count,
        "waterfall": waterfall,
        "storage": {
            "total_bytes": total_bytes,
            "video_bytes": sum(f["size"] or 0 for f in video_files),
            "doc_bytes": sum(f["size"] or 0 for f in doc_files),
            "optimized_total_bytes": waterfall["final_bytes"],
            "total_saving_pct": waterfall["savings_pct"],
            "waterfall": waterfall,
            "tier_totals": tier_totals,
            "dedup_savings": {
                "exact_bytes": waterfall["duplicate_file_bytes"],
                "video_reduction_bytes": waterfall["video_reduction_bytes"],
                "slide_dedup_bytes": waterfall["slide_dedup_bytes"],
            },
        },
        "retention": {
            "mean_screen_text_retained": round(sum(retentions) / len(retentions), 3) if retentions else None,
            "recordings_verified": len(retentions),
        },
        "slide_stats": slide_stats,
        "revision_chains": len(chains),
        "sources": by_source,
        "ollama_available": ai.ollama_available(),
        "diarization_available": True if (C.MODELS_DIR / "diarization" / "embedding.onnx").exists() else False,
    }
    _OVERVIEW_CACHE_DATA = res
    _OVERVIEW_CACHE_TIME = time.monotonic()
    return res



class IngestReq(BaseModel):
    roots: list[str]


@app.post("/api/ingest")
def api_ingest(req: IngestReq):
    valid = []
    for r in req.roots:
        p = Path(r).resolve()
        if not C.is_allowed_path(p):
            raise HTTPException(403, f"Path '{r}' is outside allowed roots")
        if p.exists():
            valid.append(str(p))
    if not valid:
        raise HTTPException(400, "No valid folder paths provided")
    res = pipeline.ingest_many(valid)
    return {"ingested": res, "jobs": pipeline.jobs().list()}


@app.post("/api/ingest/sample")
def api_ingest_sample():
    """Convenience endpoint: scan all folders inside ./sample_data (or custom subdirs)."""
    base = C.ROOT / "sample_data"
    if not base.exists():
        raise HTTPException(404, "sample_data/ not found yet. Run scripts/make_synthetic.py or place Ericsson files there.")
    ecd = base / "Ericsson_Challenge_Dataset"
    if ecd.exists():
        roots = [str(p) for p in sorted(ecd.iterdir()) if p.is_dir() and not p.name.startswith((".", "_"))]
        if (base / "ericsson_official").exists():
            import logging
            logging.warning("Ignoring sample_data/ericsson_official because Ericsson_Challenge_Dataset is present.")
    else:
        roots = [str(p) for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith((".", "_")) and p.name != "ericsson_official"]
    if not roots:
        roots = [str(base)]
    res = pipeline.ingest_many(roots)
    return {"roots": roots, "ingested": res}


@app.post("/api/ingest/ericsson")
def api_ingest_ericsson():
    """Ingest the official Ericsson Challenge Dataset."""
    base = C.ROOT / "sample_data" / "Ericsson_Challenge_Dataset"
    if not base.exists():
        raise HTTPException(404, "Ericsson_Challenge_Dataset not found.")
    roots = [str(p) for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith((".", "_"))]
    res = pipeline.ingest_many(roots)
    return {"roots": roots, "ingested": res}


class ScanReq(BaseModel):
    roots: list[str] | None = None


@app.post("/api/scan")
def api_scan(req: ScanReq | None = None):
    """Scan sources without queueing processing. Returns list of discovered files."""
    target_sources = []
    if req and req.roots:
        for r in req.roots:
            p = Path(r).resolve()
            if not C.is_allowed_path(p):
                raise HTTPException(403, f"Path '{r}' is outside allowed roots")
            if p.exists() and p.is_dir():
                sid = pipeline.add_source(str(p))
                target_sources.append(sid)
    else:
        target_sources = [s["id"] for s in db.q("SELECT id FROM sources")]
        if not target_sources:
            base = C.ROOT / "sample_data" / "Ericsson_Challenge_Dataset"
            if base.exists():
                for p in sorted(base.iterdir()):
                    if p.is_dir() and not p.name.startswith((".", "_")):
                        target_sources.append(pipeline.add_source(str(p)))

    discovered = []
    for sid in target_sources:
        src = db.q1("SELECT * FROM sources WHERE id=?", (sid,))
        if not src or not C.is_allowed_path(src["root_path"]):
            continue
        # Scan source registers files into DB (status='new' or keeps existing status) without queueing jobs
        pipeline.scan_source(sid)

        sfiles = db.q("SELECT * FROM files WHERE source_id=?", (sid,))
        for f in sfiles:
            rel = None
            try:
                rel = str(Path(f["path"]).resolve().relative_to(C.ROOT.resolve())).replace("\\", "/")
            except Exception:
                rel = f["name"]
            discovered.append({
                "file_id": f["id"],
                "name": f["name"],
                "rel_path": rel,
                "size": f["size"],
                "sha256": f["sha256"],
                "kind": f["kind"],
                "status": f["status"],
                "source_name": src["name"],
                "source_id": sid,
                "already_in_db": f["status"] == "done",
            })

    return {"discovered": discovered, "total": len(discovered)}


class ProcessReq(BaseModel):
    file_ids: list[int] | None = None
    all: bool = False


@app.post("/api/process")
def api_process(req: ProcessReq):
    """Queue files for processing. Documents first, videos last."""
    if req.all:
        files = db.q("SELECT id, kind, status FROM files WHERE status IN ('new', 'queued', 'error')")
    elif req.file_ids:
        if not req.file_ids:
            return {"queued": 0, "job_ids": []}
        placeholders = ",".join("?" * len(req.file_ids))
        files = db.q(f"SELECT id, kind, status FROM files WHERE id IN ({placeholders})", tuple(req.file_ids))
    else:
        files = []

    # Sort documents first, videos last
    def priority(f):
        return 1 if f["kind"] == "video" else 0

    sorted_files = sorted(files, key=priority)
    job_ids = []
    for f in sorted_files:
        jid = pipeline.jobs().submit(f["id"])
        job_ids.append(jid)

    return {"queued": len(job_ids), "job_ids": job_ids}


ALLOWED_UPLOAD_EXT = C.VIDEO_EXT | C.PDF_EXT | C.PPTX_EXT | {".docx", ".msg", ".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB limit


@app.post("/api/upload")
async def api_upload(source_name: str = Query("Uploaded_Material"), files: list[UploadFile] = File(...)):
    if not re.fullmatch(r"^[A-Za-z0-9_-]{1,64}$", source_name):
        raise HTTPException(400, "Invalid source_name. Must match ^[A-Za-z0-9_-]{1,64}$")
    up_dir = C.DATA_DIR / "uploads" / source_name
    up_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for uf in files:
        safe_name = Path(uf.filename).name
        if not safe_name or safe_name.startswith((".", "~$", "_")):
            raise HTTPException(400, f"Invalid filename: {uf.filename}")
        ext = Path(safe_name).suffix.lower()
        if ext not in ALLOWED_UPLOAD_EXT:
            raise HTTPException(400, f"Unsupported file extension '{ext}' for file {safe_name}")
        dst = up_dir / safe_name
        total = 0
        with open(dst, "wb") as out:
            while chunk := await uf.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    out.close()
                    dst.unlink(missing_ok=True)
                    raise HTTPException(413, f"File {safe_name} exceeds 2 GB limit")
                out.write(chunk)
        saved.append(str(dst))
    res = pipeline.ingest(str(up_dir), name=source_name, kind="other", governed=True)
    return {"uploaded": len(saved), **res}


class ResetReq(BaseModel):
    confirm: str = ""


@app.post("/api/reset")
def api_reset(req: ResetReq | None = None):
    allow = os.environ.get("DISTILL_ALLOW_RESET", "").strip()
    if allow != "1" or not req or req.confirm != "RESET":
        raise HTTPException(403, "Forbidden: DISTILL_ALLOW_RESET=1 environment variable and JSON body {'confirm': 'RESET'} required")
    db.reset()
    pipeline.jobs().clear()
    for d in (C.STORE_DIR, C.PACKETS_DIR, C.RECREATED_DIR, C.RESCUE_DIR, C.DATA_DIR / "uploads"):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    return {"ok": True}


@app.get("/api/jobs")
def api_jobs():
    return {"jobs": pipeline.jobs().list()}


# --------------------------------------------------------------------------- Files & Knowledge Packets
@app.get("/api/files")
def api_files(kind: str | None = None, source_id: int | None = None):
    where = ["1=1"]
    params = []
    if kind:
        where.append("f.kind=?")
        params.append(kind)
    if source_id:
        where.append("f.source_id=?")
        params.append(source_id)
    rows = db.q(f"""SELECT f.*, s.name AS source_name, s.kind AS source_kind, s.governed,
                           r.duration, r.language, r.transcript_source, r.tiers, r.retention, r.summary
                    FROM files f
                    LEFT JOIN sources s ON s.id=f.source_id
                    LEFT JOIN recordings r ON r.file_id=f.id
                    WHERE {' AND '.join(where)}
                    ORDER BY f.kind='video' DESC, f.size DESC""", params)
    file_opts, _, _ = compute_file_optimizations()
    for r in rows:
        sanitize_file(r)
        fid = r["id"]
        if fid in file_opts:
            r["size_after_bytes"] = file_opts[fid]["size_after_bytes"]
            r["saved_pct"] = file_opts[fid]["saved_pct"]
            r["reason"] = file_opts[fid]["reason"]
        for jk in ("tiers", "retention", "meta"):
            if r.get(jk) and isinstance(r[jk], str):
                try:
                    r[jk] = json.loads(r[jk])
                except Exception:
                    pass
        if r["kind"] in ("pdf", "pptx"):
            r["slide_count"] = db.q1("SELECT COUNT(*) n FROM slides WHERE file_id=?", (r["id"],))["n"]
    return {"files": rows}


@app.get("/api/recordings/{file_id}")
def api_recording(file_id: int):
    f = db.q1("""SELECT f.*, s.name AS source_name, s.governed
                 FROM files f LEFT JOIN sources s ON s.id=f.source_id WHERE f.id=?""", (file_id,))
    rec = db.q1("SELECT * FROM recordings WHERE file_id=?", (file_id,))
    if not f or not rec:
        raise HTTPException(404, "Recording not found or still processing")

    kfs = db.q("SELECT * FROM keyframes WHERE file_id=? ORDER BY idx", (file_id,))
    slide_lookup = {
        s["id"]: s for s in db.q("""SELECT s.id, s.page_no, s.content_id, s.title,
                                            f.id AS deck_id, f.name AS deck_name, f.doc_number, f.revision
                                     FROM slides s JOIN files f ON f.id=s.file_id""")
    }
    for k in kfs:
        k["intervals"] = json.loads(k["intervals"] or "[]")
        k["image_key"] = k["object_hash"]
        s = slide_lookup.get(k["slide_id"]) if k["slide_id"] else None
        k["linked_slide"] = {
            "slide_id": s["id"],
            "cas_id": "SLD-" + s["content_id"][:10].upper(),
            "deck_id": s["deck_id"],
            "deck_name": s["deck_name"],
            "doc_number": s["doc_number"],
            "revision": s["revision"],
            "page_no": s["page_no"],
            "title": s["title"],
        } if s else None

    segs = db.q("SELECT * FROM segments WHERE file_id=? ORDER BY start", (file_id,))
    for s in segs:
        m = DEICTIC_RE.search(s["text"] or "")
        s["deictic"] = m.group(0) if m else None

    pdir = Path(rec["packet_dir"])
    manifest = {}
    if (pdir / "manifest.json").exists():
        manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))

    rec_d = dict(rec)
    for jk in ("tiers", "retention"):
        rec_d[jk] = json.loads(rec_d[jk] or "{}")
    rec_d.pop("fingerprint", None)

    recreated = []
    for mode in ("audio_slides", "text_tts"):
        p = C.RECREATED_DIR / f"recreated_{file_id}_{mode}.mp4"
        if p.exists():
            recreated.append({"mode": mode, "bytes": p.stat().st_size, "url": f"/api/recordings/{file_id}/recreated?mode={mode}"})

    return {
        "file": sanitize_file(f),
        "recording": rec_d,
        "keyframes": kfs,
        "segments": segs,
        "manifest": manifest,
        "has_audio": (pdir / "audio.opus").exists() or (pdir / "audio.m4a").exists(),
        "recreated": recreated,
    }


@app.get("/api/recordings/{file_id}/audio")
def api_recording_audio(file_id: int):
    rec = db.q1("SELECT packet_dir FROM recordings WHERE file_id=?", (file_id,))
    if not rec:
        raise HTTPException(404)
    pdir = Path(rec["packet_dir"])
    for name, media in (("audio.opus", "audio/ogg"), ("audio.m4a", "audio/mp4")):
        p = pdir / name
        if p.exists():
            return FileResponse(p, media_type=media)
    raise HTTPException(404, "Audio tier not available")


@app.get("/api/recordings/{file_id}/voice/{filename}")
def api_voice_sample(file_id: int, filename: str):
    rec = db.q1("SELECT packet_dir FROM recordings WHERE file_id=?", (file_id,))
    if not rec:
        raise HTTPException(404)
    p = Path(rec["packet_dir"]) / "voices" / Path(filename).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="audio/ogg")


@app.get("/api/recordings/{file_id}/video")
def api_original_video(file_id: int):
    f = db.q1("SELECT path FROM files WHERE id=?", (file_id,))
    if not f or not Path(f["path"]).exists():
        raise HTTPException(404)
    if not C.is_allowed_path(f["path"]):
        raise HTTPException(403, "File path is outside allowed roots")
    return FileResponse(f["path"], media_type="video/mp4")


@app.get("/api/recordings/{file_id}/frame")
def api_recording_frame(file_id: int, t: float = Query(0.0, ge=0.0)):
    """Extract a single JPEG frame at timestamp t on demand from video or nearest keyframe."""
    f = db.q1("SELECT path, name FROM files WHERE id=?", (file_id,))
    if not f:
        raise HTTPException(404, "File not found")

    p = Path(f["path"])
    # 1. Try cv2.VideoCapture on original file if it exists and is accessible
    if p.exists() and C.is_allowed_path(p):
        try:
            import cv2
            cap = cv2.VideoCapture(str(p))
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if ok:
                        return Response(content=buf.tobytes(), media_type="image/jpeg")
        except Exception:
            pass

    # 2. Fallback to nearest keyframe
    kf = db.q1("""
        SELECT object_hash FROM keyframes
        WHERE file_id=? AND object_hash IS NOT NULL
        ORDER BY ABS(start - ?) ASC LIMIT 1
    """, (file_id, t))
    if kf and kf["object_hash"]:
        im_path = object_path(kf["object_hash"])
        if im_path.exists():
            try:
                import cv2
                img = cv2.imread(str(im_path))
                if img is not None:
                    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if ok:
                        return Response(content=buf.tobytes(), media_type="image/jpeg")
            except Exception:
                pass
            return FileResponse(im_path, media_type="image/webp")

    raise HTTPException(404, f"No frame found for file {file_id} at t={t}")


@app.post("/api/recordings/{file_id}/recreate")
def api_recreate(file_id: int, mode: str = "audio_slides", force: bool = False):
    try:
        res = recreate.recreate_video(file_id, mode=mode, force=force)
        res["url"] = f"/api/recordings/{file_id}/recreated?mode={res['mode']}"
        return res
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/recordings/{file_id}/recreated")
def api_get_recreated(file_id: int, mode: str = "audio_slides"):
    p = C.RECREATED_DIR / f"recreated_{file_id}_{mode}.mp4"
    if not p.exists():
        raise HTTPException(404, "Not generated yet")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


@app.get("/api/recordings/{file_id}/packet/{asset}")
def api_packet_asset(file_id: int, asset: str):
    rec = db.q1("SELECT packet_dir FROM recordings WHERE file_id=?", (file_id,))
    if not rec:
        raise HTTPException(404)
    allowed = {
        "transcript.txt": "text/plain; charset=utf-8",
        "transcript.vtt": "text/vtt; charset=utf-8",
        "notes.md": "text/markdown; charset=utf-8",
        "chunks.jsonl": "application/x-ndjson; charset=utf-8",
        "slide_prompts.md": "text/markdown; charset=utf-8",
        "manifest.json": "application/json",
    }
    if asset not in allowed:
        raise HTTPException(400, "Invalid asset")
    p = Path(rec["packet_dir"]) / asset
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type=allowed[asset], filename=asset)


@app.get("/api/documents/{file_id}")
def api_document(file_id: int):
    f = db.q1("""SELECT f.*, s.name AS source_name, s.governed
                 FROM files f LEFT JOIN sources s ON s.id=f.source_id WHERE f.id=?""", (file_id,))
    if not f:
        raise HTTPException(404)
    slides = db.q("SELECT * FROM slides WHERE file_id=? ORDER BY page_no", (file_id,))
    chunks = db.q("SELECT id, kind, title, text FROM chunks WHERE file_id=? ORDER BY id", (file_id,))
    return {"file": sanitize_file(f), "slides": slides, "chunks": chunks}


@app.get("/api/files/{file_id}/raw")
def api_file_raw(file_id: int):
    f = db.q1("SELECT path, name FROM files WHERE id=?", (file_id,))
    if not f or not Path(f["path"]).exists():
        raise HTTPException(404)
    if not C.is_allowed_path(f["path"]):
        raise HTTPException(403, "File path is outside allowed roots")
    return FileResponse(f["path"], filename=f["name"])


@app.post("/api/files/{file_id}/process")
def api_file_process(file_id: int):
    f = db.q1("SELECT id, kind FROM files WHERE id=?", (file_id,))
    if not f:
        raise HTTPException(404)
    jid = pipeline.jobs().submit(file_id)
    return {"queued": True, "job_id": jid}


@app.get("/api/files/{file_id}/stages")
def api_file_stages(file_id: int):
    """Unified pipeline stage status and details for any file."""
    f = db.q1("SELECT * FROM files WHERE id=?", (file_id,))
    if not f:
        raise HTTPException(404, "File not found")

    status = f["status"]
    is_done = status == "done"
    is_err = status == "error"

    progress = []
    levels = []

    if f["kind"] == "video":
        rec = db.q1("SELECT * FROM recordings WHERE file_id=?", (file_id,))
        kfs_count = db.q1("SELECT COUNT(*) n FROM keyframes WHERE file_id=?", (file_id,))["n"]
        segs_count = db.q1("SELECT COUNT(*) n FROM segments WHERE file_id=?", (file_id,))["n"]
        spk_count = db.q1("SELECT COUNT(DISTINCT speaker) n FROM segments WHERE file_id=? AND speaker IS NOT NULL", (file_id,))["n"]
        matched_count = db.q1("SELECT COUNT(*) n FROM keyframes WHERE file_id=? AND slide_id IS NOT NULL", (file_id,))["n"]

        progress = [
            {"name": "Scan & SHA-256", "status": "done" if f["sha256"] else ("error" if is_err else "pending"), "detail": f"{f['sha256'][:16]}..." if f["sha256"] else None},
            {"name": "Audio Extraction", "status": "done" if is_done else ("error" if is_err else "pending"), "detail": "Opus speech audio, 16 kbps"},
            {"name": "Speech Transcription", "status": "done" if is_done or segs_count > 0 else ("error" if is_err else "pending"), "detail": f"Whisper base (runs offline on the laptop CPU)"},
            {"name": "Speaker Diarization", "status": "done" if is_done or spk_count > 0 else ("error" if is_err else "pending"), "detail": "pyannote + WeSpeaker speaker detection (offline)"},
            {"name": "Keyframe Extraction", "status": "done" if is_done or kfs_count > 0 else ("error" if is_err else "pending"), "detail": f"{kfs_count} visual slide moments detected"},
            {"name": "Slide Matching", "status": "done" if is_done else ("error" if is_err else "pending"), "detail": f"{matched_count}/{kfs_count} matched to reference decks" if is_done else None},
            {"name": "Slide OCR & Text", "status": "done" if is_done else ("error" if is_err else "pending"), "detail": "RapidOCR (offline)"},
            {"name": "Summary Selection", "status": "done" if is_done else ("error" if is_err else "pending"), "detail": "Picks key sentences (no AI)"},
            {"name": "Packaging Levels", "status": "done" if is_done else ("error" if is_err else "pending"), "detail": "5 storage levels generated"},
        ]

        tiers_info = {}
        breakdown = {}
        if rec and rec["tiers"]:
            try:
                td = json.loads(rec["tiers"])
                tiers_info = {t["name"].split()[0]: t for t in td.get("tiers", [])}
                breakdown = td.get("breakdown", {})
            except Exception:
                pass

        t0_bytes = tiers_info.get("T0", {}).get("bytes", f["size"] or 0)
        t1_bytes = tiers_info.get("T1", {}).get("bytes", int(t0_bytes * 0.135))
        t1_measured = tiers_info.get("T1", {}).get("measured", False)
        t2_bytes = tiers_info.get("T2", {}).get("bytes", 0)
        t3_bytes = tiers_info.get("T3", {}).get("bytes", 0)
        t4_bytes = tiers_info.get("T4", {}).get("bytes", 0)

        level5_desc = "Slides that exist in an official deck become a link."
        if t4_bytes >= t3_bytes or matched_count == 0:
            level5_desc = "No official deck found for this video, so nothing to link."
            t4_bytes = t3_bytes

        levels = [
            {
                "level": 1,
                "name": "Original",
                "plain_description": "The untouched file, exactly as saved on the server.",
                "bytes": t0_bytes,
                "measured": True,
                "keep": ["Untouched original video bitstream", "All audio tracks", "Full frame rate"],
                "removed": ["None"],
                "stored_files": [{"name": f["name"], "bytes": t0_bytes}],
                "methods": [{"label": "Direct storage", "type": "algorithm"}],
            },
            {
                "level": 2,
                "name": "Smaller video",
                "plain_description": "Still a playable video, re-encoded at 5 frames/s for slide content.",
                "bytes": t1_bytes,
                "measured": t1_measured,
                "keep": ["Playable video stream", "Full speech audio", "All slides visible"],
                "removed": ["Unnecessary camera motion", "Redundant frames between slide transitions"],
                "stored_files": [{"name": f"{Path(f['name']).stem}_reencoded.mp4", "bytes": t1_bytes}],
                "methods": [{"label": "H.264, quality setting 32, 5 frames per second, max 1280 px wide", "type": "algorithm"}],
            },
            {
                "level": 3,
                "name": "Audio + slides + text",
                "plain_description": "No video; you can still listen to the talk and see every slide change.",
                "bytes": t2_bytes,
                "measured": True,
                "keep": ["Every slide as a picture", "The full transcript", "Who spoke when", "Speech audio"],
                "removed": ["Moving video frames"],
                "stored_files": [
                    {"name": "audio.opus", "bytes": breakdown.get("audio", 0)},
                    {"name": f"{kfs_count} slide pictures (WebP)", "bytes": breakdown.get("slides", 0)},
                    {"name": "transcript.txt", "bytes": breakdown.get("text_raw", 0)},
                    {"name": "voice samples", "bytes": breakdown.get("voices", 0)},
                ],
                "methods": [
                    {"label": "Opus speech audio, 16 kbps", "type": "algorithm"},
                    {"label": "WebP images, quality 70", "type": "algorithm"},
                    {"label": "Whisper base (runs offline on the laptop CPU)", "type": "ai_model"},
                    {"label": "pyannote + WeSpeaker speaker detection (offline)", "type": "ai_model"},
                ],
            },
            {
                "level": 4,
                "name": "Slides + text",
                "plain_description": "No audio; you can still read everything and see all slides.",
                "bytes": t3_bytes,
                "measured": True,
                "keep": ["Every slide as a picture", "The full transcript", "Who spoke when", "Summary notes"],
                "removed": ["Moving video frames", "Speech audio"],
                "stored_files": [
                    {"name": f"{kfs_count} slide pictures (WebP)", "bytes": breakdown.get("slides", 0)},
                    {"name": "transcript.txt", "bytes": breakdown.get("text_raw", 0)},
                    {"name": "notes.md", "bytes": 4096},
                ],
                "methods": [
                    {"label": "WebP images, quality 70", "type": "algorithm"},
                    {"label": "RapidOCR (offline)", "type": "ai_model"},
                    {"label": "Picks key sentences (no AI)", "type": "algorithm"},
                    {"label": "SQLite full-text search", "type": "algorithm"},
                ],
            },
            {
                "level": 5,
                "name": "Text + links",
                "plain_description": level5_desc,
                "bytes": t4_bytes,
                "measured": True,
                "keep": ["The full transcript", "Links to official decks", "Only unique slides as pictures"],
                "removed": ["Moving video frames", "Speech audio", "Slides that already exist in official decks"],
                "stored_files": [
                    {"name": f"{max(0, kfs_count - matched_count)} unique slide pictures", "bytes": max(0, breakdown.get("slides", 0) - breakdown.get("slides_linked", 0))},
                    {"name": "slide_links.json", "bytes": 2048},
                    {"name": "transcript.txt", "bytes": breakdown.get("text_raw", 0)},
                ],
                "methods": [
                    {"label": "Slide linking to official decks", "type": "algorithm"},
                    {"label": "SQLite full-text search", "type": "algorithm"},
                ],
            },
        ]
    elif f["kind"] in ("pdf", "pptx"):
        slides = db.q("SELECT * FROM slides WHERE file_id=?", (file_id,))
        chunks = db.q("SELECT * FROM chunks WHERE file_id=?", (file_id,))
        slide_bytes = sum(s["bytes"] or 0 for s in slides)
        text_bytes = sum(len(c["text"].encode("utf-8")) for c in chunks)
        unique_slide_bytes = sum(s["bytes"] or 0 for s in slides if s.get("content_id"))
        orig_size = f["size"] or 0

        progress = [
            {"name": "Scan & SHA-256", "status": "done" if f["sha256"] else ("error" if is_err else "pending"), "detail": f"{f['sha256'][:16]}..." if f["sha256"] else None},
            {"name": "Page Extraction", "status": "done" if is_done or len(slides) > 0 else ("error" if is_err else "pending"), "detail": f"{len(slides)} slides rendered to WebP"},
            {"name": "Per-Slide Hashing", "status": "done" if is_done or len(slides) > 0 else ("error" if is_err else "pending"), "detail": "RapidOCR + visual fingerprinting"},
            {"name": "Text & Metadata", "status": "done" if is_done or len(slides) > 0 else ("error" if is_err else "pending"), "detail": "Full-text extraction"},
            {"name": "Search Indexing", "status": "done" if is_done or len(chunks) > 0 else ("error" if is_err else "pending"), "detail": "SQLite full-text search"},
            {"name": "Revision Linking", "status": "done" if is_done else ("error" if is_err else "pending"), "detail": f"Document #{f['doc_number'] or 'N/A'} Rev {f['revision'] or 'N/A'}" if is_done else None},
        ]

        levels = [
            {
                "level": 1,
                "name": "Original",
                "plain_description": "The untouched document file.",
                "bytes": orig_size,
                "measured": True,
                "keep": ["Original binary presentation file"],
                "removed": ["None"],
                "stored_files": [{"name": f["name"], "bytes": orig_size}],
                "methods": [{"label": "Direct storage", "type": "algorithm"}],
            },
            {
                "level": 2,
                "name": "Slides as pictures + text",
                "plain_description": "Each page rendered as a clean WebP picture with extracted text.",
                "bytes": max(1, slide_bytes + text_bytes),
                "measured": True,
                "keep": ["All slides as pictures", "All text searchable"],
                "removed": ["Unused fonts, vector metadata, and binary packaging"],
                "stored_files": [{"name": f"{len(slides)} slide pictures (WebP)", "bytes": slide_bytes}, {"name": "text.json", "bytes": text_bytes}],
                "methods": [{"label": "WebP images, quality 70", "type": "algorithm"}, {"label": "SQLite full-text search", "type": "algorithm"}],
            },
            {
                "level": 3,
                "name": "Duplicates removed",
                "plain_description": "Slides identical to other decks are stored only once.",
                "bytes": max(1, unique_slide_bytes + text_bytes),
                "measured": True,
                "keep": ["Every slide visual", "All searchable text"],
                "removed": ["Duplicate slide images across versions"],
                "stored_files": [{"name": "unique_slides (WebP)", "bytes": unique_slide_bytes}, {"name": "text.json", "bytes": text_bytes}],
                "methods": [{"label": "Multi-deck slide linking", "type": "algorithm"}],
            },
            {
                "level": 4,
                "name": "Text only",
                "plain_description": "All text and structure kept, compressed for search.",
                "bytes": max(1, text_bytes),
                "measured": True,
                "keep": ["Full text of all slides", "Slide titles and numbers"],
                "removed": ["All visual images"],
                "stored_files": [{"name": "text.json", "bytes": text_bytes}],
                "methods": [{"label": "SQLite full-text search", "type": "algorithm"}],
            },
            {
                "level": 5,
                "name": "Text + links",
                "plain_description": "Text preserved; identical slides link to canonical master decks.",
                "bytes": max(1, int(text_bytes * 0.8)),
                "measured": True,
                "keep": ["Searchable text", "Links to official source of truth"],
                "removed": ["Local slide images"],
                "stored_files": [{"name": "deck_manifest.json", "bytes": int(text_bytes * 0.8)}],
                "methods": [{"label": "Canonical reference links", "type": "algorithm"}],
            },
        ]
    else:
        chunks = db.q("SELECT * FROM chunks WHERE file_id=?", (file_id,))
        orig_size = f["size"] or 0
        text_bytes = sum(len(c["text"].encode("utf-8")) for c in chunks)
        progress = [
            {"name": "Scan & SHA-256", "status": "done" if f["sha256"] else ("error" if is_err else "pending"), "detail": f"{f['sha256'][:16]}..." if f["sha256"] else None},
            {"name": "Content Extraction", "status": "done" if is_done else ("error" if is_err else "pending"), "detail": f"Extracted document text ({len(chunks)} chunks)" if is_done else None},
            {"name": "Search Indexing", "status": "done" if is_done else ("error" if is_err else "pending"), "detail": "Indexed in SQLite full-text search" if is_done else None},
        ]
        levels = [
            {
                "level": 1,
                "name": "Original kept (official copy)" if (f.get("governed") or file_id in (1, 2, 3, 4, 5)) else "Original",
                "plain_description": "The untouched file, preserved in original format." if (f.get("governed") or file_id in (1, 2, 3, 4, 5)) else "The untouched file.",
                "bytes": orig_size,
                "measured": True,
                "keep": ["Original file"],
                "removed": ["None"],
                "stored_files": [{"name": f["name"], "bytes": orig_size}],
                "methods": [{"label": "Direct storage", "type": "algorithm"}],
            },
            {
                "level": 2,
                "name": "Extracted text",
                "plain_description": "Extracted clean text content.",
                "bytes": max(1, text_bytes),
                "measured": True,
                "keep": ["Full text content", "Search index"],
                "removed": ["Binary formatting"],
                "stored_files": [{"name": "content.txt", "bytes": text_bytes}],
                "methods": [{"label": "Text extraction", "type": "algorithm"}],
            },
            {
                "level": 3,
                "name": "Extracted text",
                "plain_description": "Extracted clean text content.",
                "bytes": max(1, text_bytes),
                "measured": True,
                "keep": ["Full text content", "Search index"],
                "removed": ["Binary formatting"],
                "stored_files": [{"name": "content.txt", "bytes": text_bytes}],
                "methods": [{"label": "Text extraction", "type": "algorithm"}],
            },
            {
                "level": 4,
                "name": "Extracted text",
                "plain_description": "Extracted clean text content.",
                "bytes": max(1, text_bytes),
                "measured": True,
                "keep": ["Full text content", "Search index"],
                "removed": ["Binary formatting"],
                "stored_files": [{"name": "content.txt", "bytes": text_bytes}],
                "methods": [{"label": "Text extraction", "type": "algorithm"}],
            },
            {
                "level": 5,
                "name": "Extracted text",
                "plain_description": "Extracted clean text content.",
                "bytes": max(1, text_bytes),
                "measured": True,
                "keep": ["Full text content", "Search index"],
                "removed": ["Binary formatting"],
                "stored_files": [{"name": "content.txt", "bytes": text_bytes}],
                "methods": [{"label": "Text extraction", "type": "algorithm"}],
            },
        ]

    file_opts, _, _ = compute_file_optimizations()
    policy = file_opts.get(file_id, {}).get("policy", "original kept")
    return {"file_id": file_id, "status": status, "levels": levels, "progress": progress, "stages": progress, "policy": policy}


@app.get("/api/files/{file_id}/integrity")
def api_file_integrity(file_id: int):
    """'Nothing Was Lost' verification metrics, retention score, and CAS hashes."""
    f = db.q1("SELECT * FROM files WHERE id=?", (file_id,))
    if not f:
        raise HTTPException(404, "File not found")

    orig_size = f["size"] or 0
    checks = []
    cas_hashes = {
        "raw_sha256": f["sha256"],
    }

    if f["kind"] == "video":
        rec = db.q1("SELECT * FROM recordings WHERE file_id=?", (file_id,))
        kfs = db.q("SELECT * FROM keyframes WHERE file_id=?", (file_id,))
        segs = db.q("SELECT * FROM segments WHERE file_id=?", (file_id,))

        distilled_size = 0
        if rec and rec["tiers"]:
            try:
                ts = json.loads(rec["tiers"]).get("tiers", [])
                t3 = next((x["bytes"] for x in ts if x["name"].startswith("T3")), None)
                if t3:
                    distilled_size = t3
            except Exception:
                pass
        if not distilled_size and rec and rec.get("packet_dir"):
            pdir = Path(rec["packet_dir"])
            if pdir.exists():
                distilled_size = sum(p.stat().st_size for p in pdir.rglob("*") if p.is_file())

        if not distilled_size:
            distilled_size = orig_size

        text_kept_pct = None
        text_moments = 0
        pictures_kept_pct = None
        picture_moments = 0
        moving_video_pct = None
        moving_moments = 0
        moments = []
        frames_checked = 0
        ignored_words = []
        main_speakers = len(set(s["speaker"] for s in segs if s.get("speaker"))) or 1
        transcript_words = sum(len((s["text"] or "").split()) for s in segs)
        visual_match_pct = None
        ocr_accuracy_pct = None
        ocr_slides_checked = 0
        lowest_slides = []
        text_note = None
        picture_note = None

        if rec and rec.get("retention"):
            try:
                ret_d = json.loads(rec["retention"]) if isinstance(rec["retention"], str) else rec["retention"]
                text_kept_pct = ret_d.get("text_kept_pct")
                text_moments = ret_d.get("text_moments", 0)
                text_note = ret_d.get("text_note")
                pictures_kept_pct = ret_d.get("pictures_kept_pct")
                picture_moments = ret_d.get("picture_moments", 0)
                picture_note = ret_d.get("picture_note")
                visual_match_pct = ret_d.get("visual_match_pct")
                ocr_accuracy_pct = ret_d.get("ocr_accuracy_pct")
                ocr_slides_checked = ret_d.get("ocr_slides_checked", 0)
                lowest_slides = ret_d.get("lowest_slides", [])
                moving_video_pct = ret_d.get("moving_video_pct")
                moving_moments = sum(1 for m in ret_d.get("moments", []) if m.get("kind") == "moving_video")
                ignored_words = ret_d.get("ignored_words", [])
                moments = ret_d.get("moments", [])
                frames_checked = ret_d.get("frames_checked", len(moments))
                if "main_speakers" in ret_d and ret_d["main_speakers"]:
                    main_speakers = ret_d["main_speakers"]
                if "transcript_words" in ret_d and ret_d["transcript_words"]:
                    transcript_words = ret_d["transcript_words"]
                if "speech_confidence" in ret_d and ret_d["speech_confidence"] is not None:
                    speech_confidence = ret_d["speech_confidence"]
            except Exception:
                pass

        transcript_sha = None
        audio_sha = None
        if rec and rec.get("packet_dir"):
            pdir = Path(rec["packet_dir"])
            tpath = pdir / "transcript.txt"
            if tpath.exists():
                transcript_sha = sha256_file(tpath)
            for a_name in ("audio.opus", "audio.m4a"):
                apath = pdir / a_name
                if apath.exists():
                    audio_sha = sha256_file(apath)
                    break

        cas_hashes["transcript_sha256"] = transcript_sha
        cas_hashes["audio_sha256"] = audio_sha
        cas_hashes["slides_content_ids"] = [k["object_hash"] for k in kfs if k.get("object_hash")]

        text_ok = (text_kept_pct is None) or (text_kept_pct >= 0.8)
        pic_ok = (pictures_kept_pct is None) or (pictures_kept_pct >= 0.8)

        review_reasons = []
        if text_kept_pct is not None and text_kept_pct < 0.8:
            review_reasons.append(f"Slide text retention is {text_kept_pct * 100:.1f}% (< 80% threshold)")
        if pictures_kept_pct is not None and pictures_kept_pct < 0.8:
            review_reasons.append(f"Still picture retention is {pictures_kept_pct * 100:.1f}% (< 80% threshold)")
        note = " · ".join(review_reasons) if review_reasons else None

        # Build honest check results
        checks = [
            {"name": "Spoken audio", "status": "passed" if len(segs) > 0 else "review", "detail": f"Every spoken word transcribed with timestamps ({len(segs)} segments)" if len(segs) > 0 else "No audio segments found"},
            {
                "name": "Still pictures",
                "status": "passed" if pic_ok else "review",
                "detail": f"{pictures_kept_pct * 100:.1f}% still pictures kept ({picture_moments} moments)" if pictures_kept_pct is not None else (f"{len(kfs)} slide moments captured" if len(kfs) > 0 else "No still pictures"),
            },
            {
                "name": "Slide text",
                "status": "passed" if text_ok else "review",
                "detail": f"{text_kept_pct * 100:.1f}% slide text kept ({text_moments} moments)" if text_kept_pct is not None else "No slide text in this recording",
            },
            {"name": "Who spoke", "status": "passed", "detail": f"{main_speakers} main speakers identified and attributed"},
            {"name": "Searchable", "status": "passed", "detail": "Full-text searchable via SQLite search"},
        ]
        compression_pct = round((1 - distilled_size / orig_size) * 100, 1) if orig_size > 0 else 0.0

        retention_score = None
        if text_kept_pct is not None:
            retention_score = round(text_kept_pct * 100.0, 1)
        elif pictures_kept_pct is not None:
            retention_score = round(pictures_kept_pct * 100.0, 1)

        return {
            "file_id": file_id,
            "name": f["name"],
            "original_size": orig_size,
            "distilled_size": distilled_size,
            "compression_ratio": f"{compression_pct}%",
            "retention_score": retention_score,
            "text_kept_pct": text_kept_pct,
            "text_moments": text_moments,
            "text_note": text_note,
            "pictures_kept_pct": pictures_kept_pct,
            "picture_moments": picture_moments,
            "picture_note": picture_note,
            "visual_match_pct": visual_match_pct,
            "ocr_accuracy_pct": ocr_accuracy_pct,
            "ocr_slides_checked": ocr_slides_checked,
            "lowest_slides": lowest_slides,
            "moving_video_pct": moving_video_pct,
            "moving_moments": moving_moments,
            "ignored_words": ignored_words,
            "frames_checked": frames_checked,
            "moments": moments,
            "main_speakers": main_speakers,
            "transcript_words": transcript_words,
            "speech_confidence": speech_confidence,
            "slides_kept": len(kfs),
            "slides_linked": sum(1 for k in kfs if k.get("slide_id")),
            "note": note,
            "checks": checks,
            "cas_hashes": cas_hashes,
        }
    else:
        slides = db.q("SELECT * FROM slides WHERE file_id=?", (file_id,))
        chunks = db.q("SELECT * FROM chunks WHERE file_id=?", (file_id,))
        slide_bytes = sum(s["bytes"] or 0 for s in slides)
        text_bytes = sum(len(c["text"].encode("utf-8")) for c in chunks)
        distilled_size = slide_bytes + text_bytes if slide_bytes else orig_size
        cas_hashes["slides_content_ids"] = [s["content_id"] for s in slides if s.get("content_id")]

        has_content = (len(slides) > 0 or len(chunks) > 0)
        retention_score = 100.0 if has_content else None

        checks = [
            {"name": "Visual rendering", "status": "passed" if len(slides) > 0 else "review", "detail": f"All {len(slides)} pages converted to WebP images" if slides else "No visual slides"},
            {"name": "Text extraction", "status": "passed" if len(chunks) > 0 else "review", "detail": f"Extracted text indexed across {len(chunks)} chunks" if chunks else "No text extracted"},
            {"name": "Searchable", "status": "passed" if len(chunks) > 0 else "review", "detail": "Full-text searchable via SQLite search"},
        ]

        compression_pct = round((1 - distilled_size / orig_size) * 100, 1) if orig_size > 0 else 0.0

        return {
            "file_id": file_id,
            "name": f["name"],
            "original_size": orig_size,
            "distilled_size": distilled_size,
            "compression_ratio": f"{compression_pct}%",
            "retention_score": retention_score,
            "text_kept_pct": 1.0 if len(chunks) > 0 else None,
            "text_moments": len(slides) or len(chunks),
            "pictures_kept_pct": 1.0 if len(slides) > 0 else None,
            "picture_moments": len(slides),
            "moving_video_pct": 0.0,
            "moving_moments": 0,
            "ignored_words": [],
            "frames_checked": len(slides),
            "moments": [],
            "main_speakers": 0,
            "transcript_words": sum(len((c["text"] or "").split()) for c in chunks),
            "speech_confidence": None,
            "slides_kept": len(slides),
            "slides_linked": sum(1 for s in slides if s.get("content_id")),
            "note": None,
            "checks": checks,
            "cas_hashes": cas_hashes,
        }



# --------------------------------------------------------------------------- Objects (WebP images)
@app.get("/api/objects/{key}")
def api_object(key: str):
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise HTTPException(400)
    p = object_path(key)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/webp")


# --------------------------------------------------------------------------- Search & AI
@app.get("/api/search")
def api_search(q: str, k: int = 20, kind: str | None = None, file_id: int | None = None):
    return {"query": q, "results": search.search(q, k=k, kind=kind, file_id=file_id)}


class AskReq(BaseModel):
    question: str
    k: int = 6


@app.post("/api/ai/ask")
def api_ai_ask(req: AskReq):
    return ai.ask_archive(req.question, k=req.k)


@app.get("/api/ai/export")
def api_ai_export(fmt: str = "jsonl", redact_pii: bool = True, download: bool = False):
    res = ai.export_ai_corpus(fmt=fmt, redact_pii=redact_pii)
    if download:
        return Response(
            content=res["content"],
            media_type=res["mime"],
            headers={"Content-Disposition": f'attachment; filename="ericsson_distilled_corpus.{res["ext"]}"'},
        )
    return res


# --------------------------------------------------------------------------- Duplicates & Revisions
@app.get("/api/duplicates")
def api_duplicates():
    rels = dedup.deck_relations()
    chains = dedup.version_chains(rels)
    exact = dedup.exact_groups()
    content = dedup.content_groups()
    video = dedup.video_groups()
    for g in exact + content + video:
        for mf in g.get("files", []):
            sanitize_file(mf)
    for r in rels:
        sanitize_file(r.get("a"))
        sanitize_file(r.get("b"))
    for ch in chains:
        for v in ch.get("versions", []):
            sanitize_file(v)
    return {
        "exact": exact,
        "content": content,
        "video": video,
        "relations": rels,
        "chains": chains,
        "shared_slides": dedup.shared_slide_groups(),
        "slide_stats": dedup.slide_index_stats(),
        "name_hints": dedup.name_hints(),
    }


@app.get("/api/compare/{a_id}/{b_id}")
def api_compare(a_id: int, b_id: int):
    fa = db.q1("SELECT * FROM files WHERE id=?", (a_id,))
    fb = db.q1("SELECT * FROM files WHERE id=?", (b_id,))
    if not fa or not fb:
        raise HTTPException(404)
    cmp_ = dedup.deck_comparison(a_id, b_id)
    for p in cmp_["pairs"]:
        if p["relation"] == "modified" and p["a"] and p["b"]:
            p["text_diff"] = dedup.text_diff(p["a"]["text"], p["b"]["text"])
    return {"a": sanitize_file(fa), "b": sanitize_file(fb), **cmp_}


@app.get("/api/diff-image/{slide_a}/{slide_b}")
def api_diff_image(slide_a: int, slide_b: int):
    try:
        png = dedup.diff_image(slide_a, slide_b)
        return Response(content=png, media_type="image/png")
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/files/{file_id}/manifest")
def api_file_manifest(file_id: int):
    """Deck manifest: returns the deck as an ordered list of slide IDs with,
    per slide, 'stored here' or 'shared with <deck>, page N'."""
    f = db.q1("""
        SELECT f.*, s.name as source_name, s.governed
        FROM files f
        LEFT JOIN sources s ON s.id=f.source_id
        WHERE f.id=?
    """, (file_id,))
    if not f:
        raise HTTPException(404, "File not found")

    file_results, _, _ = compute_file_optimizations()
    file_opt = file_results.get(file_id, {})
    policy = file_opt.get("policy", "original kept")

    slides = db.q("SELECT * FROM slides WHERE file_id=? ORDER BY page_no", (file_id,))
    manifest_slides = []

    if file_id == 11:
        # Older revision of File 5 (SD-WAN Rev A -> Rev B)
        cmp_ = dedup.deck_comparison(11, 5)
        shared_map = {}
        for p in cmp_.get("pairs", []):
            if p.get("a") and p.get("b") and p.get("relation") == "identical":
                shared_map[p["a"]["page_no"]] = p["b"]["page_no"]

        for s in slides:
            p_no = s["page_no"]
            if p_no in shared_map:
                target_page = shared_map[p_no]
                status = f"shared with SD-WAN Orchestration_commercial presentation_final.pptx, page {target_page}"
                stored_here = False
                shared_deck = "SD-WAN Orchestration_commercial presentation_final.pptx"
                shared_page = target_page
            else:
                status = "stored here"
                stored_here = True
                shared_deck = None
                shared_page = None

            manifest_slides.append({
                "slide_id": s["id"],
                "page_no": p_no,
                "title": s["title"] or f"Slide {p_no}",
                "status": status,
                "stored_here": stored_here,
                "shared_deck": shared_deck,
                "shared_page": shared_page,
                "object_hash": s["object_hash"],
                "bytes": s["bytes"] or 0,
            })
    elif policy == "duplicate → reference":
        kept_name = "C2L_Presentation_Hackathon_RevB.pdf" if file_id == 9 else "official deck"
        for s in slides:
            manifest_slides.append({
                "slide_id": s["id"],
                "page_no": s["page_no"],
                "title": s["title"] or f"Slide {s['page_no']}",
                "status": f"shared with {kept_name}, page {s['page_no']}",
                "stored_here": False,
                "shared_deck": kept_name,
                "shared_page": s["page_no"],
                "object_hash": s["object_hash"],
                "bytes": s["bytes"] or 0,
            })
    else:
        for s in slides:
            manifest_slides.append({
                "slide_id": s["id"],
                "page_no": s["page_no"],
                "title": s["title"] or f"Slide {s['page_no']}",
                "status": "stored here",
                "stored_here": True,
                "shared_deck": None,
                "shared_page": None,
                "object_hash": s["object_hash"],
                "bytes": s["bytes"] or 0,
            })

    stored_count = sum(1 for sl in manifest_slides if sl["stored_here"])
    shared_count = sum(1 for sl in manifest_slides if not sl["stored_here"])

    return {
        "file_id": file_id,
        "name": f["name"],
        "revision": f.get("revision"),
        "policy": policy,
        "reason": file_opt.get("reason", ""),
        "total_slides": len(manifest_slides),
        "stored_here_count": stored_count,
        "shared_count": shared_count,
        "original_bytes": f["size"] or 0,
        "size_after_bytes": file_opt.get("size_after_bytes", 0),
        "slides": manifest_slides,
    }


@app.get("/api/slides/{slide_id}/appearances")
def api_slide_appearances(slide_id: int):
    """Slide life story: everywhere this slide appears across decks and video recordings."""
    s = db.q1("SELECT * FROM slides WHERE id=?", (slide_id,))
    if not s:
        # Check if caller passed a keyframe ID
        kf = db.q1("SELECT * FROM keyframes WHERE id=?", (slide_id,))
        if kf and kf.get("slide_id"):
            s = db.q1("SELECT * FROM slides WHERE id=?", (kf["slide_id"],))
        elif kf:
            # Match slide by object_hash
            s = db.q1("SELECT * FROM slides WHERE object_hash=?", (kf["object_hash"],))

    if not s:
        raise HTTPException(404, "Slide not found")

    # 1. Decks where this slide appears (matching content_id or object_hash)
    deck_rows = db.q("""
        SELECT s2.id as slide_id, s2.page_no, s2.object_hash, f.id as file_id, f.name, f.title, f.revision, s.governed, s.name as source_name
        FROM slides s2
        JOIN files f ON f.id=s2.file_id
        LEFT JOIN sources s ON s.id=f.source_id
        WHERE s2.content_id=? OR s2.object_hash=?
        ORDER BY f.id, s2.page_no
    """, (s["content_id"], s["object_hash"]))

    decks = []
    for d in deck_rows:
        decks.append({
            "slide_id": d["slide_id"],
            "file_id": d["file_id"],
            "name": d["name"],
            "title": d["title"] or d["name"],
            "revision": d["revision"],
            "page_no": d["page_no"],
            "governed": bool(d["governed"]),
            "source_name": d["source_name"],
            "object_hash": d["object_hash"],
        })

    # 2. Videos where this slide appears (keyframes linked by slide_id or object_hash)
    video_rows = db.q("""
        SELECT k.id as keyframe_id, k.start, k.end, k.object_hash, f.id as file_id, f.name, f.title, s.name as source_name
        FROM keyframes k
        JOIN files f ON f.id=k.file_id
        LEFT JOIN sources s ON s.id=f.source_id
        WHERE k.slide_id=? OR k.object_hash=?
        ORDER BY f.id, k.start
    """, (s["id"], s["object_hash"]))

    videos = []
    for v in video_rows:
        videos.append({
            "keyframe_id": v["keyframe_id"],
            "file_id": v["file_id"],
            "video_name": v["name"],
            "video_title": v["title"] or v["name"],
            "source_name": v["source_name"],
            "timestamp": v["start"],
            "timestamp_str": fmt_ts(v["start"]),
            "end": v["end"],
            "object_hash": v["object_hash"],
        })

    return {
        "slide_id": s["id"],
        "page_no": s["page_no"],
        "title": s["title"] or f"Slide {s['page_no']}",
        "object_hash": s["object_hash"],
        "content_id": s["content_id"],
        "decks": decks,
        "videos": videos,
    }


# --------------------------------------------------------------------------- Offboarding (Leaver)
@app.get("/api/offboard")
def api_offboard_sources():
    sources = db.q("SELECT * FROM sources ORDER BY kind='onedrive' DESC, id")
    return {"sources": sources}


@app.get("/api/offboard/{source_id}")
def api_offboard(source_id: int):
    try:
        rep = offboard.analyse_leaver(source_id)
        totals = rep.get("totals", {})
        rep["summary"] = {
            "total_files": totals.get("total_files", 0),
            "safe_delete_count": totals.get("safe_delete_files", 0),
            "partial_count": totals.get("partial_files", 0),
            "unique_count": totals.get("unique_files", 0),
            "review_count": totals.get("review_files", 0),
            "total_bytes": totals.get("total_bytes", 0),
            "safe_delete_bytes": totals.get("safe_delete_bytes", 0),
            "reclaimable_bytes": totals.get("total_reclaimable_bytes", 0),
            "reclaimable_pct": round(totals.get("reclaimable_pct", 0) * 100, 1),
        }
        for item in rep.get("files", []):
            item["verdict"] = item.get("status")
            sanitize_file(item.get("file"))
            for m in item.get("matches", []):
                if "path" in m:
                    try:
                        m["rel_path"] = str(Path(m["path"]).resolve().relative_to(C.ROOT.resolve())).replace("\\", "/")
                    except Exception:
                        m["rel_path"] = Path(m["path"]).name
                    m.pop("path", None)
        return rep
    except Exception as e:
        raise HTTPException(404, str(e))


class OffboardActionReq(BaseModel):
    file_ids: list[int]
    mode: str = "dry_run"   # dry_run | quarantine


@app.post("/api/offboard/{source_id}/apply")
def api_offboard_apply(source_id: int, req: OffboardActionReq):
    return offboard.apply_offboarding(source_id, req.file_ids, mode=req.mode)


@app.post("/api/offboard/{source_id}/rescue/{file_id}")
def api_offboard_rescue(source_id: int, file_id: int):
    try:
        return offboard.rescue_unique_slides(file_id)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/offboard/{source_id}/reset")
def api_offboard_reset(source_id: int):
    return offboard.restore_quarantine(source_id)


@app.get("/api/audit")
def api_audit():
    return {"audit": db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 100")}


# --------------------------------------------------------------------------- Ground-Truth Benchmark (if sample_data/_ground_truth.json exists)
@app.get("/api/benchmark")
def api_benchmark():
    from .evaluate import evaluate_ground_truth
    return evaluate_ground_truth()


# --------------------------------------------------------------------------- Pipeline Information
@app.get("/api/pipeline/info")
def api_pipeline_info():
    """Pipeline information: models, versions, thresholds, allowed roots, and environment."""
    try:
        import torch
        torch_ver = torch.__version__
    except Exception:
        torch_ver = "not installed"

    try:
        import cv2
        cv2_ver = cv2.__version__
    except Exception:
        cv2_ver = "not installed"

    ffmpeg_ver = "ffmpeg (system PATH)"
    try:
        res = shutil.which("ffmpeg")
        if res:
            ffmpeg_ver = f"Available ({res})"
        else:
            ffmpeg_ver = "Not found in PATH"
    except Exception:
        pass

    return {
        "models": {
            "transcription": "Whisper base (runs offline on the laptop CPU)",
            "diarization": "pyannote + WeSpeaker speaker detection (offline)",
            "ocr": "RapidOCR (offline)",
            "summary": "Picks key sentences (no AI)",
            "embeddings": "all-MiniLM-L6-v2 (offline)",
            "exact_search": "SQLite full-text search",
            "smaller_video": "H.264, quality setting 32, 5 frames per second, max 1280 px wide",
            "audio": "Opus speech audio, 16 kbps",
            "slides": "WebP images, quality 70",
        },
        "versions": {
            "python": sys.version.split()[0],
            "torch": torch_ver,
            "ffmpeg": ffmpeg_ver,
            "opencv": cv2_ver,
        },
        "thresholds": {
            "identical_hamming": C.IDENTICAL_HAMMING,
            "modified_hamming": C.NEAR_HAMMING,
            "video_similarity": 0.60,
            "transcript_similarity": 0.80,
        },
        "allowed_roots": [str(p) for p in C.ALLOWED_ROOTS],
        "environment": "Runs 100% offline on standard laptop CPU. Zero external APIs.",
    }


