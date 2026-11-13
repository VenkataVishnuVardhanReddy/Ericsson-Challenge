"""End-to-end processing pipeline + background job queue."""
from __future__ import annotations

import gzip
import json
import os
import queue
import shutil
import tempfile
import threading
import time
import traceback
from pathlib import Path

from . import config as C
from . import db, search
from .util import (canonical_name, fmt_ts, jdump, norm_text, object_path, probe_video, run_ffmpeg,
                   sha256_file)

PIPELINE_VERSION = "distill-1.0"


# =========================================================================== sources & scanning
def kind_of(path: Path) -> str:
    e = path.suffix.lower()
    if e in C.VIDEO_EXT:
        return "video"
    if e in C.PDF_EXT:
        return "pdf"
    if e in C.PPTX_EXT:
        return "pptx"
    if e in C.TRANSCRIPT_EXT:
        return "transcript"
    return "other"


def guess_source_kind(name: str) -> str:
    n = name.lower()
    if "sharepoint" in n:
        return "sharepoint"
    if "onedrive" in n:
        return "onedrive"
    if "play" in n:
        return "play"
    return "other"


def add_source(root: str, name: str | None = None, kind: str | None = None, owner: str | None = None,
               governed: bool | None = None) -> int:
    root = str(Path(root).resolve())
    name = name or Path(root).name
    kind = kind or guess_source_kind(name)
    if governed is None:
        governed = kind != "onedrive"      # personal drives are not a governed source of truth
    if owner is None and kind == "onedrive":
        owner = name.replace("OneDrive_", "").replace("_", " ")
    with db.tx() as c:
        c.execute("""INSERT INTO sources(name, root_path, kind, owner, governed) VALUES (?,?,?,?,?)
                     ON CONFLICT(root_path) DO UPDATE SET name=excluded.name, kind=excluded.kind,
                     owner=excluded.owner, governed=excluded.governed""",
                  (name, root, kind, owner, int(governed)))
    return db.q1("SELECT id FROM sources WHERE root_path=?", (root,))["id"]


def scan_source(source_id: int) -> list[int]:
    src = db.q1("SELECT * FROM sources WHERE id=?", (source_id,))
    ids = []
    for p in sorted(Path(src["root_path"]).rglob("*")):
        if not p.is_file() or p.name.startswith((".", "~$", "_")):
            continue
        st = p.stat()
        if p.suffix.lower() in C.VIDEO_EXT and (time.time() - st.st_mtime < 8 or probe_video(p)["duration"] <= 0):
            continue  # skip video file that is still actively downloading
        existing = db.q1("SELECT id, size, mtime, status FROM files WHERE path=?", (str(p),))
        if existing and existing["size"] == st.st_size and abs((existing["mtime"] or 0) - st.st_mtime) < 1 \
                and existing["status"] == "done":
            ids.append(existing["id"])
            continue
        sha = sha256_file(p)
        with db.tx() as c:
            c.execute("""INSERT INTO files(source_id, path, name, ext, kind, size, sha256, mtime, status)
                         VALUES (?,?,?,?,?,?,?,?, 'new')
                         ON CONFLICT(path) DO UPDATE SET size=excluded.size, sha256=excluded.sha256,
                         mtime=excluded.mtime, status='new'""",
                      (source_id, str(p), p.name, p.suffix.lower(), kind_of(p), st.st_size, sha, st.st_mtime))
        ids.append(db.q1("SELECT id FROM files WHERE path=?", (str(p),))["id"])
    return ids


