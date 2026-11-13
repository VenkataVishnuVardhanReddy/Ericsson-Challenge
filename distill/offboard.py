"""Employee offboarding ("leaver") analysis and safe-cleanup engine.

When an employee leaves the company, every file in their OneDrive (or chosen source)
is analysed against all other systems (SharePoint, Ericsson Play, other OneDrives):
  * safe_delete : exact byte copy, identical-content PDF/PPTX, or perceptually
                  equivalent video already exists in another location (preferring
                  governed SharePoint / Ericsson Play locations).
  * partial     : a deck shares some slides with existing files, and also contains
                  unique slides -> rescue ONLY the unique slides into a compact PDF,
                  then the original copy can be archived/deleted safely.
  * unique      : exists nowhere else -> keep (or distill a video into a tiny
                  Knowledge Packet before removing the raw MP4).

Nothing is ever deleted automatically: dry-run by default, explicit human confirmation
required, rescued artifacts written safely first, and every action recorded in the audit log.
"""
from __future__ import annotations

import json
import shutil
import time
from collections import defaultdict
from pathlib import Path

from . import config as C
from . import db
from . import dedup
from .dedup import video_similarity
from .util import hamming_hex


def _governed_copy_check(copies: list[dict]) -> tuple[bool, list[dict]]:
    # Sort preferred canonical location first (governed=1, shortest canonical path)
    ordered = sorted(copies, key=lambda c: (-(c["governed"] or 0), len(c["name"] or ""), c["id"]))
    return any(c["governed"] for c in ordered), ordered


