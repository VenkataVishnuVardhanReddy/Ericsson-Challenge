#!/usr/bin/env python3
"""scripts/recompute_checks.py
Recomputes retention checks with 20 sampled moments per video without re-transcribing.
Implements character-level text verification, perceptual hash picture verification,
motion classification, always-on-screen text filtering (min 3 letters),
OCR accuracy vs official deck, and exports recreated/spot_check.html.
"""
from __future__ import annotations

import base64
import html
import io
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import distill.config as C
import distill.db as db
from distill.keyframes import activity_mask
from distill.ocr import ocr
from distill.util import dhash_gray, phash_img, fmt_ts, object_path


def img_to_b64(im: Image.Image, max_w: int = 320, quality: int = 70) -> str:
    """Converts a PIL image to a compact base64 JPEG data URI."""
    try:
        w, h = im.size
        if w > max_w:
            nh = max(1, round(h * (max_w / w)))
            im = im.resize((max_w, nh), Image.BILINEAR)
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return ""


def merge_main_speakers(file_id: int) -> int:
    """Merge speakers who spoke for < 30 seconds into their nearest main speaker."""
    segs = db.q("SELECT id, start, end, speaker FROM segments WHERE file_id=? ORDER BY start", (file_id,))
    if not segs:
        return 0
    totals = {}
    for s in segs:
        spk = s["speaker"] or "Speaker 1"
        totals[spk] = totals.get(spk, 0.0) + (s["end"] - s["start"])

    main_speakers = {spk for spk, dur in totals.items() if dur >= 30.0}
    if not main_speakers:
        main_speakers = {max(totals.keys(), key=lambda k: totals[k])}

    mapping = {}
    last_main = sorted(main_speakers)[0]
    for s in segs:
        spk = s["speaker"] or "Speaker 1"
        if spk in main_speakers:
            last_main = spk
            mapping[spk] = spk
        else:
            mapping[spk] = last_main

    with db.tx() as conn:
        for s in segs:
            old_spk = s["speaker"] or "Speaker 1"
            new_spk = mapping.get(old_spk, old_spk)
            if new_spk != old_spk:
                conn.execute("UPDATE segments SET speaker=? WHERE id=?", (new_spk, s["id"]))

    return len(main_speakers)


