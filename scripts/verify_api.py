"""Verify all FastAPI routes, real storage numbers, and live UI against the populated DB."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from distill import db, dedup, offboard
from distill.app import app


def main() -> None:
    ev = db.q1("SELECT id FROM files WHERE name='Event_Recording_2026-10-14.mp4' AND path LIKE '%SharePoint%'")
    ra = db.q1("SELECT id FROM files WHERE name='5G_RAN_Energy_Efficiency_RevA.pdf' AND path LIKE '%SharePoint%'")
    rb = db.q1("SELECT id FROM files WHERE name='5G_RAN_Energy_Efficiency_RevB.pdf' AND path LIKE '%SharePoint%'")
    anna = db.q1("SELECT id FROM sources WHERE name LIKE '%Anna%'")
    cmp_ = dedup.deck_comparison(ra["id"], rb["id"])
    mp = next(p for p in cmp_["pairs"] if p["relation"] == "modified")

    with TestClient(app) as client:
        routes = [
            "/",
            "/api/overview",
            "/api/files",
            f"/api/recordings/{ev['id']}",
            f"/api/recordings/{ev['id']}/audio",
            f"/api/recordings/{ev['id']}/packet/notes.md",
            f"/api/recordings/{ev['id']}/packet/transcript.vtt",
            f"/api/recordings/{ev['id']}/packet/chunks.jsonl",
            f"/api/recordings/{ev['id']}/packet/slide_prompts.md",
            "/api/search?q=Micro-Sleep",
            "/api/duplicates",
            f"/api/compare/{ra['id']}/{rb['id']}",
            f"/api/diff-image/{mp['a']['id']}/{mp['b']['id']}",
            "/api/offboard",
            f"/api/offboard/{anna['id']}",
            "/api/benchmark",
            "/api/ai/export?fmt=jsonl",
            "/api/audit",
        ]
        for p in routes:
            print(f"GET {p} ...", end=" ", flush=True)
            r = client.get(p)
            print(r.status_code, len(r.content), flush=True)
            assert r.status_code == 200, f"{p}: {r.text[:200]}"
            if p == "/api/overview":
                ov = r.json()
                print("OVERVIEW:", json.dumps({k: v for k, v in ov.items() if k != "sources"}, indent=2))
            if p == f"/api/recordings/{ev['id']}":
                rec = r.json()
                print("SHAREPOINT EVENT TIERS:", json.dumps(rec["recording"]["tiers"], indent=2))
                print("SHAREPOINT EVENT RETENTION:", json.dumps(rec["recording"]["retention"], indent=2))

        print("POST /api/ai/ask ...", end=" ", flush=True)
        r = client.post("/api/ai/ask", json={"question": "How much night energy was saved in the Nordic field trial?"})
        print(r.status_code, flush=True)
        assert r.status_code == 200
        print("ASK AI:", r.json()["mode"], "->", r.json()["answer"][:180])

        print("POST /api/offboard/{anna}/apply (dry_run) ...", end=" ", flush=True)
        anna_rep = offboard.analyse_leaver(anna["id"])
        non_uniq = [x["file"]["id"] for x in anna_rep["files"] if x["status"] != "unique"]
        r = client.post(f"/api/offboard/{anna['id']}/apply", json={"file_ids": non_uniq, "mode": "dry_run"})
        print(r.status_code, "reclaimed:", r.json()["reclaimed_bytes"], flush=True)
        assert r.status_code == 200

    print("\nALL API ROUTES PASSED!")


if __name__ == "__main__":
    main()
