"""Hybrid search: keyword (SQLite FTS5 / BM25) + semantic (multilingual sentence embeddings).

Results are fused with Reciprocal Rank Fusion, so exact terms (doc numbers, product names)
AND meaning ("how do we save power at night?") both work, in English and Swedish.
"""
from __future__ import annotations

from pathlib import Path
import re
import threading

import numpy as np

from . import config as C
from . import db

_model = None
_lock = threading.Lock()
_cache = {"version": -1, "ids": None, "mat": None}
_version = [0]


def embedder():
    global _model
    with _lock:
        if _model is None:
            import os

            os.environ.setdefault("HF_HOME", str(C.MODELS_DIR / "hf"))
            os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
            from sentence_transformers import SentenceTransformer

            local_dir = C.MODELS_DIR / "all-MiniLM-L6-v2"
            if (local_dir / "model.safetensors").exists():
                _model = SentenceTransformer(str(local_dir), device="cpu")
            else:
                try:
                    _model = SentenceTransformer(
                        C.EMBED_MODEL, device="cpu", cache_folder=str(C.MODELS_DIR / "hf"), local_files_only=True
                    )
                except Exception:
                    _model = SentenceTransformer(
                        C.EMBED_MODEL, device="cpu", cache_folder=str(C.MODELS_DIR / "hf")
                    )
    return _model


def embed(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), np.float32)
    v = embedder().encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(v, dtype=np.float32)


def add_chunks(rows: list[dict]) -> None:
    """rows: {kind,file_id,ref_id,start,end,title,text}"""
    if not rows:
        return
    vecs = embed([(r["title"] or "") + "\n" + (r["text"] or "")[:2000] for r in rows])
    with db.tx() as c:
        for r, v in zip(rows, vecs):
            c.execute("""INSERT INTO chunks(kind,file_id,ref_id,start,end,title,text,embedding)
                         VALUES (?,?,?,?,?,?,?,?)""",
                      (r["kind"], r["file_id"], r.get("ref_id"), r.get("start"), r.get("end"),
                       r.get("title"), r.get("text"), v.tobytes()))
    _version[0] += 1


def delete_file_chunks(file_id: int) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM chunks WHERE file_id=?", (file_id,))
    _version[0] += 1


def _matrix():
    if _cache["version"] != _version[0] or _cache["ids"] is None:
        rows = db.connect().execute("SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL").fetchall()
        _cache["ids"] = np.array([r[0] for r in rows], dtype=np.int64)
        _cache["mat"] = (np.stack([np.frombuffer(r[1], np.float32) for r in rows])
                         if rows else np.zeros((0, 384), np.float32))
        _cache["version"] = _version[0]
    return _cache["ids"], _cache["mat"]


def _fts_query(q: str) -> str:
    toks = re.findall(r"\w+", q, re.UNICODE)
    return " OR ".join(f'"{t}"*' if len(t) > 2 else f'"{t}"' for t in toks[:12])


def search(query: str, k: int = 20, kind: str | None = None, file_id: int | None = None) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    ranks: dict[int, float] = {}
    # keyword
    fq = _fts_query(query)
    if fq:
        try:
            kw = db.connect().execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts, 2.0, 1.0) LIMIT 60",
                (fq,)).fetchall()
            for r, (cid,) in enumerate(kw):
                ranks[cid] = ranks.get(cid, 0) + 1.0 / (60 + r)
        except Exception:
            pass
    # semantic
    ids, mat = _matrix()
    sem_score = {}
    if len(ids):
        qv = embed([query])[0]
        sims = mat @ qv
        top = np.argsort(-sims)[:60]
        for r, i in enumerate(top):
            cid = int(ids[i])
            sem_score[cid] = float(sims[i])
            ranks[cid] = ranks.get(cid, 0) + 1.2 / (60 + r)
    if not ranks:
        return []
    order = sorted(ranks, key=lambda c: -ranks[c])
    out = []
    terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
    for cid in order:
        row = db.q1("""SELECT c.id, c.kind, c.file_id, c.ref_id, c.start, c.end, c.title, c.text,
                              f.name, f.path, f.kind file_kind, s.name source
                       FROM chunks c JOIN files f ON f.id=c.file_id LEFT JOIN sources s ON s.id=f.source_id
                       WHERE c.id=?""", (cid,))
        if not row or (kind and row["kind"] != kind) or (file_id and row["file_id"] != file_id):
            continue
        row["score"] = round(ranks[cid] * 1000, 2)
        row["semantic"] = round(sem_score.get(cid, 0.0), 3)
        row["snippet"] = _snippet(row["text"] or "", terms)
        if row["kind"] == "moment":
            kf = db.q1("SELECT object_hash, slide_id FROM keyframes WHERE id=?", (row["ref_id"],)) if row["ref_id"] else None
            row["image"] = kf["object_hash"] if kf else None
            row["slide_id"] = kf["slide_id"] if kf else None
        elif row["kind"] == "document":
            p = Path(row["path"]) if row.get("path") else None
            if p and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                row["image"] = f"/api/files/{row['file_id']}/raw"
            else:
                row["image"] = None
            row["page_no"] = None
        else:
            sl = db.q1("SELECT object_hash, page_no FROM slides WHERE id=?", (row["ref_id"],))
            row["image"] = sl["object_hash"] if sl else None
            row["page_no"] = sl["page_no"] if sl else None
        if row.get("path"):
            try:
                row["rel_path"] = str(Path(row["path"]).resolve().relative_to(C.ROOT.resolve())).replace("\\", "/")
            except Exception:
                row["rel_path"] = Path(row["path"]).name
            row.pop("path", None)
        row.pop("text", None)
        out.append(row)
        if len(out) >= k:
            break
    return out


def _snippet(text: str, terms: list[str], width: int = 260) -> str:
    low = text.lower()
    pos = min((low.find(t) for t in terms if low.find(t) >= 0), default=-1)
    if pos < 0:
        # spoken part is usually most informative
        i = text.find("Spoken:")
        pos = i + 8 if i >= 0 else 0
    start = max(0, pos - width // 3)
    s = text[start:start + width].replace("\n", " ")
    return ("…" if start else "") + s + ("…" if start + width < len(text) else "")