# =========================================================================== documents
def process_document(file_id: int, progress) -> None:
    from .documents import process_pdf, process_pptx

    f = db.q1("SELECT * FROM files WHERE id=?", (file_id,))
    # byte-identical file already processed -> reuse its slides (no re-rendering needed)
    twin = db.q1("SELECT id FROM files WHERE sha256=? AND id<>? AND status='done' AND kind=?",
                 (f["sha256"], file_id, f["kind"]))
    progress(0.1, "Splitting into slides")
    if twin:
        src_slides = db.q("SELECT * FROM slides WHERE file_id=?", (twin["id"],))
        t = db.q1("SELECT * FROM files WHERE id=?", (twin["id"],))
        res = {k: t[k] for k in ("title", "author", "doc_date", "doc_number", "revision", "text_hash")}
        res["meta"] = json.loads(t["meta"] or "{}")
        res["slides"] = [dict(s, core="") for s in src_slides]
    else:
        res = process_pdf(f["path"]) if f["kind"] == "pdf" else process_pptx(f["path"])
    progress(0.7, "Hashing & indexing slides")
    search.delete_file_chunks(file_id)
    with db.tx() as c:
        c.execute("DELETE FROM slides WHERE file_id=?", (file_id,))
        c.execute("""UPDATE files SET title=?, author=?, doc_date=?, doc_number=?, revision=?, text_hash=?, meta=?
                     WHERE id=?""",
                  (res["title"], res["author"], res["doc_date"], res["doc_number"], res["revision"],
                   res["text_hash"], jdump(res["meta"]), file_id))
        slide_ids = []
        for s in res["slides"]:
            cur = c.execute("""INSERT INTO slides(file_id,page_no,content_id,phash,text,title,object_hash,bytes)
                               VALUES (?,?,?,?,?,?,?,?)""",
                            (file_id, s["page_no"], s["content_id"], s["phash"], s["text"], s["title"],
                             s["object_hash"], s["bytes"]))
            slide_ids.append(cur.lastrowid)
    label = f"{f['name']}" + (f" · {res['doc_number']}" if res["doc_number"] else "") + \
            (f" Rev {res['revision']}" if res["revision"] else "")
    search.add_chunks([{"kind": "slide", "file_id": file_id, "ref_id": sid,
                        "title": f"{s['title']} — {label}, slide {s['page_no']}", "text": s["text"]}
                       for sid, s in zip(slide_ids, res["slides"]) if (s["text"] or "").strip()])


# =========================================================================== video
def _sidecar_transcript(path: str) -> str | None:
    p = Path(path)
    for ext in (".vtt", ".srt"):
        for cand in (p.with_suffix(ext), p.with_name(p.stem + ".transcript" + ext)):
            if cand.exists():
                return str(cand)
    return None


