#!/usr/bin/env python3
"""scripts/recompute_checks.py
Recomputes retention checks with 20 sampled moments per video without re-transcribing.
Implements character-level text verification, perceptual hash picture verification,
motion classification, always-on-screen text filtering, and speaker normalization.
"""
from __future__ import annotations

import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

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
    print(f"  Scanning 20 moments for on-screen text & persistent UI elements...", flush=True)
    frame_ocr = []
    word_freq = {}
    for i_f, (t, im1, _) in enumerate(moments_raw):
        res = ocr(im1)
        txt = res.get("text", "")
        words = re.findall(r"[a-z0-9]+", txt.lower())
        frame_ocr.append((txt, words))
        for w in set(words):
            word_freq[w] = word_freq.get(w, 0) + 1

    total_frames = len(moments_raw)
    threshold = total_frames * 0.6  # appearing in > 60% of frames
    ignored_words = [w for w, count in word_freq.items() if count > threshold]

    # Check if frequent name variants (>= 4 frames) cluster into > 60%
    freq_candidates = [w for w, count in word_freq.items() if 4 <= count <= threshold]
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


    print(f"  Found {len(ignored_words)} always-on-screen words: {ignored_words}")

    # Load keyframe intervals and deck text
    kfs = db.q("SELECT * FROM keyframes WHERE file_id=? ORDER BY idx", (file_id,))
    for k in kfs:
        k["intervals_list"] = json.loads(k["intervals"] or "[]")

    slide_text = {s["id"]: s["text"] for s in db.q("SELECT id, text FROM slides")}
    slide_file = {s["id"]: s["file_id"] for s in db.q("SELECT id, file_id FROM slides")}
    files_by_id = {f_row["id"]: f_row for f_row in db.q("SELECT id, name, title FROM files")}
    segs = db.q("SELECT * FROM segments WHERE file_id=? ORDER BY start", (file_id,))

    moments_res = []
    text_scores = []
    picture_scores = []
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

        if kind == "moving_video":
            moving_count += 1
            hamming = dist_motion
        elif kind == "text":
            if not matched_kf:
                missing_count = original_count
                missing_words = cleaned_words[:15]
                text_scores.append(0.0)
            else:
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
                                if SequenceMatcher(None, w, sub).ratio() >= 0.90:
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
            if not matched_kf or not matched_kf.get("object_hash"):
                hamming = 64
                picture_scores.append(0.0)
            else:
                im_path = object_path(matched_kf["object_hash"])
                if im_path.exists():
                    im_kept = Image.open(im_path)
                    g_kept = np.asarray(im_kept.resize((320, h320), Image.BILINEAR).convert("L"), dtype=np.uint8)
                    ph1 = phash_img(Image.fromarray(g1_m))
                    ph2 = phash_img(Image.fromarray((g_kept * mask).astype(np.uint8)))
                    dist_phash = bin(int(ph1, 16) ^ int(ph2, 16)).count("1")
                else:
                    dist_phash = 64

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
            "kept_slide_object": kept_obj,
            "kept_time_range": kept_time_range,
            "linked_deck": linked_deck,
            "spoken_text": spoken_text[:140],
        })

    # STEP 4: Store per video in recordings.retention
    text_kept_pct = round(sum(text_scores) / len(text_scores), 3) if text_scores else None
    pictures_kept_pct = round(sum(picture_scores) / len(picture_scores), 3) if picture_scores else None
    moving_video_pct = round(moving_count / len(moments_res), 3) if moments_res else None

    ret_orig["text_kept_pct"] = text_kept_pct
    ret_orig["text_moments"] = len(text_scores)
    ret_orig["pictures_kept_pct"] = pictures_kept_pct
    ret_orig["picture_moments"] = len(picture_scores)
    ret_orig["moving_video_pct"] = moving_video_pct
    ret_orig["screen_text_retained"] = text_kept_pct if text_kept_pct is not None else pictures_kept_pct
    ret_orig["frames_checked"] = len(moments_res)
    ret_orig["moments"] = moments_res
    ret_orig["ignored_words"] = ignored_words
    ret_orig["main_speakers"] = main_count

    with db.tx() as conn:
        conn.execute("UPDATE recordings SET retention=? WHERE file_id=?", (json.dumps(ret_orig), file_id))

    report = {
        "file_id": file_id,
        "name": f["name"],
        "old_score": old_score,
        "text_kept_pct": text_kept_pct,
        "text_moments": len(text_scores),
        "pictures_kept_pct": pictures_kept_pct,
        "picture_moments": len(picture_scores),
        "moving_video_pct": moving_video_pct,
        "moving_moments": moving_count,
        "moments": moments_res,
    }
    return report


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
        t_str = f"{rep['text_kept_pct']*100:.1f}%" if rep['text_kept_pct'] is not None else "N/A"
        p_str = f"{rep['pictures_kept_pct']*100:.1f}%" if rep['pictures_kept_pct'] is not None else "N/A"
        m_str = f"{rep['moving_video_pct']*100:.1f}%" if rep['moving_video_pct'] is not None else "0.0%"
        print(f"  Old Retention Score : {old_str}")
        print(f"  Slide Text Kept     : {t_str} ({rep['text_moments']} moments)")
        print(f"  Pictures Kept       : {p_str} ({rep['picture_moments']} moments)")
        print(f"  Moving Video        : {m_str} ({rep['moving_moments']} moments)")
        print(f"  Moment Breakdown:")
        print(f"    {'Time':>8} | {'Kind':<13} | {'Original':>8} | {'Found':>6} | {'Hamming':>7} | {'Time Range':<15}")
        print(f"    {'-'*8}-+-{'-'*13}-+-{'-'*8}-+-{'-'*6}-+-{'-'*7}-+-{'-'*15}")
        for m in rep["moments"]:
            ham_str = str(m["hamming"]) if m["hamming"] is not None else "-"
            range_str = m["kept_time_range"] or "-"
            print(f"    {fmt_ts(m['t']):>8} | {m['kind']:<13} | {m['original_count']:>8} | {m['found_count']:>6} | {ham_str:>7} | {range_str:<15}")

    print("\n[OK] All verification checks successfully computed and saved to database.")


if __name__ == "__main__":
    main()
