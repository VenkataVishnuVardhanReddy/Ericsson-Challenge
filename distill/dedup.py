"""Duplicate & revision intelligence across all connected systems.

Levels
1. exact file      : same SHA-256 (e.g. 'deck (1).pdf' downloaded and re-uploaded)
2. same content    : same normalised text hash, different bytes (re-export, metadata change)
3. shared slides   : identical slide content_id / visual hash across different decks
4. revisions       : decks with mostly identical + slightly modified slides (Rev A -> Rev B)
5. video duplicate : same recording re-encoded / trimmed on another platform (perceptual fingerprint)
"""
from __future__ import annotations

import difflib
import io
import json
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw

from . import config as C
from . import db
from .util import canonical_name, hamming_hex, norm_text, object_path


# --------------------------------------------------------------------------- helpers
def _text_sim(a: str, b: str) -> float:
    wa = {w for w in norm_text(a).split() if len(w) > 1}
    wb = {w for w in norm_text(b).split() if len(w) > 1}
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    p, r = inter / len(wb), inter / len(wa)
    return 0.0 if inter == 0 else 2 * p * r / (p + r)


def _popcount64(x: np.ndarray) -> np.ndarray:
    if hasattr(np, "bitwise_count"):
        return np.bitwise_count(x)
    x = x.astype(np.uint64)
    if x.ndim >= 2 and x.shape[0] > 256:
        out = np.empty(x.shape, dtype=np.uint8)
        for i in range(0, x.shape[0], 256):
            chunk = x[i:i + 256]
            out[i:i + 256] = np.unpackbits(chunk.view(np.uint8).reshape(*chunk.shape, 8), axis=-1).sum(-1)
        return out
    return np.unpackbits(x.view(np.uint8).reshape(*x.shape, 8), axis=-1).sum(-1)


def slide_relation(a: dict, b: dict) -> str | None:
    """'identical' | 'modified' | None between two slide rows."""
    ham = hamming_hex(a["phash"], b["phash"])
    if a["content_id"] == b["content_id"] and ham <= C.IDENTICAL_HAMMING:
        return "identical"
    ts = _text_sim(a.get("text", ""), b.get("text", ""))
    if ham <= C.IDENTICAL_HAMMING and ts > 0.97:
        return "identical"
    if ts >= C.NEAR_TEXT_SIM or (ham <= C.NEAR_HAMMING and ts >= 0.5):
        return "modified"
    return None


def _files(where: str = "1=1", params=()) -> list[dict]:
    return db.q(f"""SELECT f.*, s.name AS source_name, s.kind AS source_kind, s.owner, s.governed
                    FROM files f LEFT JOIN sources s ON s.id=f.source_id WHERE {where}""", params)


# --------------------------------------------------------------------------- exact / content groups
def exact_groups() -> list[dict]:
    rows = _files("f.sha256 IS NOT NULL")
    by = defaultdict(list)
    for r in rows:
        by[r["sha256"]].append(r)
    out = []
    for sha, fs in by.items():
        if len(fs) > 1:
            fs.sort(key=lambda f: (-(f["governed"] or 0), len(f["name"])))
            out.append({"sha256": sha, "files": fs, "keep": fs[0]["id"],
                        "reclaimable": sum(f["size"] for f in fs[1:]), "level": "exact"})
    return sorted(out, key=lambda g: -g["reclaimable"])


def content_groups() -> list[dict]:
    rows = _files("f.text_hash IS NOT NULL AND f.kind IN ('pdf','pptx')")
    by = defaultdict(list)
    for r in rows:
        by[r["text_hash"]].append(r)
    out = []
    for th, fs in by.items():
        if len({f["sha256"] for f in fs}) > 1:     # at least two different byte versions
            fs.sort(key=lambda f: (-(f["governed"] or 0), len(f["name"])))
            uniq = {}
            for f in fs:
                uniq.setdefault(f["sha256"], f)
            out.append({"text_hash": th, "files": fs, "keep": fs[0]["id"],
                        "reclaimable": sum(f["size"] for f in fs[1:]), "level": "content"})
    return out


