"""FastAPI application for Distill."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from . import ai, config as C, db, dedup, offboard, pipeline, recreate, search
from .util import object_path

app = FastAPI(title="Distill — Ericsson Data Storage Optimization")

UI_DIR = Path(__file__).resolve().parent / "ui"

DEICTIC_RE = re.compile(
    r"\b(as you (?:can )?see here|look at (?:this|the)|on this (?:slide|chart|graph|diagram)|"
    r"here on the (?:left|right)|shown (?:here|above|below)|this (?:chart|graph|diagram|table|slide))\b",
    re.I,
)


@app.on_event("startup")
def _startup() -> None:
    db.init()


# --------------------------------------------------------------------------- UI
@app.get("/", response_class=HTMLResponse)
def index():
    p = UI_DIR / "index.html"
    if not p.exists():
        return HTMLResponse("<h1>Distill API running (ui/index.html missing)</h1>")
    return HTMLResponse(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- Health / Overview / Sources
@app.get("/api/overview")
def api_overview():
    db.init()
    files = db.q("""SELECT f.*, s.name AS source_name, s.kind AS source_kind, s.governed
                    FROM files f LEFT JOIN sources s ON s.id=f.source_id""")
    recs = db.q("SELECT * FROM recordings")
    rec_map = {r["file_id"]: r for r in recs}

    total_bytes = sum(f["size"] or 0 for f in files)
    video_files = [f for f in files if f["kind"] == "video"]
    doc_files = [f for f in files if f["kind"] in ("pdf", "pptx")]

    # Deduplicated video tiers (count unique videos by sha256 or per-file)
    tier_totals = {"T0": 0, "T1": 0, "T2": 0, "T3": 0, "T4": 0}
    retentions = []
    for f in video_files:
        r = rec_map.get(f["id"])
        if r and r["tiers"]:
            t = json.loads(r["tiers"])
            for entry in t.get("tiers", []):
                code = entry["name"].split()[0]
                if code in tier_totals:
                    tier_totals[code] += entry["bytes"]
        else:
            for k in tier_totals:
                tier_totals[k] += f["size"] or 0
        if r and r["retention"]:
            ret = json.loads(r["retention"])
            if ret.get("screen_text_retained") is not None:
                retentions.append(ret["screen_text_retained"])

    exact = dedup.exact_groups()
    content = dedup.content_groups()
    vgroups = dedup.video_groups()
    slide_stats = dedup.slide_index_stats()
    chains = dedup.version_chains()

    exact_save = sum(g["reclaimable"] for g in exact)
    content_save = sum(g["reclaimable"] for g in content)
    video_dup_save = sum(g["reclaimable"] for g in vgroups if not g["byte_identical"])

    # Content-addressable document storage (each unique slide stored once)
    doc_bytes_raw = sum(f["size"] or 0 for f in doc_files)
    unique_slide_bytes = db.q1("""
        SELECT COALESCE(SUM(bytes), 0) AS b FROM (
            SELECT content_id, MIN(bytes) AS bytes FROM slides GROUP BY content_id
        )
    """)["b"]
    # Add text/overhead ~5 KB per deck
    doc_bytes_dedup = unique_slide_bytes + len(doc_files) * 4096

    # Best-case total optimized footprint: unique videos at T3 + deduplicated slides
    # (count unique video sets at T3, duplicates at 0)
    dup_video_ids = set()
    for g in vgroups:
        for m in g["files"]:
            if m["id"] != g["keep"]:
                dup_video_ids.add(m["id"])
    t3_unique_video_bytes = 0
    for f in video_files:
        if f["id"] in dup_video_ids:
            continue
        r = rec_map.get(f["id"])
        if r and r["tiers"]:
            ts = json.loads(r["tiers"]).get("tiers", [])
            t3 = next((x["bytes"] for x in ts if x["name"].startswith("T3")), f["size"])
            t3_unique_video_bytes += t3
        else:
            t3_unique_video_bytes += f["size"] or 0

    optimized_total = t3_unique_video_bytes + min(doc_bytes_raw, doc_bytes_dedup)
    total_saving_pct = round(1 - optimized_total / total_bytes, 4) if total_bytes else 0.0

    # Breakdown by source system
    sources = db.q("SELECT * FROM sources ORDER BY id")
    by_source = []
    for s in sources:
        sf = [f for f in files if f["source_id"] == s["id"]]
        by_source.append({
            **s,
            "file_count": len(sf),
            "bytes": sum(f["size"] or 0 for f in sf),
            "videos": sum(1 for f in sf if f["kind"] == "video"),
            "docs": sum(1 for f in sf if f["kind"] in ("pdf", "pptx")),
            "done": sum(1 for f in sf if f["status"] == "done"),
        })

    chunks_count = db.q1("SELECT COUNT(*) n FROM chunks")["n"]
    return {
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
        "storage": {
            "total_bytes": total_bytes,
            "video_bytes": sum(f["size"] or 0 for f in video_files),
            "doc_bytes": doc_bytes_raw,
            "optimized_total_bytes": optimized_total,
            "total_saving_pct": total_saving_pct,
            "tier_totals": tier_totals,
            "dedup_savings": {
                "exact_bytes": exact_save,
                "content_bytes": content_save,
                "video_perceptual_bytes": video_dup_save,
                "doc_slide_cas_bytes": max(0, doc_bytes_raw - doc_bytes_dedup),
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


class IngestReq(BaseModel):
    roots: list[str]


@app.post("/api/ingest")
def api_ingest(req: IngestReq):
    valid = [r for r in req.roots if Path(r).exists()]
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
    roots = [str(p) for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith((".", "_"))]
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



@app.post("/api/upload")
async def api_upload(source_name: str = Query("Uploaded_Material"), files: list[UploadFile] = File(...)):
    up_dir = C.DATA_DIR / "uploads" / source_name
    up_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for uf in files:
        dst = up_dir / Path(uf.filename).name
        with open(dst, "wb") as out:
            shutil.copyfileobj(uf.file, out)
        saved.append(str(dst))
    res = pipeline.ingest(str(up_dir), name=source_name, kind="other", governed=True)
    return {"uploaded": len(saved), **res}


@app.post("/api/reset")
def api_reset():
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
    for r in rows:
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
        "file": f,
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
    return FileResponse(f["path"], media_type="video/mp4")


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
    return {"file": f, "slides": slides, "chunks": chunks}


@app.get("/api/files/{file_id}/raw")
def api_file_raw(file_id: int):
    f = db.q1("SELECT path, name FROM files WHERE id=?", (file_id,))
    if not f or not Path(f["path"]).exists():
        raise HTTPException(404)
    return FileResponse(f["path"], filename=f["name"])


@app.post("/api/files/{file_id}/process")
def api_file_process(file_id: int):
    f = db.q1("SELECT id, kind FROM files WHERE id=?", (file_id,))
    if not f:
        raise HTTPException(404)
    jid = pipeline.jobs().submit(file_id)
    return {"queued": True, "job_id": jid}


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
    return {
        "exact": dedup.exact_groups(),
        "content": dedup.content_groups(),
        "video": dedup.video_groups(),
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
    return {"a": fa, "b": fb, **cmp_}


@app.get("/api/diff-image/{slide_a}/{slide_b}")
def api_diff_image(slide_a: int, slide_b: int):
    try:
        png = dedup.diff_image(slide_a, slide_b)
        return Response(content=png, media_type="image/png")
    except Exception as e:
        raise HTTPException(400, str(e))


# --------------------------------------------------------------------------- Offboarding (Leaver)
@app.get("/api/offboard")
def api_offboard_sources():
    sources = db.q("SELECT * FROM sources ORDER BY kind='onedrive' DESC, id")
    return {"sources": sources}


@app.get("/api/offboard/{source_id}")
def api_offboard(source_id: int):
    try:
        return offboard.analyse_leaver(source_id)
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

