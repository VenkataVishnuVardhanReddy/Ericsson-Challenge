"""Ingest and benchmark the official Ericsson Challenge Dataset."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from distill import ai, db, dedup, offboard, pipeline, search
from distill.app import app


def main() -> None:
    reset_db = "--no-reset" not in sys.argv
    if reset_db:
        print("Resetting Distill database for clean official dataset run...")
        db.reset()
    else:
        db.init()

    base = ROOT / "sample_data" / "Ericsson_Challenge_Dataset"
    if not base.exists():
        print(f"Error: {base} does not exist.")
        sys.exit(1)

    sources = [
        str(base / "SharePoint_Response_C2L"),
        str(base / "EricssonPlay"),
        str(base / "OneDrive_Gonzalo_Suardiaz"),
    ]

    print(f"Ingesting official Ericsson sources:\n  " + "\n  ".join(sources))
    res = pipeline.ingest_many(sources)
    total_files = db.q1("SELECT COUNT(*) AS c FROM files")["c"]
    print(f"Discovered {total_files} files across {len(sources)} sources. Queueing jobs...")

    t0 = time.time()
    last_stage = None
    while True:
        job_list = pipeline.jobs().list()
        done = sum(1 for j in job_list if j["status"] in ("done", "error"))
        total = len(job_list)
        active = next((j for j in job_list if j["status"] == "running"), None)
        active_name = active["name"] if active else "none"
        stage = active["stage"] if active else "All complete"

        if stage != last_stage or done == total:
            print(f"  [{time.time()-t0:>5.1f}s] Progress: {done}/{total} done | Active: {active_name} [{stage}]", flush=True)
            last_stage = stage

        if total > 0 and done == total:
            break
        time.sleep(2)

    print(f"\nPipeline processing finished in {time.time() - t0:.1f}s!\n")

    # ==================== ANALYSIS & RESULTS ====================
    print("=" * 60)
    print("DISTILL OFFICIAL ERICSSON CHALLENGE RESULTS")
    print("=" * 60)

    # 1. Exact duplicates
    exact = dedup.exact_groups()
    print(f"\n1. Exact Duplicates ({len(exact)} groups):")
    for g in exact:
        fns = [f["name"] + f" ({f['source_name']})" for f in g["files"]]
        print(f"   • Reclaimable: {g['reclaimable']:,} bytes | Files: {' == '.join(fns)}")

    # 2. Revisions
    print("\n2. Revision Chains:")
    pptx_a = db.q1("SELECT id FROM files WHERE name LIKE '%presentation_final.pptx%'")
    pptx_b = db.q1("SELECT id FROM files WHERE name LIKE '%presentation_final2.pptx%'")
    if pptx_a and pptx_b:
        cmp_ = dedup.deck_comparison(pptx_a["id"], pptx_b["id"])
        print(f"   • final.pptx -> final2.pptx:")
        print(f"     Identical slides: {cmp_['identical']}")
        print(f"     Modified slides:  {cmp_['modified']}")
        print(f"     New slides:       {cmp_['new']}")
        print(f"     Removed slides:   {len(cmp_['removed'])}")

    # 3. Offboarding Gonzalo Suardiaz
    od_src = db.q1("SELECT id FROM sources WHERE name LIKE '%Gonzalo%'")
    if od_src:
        rep = offboard.analyse_leaver(od_src["id"])
        print(f"\n3. Leaver Offboarding Analysis ({rep['source']['name']}):")
        print(f"   Total files: {rep['totals']['total_files']}")
        print(f"   Safe to delete: {rep['totals']['safe_delete_files']} files ({rep['totals']['safe_delete_bytes']:,} bytes)")
        print(f"   Reclaimable ratio: {rep['totals']['reclaimable_pct']:.2%}")
        for f in rep["files"]:
            print(f"     - {f['file']['name']}: {f['status']} ({f['reason']})")

    # 4. Storage & Distillation Summary
    from distill import app as app_mod
    ov = app_mod.api_overview()
    print("\n4. Storage Optimization Waterfall:")
    print(f"   Raw Total Storage:        {ov['storage']['total_bytes']:,} bytes ({ov['storage']['total_bytes']/(1024*1024):.2f} MB)")
    print(f"   T1 Smart Re-encode:       {ov['storage']['tier_totals'].get('T1', 0):,} bytes")
    print(f"   T2 Audio + Slides + Text: {ov['storage']['tier_totals'].get('T2', 0):,} bytes")
    print(f"   T3 Slides + Text:         {ov['storage']['tier_totals'].get('T3', 0):,} bytes")
    print(f"   T4 Text + Slide Links:    {ov['storage']['tier_totals'].get('T4', 0):,} bytes")
    print(f"   Optimized Total Footprint: {ov['storage']['optimized_total_bytes']:,} bytes ({ov['storage']['optimized_total_bytes']/(1024*1024):.2f} MB)")
    print(f"   Overall Storage Savings:  {ov['storage']['total_saving_pct']:.2%}")
    if ov.get("retention", {}).get("mean_screen_text_retained") is not None:
        print(f"   Mean Screen Text Retained: {ov['retention']['mean_screen_text_retained']:.1%}")

    # 5. Hybrid Search test
    print("\n5. Hybrid Search & AI QA:")
    hits = search.search("Ericsson Response humanitarian connectivity", k=3)
    print(f"   Search 'Ericsson Response humanitarian connectivity': {len(hits)} hits")
    for h in hits:
        print(f"     [{h.get('score', 0):.3f}] {h.get('title')}")

    ans = ai.ask_archive("What is Ericsson Response and Connect to Learn?")
    print(f"   AI QA Mode: {ans['mode']} (citations: {len(ans['citations'])})")
    print(f"   Answer:\n   {ans['answer'][:300]}...")

    print("\n" + "=" * 60)
    print("ALL OFFICIAL ERICSSON CHECKS COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