# --------------------------------------------------------------------------- slide level
def _slides_by_file() -> dict[int, list[dict]]:
    out = defaultdict(list)
    for s in db.q("SELECT id, file_id, page_no, content_id, phash, text, title, object_hash FROM slides ORDER BY file_id, page_no"):
        out[s["file_id"]].append(s)
    return out


def deck_comparison(a_id: int, b_id: int, sa=None, sb=None) -> dict:
    """Align slides of deck B against deck A."""
    if sa is None or sb is None:
        sbf = _slides_by_file()
        sa, sb = sbf.get(a_id, []), sbf.get(b_id, [])
    used = set()
    pairs = []
    for s in sb:
        best, rel_best = None, None
        for t in sa:
            rel = slide_relation(t, s)
            if rel == "identical":
                best, rel_best = t, rel
                break
            if rel == "modified" and rel_best is None:
                best, rel_best = t, rel
        if best is not None:
            used.add(best["id"])
        pairs.append({"b": s, "a": best, "relation": rel_best or "new"})
    removed = [t for t in sa if t["id"] not in used]
    ident = sum(p["relation"] == "identical" for p in pairs)
    mod = sum(p["relation"] == "modified" for p in pairs)
    return {"pairs": pairs, "removed": removed, "identical": ident, "modified": mod,
            "new": len(pairs) - ident - mod, "a_pages": len(sa), "b_pages": len(sb)}


def deck_relations() -> list[dict]:
    """All pairs of decks that share content, classified."""
    files = {f["id"]: f for f in _files("f.kind IN ('pdf','pptx')")}
    sbf = _slides_by_file()
    # skip byte-identical copies: compare one representative per sha
    reps, seen = [], set()
    for fid, f in sorted(files.items()):
        if f["sha256"] in seen or fid not in sbf:
            continue
        seen.add(f["sha256"])
        reps.append(fid)
    # quick candidate filter by shared content ids / similar phash
    cids = {fid: {s["content_id"] for s in sbf[fid]} for fid in reps}
    rels = []
    for i, a in enumerate(reps):
        for b in reps[i + 1:]:
            if files[a]["text_hash"] == files[b]["text_hash"]:
                continue  # reported as content duplicate
            shared = len(cids[a] & cids[b])
            same_doc = files[a]["doc_number"] and files[a]["doc_number"] == files[b]["doc_number"]
            if shared == 0 and not same_doc:
                # maybe modified slides only (revision with many edits): cheap title check
                ta = {norm_text(s["title"]) for s in sbf[a]}
                tb = {norm_text(s["title"]) for s in sbf[b]}
                if len(ta & tb) < 2:
                    continue
            cmp_ = deck_comparison(a, b, sbf[a], sbf[b])
            overlap = (cmp_["identical"] + cmp_["modified"]) / max(1, min(cmp_["a_pages"], cmp_["b_pages"]))
            if cmp_["identical"] + cmp_["modified"] == 0:
                continue
            if same_doc or (overlap >= 0.6 and cmp_["modified"] > 0):
                kind = "revision"
            else:
                kind = "shares_slides"
            rels.append({"a": files[a], "b": files[b], "kind": kind, "identical": cmp_["identical"],
                         "modified": cmp_["modified"], "new": cmp_["new"], "removed": len(cmp_["removed"]),
                         "overlap": round(overlap, 2)})
    return rels


def _rev_key(f: dict):
    r = (f.get("revision") or "").upper()
    return (len(r), r, f.get("doc_date") or "")


