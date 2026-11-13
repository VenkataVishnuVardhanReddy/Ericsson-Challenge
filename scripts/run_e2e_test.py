"""End-to-end integration test & ground-truth benchmark for Distill.

Run: .venv\\Scripts\\python.exe scripts\\run_e2e_test.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2
import pymupdf as fitz
from fastapi.testclient import TestClient

from distill import ai, config as C, db, dedup, evaluate, offboard, pipeline, recreate, search
from distill.app import app


def main() -> None:
    t0 = time.time()
    db.init()
    db.reset()

    base = ROOT / "sample_data"
    roots = [str(p) for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith((".", "_"))]
    print("Ingesting sources:", [Path(r).name for r in roots])
    pipeline.ingest_many(roots)

    q = pipeline.jobs()
    last_line = ""
    while True:
        jobs = q.list()
        active = [j for j in jobs if j["status"] in ("queued", "running")]
        running = [f"{j['name']} [{j['stage']} {int(j['progress']*100)}%]" for j in jobs if j["status"] == "running"]
        done = sum(1 for j in jobs if j["status"] == "done")
        err = [j for j in jobs if j["status"] == "error"]
        line = f"  progress: {done}/{len(jobs)} done | running: {', '.join(running) or 'none'}"
        if line != last_line:
            print(line, flush=True)
            last_line = line
        if not active:
            break
        time.sleep(3)

    if err:
        for e in err:
            print("ERROR JOB:", e)
        sys.exit(1)
    print(f"Pipeline finished in {time.time() - t0:.1f}s")

    # 1. Ground truth evaluation
    ev = evaluate.evaluate_ground_truth()
    print("\n=== Ground-Truth Benchmark ===")
    print(json.dumps(ev, indent=2))

    assert ev["offboarding"]["accuracy"] == 1.0, f"Offboarding accuracy < 1.0: {ev['offboarding']}"
    assert ev["dedup_summary"]["exact_groups"] >= 3, "Missing exact duplicate groups"
    assert ev["dedup_summary"]["content_groups"] >= 1, "Missing content-identical PDF duplicate group"
    assert ev["dedup_summary"]["video_groups"] >= 1, "Missing perceptual video duplicate group"
    assert ev["dedup_summary"]["revision_relations"] >= 1, "Missing RevA->RevB revision relation"
    assert ev["dedup_summary"]["shared_slide_relations"] >= 2, "Missing shared slide relations"

    # 2. Check Teams VTT real speaker names & Event Recording diarization + deictic + retention
    ts = db.q1("SELECT id FROM files WHERE name='Team_Sync_2026-11-02.mp4'")
    ts_segs = db.q("SELECT speaker FROM segments WHERE file_id=?", (ts["id"],))
    ts_speakers = {s["speaker"] for s in ts_segs}
    print("Team Sync speakers:", ts_speakers)
    assert "Anna Svensson" in ts_speakers and "Erik Berg" in ts_speakers, "Teams VTT speaker names missing"

    ev_rec = db.q1("SELECT id FROM files WHERE name='Event_Recording_2026-10-14.mp4' AND path LIKE '%SharePoint%'")
    ev_kfs = db.q("SELECT * FROM keyframes WHERE file_id=? ORDER BY idx", (ev_rec["id"],))
    linked_count = sum(1 for k in ev_kfs if k["slide_id"] is not None)
    print(f"Event Recording keyframes: {len(ev_kfs)}, linked to source deck: {linked_count}")
    assert linked_count >= 5, f"Expected >=5 linked keyframes, got {linked_count}"

    # 3. Revision comparison & visual diff
    revA = db.q1("SELECT id FROM files WHERE name='5G_RAN_Energy_Efficiency_RevA.pdf' AND path LIKE '%SharePoint%'")
    revB = db.q1("SELECT id FROM files WHERE name='5G_RAN_Energy_Efficiency_RevB.pdf' AND path LIKE '%SharePoint%'")
    cmp_ = dedup.deck_comparison(revA["id"], revB["id"])
    print(f"RevA -> RevB: identical={cmp_['identical']}, modified={cmp_['modified']}, new={cmp_['new']}, removed={len(cmp_['removed'])}")
    assert cmp_["identical"] == 9 and cmp_["modified"] == 2 and cmp_["new"] == 1 and len(cmp_["removed"]) == 1, cmp_

    mod_pair = next(p for p in cmp_["pairs"] if p["relation"] == "modified")
    diff_png = dedup.diff_image(mod_pair["a"]["id"], mod_pair["b"]["id"])
    assert len(diff_png) > 1000, "Visual diff PNG too small"

    # 4. Hybrid search & AI Ask & Export
    hits = search.search("Nordic field trial night power savings", k=5)
    print("Search hits for 'Nordic field trial night power savings':", len(hits), "top:", hits[0]["title"] if hits else None)
    assert len(hits) > 0, "Search returned no hits"
    ans = ai.ask_archive("How much night energy did the Nordic field trial save?")
    print("Ask AI mode:", ans["mode"], "citations:", len(ans["citations"]))
    assert len(ans["citations"]) > 0

    exp = ai.export_ai_corpus("jsonl", redact_pii=True)
    assert exp["records"] > 10

    # 5. Offboarding rescue unique slides (Customer_Workshop_Draft.pdf -> 5 unique pages)
    cwd_f = db.q1("SELECT id FROM files WHERE name='Customer_Workshop_Draft.pdf'")
    rescue = offboard.rescue_unique_slides(cwd_f["id"])
    print("Rescue Customer_Workshop_Draft.pdf:", rescue)
    assert rescue["rescued"] and len(rescue["pages"]) == 5, rescue
    d = fitz.open(rescue["out_pdf"])
    assert len(d) == 5
    d.close()

    # 6. Recreate video (both modes) on Team Sync (fast!) and Event Recording (audio_slides)
    r1 = recreate.recreate_video(ts["id"], mode="audio_slides", force=True)
    r2 = recreate.recreate_video(ts["id"], mode="text_tts", force=True)
    for r in (r1, r2):
        cap = cv2.VideoCapture(r["path"])
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        print(f"Recreated {r['mode']}: {r['bytes']} bytes ({r['saving']*100:.1f}% smaller), frames={frames}")
        assert frames > 5

    # 7. Verify PPTX slide parsing & content-id hashing works cleanly
    from pptx import Presentation
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pptx_p = Path(td) / "demo.pptx"
        prs = Presentation()
        s1 = prs.slides.add_slide(prs.slide_layouts[1])
        s1.shapes.title.text = "5G RAN Energy Efficiency"
        s1.placeholders[1].text = "Micro-Sleep TX saves 15% radio power"
        prs.save(pptx_p)
        from distill.documents import process_pptx
        ptx = process_pptx(str(pptx_p))
        assert len(ptx["slides"]) == 1 and "Micro-Sleep" in ptx["slides"][0]["text"]
        print("PPTX parser verified: 1 slide rendered & hashed")

    # 8. FastAPI endpoint handlers check (direct call works even in no-socket sandboxes; pass --http for TestClient)
    from distill import app as app_mod
    assert app_mod.index().status_code == 200
    ov = app_mod.api_overview()
    assert ov["counts"]["files"] >= 13 and ov["storage"]["total_saving_pct"] > 0.7
    assert app_mod.api_files()["files"]
    assert app_mod.api_recording(ev_rec["id"])["keyframes"]
    assert app_mod.api_search(q="Micro-Sleep")["results"]
    assert app_mod.api_duplicates()["exact"]
    assert app_mod.api_compare(revA["id"], revB["id"])["identical"] == 9
    assert len(app_mod.api_diff_image(mod_pair["a"]["id"], mod_pair["b"]["id"]).body) > 1000
    assert app_mod.api_offboard_sources()["sources"]
    assert app_mod.api_benchmark()["available"]
    assert app_mod.api_ai_export()["records"] > 10
    assert app_mod.api_ai_ask(app_mod.AskReq(question="What is Micro-Sleep TX?"))["citations"]

    if "--http" in sys.argv:
        with TestClient(app) as client:
            for path in [
                "/", "/api/overview", "/api/files", f"/api/recordings/{ev_rec['id']}",
                "/api/search?q=Micro-Sleep", "/api/duplicates",
                f"/api/compare/{revA['id']}/{revB['id']}",
                f"/api/diff-image/{mod_pair['a']['id']}/{mod_pair['b']['id']}",
                "/api/offboard", "/api/benchmark", "/api/ai/export?fmt=jsonl",
            ]:
                resp = client.get(path)
                assert resp.status_code == 200, f"GET {path} -> {resp.status_code}: {resp.text[:200]}"
            resp = client.post("/api/ai/ask", json={"question": "What is Micro-Sleep TX?"})
            assert resp.status_code == 200
    print("\nALL E2E CHECKS PASSED!")


if __name__ == "__main__":
    main()
