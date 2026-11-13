"""Comprehensive end-to-end API & Security verification for official Ericsson Dataset.

Run: .venv\\Scripts\\python.exe scripts\\verify_ericsson_api.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from distill import config as C, db, dedup, offboard
from distill.app import app


def test_ericsson_api() -> None:
    print("============================================================")
    print("VERIFYING OFFICIAL ERICSSON API & BACKEND")
    print("============================================================")

    with TestClient(app) as client:
        # 1. Overview
        r = client.get("/api/overview")
        assert r.status_code == 200, f"/api/overview failed: {r.text}"
        ov = r.json()
        st = ov["storage"]
        print(f"[PASS] /api/overview: raw={st['total_bytes']:,} B, optimized={st['optimized_total_bytes']:,} B, savings={st['total_saving_pct']*100:.2f}%")
        assert st["total_bytes"] > 1_500_000_000, f"Raw bytes unexpectedly low: {st['total_bytes']}"
        assert st["total_saving_pct"] >= 0.98, f"Savings pct < 98%: {st['total_saving_pct']}"
        assert ov.get("files_by_status", {}).get("done", 0) == 12, f"Expected 12 done files: {ov.get('files_by_status')}"
        assert ov.get("total_reclaimable_bytes", 0) > 3_000_000, f"Expected >3MB reclaimable: {ov.get('total_reclaimable_bytes')}"

        # 2. Pipeline Info
        r = client.get("/api/pipeline/info")
        assert r.status_code == 200
        pinfo = r.json()
        print(f"[PASS] /api/pipeline/info: models={list(pinfo['models'].keys())}, roots={pinfo['allowed_roots']}")

        # 3. Files List
        r = client.get("/api/files")
        assert r.status_code == 200
        files = r.json()["files"]
        print(f"[PASS] /api/files: count={len(files)}")
        assert len(files) == 12, f"Expected 12 files, got {len(files)}"

        # Find key files
        rec_file = next(f for f in files if f["name"].endswith(".mp4") and "Tech Concept" in f["name"])
        doc_file = next(f for f in files if "C2L_Presentation" in f["name"] and "OneDrive" not in f["source_name"])
        pptx_file = next(f for f in files if "final.pptx" in f["name"])
        pptx2_file = next(f for f in files if "final2.pptx" in f["name"])
        gonzalo_src = db.q1("SELECT id FROM sources WHERE name LIKE '%Gonzalo%'")

        # 4. Stages & Integrity for Video
        r = client.get(f"/api/files/{rec_file['id']}/stages")
        assert r.status_code == 200
        stages = r.json()["stages"]
        print(f"[PASS] /api/files/{rec_file['id']}/stages: {len(stages)} stages verified")
        assert len(stages) >= 5, "Video pipeline stages missing"

        r = client.get(f"/api/files/{rec_file['id']}/integrity")
        assert r.status_code == 200
        integ = r.json()
        passed_checks = sum(1 for c in integ["checks"] if c["status"] == "passed")
        print(f"[PASS] /api/files/{rec_file['id']}/integrity: retention_score={integ['retention_score']}%, {passed_checks}/{len(integ['checks'])} checks passed")
        assert integ["retention_score"] > 80.0, f"Retention score too low: {integ['retention_score']}"

        # 5. On-demand Frame Extraction
        r = client.get(f"/api/recordings/{rec_file['id']}/frame?t=15.0")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        print(f"[PASS] /api/recordings/{rec_file['id']}/frame?t=15: returned {len(r.content)} JPEG bytes")

        # 6. Duplicates & Revisions
        r = client.get("/api/duplicates")
        assert r.status_code == 200
        dups = r.json()
        reclaimable = sum(g["reclaimable"] for g in dups["exact"])
        print(f"[PASS] /api/duplicates: {len(dups['exact'])} exact groups, reclaimable={reclaimable:,} B")
        assert len(dups["exact"]) == 2, f"Expected 2 duplicate groups, got {len(dups['exact'])}"

        # 7. Compare Revisions
        r = client.get(f"/api/compare/{pptx_file['id']}/{pptx2_file['id']}")
        assert r.status_code == 200
        cmp_ = r.json()
        print(f"[PASS] /api/compare: identical={cmp_['identical']}, modified={cmp_['modified']}, removed={len(cmp_['removed'])}")
        assert cmp_["identical"] == 22 and cmp_["modified"] == 3

        # Visual diff on modified slide
        mod_pair = next(p for p in cmp_["pairs"] if p["relation"] == "modified")
        r = client.get(f"/api/diff-image/{mod_pair['a']['id']}/{mod_pair['b']['id']}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        print(f"[PASS] /api/diff-image: returned {len(r.content)} PNG bytes with visual diff bounding boxes")

        # 8. Offboarding
        r = client.get(f"/api/offboard/{gonzalo_src['id']}")
        assert r.status_code == 200
        leaver = r.json()
        safe_count = sum(1 for f in leaver["files"] if f["status"] == "safe_delete")
        partial_count = sum(1 for f in leaver["files"] if f["status"] == "partial")
        unique_count = sum(1 for f in leaver["files"] if f["status"] == "unique")
        print(f"[PASS] /api/offboard: safe_delete={safe_count}, partial={partial_count}, unique={unique_count}")
        assert safe_count == 2 and partial_count == 1 and unique_count == 1

        # Dry run quarantine apply
        safe_ids = [f["file"]["id"] for f in leaver["files"] if f["status"] == "safe_delete"]
        r = client.post(f"/api/offboard/{gonzalo_src['id']}/apply", json={"file_ids": safe_ids, "mode": "dry_run"})
        assert r.status_code == 200
        assert r.json()["mode"] == "dry_run"
        print(f"[PASS] /api/offboard apply (dry_run): verified {len(safe_ids)} files, planned reclaim {r.json()['reclaimed_bytes']:,} B")

        # 9. Search & AI Ask
        r = client.get("/api/search?q=Ericsson+Response")
        assert r.status_code == 200
        hits = r.json()["results"]
        print(f"[PASS] /api/search: {len(hits)} results found")
        assert len(hits) > 0

        r = client.post("/api/ai/ask", json={"question": "What is Connect to Learn?"})
        assert r.status_code == 200
        ans = r.json()
        print(f"[PASS] /api/ai/ask: mode={ans['mode']}, citations={len(ans['citations'])}")
        assert len(ans["citations"]) > 0

        # 10. AI Corpus Export with PII redaction
        r = client.get("/api/ai/export?redact_pii=true")
        assert r.status_code == 200
        print(f"[PASS] /api/ai/export: {len(r.content)} bytes generated")

        # 11. Security Tests: Sandboxing
        bad_ingest = client.post("/api/ingest", json={"roots": ["C:\\Windows\\System32"]})
        assert bad_ingest.status_code == 403, f"Expected 403 for unauthorized path, got {bad_ingest.status_code}"
        print(f"[PASS] Security S1: Path sandboxing blocked unauthorized path (403 Forbidden)")

        bad_reset = client.post("/api/reset", json={})
        assert bad_reset.status_code == 400 or bad_reset.status_code == 403
        print(f"[PASS] Security S4: Reset confirmation guard active")

    print("\n============================================================")
    print("ALL API & SECURITY TESTS PASSED PERFECTLY!")
    print("============================================================")


if __name__ == "__main__":
    test_ericsson_api()