def version_chains(rels: list[dict] | None = None) -> list[dict]:
    rels = rels if rels is not None else deck_relations()
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    files = {}
    for r in rels:
        if r["kind"] == "revision":
            files[r["a"]["id"]], files[r["b"]["id"]] = r["a"], r["b"]
            parent[find(r["a"]["id"])] = find(r["b"]["id"])
    groups = defaultdict(list)
    for fid in files:
        groups[find(fid)].append(files[fid])
    chains = []
    for g in groups.values():
        g.sort(key=_rev_key)
        steps = []
        for x, y in zip(g, g[1:]):
            c = deck_comparison(x["id"], y["id"])
            steps.append({"from": x["id"], "to": y["id"], "identical": c["identical"],
                          "modified": c["modified"], "new": c["new"], "removed": len(c["removed"])})
        latest = g[-1]
        # storage as deltas: keep latest in full, older revisions only their differing slides
        delta_bytes = 0
        for x in g[:-1]:
            c = deck_comparison(latest["id"], x["id"])
            pages = max(1, c["b_pages"])
            delta_bytes += int(x["size"] * (pages - c["identical"]) / pages)
        full = sum(x["size"] for x in g)
        chains.append({"doc_number": latest.get("doc_number"), "title": latest.get("title"),
                       "versions": g, "steps": steps, "latest": latest["id"],
                       "full_bytes": full, "delta_bytes": latest["size"] + delta_bytes})
    return chains


def slide_index_stats() -> dict:
    rows = db.q("SELECT content_id, COUNT(*) n, COUNT(DISTINCT file_id) nf FROM slides GROUP BY content_id")
    total = sum(r["n"] for r in rows)
    return {"total_slides": total, "unique_slides": len(rows),
            "shared_slides": sum(1 for r in rows if r["nf"] > 1),
            "dedup_ratio": round(1 - len(rows) / total, 3) if total else 0}


def shared_slide_groups(limit: int = 60) -> list[dict]:
    rows = db.q("""SELECT content_id, COUNT(DISTINCT file_id) nf FROM slides GROUP BY content_id
                   HAVING nf > 1 ORDER BY nf DESC LIMIT ?""", (limit,))
    out = []
    for r in rows:
        occ = db.q("""SELECT s.id, s.page_no, s.title, s.object_hash, f.id file_id, f.name, src.name source
                      FROM slides s JOIN files f ON f.id=s.file_id LEFT JOIN sources src ON src.id=f.source_id
                      WHERE s.content_id=? ORDER BY f.id""", (r["content_id"],))
        out.append({"content_id": r["content_id"], "slide_id": "SLD-" + r["content_id"][:10].upper(),
                    "files": r["nf"], "occurrences": occ})
    return out