def process_video(file_id: int, progress) -> None:
    from . import diarize, transcribe
    from .keyframes import extract_keyframes
    from .linker import keyframe_for_time, match_keyframes, slide_prompt
    from .ocr import ocr, slide_likeness

    f = db.q1("SELECT * FROM files WHERE id=?", (file_id,))
    path = f["path"]
    info = probe_video(path)
    dur = info["duration"]
    pdir = C.PACKETS_DIR / str(file_id)
    if pdir.exists():
        shutil.rmtree(pdir, ignore_errors=True)
    (pdir / "slides").mkdir(parents=True)

    # reuse analysis of a byte-identical copy (same recording uploaded to several systems)
    twin = db.q1("""SELECT f.id FROM files f JOIN recordings r ON r.file_id=f.id
                    WHERE f.sha256=? AND f.id<>? AND f.status='done'""", (f["sha256"], file_id))
    if twin:
        progress(0.5, "Identical copy already distilled — linking")
        _clone_recording(twin["id"], file_id)
        return

    tmp = Path(tempfile.mkdtemp(prefix="distill_"))
    try:
        progress(0.02, "Extracting audio")
        wav = str(tmp / "audio.wav")
        has_audio = True
        try:
            transcribe.extract_audio_wav(path, wav)
        except Exception:
            has_audio = False

        # ---- transcript
        side = _sidecar_transcript(path)
        tmeta = {}
        audio = None
        if side:
            progress(0.05, "Importing existing transcript (with speaker names)")
            segs = transcribe.parse_subtitles(side)
            tsource = "vtt"
            tmeta = {"language": None, "mean_confidence": 1.0, "model": "imported " + Path(side).suffix}
        elif has_audio:
            progress(0.05, f"Transcribing speech (Whisper {C.WHISPER_MODEL}, CPU)")
            words, tmeta = transcribe.transcribe(wav, lambda p: progress(0.05 + 0.45 * p, "Transcribing speech"), dur)
            turns = []
            audio = transcribe.load_wav(wav)
            if diarize.available() and len(words) > 0:
                progress(0.52, "Identifying speakers")
                try:
                    turns = diarize.diarize(audio)
                except Exception as e:
                    print("diarization failed", e)
            segs = transcribe.words_to_segments(words, turns)
            tsource = "whisper"
        else:
            segs, tsource = [], "none"

        # ---- voice samples (one short clip per speaker)
        voices = {}
        if has_audio and segs:
            try:
                if audio is None:
                    audio = transcribe.load_wav(wav)
                vtmp = tmp / "voices"
                wavs = diarize.voice_samples(audio, segs, vtmp)
                (pdir / "voices").mkdir(exist_ok=True)
                for spk, name in wavs.items():
                    out = pdir / "voices" / (Path(name).stem + ".opus")
                    transcribe.encode_opus(str(vtmp / name), str(out), "24k")
                    voices[spk] = "voices/" + out.name
            except Exception as e:
                print("voice samples failed", e)

        # ---- keyframes
        progress(0.58, "Detecting slide changes")
        kfs, diag = extract_keyframes(path, dur, lambda p: progress(0.58 + 0.2 * p, "Detecting slide changes"))

        # ---- OCR + slide prompts
        kf_rows = []
        for i, k in enumerate(kfs):
            progress(0.78 + 0.1 * i / max(1, len(kfs)), f"Reading slide text (OCR) {i + 1}/{len(kfs)}")
            o = ocr(k.image)
            like = slide_likeness(k.image, o)
            kf_rows.append({"k": k, "ocr": o, "is_slide": int(like >= 0.35 or len(o["text"]) > 40),
                            "prompt": slide_prompt(k.image, o)})

        # ---- persist recording, keyframes
        with db.tx() as c:
            for t in ("segments", "keyframes", "chunks"):
                c.execute(f"DELETE FROM {t} WHERE file_id=?", (file_id,))
            for i, r in enumerate(kf_rows):
                k = r["k"]
                cur = c.execute("""INSERT INTO keyframes(file_id, idx, start, end, intervals, object_hash, bytes, phash,
                                   ocr_text, is_slide, description) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                (file_id, i, k.start, k.end, jdump(k.intervals), k.object_hash, k.bytes, k.phash,
                                 r["ocr"]["text"], r["is_slide"], r["prompt"]))
                r["id"] = cur.lastrowid
        search._version[0] += 1

        # ---- link frames to deck slides
        progress(0.89, "Linking frames to source decks")
        kmini = [{"id": r["id"], "ocr_text": r["ocr"]["text"], "phash": r["k"].phash, "is_slide": r["is_slide"]}
                 for r in kf_rows]
        m = match_keyframes(kmini)
        with db.tx() as c:
            for kid, (sid, score) in m["links"].items():
                c.execute("UPDATE keyframes SET slide_id=?, match_score=? WHERE id=?", (sid, score, kid))

        # ---- time-link transcript to keyframes
        kf_time = [{"id": r["id"], "intervals": r["k"].intervals} for r in kf_rows]
        with db.tx() as c:
            for s in segs:
                kid = keyframe_for_time(kf_time, (s["start"] + s["end"]) / 2) if kf_time else None
                s["keyframe_id"] = kid
                c.execute("""INSERT INTO segments(file_id,start,end,speaker,text,keyframe_id,confidence)
                             VALUES (?,?,?,?,?,?,?)""",
                          (file_id, s["start"], s["end"], s["speaker"], s["text"], kid, s.get("confidence")))

        # ---- knowledge packet + measured tiers
        progress(0.91, "Writing knowledge packet")
        audio_bytes = 0
        if has_audio:
            audio_bytes = transcribe.encode_opus(wav, str(pdir / "audio.opus"))
        packet = write_packet(file_id, f, info, segs, kf_rows, m, voices, tsource, tmeta, diag)

        progress(0.93, "Measuring compressed-video tier")
        t1 = compressed_video_tier(path, file_id, dur)

        progress(0.95, "Verifying information retention")
        retention = measure_retention(path, kf_rows, m, segs, tmeta, diag, dur)

        tiers = packet_tiers(pdir, f["size"], t1, kf_rows, m)
        with db.tx() as c:
            c.execute("""INSERT OR REPLACE INTO recordings(file_id,duration,width,height,fps,language,transcript_source,
                         tiers,retention,fingerprint,packet_dir,summary) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (file_id, dur, info["width"], info["height"], info["fps"], tmeta.get("language"), tsource,
                       jdump(tiers), jdump(retention), jdump(diag["fingerprint"]), str(pdir),
                       packet.get("summary")))
        # manifest gets final numbers too
        man = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
        man.update({"storage_tiers": tiers, "information_retention": retention})
        (pdir / "manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")

        # ---- search index
        progress(0.97, "Indexing for search")
        search.add_chunks(build_moment_chunks(file_id, f["name"], segs, kf_rows, m))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _clone_recording(src_id: int, dst_id: int) -> None:
    rec = db.q1("SELECT * FROM recordings WHERE file_id=?", (src_id,))
    with db.tx() as c:
        for t in ("segments", "keyframes", "chunks"):
            c.execute(f"DELETE FROM {t} WHERE file_id=?", (dst_id,))
        rec = dict(rec, file_id=dst_id)
        cols = ",".join(rec)
        c.execute(f"INSERT OR REPLACE INTO recordings({cols}) VALUES ({','.join('?' * len(rec))})", tuple(rec.values()))
        kmap = {}
        for k in db.q("SELECT * FROM keyframes WHERE file_id=?", (src_id,)):
            old = k.pop("id")
            k["file_id"] = dst_id
            cur = c.execute(f"INSERT INTO keyframes({','.join(k)}) VALUES ({','.join('?' * len(k))})", tuple(k.values()))
            kmap[old] = cur.lastrowid
        for s in db.q("SELECT * FROM segments WHERE file_id=?", (src_id,)):
            s.pop("id")
            s["file_id"], s["keyframe_id"] = dst_id, kmap.get(s["keyframe_id"])
            c.execute(f"INSERT INTO segments({','.join(s)}) VALUES ({','.join('?' * len(s))})", tuple(s.values()))
    # copies are not indexed twice for search (one source of truth); they show up as duplicates


