"""SQLite storage layer (single file, zero setup, FTS5 full-text search built in)."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterable

from .config import DB_PATH

_local = threading.local()

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    kind TEXT DEFAULT 'other',          -- sharepoint | onedrive | play | other
    owner TEXT,
    governed INTEGER DEFAULT 1          -- 1 = managed location with retention (safe as "source of truth")
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    path TEXT NOT NULL UNIQUE,
    name TEXT,
    ext TEXT,
    kind TEXT,                           -- video | pdf | pptx | transcript | other
    size INTEGER,
    sha256 TEXT,
    text_hash TEXT,                      -- hash of normalised text content (catches re-exports)
    mtime REAL,
    doc_number TEXT,
    revision TEXT,
    title TEXT,
    author TEXT,
    doc_date TEXT,
    status TEXT DEFAULT 'new',           -- new | processing | done | error
    error TEXT,
    meta TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_files_sha ON files(sha256);
CREATE INDEX IF NOT EXISTS ix_files_texthash ON files(text_hash);

CREATE TABLE IF NOT EXISTS recordings (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    duration REAL, width INTEGER, height INTEGER, fps REAL,
    language TEXT,
    transcript_source TEXT,              -- whisper | vtt
    tiers TEXT DEFAULT '{}',             -- bytes per storage tier
    retention TEXT DEFAULT '{}',         -- information retention metrics
    fingerprint TEXT DEFAULT '[]',       -- per-second perceptual hashes (video dedup)
    packet_dir TEXT,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY,
    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    start REAL, end REAL,
    speaker TEXT,
    text TEXT,
    keyframe_id INTEGER,
    confidence REAL
);
CREATE INDEX IF NOT EXISTS ix_seg_file ON segments(file_id, start);

CREATE TABLE IF NOT EXISTS keyframes (
    id INTEGER PRIMARY KEY,
    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    idx INTEGER,
    start REAL, end REAL,
    intervals TEXT DEFAULT '[]',         -- all [start,end] ranges where this screen was visible
    object_hash TEXT,                    -- content-addressable store key of the WebP image
    bytes INTEGER,
    phash TEXT,
    ocr_text TEXT,
    is_slide INTEGER DEFAULT 1,
    slide_id INTEGER,                    -- linked deck slide (single source of truth)
    match_score REAL,
    description TEXT                     -- text prompt that can recreate the slide
);
CREATE INDEX IF NOT EXISTS ix_kf_file ON keyframes(file_id, idx);

CREATE TABLE IF NOT EXISTS slides (
    id INTEGER PRIMARY KEY,
    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    page_no INTEGER,
    content_id TEXT,                     -- sha256 of normalised text + embedded image hashes
    phash TEXT,                          -- 64-bit perceptual hash of rendered slide
    text TEXT,
    title TEXT,
    object_hash TEXT,
    bytes INTEGER
);
CREATE INDEX IF NOT EXISTS ix_slides_content ON slides(content_id);
CREATE INDEX IF NOT EXISTS ix_slides_file ON slides(file_id, page_no);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    kind TEXT,                           -- moment | slide
    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    ref_id INTEGER,                      -- keyframe id or slide id
    start REAL, end REAL,
    title TEXT,
    text TEXT,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS ix_chunks_file ON chunks(file_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    title, text, content='chunks', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, title, text) VALUES('delete', old.id, old.title, old.text);
END;

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    ts TEXT DEFAULT CURRENT_TIMESTAMP,
    action TEXT,
    detail TEXT
);
"""


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def init() -> None:
    connect().executescript(SCHEMA)
    connect().commit()


@contextmanager
def tx():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def q(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    return [dict(r) for r in connect().execute(sql, tuple(params)).fetchall()]


def q1(sql: str, params: Iterable[Any] = ()) -> dict | None:
    r = connect().execute(sql, tuple(params)).fetchone()
    return dict(r) if r else None


def audit(action: str, detail: Any) -> None:
    with tx() as c:
        c.execute("INSERT INTO audit(action, detail) VALUES (?, ?)", (action, json.dumps(detail)))


def reset() -> None:
    """Delete everything (used by the demo 'reset' button)."""
    conn = connect()
    conn.executescript(
        "DELETE FROM chunks; DELETE FROM segments; DELETE FROM keyframes; DELETE FROM slides;"
        "DELETE FROM recordings; DELETE FROM files; DELETE FROM sources; DELETE FROM audit;"
        "INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');"
    )
    conn.commit()
