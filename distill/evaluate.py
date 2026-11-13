"""Evaluate Distill's output against sample_data/_ground_truth.json (if present)."""
from __future__ import annotations

import json
from pathlib import Path

from . import config as C
from . import db, dedup, offboard


def evaluate_ground_truth() -> dict:
    gt_path = C.ROOT / "sample_data" / "_ground_truth.json"
    if not gt_path.exists():
        return {"available": False}
    gt = json.loads(gt_path.read_text(encoding="utf-8"))

    report = {"available": True, "checks": []}

    # 1. Check recordings: keyframes, linked source slides, speaker turns, duration
    rec_results = []
    for v_rel, v_gt in gt.get("videos", {}).items():
        name = Path(v_rel).name
        f = db.q1("SELECT id, size FROM files WHERE path LIKE ?", (f"%{name}",))
        if not f:
            continue
        rec = db.q1("SELECT * FROM recordings WHERE file_id=?", (f["id"],))
        kfs = db.q("SELECT * FROM keyframes WHERE file_id=? ORDER BY idx", (f["id"],))
        segs = db.q("SELECT * FROM segments WHERE file_id=? ORDER BY start", (f["id"],))

        gt_slides = [s for s in v_gt.get("intervals", []) if s.get("kind", "slide") == "slide"]
        unique_gt_pages = {(s.get("deck_file"), s.get("page_no")) for s in gt_slides}
        linked_pages = sum(1 for k in kfs if k["slide_id"] is not None)
        speakers_found = sorted({s["speaker"] for s in segs})
        gt_speakers = sorted({t["speaker"] for t in v_gt.get("speaker_turns", [])})
        ret = json.loads(rec["retention"] or "{}") if rec else {}
        tiers = json.loads(rec["tiers"] or "{}") if rec else {}
        t3 = next((t for t in tiers.get("tiers", []) if t["name"].startswith("T3")), None)
        rec_results.append({
            "file": name,
            "gt_unique_slides": len(unique_gt_pages),
            "detected_keyframes": len(kfs),
            "linked_to_source_deck": linked_pages,
            "gt_speakers": len(gt_speakers),
            "detected_speakers": len(speakers_found),
            "speaker_names": speakers_found,
            "screen_text_retained": ret.get("screen_text_retained"),
            "t3_saving": t3["saving"] if t3 else None,
        })
    report["videos"] = rec_results

    # 2. Check offboarding classification vs ground truth
    off_gt = gt.get("offboarding", {})
    off_results = []
    anna_src = db.q1("SELECT id FROM sources WHERE name LIKE '%Anna%'")
    if anna_src and off_gt:
        analysis = offboard.analyse_leaver(anna_src["id"])
        by_name = {item["file"]["name"]: item for item in analysis["files"]}
        correct = 0
        for fname, exp in off_gt.items():
            exp_status = exp["status"] if isinstance(exp, dict) else exp
            got = by_name.get(fname, {}).get("status")
            ok = (got == exp_status)
            if ok:
                correct += 1
            off_results.append({"file": fname, "expected": exp_status, "actual": got, "match": ok})
        report["offboarding"] = {
            "accuracy": round(correct / max(1, len(off_gt)), 3),
            "correct": correct,
            "total": len(off_gt),
            "items": off_results,
        }

    # 3. Check duplicate & revision relations
    exact = dedup.exact_groups()
    content = dedup.content_groups()
    vgroups = dedup.video_groups()
    rels = dedup.deck_relations()
    report["dedup_summary"] = {
        "exact_groups": len(exact),
        "content_groups": len(content),
        "video_groups": len(vgroups),
        "revision_relations": sum(1 for r in rels if r["kind"] == "revision"),
        "shared_slide_relations": sum(1 for r in rels if r["kind"] == "shares_slides"),
    }
    return report