# --------------------------------------------------------------------------- packet
def write_packet(file_id, f, info, segs, kf_rows, m, voices, tsource, tmeta, diag) -> dict:
    pdir = C.PACKETS_DIR / str(file_id)
    links = m["links"]
    slide_rows = {s["id"]: s for s in db.q("""SELECT s.id, s.page_no, s.content_id, f.name, f.doc_number, f.revision
                                              FROM slides s JOIN files f ON f.id=s.file_id""")}
    kf_meta = []
    for i, r in enumerate(kf_rows):
        k = r["k"]
        fn = f"slides/{i + 1:03d}.webp"
        shutil.copy(object_path(k.object_hash), pdir / fn)
        link = links.get(r["id"])
        ref = None
        if link:
            s = slide_rows.get(link[0])
            if s:
                ref = {"deck": s["name"], "doc_number": s["doc_number"], "revision": s["revision"],
                       "page": s["page_no"], "slide_id": "SLD-" + s["content_id"][:10].upper(), "score": link[1]}
        kf_meta.append({"n": i + 1, "file": fn, "intervals": k.intervals, "title": r["ocr"]["title"],
                        "is_slide": bool(r["is_slide"]), "source_slide": ref, "sha256_webp": k.object_hash})

    # transcript.txt (plain text with speakers), transcript.vtt (speaker-tagged), notes.md
    txt = [f"{fmt_ts(s['start'])} {s['speaker']}: {s['text']}" for s in segs]
    (pdir / "transcript.txt").write_text("\n".join(txt), encoding="utf-8")

    def vts(t):
        h, r = divmod(t, 3600)
        mm, ss = divmod(r, 60)
        return f"{int(h):02d}:{int(mm):02d}:{ss:06.3f}"

    vtt = ["WEBVTT", ""]
    for s in segs:
        vtt += [f"{vts(s['start'])} --> {vts(s['end'])}", f"<v {s['speaker']}>{s['text']}</v>", ""]
    (pdir / "transcript.vtt").write_text("\n".join(vtt), encoding="utf-8")

    by_kf: dict = {}
    for s in segs:
        by_kf.setdefault(s.get("keyframe_id"), []).append(s)
    md = [f"# {f['name']}", "",
          f"*Distilled by {PIPELINE_VERSION} · duration {fmt_ts(info['duration'])} · "
          f"speakers: {', '.join(sorted({s['speaker'] for s in segs})) or 'n/a'}*", ""]
    timeline = []
    for i, r in enumerate(kf_rows):
        for a, b in r["k"].intervals:
            timeline.append((a, b, i, r))
    timeline.sort(key=lambda x: x[0])
    for a, b, i, r in timeline:
        meta = kf_meta[i]
        head = meta["title"] or f"Screen {i + 1}"
        ref = meta["source_slide"]
        md += [f"## [{fmt_ts(a)}–{fmt_ts(b)}] {head}", "", f"![slide {i + 1}]({meta['file']})", ""]
        if ref:
            md += [f"> Source of truth: **{ref['deck']}**"
                   + (f" ({ref['doc_number']} Rev {ref['revision']})" if ref["doc_number"] else "")
                   + f", slide {ref['page']} · `{ref['slide_id']}`", ""]
        for s in segs:
            mid = (s["start"] + s["end"]) / 2
            if a <= mid <= b:
                md.append(f"**{s['speaker']}** ({fmt_ts(s['start'])}): {s['text']}  ")
        md.append("")
    (pdir / "notes.md").write_text("\n".join(md), encoding="utf-8")

    prompts = [f"# Slide recreation prompts — {f['name']}", ""]
    for i, r in enumerate(kf_rows):
        prompts += [f"## Slide {i + 1}", "", "```", r["prompt"], "```", ""]
    (pdir / "slide_prompts.md").write_text("\n".join(prompts), encoding="utf-8")

    summary = extractive_summary(segs)
    manifest = {
        "schema": "distill.knowledge-packet/1.0",
        "pipeline": PIPELINE_VERSION,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": {"name": f["name"], "path": f["path"], "sha256": f["sha256"], "bytes": f["size"]},
        "media": {k: info[k] for k in ("duration", "width", "height", "fps")},
        "transcript": {"source": tsource, **tmeta, "segments": len(segs),
                       "speakers": sorted({s["speaker"] for s in segs})},
        "voices": voices,
        "keyframes": kf_meta,
        "presented_deck_file_id": m.get("deck"),
        "summary": summary,
        "files": {"transcript_txt": "transcript.txt", "transcript_vtt": "transcript.vtt", "notes": "notes.md",
                  "chunks": "chunks.jsonl", "slide_prompts": "slide_prompts.md", "audio": "audio.opus"},
    }
    (pdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # RAG-ready chunks
    with open(pdir / "chunks.jsonl", "w", encoding="utf-8") as fh:
        for a, b, i, r in timeline:
            spoken = [s for s in segs if a <= (s["start"] + s["end"]) / 2 <= b]
            fh.write(json.dumps({
                "id": f"{f['sha256'][:12]}-{int(a)}", "source": f["name"], "start": a, "end": b,
                "slide": kf_meta[i]["file"], "source_slide": kf_meta[i]["source_slide"],
                "slide_text": r["ocr"]["text"], "speakers": sorted({s["speaker"] for s in spoken}),
                "text": " ".join(f"{s['speaker']}: {s['text']}" for s in spoken),
            }, ensure_ascii=False) + "\n")
    return {"summary": summary}


def extractive_summary(segs: list[dict], n: int = 5) -> str:
    """Cheap, model-free summary: most 'central' sentences by word frequency."""
    from collections import Counter

    sents = [s["text"] for s in segs if len(s["text"].split()) >= 6]
    if not sents:
        return ""
    stop = set("the a an and or of to in on for is are was were be this that it we you i they with as at by from so "
               "our can will have has here there what which about just like also very really okay yeah".split())
    freq = Counter(w for s in sents for w in norm_text(s).split() if w not in stop and len(w) > 2)
    scored = sorted(((sum(freq[w] for w in norm_text(s).split()) / (len(s.split()) ** 0.7), i, s)
                     for i, s in enumerate(sents)), reverse=True)[:n]
    return " ".join(s for _, _, s in sorted(scored, key=lambda x: x[1]))


def packet_tiers(pdir: Path, original: int, t1: dict, kf_rows, m) -> dict:
    def size(p: Path) -> int:
        return p.stat().st_size if p.exists() else 0

    files = [p for p in pdir.rglob("*") if p.is_file()]
    total = sum(size(p) for p in files)
    audio = size(pdir / "audio.opus") + size(pdir / "audio.m4a")
    slides_total = sum(size(p) for p in (pdir / "slides").glob("*.webp"))
    linked_bytes = sum(r["k"].bytes for r in kf_rows if r["id"] in m["links"])
    text_files = ["transcript.txt", "transcript.vtt", "notes.md", "chunks.jsonl", "slide_prompts.md", "manifest.json"]
    text_raw = sum(size(pdir / t) for t in text_files)
    text_gz = sum(len(gzip.compress((pdir / t).read_bytes())) for t in text_files if (pdir / t).exists())
    voices = sum(size(p) for p in (pdir / "voices").glob("*")) if (pdir / "voices").exists() else 0
    t2 = audio + slides_total + text_gz + voices
    t3 = slides_total + text_gz + voices
    t4 = (slides_total - linked_bytes) + text_gz + voices

    def tier(name, b, desc, measured=True):
        return {"name": name, "bytes": int(b), "saving": round(1 - b / original, 5) if original else 0,
                "desc": desc, "measured": measured}

    return {
        "original": original,
        "tiers": [
            tier("T0 Original", original, "Original recording"),
            tier("T1 Smart re-encode", t1["bytes"], "Same video, re-encoded for screen content", t1["measured"]),
            tier("T2 Audio + slides + text", t2, "Opus speech audio, WebP keyframes, transcript, notes"),
            tier("T3 Slides + text", t3, "Keyframes + speaker transcript + voice samples"),
            tier("T4 Text + slide links", t4, "Transcript; slides replaced by links to source-of-truth decks"),
        ],
        "breakdown": {"audio": audio, "slides": slides_total, "slides_linked": linked_bytes,
                      "text_raw": text_raw, "text_gzip": text_gz, "voices": voices, "packet_total": total},
    }


def compressed_video_tier(path: str, file_id: int, dur: float) -> dict:
    """Real re-encode for short videos; for long ones estimate from the measured bitrate model."""
    out = C.RECREATED_DIR / f"t1_{file_id}.mp4"
    if dur <= float(os.environ.get("DISTILL_T1_MAX_SEC", 1500)):
        try:
            run_ffmpeg(["-i", path, "-vf", "fps=5,scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "32", "-tune", "stillimage", "-c:a", "aac", "-b:a", "32k", "-ac", "1",
                        "-movflags", "+faststart", str(out)])
            return {"bytes": out.stat().st_size, "measured": True, "path": str(out)}
        except Exception as e:
            print("T1 encode failed", e)
    return {"bytes": int(dur * (110_000 + 32_000) / 8), "measured": False, "path": None}


def measure_retention(path, kf_rows, m, segs, tmeta, diag, dur) -> dict:
    """Prove 'without losing information': OCR random frames of the ORIGINAL video and check how much of
    their on-screen text is present in the distilled keyframes covering the same moment."""
    from .keyframes import frame_at
    from .linker import keyframe_for_time
    from .ocr import ocr

    n = int(os.environ.get("DISTILL_RETENTION_SAMPLES", 8))
    kf_time = [{"id": r["id"], "intervals": r["k"].intervals} for r in kf_rows]
    by_id = {r["id"]: r for r in kf_rows}
    slide_text = {s["id"]: s["text"] for s in db.q("SELECT id, text FROM slides")}
    covered = sum(b - a for r in kf_rows for a, b in r["k"].intervals)
    scores, checked = [], 0
    for i in range(n):
        t = dur * (i + 0.5) / n
        kid = keyframe_for_time(kf_time, t) if kf_time else None
        if kid is None:
            continue
        img = frame_at(path, t)
        if img is None:
            continue
        words = {w for w in norm_text(ocr(img)["text"]).split() if len(w) > 3}
        if len(words) < 3:
            continue
        r = by_id[kid]
        kept = norm_text(r["ocr"]["text"]) + " " + norm_text(slide_text.get(m["links"].get(kid, (None,))[0], "") or "")
        kept_w = set(kept.split())
        scores.append(len(words & kept_w) / len(words))
        checked += 1
    words_total = sum(len(s["text"].split()) for s in segs)
    return {
        "screen_text_retained": round(sum(scores) / len(scores), 3) if scores else None,
        "frames_checked": checked,
        "timeline_covered_by_keyframes": round(min(1.0, covered / dur), 3) if dur else 0,
        "keyframes": len(kf_rows),
        "linked_to_source_deck": len(m["links"]),
        "transcript_words": words_total,
        "speech_confidence": tmeta.get("mean_confidence"),
        "speakers": len({s["speaker"] for s in segs}),
        "live_video_area": diag.get("live_area_share"),
    }


def build_moment_chunks(file_id, name, segs, kf_rows, m) -> list[dict]:
    rows = []
    slide_info = {s["id"]: s for s in db.q("SELECT s.id, s.page_no, f.name FROM slides s JOIN files f ON f.id=s.file_id")}
    for r in kf_rows:
        for a, b in r["k"].intervals:
            # split long intervals into ~90 s windows so search lands on the right moment
            t = a
            while t < b - 1:
                e = min(b, t + 90)
                spoken = [s for s in segs if t <= (s["start"] + s["end"]) / 2 < e]
                link = m["links"].get(r["id"])
                ref = slide_info.get(link[0]) if link else None
                title = (r["ocr"]["title"] or "Screen") + f" — {name} @ {fmt_ts(t)}"
                if ref:
                    title += f" (= {ref['name']} slide {ref['page_no']})"
                text = "On screen: " + (r["ocr"]["text"] or "") + "\nSpoken: " + \
                       " ".join(f"[{s['speaker']}] {s['text']}" for s in spoken)
                rows.append({"kind": "moment", "file_id": file_id, "ref_id": r["id"], "start": t, "end": e,
                             "title": title, "text": text})
                t = e
    if not kf_rows:  # audio-only / camera-only: plain time windows
        t, end = 0.0, max((s["end"] for s in segs), default=0)
        while t < end:
            spoken = [s for s in segs if t <= s["start"] < t + 60]
            if spoken:
                rows.append({"kind": "moment", "file_id": file_id, "ref_id": None, "start": t, "end": t + 60,
                             "title": f"{name} @ {fmt_ts(t)}",
                             "text": "Spoken: " + " ".join(f"[{s['speaker']}] {s['text']}" for s in spoken)})
            t += 60
    return rows


# =========================================================================== job queue
class Jobs:
    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.jobs: dict[int, dict] = {}
        self.order: list[int] = []
        self._n = 0
        self._lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, file_id: int) -> int:
        f = db.q1("SELECT id, name, kind, size FROM files WHERE id=?", (file_id,))
        with self._lock:
            for j in self.jobs.values():   # don't queue the same file twice
                if j["file_id"] == file_id and j["status"] in ("queued", "running"):
                    return j["id"]
            self._n += 1
            j = {"id": self._n, "file_id": file_id, "name": f["name"], "kind": f["kind"], "size": f["size"],
                 "status": "queued", "progress": 0.0, "stage": "Queued", "error": None,
                 "queued_at": time.time(), "started_at": None, "finished_at": None}
            self.jobs[j["id"]] = j
            self.order.append(j["id"])
        self.q.put(j["id"])
        return j["id"]

    def list(self) -> list[dict]:
        return [self.jobs[i] for i in self.order[-200:]]

    def clear(self) -> None:
        with self._lock:
            self.jobs.clear()
            self.order.clear()

    def _worker(self):
        while True:
            jid = self.q.get()
            j = self.jobs[jid]
            j.update(status="running", started_at=time.time(), stage="Starting")

            def progress(p, stage=None):
                j["progress"] = round(float(p), 3)
                if stage:
                    j["stage"] = stage

            try:
                with db.tx() as c:
                    c.execute("UPDATE files SET status='processing', error=NULL WHERE id=?", (j["file_id"],))
                if j["kind"] == "video":
                    process_video(j["file_id"], progress)
                elif j["kind"] in ("pdf", "pptx"):
                    process_document(j["file_id"], progress)
                with db.tx() as c:
                    c.execute("UPDATE files SET status='done' WHERE id=?", (j["file_id"],))
                j.update(status="done", progress=1.0, stage="Done")
            except Exception as e:
                traceback.print_exc()
                with db.tx() as c:
                    c.execute("UPDATE files SET status='error', error=? WHERE id=?", (str(e)[:500], j["file_id"]))
                j.update(status="error", error=str(e)[:500], stage="Failed")
            finally:
                j["finished_at"] = time.time()