def analyse_leaver(source_id: int) -> dict:
    src = db.q1("SELECT * FROM sources WHERE id=?", (source_id,))
    if not src:
        raise ValueError(f"Source {source_id} not found")

    own_files = db.q("SELECT * FROM files WHERE source_id=? ORDER BY size DESC", (source_id,))
    raw_other_files = db.q("""SELECT f.*, s.name AS source_name, s.kind AS source_kind, s.governed
                              FROM files f JOIN sources s ON s.id=f.source_id
                              WHERE f.source_id<>?""", (source_id,))
    single_source_mode = len(raw_other_files) == 0
    if single_source_mode:
        raw_other_files = db.q("""SELECT f.*, s.name AS source_name, s.kind AS source_kind, s.governed
                                  FROM files f JOIN sources s ON s.id=f.source_id
                                  WHERE f.source_id=?""", (source_id,))

    # Skip other files whose meta.quarantined is true
    other_files = []
    for o in raw_other_files:
        meta_o = json.loads(o["meta"] or "{}")
        if not meta_o.get("quarantined"):
            other_files.append(o)

    by_sha: dict[str, list[dict]] = {}
    by_text: dict[str, list[dict]] = {}
    other_videos: list[dict] = []
    for o in other_files:
        if o["sha256"]:
            by_sha.setdefault(o["sha256"], []).append(o)
        if o["text_hash"] and o["kind"] in ("pdf", "pptx"):
            by_text.setdefault(o["text_hash"], []).append(o)
        if o["kind"] == "video":
            other_videos.append(o)

    other_fps = {}
    other_transcripts = {}
    if other_videos:
        ids = [v["id"] for v in other_videos]
        rows = db.q(f"SELECT file_id, fingerprint FROM recordings WHERE file_id IN ({','.join('?' * len(ids))})", ids)
        for r in rows:
            other_fps[r["file_id"]] = json.loads(r["fingerprint"] or "[]")
        t_rows = db.q(f"SELECT file_id, text FROM segments WHERE file_id IN ({','.join('?' * len(ids))}) ORDER BY file_id, start", ids)
        for r in t_rows:
            other_transcripts.setdefault(r["file_id"], []).append(r["text"] or "")
        other_transcripts = {fid: " ".join(texts) for fid, texts in other_transcripts.items()}

    # All slide content_ids present outside this leaver's source (excluding quarantined files)
    ext_slides_by_cid: dict[str, list[dict]] = defaultdict(list)
    if not single_source_mode:
        for s in db.q("""SELECT s.id, s.content_id, s.phash, s.page_no, f.id AS file_id, f.name, f.meta,
                                src.name AS source_name, src.governed
                         FROM slides s JOIN files f ON f.id=s.file_id JOIN sources src ON src.id=f.source_id
                         WHERE f.source_id<>?""", (source_id,)):
            fmeta = json.loads(s.get("meta") or "{}")
            if fmeta.get("quarantined"):
                continue
            ext_slides_by_cid[s["content_id"]].append(s)

    chains = dedup.version_chains()
    newer_than: dict[int, set[int]] = {}
    for chain in chains:
        v_ids = [v["id"] for v in chain["versions"]]
        for idx_v, fid in enumerate(v_ids):
            newer_than.setdefault(fid, set()).update(v_ids[idx_v + 1:])

    all_slides_single = db.q("""SELECT s.id, s.content_id, s.phash, s.page_no, f.id AS file_id, f.name, f.revision,
                                        f.meta, src.name AS source_name, src.governed
                                 FROM slides s JOIN files f ON f.id=s.file_id JOIN sources src ON src.id=f.source_id
                                 WHERE f.source_id=?""", (source_id,)) if single_source_mode else []

    def _find_slide_match(slide, candidates_by_cid):
        matches = candidates_by_cid.get(slide["content_id"], [])
        if not matches:
            return None
        return sorted(matches, key=lambda c: (not c.get("governed"), c["id"]))[0]

    results = []
    totals = {
        "total_files": len(own_files),
        "total_bytes": sum(f["size"] or 0 for f in own_files),
        "safe_delete_files": 0,
        "safe_delete_bytes": 0,
        "review_files": 0,
        "review_bytes": 0,
        "partial_files": 0,
        "partial_bytes": 0,
        "partial_reclaimable_bytes": 0,
        "unique_files": 0,
        "unique_bytes": 0,
        "governed_backed": 0,
        "quarantined_files": 0,
    }

    for f in own_files:
        size = f["size"] or 0
        meta = json.loads(f["meta"] or "{}")
        quarantined = bool(meta.get("quarantined"))
        if quarantined:
            totals["quarantined_files"] += 1

        # 1. Exact SHA-256 duplicate
        all_sha = by_sha.get(f["sha256"] or "", [])
        if single_source_mode:
            _, canon_order = _governed_copy_check(all_sha)
            exact = [x for x in canon_order if x["id"] != f["id"]] if (len(canon_order) > 1 and canon_order[0]["id"] != f["id"]) else []
        else:
            exact = [x for x in all_sha if x["id"] != f["id"]]
        if exact:
            has_gov, ordered = _governed_copy_check(exact)
            if has_gov:
                totals["safe_delete_files"] += 1
                totals["safe_delete_bytes"] += size
                totals["governed_backed"] += 1
                status = "safe_delete"
                reclaim = size
                reason = f"Exact byte-identical copy exists in {ordered[0]['source_name']} ({ordered[0]['name']})"
                action = "Delete leaver copy (duplicate already stored elsewhere)"
            else:
                totals["review_files"] += 1
                totals["review_bytes"] += size
                status = "review"
                reclaim = 0
                reason = "Only copy elsewhere is in another personal drive"
                action = "Review: Keep or migrate to governed source (only exists in personal drive)"
            results.append({
                "file": f,
                "status": status,
                "match_type": "exact_sha256",
                "governed_copy": has_gov,
                "reclaimable_bytes": reclaim,
                "reason": reason,
                "matches": [{"file_id": m["id"], "name": m["name"], "source": m["source_name"],
                             "governed": bool(m["governed"]), "path": m["path"]} for m in ordered[:5]],
                "unique_slides": [],
                "shared_slides": [],
                "quarantined": quarantined,
                "recommended_action": action,
            })
            continue

        # 2. Content-identical PDF/PPTX (re-saved / metadata altered)
        all_content = by_text.get(f["text_hash"] or "", []) if f["kind"] in ("pdf", "pptx") else []
        if single_source_mode:
            _, canon_c = _governed_copy_check(all_content)
            content = [x for x in canon_c if x["id"] != f["id"]] if (len(canon_c) > 1 and canon_c[0]["id"] != f["id"]) else []
        else:
            content = [x for x in all_content if x["id"] != f["id"]]
        if content:
            has_gov, ordered = _governed_copy_check(content)
            if has_gov:
                totals["safe_delete_files"] += 1
                totals["safe_delete_bytes"] += size
                totals["governed_backed"] += 1
                status = "safe_delete"
                reclaim = size
                reason = f"100% identical text & slide content exists in {ordered[0]['source_name']} ({ordered[0]['name']})"
                action = "Delete leaver copy (identical content stored elsewhere)"
            else:
                totals["review_files"] += 1
                totals["review_bytes"] += size
                status = "review"
                reclaim = 0
                reason = "Only copy elsewhere is in another personal drive"
                action = "Review: Keep or migrate to governed source (only exists in personal drive)"
            results.append({
                "file": f,
                "status": status,
                "match_type": "identical_content",
                "governed_copy": has_gov,
                "reclaimable_bytes": reclaim,
                "reason": reason,
                "matches": [{"file_id": m["id"], "name": m["name"], "source": m["source_name"],
                             "governed": bool(m["governed"]), "path": m["path"]} for m in ordered[:5]],
                "unique_slides": [],
                "shared_slides": [],
                "quarantined": quarantined,
                "recommended_action": action,
            })
            continue

        # 3. Video perceptual duplicate (re-encoded / trimmed copy elsewhere)
        if f["kind"] == "video":
            rec = db.q1("SELECT fingerprint, tiers FROM recordings WHERE file_id=?", (f["id"],))
            fp = json.loads(rec["fingerprint"] or "[]") if rec else []
            v_matches = []
            if fp:
                f_segs = db.q("SELECT text FROM segments WHERE file_id=? ORDER BY start", (f["id"],))
                f_txt = " ".join(s["text"] or "" for s in f_segs)
                for ov in other_videos:
                    if ov["id"] == f["id"]:
                        continue
                    if single_source_mode and (ov["size"] or 0) < (f["size"] or 0):
                        continue
                    ofp = other_fps.get(ov["id"], [])
                    if not ofp:
                        continue
                    ov_txt = other_transcripts.get(ov["id"], "")
                    sim = video_similarity(fp, ofp, text_a=f_txt, text_b=ov_txt)
                    if sim >= 0.6:
                        v_matches.append((sim, ov))
            if v_matches:
                v_matches.sort(key=lambda x: (-(x[1]["governed"] or 0), -x[0]))
                best_sim, best_v = v_matches[0]
                has_gov = any(m[1]["governed"] for m in v_matches)
                if has_gov:
                    totals["safe_delete_files"] += 1
                    totals["safe_delete_bytes"] += size
                    totals["governed_backed"] += 1
                    status = "safe_delete"
                    reclaim = size
                    reason = f"Perceptually matching recording ({round(best_sim * 100)}% overlap) exists in {best_v['source_name']} ({best_v['name']})"
                    action = "Delete leaver recording (duplicate recording exists)"
                else:
                    totals["review_files"] += 1
                    totals["review_bytes"] += size
                    status = "review"
                    reclaim = 0
                    reason = "Only copy elsewhere is in another personal drive"
                    action = "Review: Keep or migrate to governed source (only exists in personal drive)"
                results.append({
                    "file": f,
                    "status": status,
                    "match_type": "video_perceptual",
                    "governed_copy": has_gov,
                    "reclaimable_bytes": reclaim,
                    "reason": reason,
                    "matches": [{"file_id": m["id"], "name": m["name"], "source": m["source_name"],
                                 "governed": bool(m["governed"]), "similarity": round(sim, 3)}
                                for sim, m in v_matches[:5]],
                    "unique_slides": [],
                    "shared_slides": [],
                    "quarantined": quarantined,
                    "recommended_action": action,
                })
                continue

        # 4. Slide-level overlap in PDF/PPTX -> partial vs unique
        if f["kind"] in ("pdf", "pptx"):
            own_slides = db.q("SELECT id, page_no, content_id, phash, title, bytes, object_hash FROM slides WHERE file_id=? ORDER BY page_no",
                              (f["id"],))
            if single_source_mode:
                local_cands = defaultdict(list)
                newer_ids = newer_than.get(f["id"], set())
                for s in all_slides_single:
                    if s["file_id"] in newer_ids:
                        local_cands[s["content_id"]].append(s)
            else:
                local_cands = ext_slides_by_cid

            shared, unique = [], []
            for s in own_slides:
                ext = _find_slide_match(s, local_cands)
                if ext:
                    shared.append({"slide_id": s["id"], "page_no": s["page_no"], "title": s["title"],
                                   "matched_deck": ext["name"], "matched_source": ext["source_name"],
                                   "matched_page": ext["page_no"], "matched_governed": bool(ext.get("governed"))})
                else:
                    unique.append({"slide_id": s["id"], "page_no": s["page_no"], "title": s["title"],
                                   "object_hash": s["object_hash"], "bytes": s["bytes"]})
            if shared and unique:
                n_total = max(1, len(own_slides))
                reclaim = int(size * len(shared) / n_total)
                totals["partial_files"] += 1
                totals["partial_bytes"] += size
                totals["partial_reclaimable_bytes"] += reclaim
                results.append({
                    "file": f,
                    "status": "partial",
                    "match_type": "shared_slides",
                    "governed_copy": any(s.get("matched_governed") for s in shared),
                    "reclaimable_bytes": reclaim,
                    "reason": f"{len(shared)} of {len(own_slides)} slides already exist elsewhere; {len(unique)} unique slides must be rescued before deleting",
                    "matches": [],
                    "unique_slides": unique,
                    "shared_slides": shared,
                    "quarantined": quarantined,
                    "recommended_action": f"Rescue {len(unique)} unique slides to compact archive, then delete full deck",
                })
                continue
            elif shared and not unique:
                has_gov = any(s.get("matched_governed") for s in shared)
                if has_gov:
                    totals["safe_delete_files"] += 1
                    totals["safe_delete_bytes"] += size
                    totals["governed_backed"] += 1
                    status = "safe_delete"
                    reclaim = size
                    reason = f"All {len(own_slides)} slides already exist across other indexed decks"
                    action = "Delete leaver deck (100% of slides exist elsewhere)"
                else:
                    totals["review_files"] += 1
                    totals["review_bytes"] += size
                    status = "review"
                    reclaim = 0
                    reason = "Only copy elsewhere is in another personal drive"
                    action = "Review: Keep or migrate to governed source (only exists in personal drive)"
                results.append({
                    "file": f,
                    "status": status,
                    "match_type": "all_slides_elsewhere",
                    "governed_copy": has_gov,
                    "reclaimable_bytes": reclaim,
                    "reason": reason,
                    "matches": [],
                    "unique_slides": [],
                    "shared_slides": shared,
                    "quarantined": quarantined,
                    "recommended_action": action,
                })
                continue

        # 5. Unique file
        totals["unique_files"] += 1
        totals["unique_bytes"] += size
        if f["kind"] == "video":
            rec = db.q1("SELECT tiers FROM recordings WHERE file_id=?", (f["id"],))
            tiers = json.loads(rec["tiers"] or "{}") if rec else {}
            t3 = next((t["bytes"] for t in tiers.get("tiers", []) if t["name"].startswith("T3")), None)
            reclaim_hint = size - t3 if t3 else int(size * 0.99)
            action = "Unique video: distill to Knowledge Packet (~99% smaller) and archive packet before deletion"
        else:
            reclaim_hint = 0
            action = "Unique document: preserve or move to team SharePoint"
        results.append({
            "file": f,
            "status": "unique",
            "match_type": "none",
            "governed_copy": False,
            "reclaimable_bytes": 0,
            "distill_reclaimable_bytes": reclaim_hint,
            "reason": "No matching file or slides found in any other system",
            "matches": [],
            "unique_slides": [],
            "shared_slides": [],
            "quarantined": quarantined,
            "recommended_action": action,
        })

    totals["total_reclaimable_bytes"] = totals["safe_delete_bytes"] + totals["partial_reclaimable_bytes"]
    totals["reclaimable_pct"] = round(
        totals["total_reclaimable_bytes"] / totals["total_bytes"], 4
    ) if totals["total_bytes"] else 0.0
    return {"source": src, "totals": totals, "files": results}