# --------------------------------------------------------------------------- visual diff
def diff_image(slide_a: int, slide_b: int) -> bytes:
    """Side-by-side PNG with changed regions boxed in red."""
    a = db.q1("SELECT object_hash, text FROM slides WHERE id=?", (slide_a,))
    b = db.q1("SELECT object_hash, text FROM slides WHERE id=?", (slide_b,))
    ia = Image.open(object_path(a["object_hash"])).convert("RGB")
    ib = Image.open(object_path(b["object_hash"])).convert("RGB").resize(ia.size)
    import cv2

    ga = np.asarray(ia.convert("L"), np.int16)
    gb = np.asarray(ib.convert("L"), np.int16)
    d = (np.abs(ga - gb) > 40).astype(np.uint8) * 255
    d = cv2.dilate(d, np.ones((15, 15), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(d)
    canvas = Image.new("RGB", (ia.width * 2 + 20, ia.height), "white")
    canvas.paste(ia, (0, 0))
    canvas.paste(ib, (ia.width + 20, 0))
    dr = ImageDraw.Draw(canvas)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 150:
            continue
        for off in (0, ia.width + 20):
            dr.rectangle([x + off - 3, y - 3, x + off + w + 3, y + h + 3], outline=(230, 30, 60), width=4)
    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    return buf.getvalue()


def text_diff(a: str, b: str) -> list[dict]:
    out = []
    for op in difflib.ndiff((a or "").splitlines(), (b or "").splitlines()):
        if op.startswith("?"):
            continue
        out.append({"op": {"+": "add", "-": "del"}.get(op[0], "same"), "text": op[2:]})
    return out


# --------------------------------------------------------------------------- video fingerprints
def video_similarity(fa: list[str], fb: list[str], max_ham: int = 10,
                     text_a: str | None = None, text_b: str | None = None) -> float:
    """Share of A's timeline found in B in the same temporal order (robust to re-encode & trimming)."""
    if not fa or not fb:
        return 0.0
    if text_a and text_b and text_a.strip() and text_b.strip():
        if _text_sim(text_a, text_b) < 0.8:
            return 0.0
    a = np.array([int(h, 16) for h in fa], dtype=np.uint64)
    b = np.array([int(h, 16) for h in fb], dtype=np.uint64)
    if len(a) * len(b) > 4e7:   # keep memory bounded for very long videos
        step = int(np.ceil(np.sqrt(len(a) * len(b) / 4e7)))
        a, b = a[::step], b[::step]
    if hasattr(np, "bitwise_count"):
        ham = np.bitwise_count(a[:, None] ^ b[None, :])
    else:
        ham = np.empty((len(a), len(b)), dtype=np.uint8)
        for i in range(0, len(a), 256):
            chunk = a[i:i + 256, None] ^ b[None, :]
            ham[i:i + 256] = np.unpackbits(chunk.view(np.uint8).reshape(*chunk.shape, 8), axis=-1).sum(-1)
    ii, jj = np.nonzero(ham <= max_ham)
    if len(ii) == 0:
        return 0.0
    # temporal consistency: dominant offset j - i
    offs = jj - ii
    vals, cnts = np.unique(offs, return_counts=True)
    best = vals[np.argmax(cnts)]
    ok = np.abs(offs - best) <= 2
    matched = len(np.unique(ii[ok]))
    sim = matched / len(a)
    return float(sim)


def video_groups(threshold: float = 0.6) -> list[dict]:
    vids = db.q("""SELECT f.*, r.fingerprint, r.duration, s.name source_name, s.governed FROM files f
                   JOIN recordings r ON r.file_id=f.id LEFT JOIN sources s ON s.id=f.source_id""")
    fps = {v["id"]: json.loads(v["fingerprint"] or "[]") for v in vids}
    transcripts = {}
    for row in db.q("SELECT file_id, text FROM segments ORDER BY file_id, start"):
        transcripts.setdefault(row["file_id"], []).append(row["text"] or "")
    transcripts = {fid: " ".join(texts) for fid, texts in transcripts.items()}

    groups, assigned = [], set()
    for i, v in enumerate(vids):
        if v["id"] in assigned:
            continue
        members = [dict(v, similarity=1.0)]
        txt_v = transcripts.get(v["id"], "")
        for w in vids[i + 1:]:
            if w["id"] in assigned:
                continue
            if v["sha256"] == w["sha256"]:
                sim = 1.0
            else:
                txt_w = transcripts.get(w["id"], "")
                sim = max(video_similarity(fps[v["id"]], fps[w["id"]], text_a=txt_v, text_b=txt_w),
                          video_similarity(fps[w["id"]], fps[v["id"]], text_a=txt_w, text_b=txt_v))
            if sim >= threshold:
                members.append(dict(w, similarity=round(sim, 3)))
                assigned.add(w["id"])
        if len(members) > 1:
            assigned.add(v["id"])
            members.sort(key=lambda m: (-(m.get("duration") or 0), -(m.get("governed") or 0), -(m.get("size") or 0)))
            for m in members:
                m.pop("fingerprint", None)
            groups.append({"files": members, "keep": members[0]["id"],
                           "byte_identical": len({m["sha256"] for m in members}) == 1,
                           "reclaimable": sum(m["size"] for m in members[1:]), "level": "video"})
    return groups


def name_hints() -> list[dict]:
    """Files whose names look like download copies: '(1)', 'Copy of', '- Copy'."""
    out = []
    for f in _files():
        cn = canonical_name(f["name"])
        if cn != f["name"].lower():
            out.append({"file": f, "canonical": cn})
    return out