JOBS: Jobs | None = None


def jobs() -> Jobs:
    global JOBS
    if JOBS is None:
        JOBS = Jobs()
    return JOBS


def _process_aux(file_id: int) -> None:
    from .documents import process_docx, process_msg

    f = db.q1("SELECT * FROM files WHERE id=?", (file_id,))
    if not f:
        return
    try:
        if f["ext"] == ".docx":
            res = process_docx(f["path"])
        elif f["ext"] == ".msg":
            res = process_msg(f["path"])
        elif f["ext"] in (".png", ".jpg", ".jpeg", ".webp"):
            from .ocr import ocr
            from PIL import Image
            from .documents import text_hash
            im = Image.open(f["path"])
            o = ocr(im)
            res = {
                "title": o.get("title") or Path(f["path"]).stem,
                "text": o.get("text", ""),
                "text_hash": text_hash(o.get("text", "")) if o.get("text") else None,
            }
        else:
            res = None
        if res and res.get("text"):
            search.delete_file_chunks(file_id)
            with db.tx() as c:
                c.execute("UPDATE files SET title=?, text_hash=?, doc_number=?, revision=? WHERE id=?",
                          (res.get("title"), res.get("text_hash"), res.get("doc_number"), res.get("revision"), file_id))
            search.add_chunks([{"kind": "slide", "file_id": file_id, "ref_id": file_id,
                                "title": f"{res.get('title') or f['name']} ({f['name']})", "text": res["text"]}])
    except Exception:
        pass
    with db.tx() as c:
        c.execute("UPDATE files SET status='done' WHERE id=?", (file_id,))