def rescue_unique_slides(file_id: int) -> dict:
    """For a 'partial' PDF/PPTX file, extract ONLY the unique slides into a compact PDF."""
    f = db.q1("SELECT * FROM files WHERE id=?", (file_id,))
    if not f:
        raise ValueError("File not found")
    report = analyse_leaver(f["source_id"])
    entry = next((r for r in report["files"] if r["file"]["id"] == file_id), None)
    if not entry:
        raise ValueError("File not in source analysis")
    pages = [u["page_no"] for u in entry["unique_slides"]]
    if not pages:
        return {"rescued": False, "reason": "No unique slides to rescue", "pages": []}

    out_dir = C.RESCUE_DIR / f"source_{f['source_id']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(f["name"]).stem
    out_pdf = out_dir / f"{stem}_UNIQUE_SLIDES.pdf"

    if f["kind"] == "pdf" and Path(f["path"]).exists():
        import fitz
        src = fitz.open(f["path"])
        dst = fitz.open()
        for pno in pages:
            dst.insert_pdf(src, from_page=pno - 1, to_page=pno - 1)
        dst.set_metadata({
            "title": f"{f['title'] or stem} (Unique slides rescued during offboarding)",
            "subject": f"Rescued {len(pages)} unique slides from {f['name']}",
        })
        dst.save(str(out_pdf), garbage=4, deflate=True)
        dst.close()
        src.close()
    else:
        # Fallback: assemble from stored slide WebP images
        import fitz
        from .util import object_path
        dst = fitz.open()
        for u in entry["unique_slides"]:
            img_p = object_path(u["object_hash"])
            if img_p.exists():
                page = dst.new_page(width=960, height=540)
                page.insert_image(page.rect, filename=str(img_p))
        dst.save(str(out_pdf), garbage=4, deflate=True)
        dst.close()

    size = out_pdf.stat().st_size
    db.audit("rescue_unique_slides", {
        "file_id": file_id, "name": f["name"], "pages": pages,
        "out_pdf": str(out_pdf), "bytes": size
    })
    return {
        "rescued": True,
        "file_id": file_id,
        "pages": pages,
        "out_pdf": str(out_pdf),
        "rescued_bytes": size,
        "original_bytes": f["size"],
        "saved_bytes": max(0, (f["size"] or 0) - size),
    }


