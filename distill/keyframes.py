"""Keyframe extraction: turn hours of video into the handful of screens that matter.

Algorithm (CPU only, ~real-time/20 on a laptop):
1. Stream the video through ffmpeg at SAMPLE_FPS, downscaled, as raw grayscale frames.
2. Build an *activity mask*: pixels that change in a large share of frames are live video
   (webcam tiles, presenter thumbnail, mouse jitter) and are ignored for slide detection.
3. Segment the timeline where the masked difference jumps above CHANGE_THRESHOLD, both
   frame-to-frame and versus the segment's anchor (catches slow fades).
4. Drop transitions shorter than MIN_STABLE_SEC; merge consecutive segments that are the
   same slide (animation builds) and keep the LAST frame, which is the fully built slide.
5. Recognise revisits: a slide shown again later re-uses the same keyframe object, with
   several time intervals.
6. Grab each keyframe at full resolution and store it as WebP in the content-addressable store.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np
from PIL import Image

from . import config as C
from .util import ffmpeg_bin, phash_img, hamming_hex, store_image

SMALL_W, SMALL_H = 160, 90


@dataclass
class Keyframe:
    start: float
    end: float
    t_pick: float
    intervals: list = field(default_factory=list)
    image: Image.Image | None = None
    small_gray: np.ndarray | None = None
    phash: str = ""
    object_hash: str = ""
    bytes: int = 0


def _stream_gray(path: str, width: int, height: int, fps: float):
    """Yield (t, gray uint8 array) using ffmpeg; falls back to OpenCV if ffmpeg fails."""
    vf = f"fps={fps},scale={width}:{height}:flags=area,format=gray"
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-i", path,
           "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10 ** 7)
    frame_bytes = width * height
    i = 0
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield i / fps, np.frombuffer(buf, np.uint8).reshape(height, width)
            i += 1
    finally:
        proc.stdout.close()
        proc.wait()


def sample_frames(path: str, duration: float, progress: Callable[[float], None] | None = None):
    """Return (times, small_frames[N,H,W] uint8)."""
    times, frames = [], []
    for t, g in _stream_gray(path, SMALL_W, SMALL_H, C.SAMPLE_FPS):
        times.append(t)
        frames.append(g)
        if progress and duration and len(times) % 30 == 0:
            progress(min(1.0, t / duration))
    if not frames:
        raise RuntimeError("Could not decode any frames from video")
    return np.array(times), np.stack(frames)


def activity_mask(frames: np.ndarray) -> np.ndarray:
    """1.0 where pixels are 'static content' (slides), 0.0 where they are live video."""
    if len(frames) < 5:
        return np.ones(frames.shape[1:], np.float32)
    f = frames.astype(np.int16)
    changed = (np.abs(np.diff(f, axis=0)) > 12).mean(axis=0)   # share of frames where pixel changed
    live = changed > 0.15
    live = cv2.dilate(live.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    mask = (~live).astype(np.float32)
    if mask.mean() < 0.2:   # whole frame is "live" (camera-only video) -> don't mask
        mask[:] = 1.0
    return mask


def _mdiff(a: np.ndarray, b: np.ndarray, mask: np.ndarray, msum: float) -> float:
    """Fraction of static (masked) pixels whose brightness changed by >20 levels."""
    return float(((np.abs(a.astype(np.int16) - b.astype(np.int16)) > 20) * mask).sum() / msum)


def _is_build_step(prev_g: np.ndarray, cur_g: np.ndarray, mask: np.ndarray) -> bool:
    """True when cur_g keeps the same top title band and only adds content (animation build)."""
    top_rows = max(8, int(prev_g.shape[0] * 0.18))
    tm = mask[:top_rows]
    tmsum = float(tm.sum()) or 1.0
    title_diff = _mdiff(prev_g[:top_rows], cur_g[:top_rows], tm, tmsum)
    if title_diff > 0.015:
        return False
    # Ensure it's mostly additive/minor refinement rather than an unrelated slide with same header
    body_prev = prev_g[top_rows:].astype(np.int16)
    body_cur = cur_g[top_rows:].astype(np.int16)
    bm = mask[top_rows:] > 0.5
    # Pixels that differed from the background mode in prev and vanished in cur
    bg = int(np.median(body_prev[bm])) if bm.any() else 255
    had_ink = bm & (np.abs(body_prev - bg) > 25)
    if had_ink.sum() < 15:
        return True
    vanished = (had_ink & (np.abs(body_cur - bg) <= 15)).sum() / float(had_ink.sum())
    return vanished < 0.25


def segment(times: np.ndarray, frames: np.ndarray, mask: np.ndarray) -> list[tuple[int, int]]:
    """Return list of (first_idx, last_idx) for stable screens."""
    msum = float(mask.sum()) or 1.0
    thr = C.CHANGE_THRESHOLD
    segs, s0 = [], 0
    for i in range(1, len(frames)):
        d_prev = _mdiff(frames[i], frames[i - 1], mask, msum)
        d_anchor = _mdiff(frames[i], frames[s0], mask, msum)
        if d_prev > thr or d_anchor > thr * 1.5:
            segs.append((s0, i - 1))
            s0 = i
    segs.append((s0, len(frames) - 1))

    # remove short transitions (fades, scrolling), but keep sustained motion spans (>= 2*min_len)
    # as a single segment (e.g. a 15 s live hardware/camera feed) so 100% of the timeline is covered.
    step = 1.0 / C.SAMPLE_FPS
    min_len = max(1, int(round(C.MIN_STABLE_SEC / step)))
    out: list[tuple[int, int]] = []
    motion_run: list[tuple[int, int]] = []

    def flush_motion():
        if motion_run:
            a, b = motion_run[0][0], motion_run[-1][1]
            if (b - a + 1) >= min_len * 2:
                out.append((a, b))
            motion_run.clear()

    for s in segs:
        if (s[1] - s[0] + 1) >= min_len:
            flush_motion()
            out.append(s)
        else:
            motion_run.append(s)
    flush_motion()
    return out or [max(segs, key=lambda s: s[1] - s[0])]


def extract_keyframes(path: str, duration: float = 0.0, progress=None) -> tuple[list[Keyframe], dict]:
    """Full keyframe pipeline. Returns keyframes and diagnostics (fingerprint, mask share)."""
    if not duration:
        cap0 = cv2.VideoCapture(path)
        fps = cap0.get(cv2.CAP_PROP_FPS) or 25.0
        n_frames = cap0.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        duration = n_frames / fps if fps else 0.0
        cap0.release()
    times, frames = sample_frames(path, duration, (lambda p: progress(0.8 * p)) if progress else None)
    mask = activity_mask(frames)
    segs = segment(times, frames, mask)
    step = 1.0 / C.SAMPLE_FPS

    cap = cv2.VideoCapture(path)

    def grab(t: float) -> Image.Image | None:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
        ok, bgr = cap.read()
        if not ok:
            return None
        return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

    msum = float(mask.sum()) or 1.0
    kfs: list[Keyframe] = []
    for n, (a, b) in enumerate(segs):
        start, end = float(times[a]), float(times[b]) + step
        # pick a frame slightly before the end: fully built slide, before the next transition
        pick_idx = max(a, b - 1) if b - a >= 2 else b
        t_pick = float(times[pick_idx])
        cur_small = frames[pick_idx]
        img = grab(t_pick)
        if img is None:
            continue
        ph = phash_img(img)
        prev = kfs[-1] if kfs else None
        # animation build / tiny change of the same slide -> extend previous keyframe, keep later image
        if prev and prev.small_gray is not None and abs(prev.end - start) <= step * 3:
            same_pix = _mdiff(prev.small_gray, cur_small, mask, msum) <= 0.02
            if same_pix or _is_build_step(prev.small_gray, cur_small, mask):
                prev.end = end
                prev.intervals[-1][1] = end
                prev.image, prev.small_gray, prev.phash, prev.t_pick = img, cur_small, ph, t_pick
                continue
        # revisit of an earlier slide -> require both static pixel agreement & close pHash
        revisit = next(
            (k for k in kfs if k.small_gray is not None
             and _mdiff(k.small_gray, cur_small, mask, msum) <= 0.02
             and hamming_hex(k.phash, ph) <= C.SAME_SLIDE_HAMMING),
            None,
        )
        if revisit:
            revisit.intervals.append([start, end])
            continue
        kfs.append(Keyframe(start=start, end=end, t_pick=t_pick, intervals=[[start, end]],
                            image=img, small_gray=cur_small, phash=ph))
        if progress:
            progress(0.8 + 0.2 * (n + 1) / len(segs))
    cap.release()

    for k in kfs:
        k.object_hash, k.bytes = store_image(k.image, C.KEYFRAME_MAX_WIDTH, C.KEYFRAME_WEBP_QUALITY)

    # video fingerprint: one 64-bit dHash every 2 s (robust to re-encoding/resolution changes)
    from .util import dhash_gray

    every = max(1, int(round(2 * C.SAMPLE_FPS)))
    fingerprint = [format(dhash_gray(frames[i]), "016x") for i in range(0, len(frames), every)]

    diag = {
        "sampled_frames": int(len(frames)),
        "live_area_share": round(1 - float(mask.mean()), 3),
        "segments": len(segs),
        "fingerprint": fingerprint,
        "sample_times": times.tolist(),
    }
    return kfs, diag


def frame_at(path: str, t: float) -> Image.Image | None:
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
    ok, bgr = cap.read()
    cap.release()
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)) if ok else None