def ingest(root: str, **kw) -> dict:
    """Register a folder as a source, scan it and queue processing (documents first, then videos)."""
    sid = add_source(root, **kw)
    ids = scan_source(sid)
    files = db.q(f"SELECT id, kind, status FROM files WHERE id IN ({','.join('?' * len(ids))})", ids) if ids else []
    queued = 0
    for kind in ("pdf", "pptx", "video"):
        for f in files:
            if f["kind"] == kind and f["status"] != "done":
                jobs().submit(f["id"])
                queued += 1
    for f in files:
        if f["kind"] in ("transcript", "other") and f["status"] != "done":
            _process_aux(f["id"])
    return {"source_id": sid, "files": len(ids), "queued": queued}


def ingest_many(roots: list[str]) -> list[dict]:
    """Ingest several sources; all documents from all sources are processed before any video,
    so video frames can be linked to deck slides regardless of where the decks live."""
    sids = [add_source(r) for r in roots]
    all_ids = []
    for sid in sids:
        all_ids += scan_source(sid)
    files = db.q(f"SELECT id, kind, status FROM files WHERE id IN ({','.join('?' * len(all_ids))})", all_ids) if all_ids else []
    for kind in ("pdf", "pptx", "video"):
        for f in files:
            if f["kind"] == kind and f["status"] != "done":
                jobs().submit(f["id"])
    for f in files:
        if f["kind"] in ("transcript", "other") and f["status"] != "done":
            _process_aux(f["id"])
    return [{"source_id": s} for s in sids]