def apply_offboarding(source_id: int, file_ids: list[int], mode: str = "dry_run", delete_original: bool = False) -> dict:
    """Dry-run or quarantine-stage selected files (NEVER permanently deletes without quarantine).
    In 'quarantine' mode, files are copied to data/rescued/quarantine_<source_id>/ (originals are NEVER deleted; delete_original=False).
    """
    report = analyse_leaver(source_id)
    by_id = {r["file"]["id"]: r for r in report["files"]}
    actions = []
    reclaimed = 0
    for fid in file_ids:
        item = by_id.get(fid)
        if not item:
            continue
        f = item["file"]
        if item["status"] in ("unique", "review"):
            actions.append({"file_id": fid, "name": f["name"], "action": f"skipped_{item['status']}",
                            "reason": f"Blocked by safety rule: {item['reason']}"})
            continue
        rescued = None
        if item["status"] == "partial" and mode == "quarantine":
            rescued = rescue_unique_slides(fid)
        if mode == "dry_run":
            actions.append({
                "file_id": fid, "name": f["name"], "status": item["status"],
                "planned_action": "rescue_unique_then_quarantine" if item["status"] == "partial" else "quarantine_safe_duplicate",
                "reclaimable_bytes": item["reclaimable_bytes"],
                "reason": item["reason"],
            })
            reclaimed += item["reclaimable_bytes"]
        elif mode == "quarantine":
            qdir = C.RESCUE_DIR / f"quarantine_{source_id}"
            qdir.mkdir(parents=True, exist_ok=True)
            src_p = Path(f["path"])
            dst_p = qdir / f"{fid}_{src_p.name}"
            moved = False
            if src_p.exists() and not dst_p.exists():
                shutil.copy2(src_p, dst_p)
                moved = True
            meta = json.loads(f["meta"] or "{}")
            meta["quarantined"] = True
            meta["quarantine_path"] = str(dst_p)
            meta["quarantined_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            if rescued:
                meta["rescued_pdf"] = rescued["out_pdf"]
            with db.tx() as c:
                c.execute("UPDATE files SET meta=? WHERE id=?", (json.dumps(meta), fid))
            db.audit("quarantine_file", {
                "file_id": fid, "name": f["name"], "source_id": source_id,
                "quarantine_copy": str(dst_p), "reclaimable_bytes": item["reclaimable_bytes"],
                "deleted_original": False,
            })
            actions.append({
                "file_id": fid, "name": f["name"], "action": "quarantined_staged",
                "quarantine_copy": str(dst_p), "rescued": rescued,
                "reclaimable_bytes": item["reclaimable_bytes"], "copied": moved,
            })
            reclaimed += item["reclaimable_bytes"]
    db.audit("offboarding_" + mode, {"source_id": source_id, "count": len(actions), "reclaimed_bytes": reclaimed})
    return {"mode": mode, "source_id": source_id, "actions": actions, "reclaimed_bytes": reclaimed}


def restore_quarantine(source_id: int) -> dict:
    """Restore quarantine flags so the demo can be re-run cleanly."""
    files = db.q("SELECT id, meta FROM files WHERE source_id=?", (source_id,))
    n = 0
    with db.tx() as c:
        for f in files:
            meta = json.loads(f["meta"] or "{}")
            if meta.pop("quarantined", None):
                meta.pop("quarantine_path", None)
                meta.pop("quarantined_at", None)
                c.execute("UPDATE files SET meta=? WHERE id=?", (json.dumps(meta), f["id"]))
                n += 1
    db.audit("offboarding_reset", {"source_id": source_id, "restored": n})
    return {"restored": n}