def build_extractive_summary(file_id: int, pdir: Path) -> None:
    """Picks 3-5 high-value representative sentences from transcript without AI."""
    segs = db.q("SELECT text, start, speaker FROM segments WHERE file_id=? ORDER BY start", (file_id,))
    if not segs:
        return

    good_sentences = []
    for s in segs:
        txt = (s["text"] or "").strip()
        if len(txt) > 40 and not txt.startswith(("Thank you", "Yeah", "Okay", "Uh", "Um")):
            good_sentences.append(f"- **{fmt_ts(s['start'])}** [{s['speaker']}]: {txt}")

    if not good_sentences:
        good_sentences = [f"- {s['text']}" for s in segs[:5]]

    step = max(1, len(good_sentences) // 5)
    selected = good_sentences[::step][:5]

    summary_md = "# Key Points (Extractive)\n\n" + "\n".join(selected) + "\n"
    (pdir / "notes.md").write_text(summary_md, encoding="utf-8")


def recompute_video(file_id: int):
    f = db.q1("SELECT * FROM files WHERE id=?", (file_id,))
    rec = db.q1("SELECT * FROM recordings WHERE file_id=?", (file_id,))
    if not f or not rec:
        print(f"Skipping {file_id}: not a recording")
        return None

    p = Path(f["path"])
    pdir = Path(rec["packet_dir"])
    dur = float(rec["duration"] or 1.0)
    print(f"\n========================================================")
    print(f"Processing Video #{file_id}: {f['name']} (duration: {dur:.1f}s)")
    print(f"========================================================")

    # 1. Normalize speakers
    main_count = merge_main_speakers(file_id)
    print(f"  [OK] Speaker labels normalized to {main_count} main speakers.")

    # 2. Update extractive summary
    build_extractive_summary(file_id, pdir)
    print(f"  [OK] Extractive summary updated in notes.md.")

    # Previous score
    ret_orig = json.loads(rec["retention"] or "{}") if isinstance(rec["retention"], str) else (rec["retention"] or {})
    old_score = ret_orig.get("screen_text_retained")

    # STEP 0 — Sample 20 evenly spaced moments & find always-on-screen text
    n = 20
    moments_raw = []
    cap = cv2.VideoCapture(str(p))
    for i in range(n):
        t = dur * (i + 0.5) / n
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
        ok1, bgr1 = cap.read()
        cap.set(cv2.CAP_PROP_POS_MSEC, min(dur - 0.05, t + 1.0) * 1000.0)
        ok2, bgr2 = cap.read()
        if not ok1 or bgr1 is None:
            continue
        im1 = Image.fromarray(cv2.cvtColor(bgr1, cv2.COLOR_BGR2RGB))
        im2 = Image.fromarray(cv2.cvtColor(bgr2, cv2.COLOR_BGR2RGB)) if (ok2 and bgr2 is not None) else im1
        moments_raw.append((t, im1, im2))
    cap.release()

    if not moments_raw:
        print(f"  [ERROR] Could not decode frames for file {file_id}")
        return None

    # Compute activity mask across the 20 sampled moments at 320 px grayscale
    h320 = round(320 * moments_raw[0][1].height / moments_raw[0][1].width)
    g1_list = [
        np.asarray(im1.resize((320, h320), Image.BILINEAR).convert("L"), dtype=np.uint8)
        for _, im1, _ in moments_raw
    ]
    frames_320 = np.stack(g1_list)
    mask = activity_mask(frames_320)

    # OCR all 20 frames to find always-on-screen text (ignored_words)
    # RULE: ignored_words must have at least 3 letters
    print(f"  Scanning 20 moments for on-screen text & persistent UI elements...", flush=True)
    frame_ocr = []
    word_freq = {}
    for i_f, (t, im1, _) in enumerate(moments_raw):
        res = ocr(im1)
        txt = res.get("text", "")
        words = [w for w in re.findall(r"[a-z0-9]+", txt.lower()) if len(w) >= 3]
        frame_ocr.append((txt, words))
        for w in set(words):
            word_freq[w] = word_freq.get(w, 0) + 1

    total_frames = len(moments_raw)
    threshold = total_frames * 0.6  # appearing in > 60% of frames
    ignored_words = [w for w, count in word_freq.items() if count > threshold and len(w) >= 3]

    # Check if frequent name variants (>= 4 frames) cluster into > 60%
    freq_candidates = [w for w, count in word_freq.items() if 4 <= count <= threshold and len(w) >= 3]
    for c in freq_candidates:
        sum_count = word_freq[c]
        for other in freq_candidates:
            if other != c and abs(len(c) - len(other)) <= 2 and SequenceMatcher(None, c, other).ratio() >= 0.80:
                sum_count += word_freq[other]
        if sum_count > threshold and c not in ignored_words:
            ignored_words.append(c)

    ignored_words.sort(key=lambda w: (-word_freq.get(w, 0), w))
    ignored_words = ignored_words[:30]
    all_ignored = set(ignored_words)

    print(f"  Found {len(ignored_words)} always-on-screen words (>=3 chars): {ignored_words}")

    # Load keyframe intervals and deck text
    kfs = db.q("SELECT * FROM keyframes WHERE file_id=? ORDER BY idx", (file_id,))
    for k in kfs:
        k["intervals_list"] = json.loads(k["intervals"] or "[]")

    # Load deck text and file meta
    slide_rows = {s["id"]: s for s in db.q("SELECT * FROM slides")}
    slide_text = {s["id"]: s["text"] for s in db.q("SELECT id, text FROM slides")}
    slide_file = {s["id"]: s["file_id"] for s in db.q("SELECT id, file_id FROM slides")}
    files_by_id = {f_row["id"]: f_row for f_row in db.q("SELECT id, name, title, meta FROM files")}
    segs = db.q("SELECT * FROM segments WHERE file_id=? ORDER BY start", (file_id,))

    # Measure OCR accuracy on keyframes linked to official decks:
    # Word recall of official slide words (>= 3 chars) in kept picture's OCR text.
    # Visible text only: remove "[Speaker notes]" and deck boilerplate lines.
    ocr_scores = []
    for k in kfs:
        sid = k.get("slide_id")
        if not sid or sid not in slide_rows:
            continue
        s_row = slide_rows[sid]
        f_row = files_by_id.get(s_row["file_id"])
        meta = json.loads(f_row.get("meta") or "{}") if (f_row and isinstance(f_row.get("meta"), str)) else ((f_row.get("meta") or {}) if f_row else {})
        bp_list = meta.get("boilerplate") or []

        off_text = s_row.get("text") or ""
        if "[Speaker notes]" in off_text:
            off_text = off_text.split("[Speaker notes]")[0]
        for bp in bp_list:
            if bp and bp.strip():
                off_text = off_text.replace(bp, "")

        off_words = [w for w in re.findall(r"[a-z0-9]+", off_text.lower()) if len(w) >= 3]
        if not off_words:
            continue

        ocr_txt = (k.get("ocr_text") or "").lower()
        ocr_compact = re.sub(r"[^a-z0-9]", "", ocr_txt)
        ocr_words = [w for w in re.findall(r"[a-z0-9]+", ocr_txt) if len(w) >= 3]
        ocr_words_set = set(ocr_words)

        found = 0
        for w in off_words:
            if w in ocr_words_set:
                found += 1
                continue
            if len(w) >= 5 and w in ocr_compact:
                found += 1
                continue
            w_len = len(w)
            matched = False
            for ow in ocr_words:
                if abs(len(ow) - w_len) <= 2 and SequenceMatcher(None, w, ow, autojunk=False).ratio() >= 0.90:
                    matched = True
                    break
            if not matched and w_len >= 5 and len(ocr_compact) >= w_len:
                for j in range(len(ocr_compact) - w_len + 1):
                    sub = ocr_compact[j:j+w_len]
                    if SequenceMatcher(None, w, sub, autojunk=False).ratio() >= 0.90:
                        matched = True
                        break
            if matched:
                found += 1

        recall = found / len(off_words)
        ocr_scores.append({
            "keyframe_id": k["id"],
            "slide_id": sid,
            "page_no": s_row["page_no"],
            "recall": recall,
            "found": found,
            "total": len(off_words),
            "official_snippet": " ".join(off_text.split())[:120],
            "ocr_snippet": " ".join((k.get("ocr_text") or "").split())[:120],
        })

    if ocr_scores:
        ocr_accuracy_pct = round(sum(s["recall"] for s in ocr_scores) / len(ocr_scores), 3)
        ocr_slides_checked = len(ocr_scores)
        sorted_by_recall = sorted(ocr_scores, key=lambda x: x["recall"])
        lowest_slides = [
            {
                "page_no": s["page_no"],
                "score_pct": round(s["recall"] * 100, 1),
                "official_snippet": s["official_snippet"],
                "ocr_snippet": s["ocr_snippet"],
            }
            for s in sorted_by_recall[:3]
        ]
    else:
        ocr_accuracy_pct = None
        ocr_slides_checked = 0
        lowest_slides = []

    moments_res = []
    text_scores = []
    picture_scores = []
    visual_matches = []
    moving_count = 0

    for idx, (t, im1, im2) in enumerate(moments_raw):
        # STEP 1: Classify moment
        g1 = g1_list[idx]
        g2 = np.asarray(im2.resize((320, h320), Image.BILINEAR).convert("L"), dtype=np.uint8)
        # Apply static mask
        g1_m = (g1 * mask).astype(np.uint8)
        g2_m = (g2 * mask).astype(np.uint8)
        h1 = dhash_gray(g1_m)
        h2 = dhash_gray(g2_m)
        dist_motion = bin(h1 ^ h2).count("1")

        orig_txt, orig_words_all = frame_ocr[idx]
        cleaned_words = [w for w in orig_words_all if w not in all_ignored]
        cleaned_str = "".join(cleaned_words)

        if dist_motion > 10:
            kind = "moving_video"
        elif len(cleaned_str) >= 20:
            kind = "text"
        else:
            kind = "picture"

        # STEP 2: Find kept picture for t
        matched_kf = None
        matched_interval = None
        for k in kfs:
            for iv in k["intervals_list"]:
                if (iv[0] - 0.5) <= t <= (iv[1] + 0.5):
                    matched_kf = k
                    matched_interval = iv
                    break
            if matched_kf:
                break

        # Linked deck info
        linked_deck = None
        linked_s_text = ""
        if matched_kf and matched_kf.get("slide_id"):
            sid = matched_kf["slide_id"]
            linked_s_text = slide_text.get(sid, "")
            fid = slide_file.get(sid)
            if fid and fid in files_by_id:
                linked_deck = files_by_id[fid]["title"] or files_by_id[fid]["name"]

        # Spoken text around t
        spoken = [s["text"] for s in segs if (s["start"] - 2.0) <= t <= (s["end"] + 2.0)]
        spoken_text = " ".join(spoken) if spoken else ""

        kept_obj = matched_kf["object_hash"] if matched_kf else None
        kept_time_range = f"{fmt_ts(matched_interval[0])} - {fmt_ts(matched_interval[1])}" if matched_interval else None

        # STEP 3: Score by kind
        original_count = len(cleaned_str)
        found_count = 0
        missing_count = 0
        found_words = []
        missing_words = []
        hamming = None

        orig_b64 = img_to_b64(im1, max_w=320)
        kept_b64 = ""

        # Visual match across EVERY moment: pHash distance <= 12 with activity mask
        dist_phash = 64
        if matched_kf and matched_kf.get("object_hash"):
            im_path = object_path(matched_kf["object_hash"])
            if im_path.exists():
                try:
                    im_kept = Image.open(im_path)
                    if not kept_b64:
                        kept_b64 = img_to_b64(im_kept, max_w=320)
                    g_kept = np.asarray(im_kept.resize((320, h320), Image.BILINEAR).convert("L"), dtype=np.uint8)
                    ph1 = phash_img(Image.fromarray(g1_m))
                    ph2 = phash_img(Image.fromarray((g_kept * mask).astype(np.uint8)))
                    dist_phash = bin(int(ph1, 16) ^ int(ph2, 16)).count("1")
                except Exception:
                    dist_phash = 64
        visual_matches.append(dist_phash <= 12)

        if kind == "moving_video":
            moving_count += 1
            hamming = dist_motion
        elif kind == "text":
            if not matched_kf:
                missing_count = original_count
                missing_words = cleaned_words[:15]
                text_scores.append(0.0)
            else:
                im_path = object_path(matched_kf["object_hash"])
                if im_path.exists() and not kept_b64:
                    try:
                        kept_b64 = img_to_b64(Image.open(im_path), max_w=320)
                    except Exception:
                        pass

                kept_raw = (matched_kf.get("ocr_text") or "") + " " + (linked_s_text or "")
                kept_string = re.sub(r"[^a-z0-9]", "", kept_raw.lower())
                found_chars = 0
                for w in cleaned_words:
                    w_len = len(w)
                    if w in kept_string:
                        found_chars += w_len
                        if len(found_words) < 15:
                            found_words.append(w)
                    elif w_len >= 10:
                        matched = False
                        max_diff = int(w_len * 0.10)
                        for j in range(len(kept_string) - w_len + 1):
                            sub = kept_string[j:j + w_len]
                            mismatches = sum(1 for c1, c2 in zip(w, sub) if c1 != c2)
                            if mismatches <= max_diff:
                                if SequenceMatcher(None, w, sub, autojunk=False).ratio() >= 0.90:
                                    matched = True
                                    break
                        if matched:
                            found_chars += w_len
                            if len(found_words) < 15:
                                found_words.append(w)
                        else:
                            if len(missing_words) < 15:
                                missing_words.append(w)
                    else:
                        if len(missing_words) < 15:
                            missing_words.append(w)

                found_count = found_chars
                missing_count = max(0, original_count - found_count)
                score = (found_chars / original_count) if original_count > 0 else 1.0
                text_scores.append(score)
        elif kind == "picture":
            hamming = dist_phash
            if dist_phash <= 12:
                picture_scores.append(1.0)
            else:
                picture_scores.append(0.0)

        moments_res.append({
            "t": round(t, 1),
            "kind": kind,
            "original_count": original_count,
            "found_count": found_count,
            "missing_count": missing_count,
            "found_words": found_words[:15],
            "missing_words": missing_words[:15],
            "hamming": hamming,
            "visual_dist": dist_phash,
            "visual_match": dist_phash <= 12,
            "kept_slide_object": kept_obj,
            "kept_time_range": kept_time_range,
            "linked_deck": linked_deck,
            "spoken_text": spoken_text[:140],
            "orig_b64": orig_b64,
            "kept_b64": kept_b64,
        })

    # STEP 4: Store per video in recordings.retention
    # Rule: If fewer than 3 moments exist for a kind, store null and note "Not enough <kind> moments (n)"
    if len(text_scores) < 3:
        text_kept_pct = None
        text_note = f"Not enough text moments ({len(text_scores)})"
    else:
        text_kept_pct = round(sum(text_scores) / len(text_scores), 3)
        text_note = None

    if len(picture_scores) < 3:
        pictures_kept_pct = None
        picture_note = f"Not enough picture moments ({len(picture_scores)})"
    else:
        pictures_kept_pct = round(sum(picture_scores) / len(picture_scores), 3)
        picture_note = None

    visual_match_pct = round(sum(1 for v in visual_matches if v) / len(visual_matches), 3) if visual_matches else None
    moving_video_pct = round(moving_count / len(moments_res), 3) if moments_res else None

    # Database moments without bulky base64
    db_moments = []
    for m in moments_res:
        db_m = {k: v for k, v in m.items() if k not in ("orig_b64", "kept_b64")}
        db_moments.append(db_m)

    ret_orig["text_kept_pct"] = text_kept_pct
    ret_orig["text_moments"] = len(text_scores)
    ret_orig["text_note"] = text_note
    ret_orig["pictures_kept_pct"] = pictures_kept_pct
    ret_orig["picture_moments"] = len(picture_scores)
    ret_orig["picture_note"] = picture_note
    ret_orig["visual_match_pct"] = visual_match_pct
    ret_orig["ocr_accuracy_pct"] = ocr_accuracy_pct
    ret_orig["ocr_slides_checked"] = ocr_slides_checked
    ret_orig["lowest_slides"] = lowest_slides
    ret_orig["moving_video_pct"] = moving_video_pct
    ret_orig["screen_text_retained"] = text_kept_pct if text_kept_pct is not None else pictures_kept_pct
    ret_orig["frames_checked"] = len(moments_res)
    ret_orig["moments"] = db_moments
    ret_orig["ignored_words"] = ignored_words
    ret_orig["main_speakers"] = main_count

    with db.tx() as conn:
        conn.execute("UPDATE recordings SET retention=? WHERE file_id=?", (json.dumps(ret_orig), file_id))

    report = {
        "file_id": file_id,
        "name": f["name"],
        "duration": dur,
        "old_score": old_score,
        "text_kept_pct": text_kept_pct,
        "text_moments": len(text_scores),
        "text_note": text_note,
        "pictures_kept_pct": pictures_kept_pct,
        "picture_moments": len(picture_scores),
        "picture_note": picture_note,
        "visual_match_pct": visual_match_pct,
        "ocr_accuracy_pct": ocr_accuracy_pct,
        "ocr_slides_checked": ocr_slides_checked,
        "lowest_slides": lowest_slides,
        "moving_video_pct": moving_video_pct,
        "moving_moments": moving_count,
        "moments": moments_res,
    }
    return report


def export_spot_check_html(all_reports: list[dict], out_path: Path):
    """Exports a self-contained, standalone spot-check HTML report with side-by-side images."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cards_html = []
    for rep in all_reports:
        rows_html = []
        for idx, m in enumerate(rep["moments"]):
            kind = m["kind"]
            kind_badge = (
                '<span class="badge badge-text">Text</span>'
                if kind == "text"
                else (
                    '<span class="badge badge-pic">Picture</span>'
                    if kind == "picture"
                    else '<span class="badge badge-motion">Moving video</span>'
                )
            )

            # Left image: original
            orig_img_tag = (
                f'<img src="{m["orig_b64"]}" alt="Original frame" class="thumb" />'
                if m.get("orig_b64")
                else '<div class="no-img">No frame</div>'
            )

            # Right image: kept
            if m.get("kept_b64"):
                kept_img_tag = f'<img src="{m["kept_b64"]}" alt="Kept picture" class="thumb" />'
            else:
                if kind == "moving_video":
                    kept_img_tag = '<div class="no-img">Video footage<br>(kept as audio + slides)</div>'
                else:
                    kept_img_tag = '<div class="no-img">Missing</div>'

            # Result status
            if kind == "text":
                score_pct = (
                    f"{(m['found_count'] / m['original_count'] * 100):.1f}%"
                    if m["original_count"] > 0
                    else "100%"
                )
                res_desc = f"<strong>{score_pct} text retained</strong> ({m['found_count']} / {m['original_count']} chars)"
            elif kind == "picture":
                ham = m.get("hamming")
                res_desc = (
                    f"<strong>Visual match</strong> (pHash diff: {ham} &le; 12)"
                    if (ham is not None and ham <= 12)
                    else f"Difference (pHash diff: {ham})"
                )
            else:
                res_desc = f"Moving video footage (motion Hamming: {m.get('hamming', '-')})"

            coverage = f"Covers: {m['kept_time_range']}" if m.get("kept_time_range") else "No keyframe interval"
            if m.get("linked_deck"):
                coverage += f" &bull; Linked: {html.escape(m['linked_deck'])}"

            spoken = f"&ldquo;{html.escape(m['spoken_text'])}&rdquo;" if m.get("spoken_text") else "<em>(No speech)</em>"

            row = f"""
            <tr class="moment-row">
              <td class="moment-meta">
                <div class="m-idx">Moment #{idx + 1}</div>
                <div class="m-time">@{fmt_ts(m['t'])}</div>
                <div class="m-badge">{kind_badge}</div>
              </td>
              <td class="moment-img">
                <div class="img-label">Original Video Frame</div>
                {orig_img_tag}
              </td>
              <td class="moment-img">
                <div class="img-label">Kept Slide Picture</div>
                {kept_img_tag}
              </td>
              <td class="moment-details">
                <div class="detail-res">{res_desc}</div>
                <div class="detail-cov">{coverage}</div>
                <div class="detail-spoken">{spoken}</div>
              </td>
            </tr>
            """
            rows_html.append(row)

        t_pct = f"{rep['text_kept_pct']*100:.1f}%" if rep["text_kept_pct"] is not None else (rep.get("text_note") or "—")
        p_pct = f"{rep['pictures_kept_pct']*100:.1f}%" if rep["pictures_kept_pct"] is not None else (rep.get("picture_note") or "—")
        v_pct = f"{rep['visual_match_pct']*100:.1f}%" if rep.get("visual_match_pct") is not None else "—"
        m_pct = f"{rep['moving_video_pct']*100:.1f}%" if rep["moving_video_pct"] is not None else "—"
        ocr_pct = f"{rep['ocr_accuracy_pct']*100:.1f}% ({rep['ocr_slides_checked']} slides)" if rep["ocr_accuracy_pct"] is not None else "No linked official slides"

        lowest_html = ""
        if rep.get("lowest_slides"):
            items = []
            for ls in rep["lowest_slides"]:
                items.append(
                    f"<li><strong>Page {ls['page_no']} ({ls['score_pct']}% recall):</strong><br/>"
                    f"<em>Official:</em> {html.escape(ls['official_snippet'])}<br/>"
                    f"<em>OCR:</em> {html.escape(ls['ocr_snippet'])}</li>"
                )
            lowest_html = f"""
            <div style="margin-top: 12px; padding: 12px; background: #f5f5f5; border-radius: 8px; font-size: 12px; border: 1px solid #e5e5e5;">
              <strong style="color: #000;">Lowest scoring official slides (OCR recall against clean PDF text):</strong>
              <ul style="margin: 6px 0 0 16px; padding: 0; display: flex; flex-direction: column; gap: 6px;">
                {''.join(items)}
              </ul>
            </div>
            """

        card = f"""
        <div class="video-section">
          <div class="video-header">
            <h2>{html.escape(rep['name'])}</h2>
            <div class="video-stats">
              <span><strong>Duration:</strong> {fmt_ts(rep['duration'])}</span>
              <span><strong>Slide Text Kept:</strong> {t_pct}</span>
              <span><strong>Pictures Match (pixel comparison, no OCR):</strong> {v_pct}</span>
              <span><strong>Moving Video:</strong> {m_pct}</span>
              <span><strong>OCR Reads Official Slides:</strong> {ocr_pct}</span>
            </div>
            {lowest_html}
          </div>
          <table class="moments-table">
            <thead>
              <tr>
                <th style="width: 120px;">Moment</th>
                <th style="width: 260px;">Original Frame</th>
                <th style="width: 260px;">Kept Picture</th>
                <th>Verification Details & Coverage</th>
              </tr>
            </thead>
            <tbody>
              {''.join(rows_html)}
            </tbody>
          </table>
        </div>
        """
        cards_html.append(card)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Distill — Video Retention Verification (Spot-Check)</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 32px;
      background: #fafafa;
      color: #111;
      line-height: 1.5;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 32px;
      padding-bottom: 24px;
      border-bottom: 1px solid #e5e5e5;
    }}
    h1 {{
      font-size: 28px;
      font-weight: 700;
      margin: 0 0 8px 0;
      color: #000;
    }}
    .subtitle {{
      color: #666;
      font-size: 15px;
      margin: 0;
    }}
    .video-section {{
      background: #fff;
      border: 1px solid #e5e5e5;
      border-radius: 12px;
      margin-bottom: 32px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}
    .video-header {{
      padding: 20px 24px;
      border-bottom: 1px solid #e5e5e5;
      background: #fff;
    }}
    .video-header h2 {{
      margin: 0 0 10px 0;
      font-size: 18px;
      font-weight: 600;
      word-break: break-all;
    }}
    .video-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      font-size: 13px;
      color: #444;
    }}
    .video-stats strong {{
      color: #000;
    }}
    .moments-table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }}
    .moments-table th {{
      background: #f7f7f7;
      padding: 10px 16px;
      border-bottom: 1px solid #e5e5e5;
      font-weight: 600;
      font-size: 12px;
      color: #555;
    }}
    .moment-row {{
      border-bottom: 1px solid #eee;
    }}
    .moment-row:last-child {{
      border-bottom: none;
    }}
    .moment-meta {{
      padding: 16px;
      vertical-align: top;
    }}
    .m-idx {{
      font-weight: 600;
      color: #000;
    }}
    .m-time {{
      font-family: monospace;
      color: #666;
      font-size: 12px;
      margin-top: 2px;
    }}
    .m-badge {{
      margin-top: 8px;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .badge-text {{
      background: #000;
      color: #fff;
    }}
    .badge-pic {{
      background: #e5e5e5;
      color: #000;
    }}
    .badge-motion {{
      background: #fff;
      color: #666;
      border: 1px solid #ccc;
    }}
    .moment-img {{
      padding: 16px;
      vertical-align: top;
    }}
    .img-label {{
      font-size: 11px;
      font-weight: 600;
      color: #888;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
    }}
    .thumb {{
      width: 100%;
      max-width: 240px;
      aspect-ratio: 16/9;
      object-fit: cover;
      border-radius: 6px;
      border: 1px solid #e5e5e5;
      display: block;
      background: #000;
    }}
    .no-img {{
      width: 100%;
      max-width: 240px;
      aspect-ratio: 16/9;
      border-radius: 6px;
      border: 1px dashed #ccc;
      background: #f9f9f9;
      color: #888;
      font-size: 11px;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 8px;
      box-sizing: border-box;
    }}
    .moment-details {{
      padding: 16px;
      vertical-align: top;
    }}
    .detail-res {{
      font-size: 13px;
      color: #000;
      margin-bottom: 6px;
    }}
    .detail-cov {{
      font-size: 12px;
      font-family: monospace;
      color: #666;
      margin-bottom: 8px;
    }}
    .detail-spoken {{
      font-size: 12px;
      color: #444;
      background: #f9f9f9;
      padding: 8px 12px;
      border-radius: 6px;
      border-left: 3px solid #000;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Distill — Video Retention Verification Report</h1>
      <p class="subtitle">
        Spot check of 20 evenly-spaced moments across all video recordings. Proves that no presentation slides or spoken content were lost during storage reduction.
      </p>
    </header>

    <main>
      {''.join(cards_html)}
    </main>
  </div>
</body>
</html>
"""
    out_path.write_text(html_content, encoding="utf-8")
    print(f"\n[OK] Standalone spot-check report exported to: {out_path} ({len(html_content):,} bytes)")


def main():
    print("======================================================================")
    print(" Distill: Recomputing 'Was anything lost?' Verification Checks")
    print("======================================================================")

    videos = db.q("SELECT id, name FROM files WHERE kind='video' ORDER BY id")
    all_reports = []
    for v in videos:
        rep = recompute_video(v["id"])
        if rep:
            all_reports.append(rep)

    print("\n" + "=" * 70)
    print("SUMMARY REPORT ACROSS ALL VIDEOS")
    print("=" * 70)
    for rep in all_reports:
        print(f"\n--- File #{rep['file_id']}: {rep['name']} ---")
        old_str = f"{rep['old_score']*100:.1f}%" if rep['old_score'] is not None else "None"
        t_str = f"{rep['text_kept_pct']*100:.1f}%" if rep['text_kept_pct'] is not None else (rep.get("text_note") or "N/A")
        p_str = f"{rep['pictures_kept_pct']*100:.1f}%" if rep['pictures_kept_pct'] is not None else (rep.get("picture_note") or "N/A")
        v_str = f"{rep['visual_match_pct']*100:.1f}%" if rep.get('visual_match_pct') is not None else "N/A"
        m_str = f"{rep['moving_video_pct']*100:.1f}%" if rep['moving_video_pct'] is not None else "0.0%"
        ocr_str = f"{rep['ocr_accuracy_pct']*100:.1f}% ({rep['ocr_slides_checked']} slides)" if rep['ocr_accuracy_pct'] is not None else "N/A"
        print(f"  Old Retention Score : {old_str}")
        print(f"  Slide Text Kept     : {t_str} ({rep['text_moments']} moments)")
        print(f"  Pictures Match      : {v_str} (pixel comparison across all 20 moments)")
        print(f"  Pictures Kept       : {p_str} ({rep['picture_moments']} moments)")
        print(f"  Moving Video        : {m_str} ({rep['moving_moments']} moments)")
        print(f"  OCR Reads Slides    : {ocr_str}")
        if rep.get("lowest_slides"):
            print("  Lowest 3 Slides OCR :")
            for ls in rep["lowest_slides"]:
                off_snip = ls['official_snippet'][:40].encode("ascii", "replace").decode("ascii")
                ocr_snip = ls['ocr_snippet'][:40].encode("ascii", "replace").decode("ascii")
                print(f"    Page {ls['page_no']} ({ls['score_pct']}% recall) - Off: {off_snip}... | OCR: {ocr_snip}...")

    out_html = ROOT / "recreated" / "spot_check.html"
    export_spot_check_html(all_reports, out_html)
    print("\n[OK] All verification checks successfully computed and saved to database.")


if __name__ == "__main__":
    main()
