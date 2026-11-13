"""Generate a deterministic, realistic Ericsson-style synthetic dataset with ground truth.

Run: .venv\\Scripts\\python.exe scripts\\make_synthetic.py

Produces under sample_data/:
  SharePoint_Training/
    - 5G_RAN_Energy_Efficiency_RevA.pdf   (12 slides, doc 1/1551-LZA 701 6001 Uen, Rev A)
    - 5G_RAN_Energy_Efficiency_RevB.pdf   (12 slides, Rev B: 2 modified, 1 added, 1 removed vs Rev A)
    - Cloud_Native_Core_Overview.pdf      (10 slides, doc 2/1551-AXB 250 1234 Uen, shares 4 slides w/ Energy)
    - Event_Recording_2026-10-14.mp4      (~4.5 min Teams-like video w/ webcam corner, build animation,
                                           revisited slide, 15s camera demo segment, mouse cursor, 2 speakers)
    - Team_Sync_2026-11-02.mp4            (~1.5 min Teams recording + Team_Sync_2026-11-02.vtt speaker tags)
    - Team_Sync_2026-11-02.vtt
  EricssonPlay/
    - Event_Recording_2026-10-14_720p.mp4 (re-encoded 854x480 + first 5s trimmed -> perceptual duplicate)
  OneDrive_Anna_Svensson/ (leaver)
    - 5G_RAN_Energy_Efficiency_RevB (1).pdf       -> safe_delete (exact SHA-256 copy)
    - Cloud_Native_Core_Overview - Copy.pdf       -> safe_delete (re-saved: different SHA-256, identical content)
    - Customer_Workshop_Draft.pdf                 -> partial (3 shared slides + 5 unique slides)
    - Personal_Notes_Q3.pdf                       -> unique (4 unique pages)
    - Event_Recording_2026-10-14.mp4              -> safe_delete (exact SHA-256 copy)
  OneDrive_Erik_Berg/
    - 5G_RAN_Energy_Efficiency_RevA.pdf           -> exact copy
    - Copy of Cloud_Native_Core_Overview.pdf      -> exact copy
  _ground_truth.json
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np
import pymupdf as fitz
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sample_data"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
RNG = np.random.default_rng(20261113)

NAVY = (0 / 255, 37 / 255, 97 / 255)
BLUE = (0 / 255, 130 / 255, 240 / 255)
SLATE = (30 / 255, 41 / 255, 59 / 255)
MUTED = (100 / 255, 116 / 255, 139 / 255)
LIGHT = (241 / 255, 245 / 255, 249 / 255)
ACCENT = (16 / 255, 185 / 255, 129 / 255)
AMBER = (245 / 255, 158 / 255, 11 / 255)


# --------------------------------------------------------------------------- Slide library
# Each slide dict has: key, title, bullets, diagram (optional spec)
SLIDES = {
    "ee_01": {
        "title": "5G RAN Energy Efficiency & Sleep Modes",
        "bullets": [
            "Radio Access Network accounts for ~73% of mobile operator energy consumption",
            "Target: cut baseband & radio power 35% during low-traffic night hours",
            "Core levers: Micro-Sleep TX, MIMO Cell DTX, Deep Sleep & Carrier Shutdown",
            "Zero degradation on user throughput or handover KPIs",
        ],
        "diagram": ("bars", [("Radio Unit", 73), ("Baseband", 15), ("Site Cooling", 8), ("Transport", 4)], "Site Power Breakdown (%)"),
    },
    "ee_02": {
        "title": "Traffic Profile vs Power Consumption",
        "bullets": [
            "Peak busy hour uses 100% of carriers and massive MIMO layers",
            "00:00–06:00 carries under 8% of daily data volume",
            "Static energy baseline wastes power when radios transmit empty control slots",
            "Dynamic cell orchestration adapts capacity every 15 minutes",
        ],
        "diagram": ("bars", [("00-06h", 12), ("06-12h", 62), ("12-18h", 88), ("18-24h", 95)], "Traffic Load by Time Window (%)"),
    },
    "ee_03": {
        "title": "Micro-Sleep TX & Symbol-Level Shutdown",
        "bullets": [
            "Deactivates power amplifier between OFDM symbols with no active traffic",
            "Sub-millisecond wake-up preserves 5G ultra-reliable low-latency SLA",
            "Works automatically across TDD and FDD NR bands",
            "Measured field gain: 12% to 18% radio unit energy reduction",
        ],
        "diagram": ("flow", ["Traffic Buffer Empty", "Gate PA Bias (<1 ms)", "Save 15% Power", "Instant Wake on PDCCH"], "Micro-Sleep Cycle"),
    },
    "ee_04": {
        "title": "AI-Driven Cell Sleep Orchestration",
        "bullets": [
            "Reinforcement learning agent predicts PRB utilization 15 min ahead",
            "Moves residual UEs smoothly onto anchor coverage carrier",
            "Switches secondary 3.5 GHz Massive MIMO layers into Deep Sleep",
            "Safety guardrails auto-abort sleep if call-drop rate shifts >0.05%",
        ],
        "diagram": ("flow", ["Telemetry Stream", "LSTM Load Forecast", "Policy Optimizer", "RAN Sleep Action"], "Closed-Loop AI Control"),
    },
    "ee_05": {
        "title": "Field Trial Results — Nordic Cluster",
        "bullets": [
            "120 urban & suburban macro sites monitored over 8 weeks",
            "Average daily energy reduction: 29.4% across NR + LTE layers",
            "Nighttime energy drop reached 41.2% with Deep Sleep enabled",
            "Accessibility and retainability KPIs remained flat at 99.94%",
        ],
        "diagram": ("bars", [("Baseline", 100), ("Micro-Sleep", 86), ("+Carrier Off", 74), ("+AI DeepSleep", 59)], "Night Power Index (Baseline=100)"),
    },
    "ee_05_revB": {
        "title": "Field Trial Results — Nordic Cluster",
        "bullets": [
            "180 urban & suburban macro sites monitored over 12 weeks",
            "Average daily energy reduction: 32.8% across NR + LTE layers",
            "Nighttime energy drop reached 44.5% with Deep Sleep v2 enabled",
            "Accessibility and retainability KPIs remained flat at 99.96%",
        ],
        "diagram": ("bars", [("Baseline", 100), ("Micro-Sleep", 84), ("+Carrier Off", 70), ("+AI DeepSleep", 55)], "Night Power Index (Baseline=100)"),
    },
    "ee_06": {
        "title": "Thermal & Cooling Optimization",
        "bullets": [
            "Passive free-cooling louvres replace compressor runs below 18 C",
            "Baseband fan curves linked to actual ASIC junction telemetry",
            "Reduces auxiliary enclosure load by 220 kWh per site annually",
        ],
        "diagram": None,
    },
    "ee_07": {
        "title": "Solar & Hybrid Site Integration",
        "bullets": [
            "Lithium-iron-phosphate batteries absorb daytime PV surplus",
            "Grid peak-shaving lowers tariff spend during evening busy hour",
            "Remote BMS telemetry streams to Ericsson Network Manager",
        ],
        "diagram": None,
    },
    "ee_08": {
        "title": "Hardware Modernization: Silicon & GaN",
        "bullets": [
            "Ericsson Silicon baseband doubles compute per watt vs Gen-3 boards",
            "Gallium Nitride (GaN) power amplifiers lift wideband efficiency by 9%",
            "Lighter 12 kg radio units lower tower structural load and install time",
        ],
        "diagram": ("bars", [("Gen-3 LDMOS", 38), ("Gen-4 GaN", 47), ("NextGen GaN", 54)], "PA Efficiency (%)"),
    },
    "ee_08_revB": {
        "title": "Hardware Modernization: Silicon & GaN",
        "bullets": [
            "Ericsson Silicon baseband doubles compute per watt vs Gen-3 boards",
            "Gallium Nitride (GaN) power amplifiers lift wideband efficiency by 11%",
            "Lighter 11.5 kg radio units lower tower load and cut embodied carbon",
        ],
        "diagram": ("bars", [("Gen-3 LDMOS", 38), ("Gen-4 GaN", 49), ("NextGen GaN", 57)], "PA Efficiency (%)"),
    },
    "ee_09_onlyA": {
        "title": "Legacy 3G Decommissioning Checklist",
        "bullets": [
            "Refarm remaining 2100 MHz spectrum from UMTS to 5G DSS/NR",
            "Decommission legacy RNC cabinets to reclaim 1.4 kW per hub",
            "Archive legacy performance counters before hardware power-off",
        ],
        "diagram": None,
    },
    "ee_13_newB": {
        "title": "AI Energy Digital Twin & Carbon Ledger",
        "bullets": [
            "Per-cell kWh and Scope-2 CO2 tracked hourly across all clusters",
            "What-if simulation forecasts annual savings before cluster rollout",
            "Verified ESG export feeds corporate sustainability reporting",
        ],
        "diagram": ("flow", ["Site Smart Meter", "Energy Digital Twin", "Cluster Simulator", "ESG Carbon Ledger"], "Digital Twin Pipeline"),
    },
    # ---- Shared across Energy & Cloud-Native decks (4 slides)
    "shared_01": {
        "title": "Cloud-Native Telemetry & Observability",
        "bullets": [
            "OpenTelemetry collectors ingest 450k metrics/sec per region",
            "Prometheus + Thanos long-term retention compressed via Parquet",
            "Unified trace ID links RAN alarms to Core session events",
        ],
        "diagram": ("flow", ["RAN / Core Pods", "OTel Collector", "Thanos TSDB", "AIOps Dashboard"], "Observability Stack"),
    },
    "shared_02": {
        "title": "Kubernetes Platform Architecture (CNIS)",
        "bullets": [
            "Bare-metal worker nodes tuned with SR-IOV and DPDK for UPF line rate",
            "Automated GitOps lifecycle via ArgoCD across 14 edge data centers",
            "Zero-downtime rolling upgrades under 8 minutes per cluster",
        ],
        "diagram": None,
    },
    "shared_03": {
        "title": "Zero-Trust Service Mesh Security",
        "bullets": [
            "Mutual TLS enforced between every 5G SBA network function",
            "Short-lived SPIFFE/SPIRE workload identities rotated every 4 hours",
            "Automated policy compliance checks block unencrypted east-west traffic",
        ],
        "diagram": None,
    },
    "shared_04": {
        "title": "Sustainability KPIs & 2030 Roadmap",
        "bullets": [
            "Commit to Net Zero across Ericsson operations by 2030",
            "Break the energy curve: double mobile traffic without raising power",
            "Standardize energy KPIs across RAN, Core, Cloud and IT Storage",
        ],
        "diagram": ("bars", [("2022", 100), ("2024", 78), ("2026", 61), ("2030 Target", 35)], "Relative Energy Intensity"),
    },
    # ---- Cloud-Native Core exclusive slides (6 slides -> total 10 with 4 shared)
    "cn_01": {
        "title": "5G Cloud-Native Core (5GC) Overview",
        "bullets": [
            "Service-Based Architecture decouples control plane (AMF/SMF) from UPF",
            "Stateless microservices scale horizontally on demand",
            "Supports network slicing for enterprise private 5G and URLLC",
        ],
        "diagram": ("flow", ["UE / gNB", "AMF / AUSF", "SMF Policy", "User Plane UPF"], "5GC Control & User Plane"),
    },
    "cn_02": {
        "title": "User Plane Function (UPF) Edge Breakout",
        "bullets": [
            "Local breakout keeps industrial IoT traffic inside factory campus",
            "Achieves sub-5 ms round-trip latency for autonomous AGVs",
            "Hardware offload via SmartNIC drops CPU cores per Gbps by 40%",
        ],
        "diagram": None,
    },
    "cn_03": {
        "title": "Automated CI/CD & Canary Rollouts",
        "bullets": [
            "Every CNF helm chart signed and scanned for CVEs before deploy",
            "Canary traffic shifts 5% -> 25% -> 100% gated on error budgets",
            "Instant automated rollback within 30 seconds on latency spike",
        ],
        "diagram": None,
    },
    "cn_04": {
        "title": "Geo-Redundant Session Resilience",
        "bullets": [
            "Redis-backed session store replicates active PDU contexts across sites",
            "N+2 regional failover handles full data-center maintenance",
            "Tested at 2.4 million concurrent subscribers without session drop",
        ],
        "diagram": None,
    },
    "cn_05": {
        "title": "Network Slicing SLA Assurance",
        "bullets": [
            "Closed-loop assurance monitors slice latency, jitter and packet loss",
            "Dynamic QoS enforcement protects mission-critical rail & port slices",
            "Exposes CAMARA APIs to enterprise application developers",
        ],
        "diagram": None,
    },
    "cn_06": {
        "title": "Data Storage & Knowledge Lifecycle in IT",
        "bullets": [
            "Unstructured SharePoint/OneDrive recordings grow 45% year-over-year",
            "Distilling video to text + keyframes frees 99% storage without data loss",
            "Single-source-of-truth slide hashing eliminates cross-drive duplicates",
        ],
        "diagram": None,
    },
    # ---- Customer Workshop Draft exclusive slides (5 unique + 3 shared with Cloud = 8)
    "ws_01": {
        "title": "Nordic Telecom Customer Workshop Agenda",
        "bullets": [
            "09:00 Architecture alignment on 5GC edge rollout",
            "10:30 Live latency benchmark on factory private 5G slice",
            "13:00 Joint energy efficiency & TCO modeling session",
        ],
        "diagram": None,
    },
    "ws_02": {
        "title": "Customer Deployment Timeline Q1–Q4",
        "bullets": [
            "Q1: Lab validation of UPF SmartNIC offload in Stockholm",
            "Q2: Pilot launch across 25 port logistics cranes in Gothenburg",
            "Q4: Full national production cutover across 4 regions",
        ],
        "diagram": None,
    },
    "ws_03": {
        "title": "Site Readiness & Fiber Backhaul Check",
        "bullets": [
            "Dual 100 GbE redundant optical rings verified at all edge PoPs",
            "PTP Grandmaster clock sync accuracy within +/- 150 nanoseconds",
            "Rack power budget confirmed at 14 kW per cabinet",
        ],
        "diagram": None,
    },
    "ws_04": {
        "title": "Joint Risk Register & Mitigation Actions",
        "bullets": [
            "Risk 1: Legacy firewall MTU fragmentation -> enable jumbo frames",
            "Risk 2: Spectrum coordination near border -> align with regulator",
            "Risk 3: Operator NOC runbook training -> schedule 3 workshops",
        ],
        "diagram": None,
    },
    "ws_05": {
        "title": "Workshop Next Steps & Action Owners",
        "bullets": [
            "Finalize BoM sign-off with procurement by Friday",
            "Grant Ericsson engineers VPN bastion access to staging cluster",
            "Weekly sync every Tuesday 10:00 CET with transcript archive",
        ],
        "diagram": None,
    },
    # ---- Personal Notes Q3 (unique)
    "pn_01": {
        "title": "Anna Svensson — Q3 Architecture Scratchpad",
        "bullets": [
            "Investigate WebAssembly filters for custom OTel log scrubbing",
            "Compare eBPF Cilium CNI throughput against Multus SR-IOV",
            "Draft mentoring plan for incoming autumn graduate engineers",
        ],
        "diagram": None,
    },
    "pn_02": {
        "title": "Performance Review Goals — Autumn Cycle",
        "bullets": [
            "Lead cross-site cloud-native observability guild",
            "Publish internal playbook on zero-downtime SMF upgrades",
            "Speak at Ericsson Karlskrona tech summit in November",
        ],
        "diagram": None,
    },
    "pn_03": {
        "title": "Karlskrona Hackathon Ideas & Notes",
        "bullets": [
            "How to store meeting knowledge at 1% of the MP4 size",
            "Combine Whisper timestamps with slide perceptual hashes",
            "Make employee offboarding safe with content-addressable checks",
        ],
        "diagram": None,
    },
    "pn_04": {
        "title": "Reading List & Internal RFC Links",
        "bullets": [
            "RFC-2026-04: Standardized Parquet schemas for RAN telemetry",
            "RFC-2026-09: Automated retention policy for Teams recordings",
            "Paper review: Vector + BM25 hybrid retrieval on telecom docs",
        ],
        "diagram": None,
    },
    # ---- Team Sync slides
    "ts_01": {
        "title": "Weekly Platform Sync — Sprint 42",
        "bullets": [
            "Storage audit: SharePoint training site hit 94% quota",
            "Need automated video distillation before retention purge triggers",
            "Demo planned for Friday stakeholder review",
        ],
        "diagram": None,
    },
    "ts_02": {
        "title": "Teams Transcript Integration Check",
        "bullets": [
            "New Teams meetings include WebVTT with speaker identity tags",
            "Older MP4 archive lacks transcripts and needs offline Whisper STT",
            "Both paths must link spoken sentences to the visible slide frame",
        ],
        "diagram": None,
    },
    "ts_03": {
        "title": "Action Items & Ownership",
        "bullets": [
            "Anna: export sample VTT + test slide matching accuracy",
            "Erik: validate duplicate detection across OneDrive copies",
            "Team: verify zero-cost offline execution before hackathon",
        ],
        "diagram": None,
    },
}


def _draw_slide(page: fitz.Page, slide: dict, footer: str, visible_bullets: int | None = None) -> None:
    W, H = 960, 540
    # Background
    page.draw_rect(fitz.Rect(0, 0, W, H), color=None, fill=(1, 1, 1))
    # Top navy accent bar
    page.draw_rect(fitz.Rect(0, 0, W, 12), color=None, fill=NAVY)
    # Wordmark
    page.insert_text((W - 140, 44), "ERICSSON", fontsize=14, fontname="hebo", color=NAVY)
    # Title
    page.insert_textbox(fitz.Rect(48, 28, W - 165, 86), slide["title"],
                        fontsize=24, fontname="hebo", color=NAVY)
    # Thin blue divider
    page.draw_line((48, 92), (W - 48, 92), color=BLUE, width=2.2)

    bullets = slide["bullets"]
    if visible_bullets is not None:
        bullets = bullets[:visible_bullets]

    has_diag = slide.get("diagram") is not None
    text_right = 540 if has_diag else (W - 54)
    y = 118
    for b in bullets:
        page.draw_circle((60, y + 8), 4.2, color=None, fill=BLUE)
        rect = fitz.Rect(76, y - 2, text_right, y + 84)
        page.insert_textbox(rect, b, fontsize=16, fontname="helv", color=SLATE, lineheight=1.28)
        y += 84 if has_diag else 76

    if has_diag and (visible_bullets is None or visible_bullets >= len(slide["bullets"])):
        kind, items, cap = slide["diagram"]
        box = fitz.Rect(565, 118, W - 48, 455)
        page.draw_rect(box, color=(203 / 255, 213 / 255, 225 / 255), fill=LIGHT, width=1.0)
        page.insert_textbox(fitz.Rect(578, 128, W - 60, 158), cap, fontsize=13, fontname="hebo", color=NAVY)
        if kind == "bars":
            max_v = max(v for _, v in items) or 1
            bx0, by0, bw = 590, 410, 62
            gap = 20
            for idx, (lbl, val) in enumerate(items):
                x = bx0 + idx * (bw + gap)
                bh = int(205 * val / max_v)
                col = BLUE if idx % 2 == 0 else ACCENT
                page.draw_rect(fitz.Rect(x, by0 - bh, x + bw, by0), color=None, fill=col)
                page.insert_textbox(fitz.Rect(x - 4, by0 - bh - 22, x + bw + 4, by0 - bh),
                                    str(val), fontsize=12, fontname="hebo", color=SLATE, align=1)
                page.insert_textbox(fitz.Rect(x - 8, by0 + 6, x + bw + 8, by0 + 40),
                                    lbl, fontsize=10, fontname="helv", color=MUTED, align=1)
        elif kind == "flow":
            fx, fy, fw, fh = 605, 172, 270, 48
            for idx, step in enumerate(items):
                y0 = fy + idx * 70
                col = NAVY if idx in (0, len(items) - 1) else BLUE
                page.draw_rect(fitz.Rect(fx, y0, fx + fw, y0 + fh), color=None, fill=col)
                page.insert_textbox(fitz.Rect(fx + 8, y0 + 13, fx + fw - 8, y0 + fh),
                                    step, fontsize=13, fontname="hebo", color=(1, 1, 1), align=1)
                if idx < len(items) - 1:
                    mx = fx + fw / 2
                    page.draw_line((mx, y0 + fh), (mx, y0 + 68), color=SLATE, width=2)
                    p1 = (mx, y0 + 70)
                    page.draw_polyline([(mx - 5, y0 + 61), (mx + 5, y0 + 61), p1, (mx - 5, y0 + 61)],
                                       color=SLATE, fill=SLATE)

    # Footer
    page.draw_line((48, 492), (W - 48, 492), color=(226 / 255, 232 / 255, 240 / 255), width=1.0)
    page.insert_text((48, 514), footer, fontsize=10, fontname="helv", color=MUTED)


def make_pdf(path: Path, slide_keys: list[str], doc_no: str, rev: str, title: str,
             author: str, date_str: str, company_tag: str = "Ericsson Internal",
             deflate_garbage: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    n = len(slide_keys)
    for i, sk in enumerate(slide_keys, 1):
        page = doc.new_page(width=960, height=540)
        footer = f"{company_tag}  |  {doc_no}  Rev {rev}  |  {date_str}  |  Slide {i} / {n}"
        _draw_slide(page, SLIDES[sk], footer)
    doc.set_metadata({
        "title": title,
        "author": author,
        "subject": f"Document {doc_no} Revision {rev}",
        "keywords": f"{doc_no}, Rev {rev}, Ericsson",
        "creator": "Distill Synthetic Deck Generator",
        "creationDate": f"D:{date_str.replace('-', '')}090000Z",
        "modDate": f"D:{date_str.replace('-', '')}120000Z",
    })
    doc.save(str(path), garbage=deflate_garbage, deflate=True)
    doc.close()


def render_slide_states(slide_key: str, footer: str, width: int = 1280, height: int = 720,
                        build_steps: bool = False) -> list[np.ndarray]:
    """Render slide (or progressive bullet builds) to BGR numpy arrays for OpenCV video writing."""
    s = SLIDES[slide_key]
    counts = list(range(1, len(s["bullets"]) + 1)) if build_steps else [len(s["bullets"])]
    imgs = []
    for k in counts:
        doc = fitz.open()
        page = doc.new_page(width=960, height=540)
        _draw_slide(page, s, footer, visible_bullets=k)
        pix = page.get_pixmap(matrix=fitz.Matrix(width / 960, height / 540), alpha=False)
        rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        imgs.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        doc.close()
    return imgs


# --------------------------------------------------------------------------- TTS via System.Speech
def synth_utterances(utterances: list[dict], cache_dir: Path) -> list[dict]:
    """Synthesise each utterance with Windows System.Speech + ffmpeg pitch-shift for Speaker B.
    Returns list with added keys: wav_path, duration.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    ps_lines = [
        "Add-Type -AssemblyName System.Speech",
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)",
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
    ]
    raw_wavs = []
    for i, u in enumerate(utterances):
        raw_p = cache_dir / f"raw_{i:03d}.wav"
        safe = u["text"].replace("'", "''")
        rate = 0 if u["speaker"] == "Speaker A" else -1
        ps_lines.append(f"$s.Rate = {rate}")
        ps_lines.append(f"$s.SetOutputToWaveFile('{str(raw_p)}')")
        ps_lines.append(f"$s.Speak('{safe}')")
        raw_wavs.append(raw_p)
    ps_lines.append("$s.Dispose()")
    ps_path = cache_dir / "tts_batch.ps1"
    ps_path.write_text("\n".join(ps_lines), encoding="utf-8")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_path)],
                   check=True, capture_output=True, timeout=240)

    out = []
    for i, (u, raw_p) in enumerate(zip(utterances, raw_wavs)):
        final_p = cache_dir / f"utt_{i:03d}.wav"
        if u["speaker"] != "Speaker A":
            # Lower pitch by 18% and keep speed natural -> clearly distinct speaker voice!
            subprocess.run([
                FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_p),
                "-af", "asetrate=22050*0.82,aresample=22050,atempo=1.18", str(final_p)
            ], check=True, capture_output=True)
        else:
            shutil.copyfile(raw_p, final_p)
        data, sr = sf.read(final_p, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        out.append({**u, "wav_path": final_p, "audio": data, "sr": sr, "duration": len(data) / sr})
    return out


# --------------------------------------------------------------------------- Video synthesis
def _camera_frame(t: float, w: int = 1280, h: int = 720, label: str = "Live Lab Hardware Demo") -> np.ndarray:
    """Moving pseudo-camera frame (gradient + moving wave + telemetry box) to test non-slide detection."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    x = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    r = (40 + 40 * np.sin(2 * np.pi * (x * 1.5 + t * 0.4))).astype(np.uint8)
    g = (65 + 45 * np.cos(2 * np.pi * (y * 1.2 - t * 0.3))).astype(np.uint8)
    b = (110 + 50 * np.sin(2 * np.pi * (x + y + t * 0.25))).astype(np.uint8)
    frame[:, :, 0] = b
    frame[:, :, 1] = g
    frame[:, :, 2] = r
    cx = int(w * (0.5 + 0.28 * np.sin(t * 1.3)))
    cy = int(h * (0.5 + 0.20 * np.cos(t * 0.9)))
    cv2.circle(frame, (cx, cy), 85, (240, 180, 60), -1)
    cv2.circle(frame, (w - cx, h - cy), 55, (70, 220, 140), -1)
    cv2.putText(frame, label, (60, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.putText(frame, f"t = {t:05.1f} s  [Camera Feed]", (60, 130),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (220, 235, 255), 2, cv2.LINE_AA)
    return frame


def _overlay_webcam_and_cursor(base: np.ndarray, t: float, cursor_t_range: tuple[float, float] | None) -> np.ndarray:
    """Add a constantly moving webcam tile in bottom-right corner + optional mouse movement."""
    img = base.copy()
    h, w = img.shape[:2]
    # Webcam tile (240x135) at bottom-right
    ww, wh = 240, 135
    x0, y0 = w - ww - 18, h - wh - 18
    tile = np.zeros((wh, ww, 3), dtype=np.uint8)
    tile[:] = (45, 32, 24)
    # Moving head/shoulders + animated waveform bar so pixels continuously change
    dx = int(12 * np.sin(t * 1.7))
    dy = int(5 * np.cos(t * 2.1))
    cv2.ellipse(tile, (ww // 2 + dx, wh + 10 + dy), (58, 52), 0, 180, 360, (120, 90, 70), -1)
    cv2.circle(tile, (ww // 2 + dx, 54 + dy), 26, (185, 155, 135), -1)
    # Animated audio bar + timestamp
    bar = int(20 + 60 * abs(np.sin(t * 4.5)))
    cv2.rectangle(tile, (12, wh - 16), (12 + bar, wh - 8), (60, 220, 130), -1)
    cv2.putText(tile, "Presenter Cam", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (235, 245, 255), 1, cv2.LINE_AA)
    cv2.rectangle(img, (x0 - 2, y0 - 2), (x0 + ww + 2, y0 + wh + 2), (0, 130, 240), 2)
    img[y0:y0 + wh, x0:x0 + ww] = tile

    if cursor_t_range and cursor_t_range[0] <= t <= cursor_t_range[1]:
        u = (t - cursor_t_range[0]) / max(0.1, cursor_t_range[1] - cursor_t_range[0])
        mx = int(260 + 540 * u)
        my = int(310 + 40 * np.sin(u * np.pi * 2))
        pts = np.array([[mx, my], [mx, my + 22], [mx + 6, my + 17], [mx + 14, my + 20]], np.int32)
        cv2.fillPoly(img, [pts], (255, 255, 255))
        cv2.polylines(img, [pts], True, (0, 0, 0), 2)
    return img


def build_video(out_mp4: Path, timeline_spec: list[dict], revB_deck_name: str, footer_fmt: str,
                cache_dir: Path, fps: int = 12, target_bitrate: str = "1100k") -> dict:
    """Build video from timeline_spec items:
       {kind: 'slide'|'camera', slide_key, page_no, build (bool), utterances: [{speaker, text, deictic}]}
    """
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    # Collect all utterances and synthesise in one PowerShell batch
    all_utts = []
    for item in timeline_spec:
        for u in item["utterances"]:
            all_utts.append(u)
    synth = synth_utterances(all_utts, cache_dir)
    sr = synth[0]["sr"] if synth else 22050

    # Assign exact intervals based on audio durations + small pauses
    t_cur = 0.0
    u_idx = 0
    intervals = []
    speaker_turns = []
    deictic_gt = []
    audio_chunks = []

    def add_silence(sec: float):
        audio_chunks.append(np.zeros(int(round(sec * sr)), dtype=np.float32))

    # 1s intro pause
    add_silence(1.0)
    t_cur += 1.0

    for item in timeline_spec:
        seg_start = t_cur
        # 0.5s pause at slide entry
        add_silence(0.5)
        t_cur += 0.5
        for u in item["utterances"]:
            su = synth[u_idx]
            u_idx += 1
            u_start = t_cur
            audio_chunks.append(su["audio"])
            u_end = u_start + su["duration"]
            speaker_turns.append({
                "start": round(u_start, 3),
                "end": round(u_end, 3),
                "speaker": su.get("label", su["speaker"]),
                "text": su["text"],
            })
            if su.get("deictic"):
                deictic_gt.append({
                    "phrase": su["deictic"],
                    "start": round(u_start, 3),
                    "end": round(u_end, 3),
                    "deck_file": revB_deck_name if item["kind"] == "slide" else None,
                    "page_no": item.get("page_no"),
                })
            t_cur = u_end
            add_silence(0.45)
            t_cur += 0.45
        # ensure camera or slide stays at least min_dur if needed
        min_dur = item.get("min_dur", 0.0)
        if t_cur - seg_start < min_dur:
            pad = min_dur - (t_cur - seg_start)
            add_silence(pad)
            t_cur += pad
        add_silence(0.4)
        t_cur += 0.4
        intervals.append({
            "start": round(seg_start, 3),
            "end": round(t_cur, 3),
            "kind": item["kind"],
            "slide_key": item.get("slide_key"),
            "deck_file": revB_deck_name if item["kind"] == "slide" else None,
            "page_no": item.get("page_no"),
            "build": bool(item.get("build")),
            "revisit": bool(item.get("revisit")),
        })

    full_audio = np.concatenate(audio_chunks)
    # tiny low-level room ambience so silence isn't mathematically sterile
    full_audio = np.clip(full_audio + RNG.normal(0, 0.0008, len(full_audio)).astype(np.float32), -1.0, 1.0)
    wav_out = cache_dir / "full_mix.wav"
    sf.write(wav_out, full_audio, sr)
    total_dur = len(full_audio) / sr

    # Pre-render slide states
    slide_cache: dict[tuple[str, int, bool], list[np.ndarray]] = {}
    for iv in intervals:
        if iv["kind"] == "slide":
            key = (iv["slide_key"], iv["page_no"], iv["build"])
            if key not in slide_cache:
                footer = footer_fmt.format(page=iv["page_no"])
                slide_cache[key] = render_slide_states(iv["slide_key"], footer, 1280, 720, build_steps=iv["build"])

    # Pick one interval for a subtle mouse cursor pass
    cursor_iv = next((iv for iv in intervals if iv["kind"] == "slide" and not iv["build"] and not iv["revisit"]), None)
    cursor_range = (cursor_iv["start"] + 2.0, min(cursor_iv["end"] - 1.0, cursor_iv["start"] + 6.0)) if cursor_iv else None

    # Stream raw BGR frames directly into ffmpeg H.264 + AAC muxer -> fast and clean
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1280x720", "-r", str(fps), "-i", "-",
        "-i", str(wav_out),
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", target_bitrate, "-maxrate", "1600k", "-bufsize", "3200k",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart", str(out_mp4),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n_frames = int(round(total_dur * fps))
    iv_idx = 0
    for fi in range(n_frames):
        t = fi / fps
        while iv_idx + 1 < len(intervals) and t >= intervals[iv_idx]["end"]:
            iv_idx += 1
        iv = intervals[iv_idx]
        if iv["kind"] == "camera":
            frame = _camera_frame(t)
        else:
            states = slide_cache[(iv["slide_key"], iv["page_no"], iv["build"])]
            if len(states) > 1:
                # progressively reveal bullets over the first 6 seconds of this slide
                frac = min(0.999, max(0.0, (t - iv["start"]) / 6.0))
                base = states[int(frac * len(states))]
            else:
                base = states[0]
            frame = _overlay_webcam_and_cursor(base, t, cursor_range)
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {rc}")

    return {
        "duration": round(total_dur, 2),
        "intervals": intervals,
        "speaker_turns": speaker_turns,
        "deictic": deictic_gt,
        "reference_transcript": " ".join(s["text"] for s in speaker_turns),
    }


def main() -> None:
    for sub in ("SharePoint_Training", "EricssonPlay", "OneDrive_Anna_Svensson", "OneDrive_Erik_Berg"):
        p = OUT / sub
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)
    gt_file = OUT / "_ground_truth.json"
    if gt_file.exists():
        gt_file.unlink()

    sp = OUT / "SharePoint_Training"
    ep = OUT / "EricssonPlay"
    anna = OUT / "OneDrive_Anna_Svensson"
    erik = OUT / "OneDrive_Erik_Berg"

    # 1. PDFs
    revA_keys = ["ee_01", "ee_02", "ee_03", "ee_04", "ee_05", "ee_06", "ee_07", "ee_08",
                 "ee_09_onlyA", "shared_01", "shared_02", "shared_04"]  # 12 slides
    revB_keys = ["ee_01", "ee_02", "ee_03", "ee_04", "ee_05_revB", "ee_06", "ee_07", "ee_08_revB",
                 "ee_13_newB", "shared_01", "shared_02", "shared_04"]  # 12 slides (2 mod, 1 new, 1 rem)
    cloud_keys = ["cn_01", "cn_02", "cn_03", "cn_04", "cn_05", "cn_06",
                  "shared_01", "shared_02", "shared_03", "shared_04"]  # 10 slides (4 shared w/ Energy)
    workshop_keys = ["ws_01", "shared_01", "ws_02", "shared_02", "ws_03", "shared_04", "ws_04", "ws_05"]  # 8 slides (3 shared + 5 unique)
    notes_keys = ["pn_01", "pn_02", "pn_03", "pn_04"]
    teams_keys = ["ts_01", "ts_02", "ts_03"]

    revA_pdf = sp / "5G_RAN_Energy_Efficiency_RevA.pdf"
    revB_pdf = sp / "5G_RAN_Energy_Efficiency_RevB.pdf"
    cloud_pdf = sp / "Cloud_Native_Core_Overview.pdf"
    make_pdf(revA_pdf, revA_keys, "1/1551-LZA 701 6001 Uen", "A",
             "5G RAN Energy Efficiency & Sleep Modes", "Lars Nilsson", "2026-06-15")
    make_pdf(revB_pdf, revB_keys, "1/1551-LZA 701 6001 Uen", "B",
             "5G RAN Energy Efficiency & Sleep Modes", "Lars Nilsson", "2026-09-20")
    make_pdf(cloud_pdf, cloud_keys, "2/1551-AXB 250 1234 Uen", "A",
             "Cloud-Native Core Architecture Overview", "Maya Lindholm", "2026-08-10")

    # Optional team sync deck in SharePoint? Keep Team Sync purely as MP4 + VTT, or slides inside video
    # OneDrive Erik
    shutil.copyfile(revA_pdf, erik / "5G_RAN_Energy_Efficiency_RevA.pdf")
    shutil.copyfile(cloud_pdf, erik / "Copy of Cloud_Native_Core_Overview.pdf")

    # OneDrive Anna (leaver)
    shutil.copyfile(revB_pdf, anna / "5G_RAN_Energy_Efficiency_RevB (1).pdf")
    # Re-saved Cloud PDF with altered metadata + no deflate garbage -> different SHA-256, identical content!
    make_pdf(anna / "Cloud_Native_Core_Overview - Copy.pdf", cloud_keys, "2/1551-AXB 250 1234 Uen", "A",
             "Cloud-Native Core Overview (Personal Archive)", "Anna Svensson", "2026-10-02", deflate_garbage=0)
    make_pdf(anna / "Customer_Workshop_Draft.pdf", workshop_keys, "3/1551-CWD 100 0042 Uen", "PA1",
             "Nordic Telecom Customer Workshop Draft", "Anna Svensson", "2026-10-18",
             company_tag="Draft Workshop Material")
    make_pdf(anna / "Personal_Notes_Q3.pdf", notes_keys, "LOCAL-NOTES-Q3", "1",
             "Personal Architecture Notes Q3", "Anna Svensson", "2026-10-25",
             company_tag="Personal Notes")

    # 2. Main Event Recording (SharePoint) + re-encoded EricssonPlay duplicate + Anna exact copy
    tmp_cache = Path(tempfile.mkdtemp(prefix="distill_synth_"))
    try:
        ev_timeline = [
            {
                "kind": "slide", "slide_key": "ee_01", "page_no": 1, "build": False,
                "utterances": [
                    {"speaker": "Speaker A", "text": "Welcome everyone to our 5G RAN energy efficiency briefing. Today we review how radio sleep modes reduce site power consumption by thirty five percent during low traffic hours without hurting subscriber quality."},
                    {"speaker": "Speaker A", "text": "As you see here on this slide, the radio unit accounts for roughly seventy three percent of total mobile site electricity usage."},
                ],
            },
            {
                "kind": "slide", "slide_key": "ee_02", "page_no": 2, "build": True,   # animated bullet build!
                "utterances": [
                    {"speaker": "Speaker A", "text": "Looking at the daily traffic profile, busy evening hours saturate capacity while midnight to six in the morning carries under eight percent of traffic."},
                    {"speaker": "Speaker B", "text": "Does the baseline radio hardware still draw power when almost nobody is connected at three in the morning?"},
                    {"speaker": "Speaker A", "text": "Yes, without automated sleep features, radios waste substantial power transmitting empty control signals."},
                ],
            },
            {
                "kind": "slide", "slide_key": "ee_03", "page_no": 3, "build": False,
                "utterances": [
                    {"speaker": "Speaker A", "text": "Micro sleep transmission solves this by gating the power amplifier between empty OFDM symbols with sub millisecond wake up latency."},
                ],
            },
            {
                "kind": "slide", "slide_key": "ee_04", "page_no": 4, "build": False,
                "utterances": [
                    {"speaker": "Speaker A", "text": "Our reinforcement learning controller forecasts cell utilization fifteen minutes ahead and shifts residual users onto the anchor layer before putting secondary carriers into deep sleep."},
                ],
            },
            {
                "kind": "slide", "slide_key": "ee_05_revB", "page_no": 5, "build": False,
                "utterances": [
                    {"speaker": "Speaker A", "text": "As you see here on this chart, the Nordic field trial across one hundred eighty sites achieved thirty two point eight percent daily savings and over forty four percent at night."},
                    {"speaker": "Speaker B", "text": "Did call retainability or handover success degrade at all during the deep sleep transitions?"},
                    {"speaker": "Speaker A", "text": "Not at all, retainability remained flat at ninety nine point nine six percent across all twelve weeks."},
                ],
            },
            {
                "kind": "camera", "min_dur": 15.0,   # ~15 s non-slide full-frame motion demo
                "utterances": [
                    {"speaker": "Speaker A", "text": "Switching over to the live laboratory camera feed now so you can observe real time power meter telemetry responding as traffic drops on the test rack."},
                ],
            },
            {
                "kind": "slide", "slide_key": "ee_08_revB", "page_no": 8, "build": False,
                "utterances": [
                    {"speaker": "Speaker A", "text": "Next, silicon and gallium nitride power amplifiers lift hardware efficiency by eleven percent while lowering tower weight."},
                ],
            },
            {
                "kind": "slide", "slide_key": "ee_13_newB", "page_no": 9, "build": False,
                "utterances": [
                    {"speaker": "Speaker A", "text": "Our new digital twin pipeline maps hourly kilowatt hours straight into an automated ESG carbon ledger for sustainability audits."},
                ],
            },
            {
                "kind": "slide", "slide_key": "ee_05_revB", "page_no": 5, "build": False, "revisit": True,  # revisit earlier slide!
                "utterances": [
                    {"speaker": "Speaker B", "text": "Could we jump back to the Nordic trial chart for one quick question on the carrier shutdown step?"},
                    {"speaker": "Speaker A", "text": "Sure, looking back at this chart, carrier shutdown alone takes the night power index down from eighty four to seventy before AI deep sleep reaches fifty five."},
                ],
            },
            {
                "kind": "slide", "slide_key": "shared_04", "page_no": 12, "build": False,
                "utterances": [
                    {"speaker": "Speaker A", "text": "To wrap up, breaking the energy curve is core to our twenty thirty net zero roadmap across RAN, cloud core, and IT data storage. Thank you everyone."},
                ],
            },
        ]
        # patch deictic tags cleanly
        ev_timeline[0]["utterances"][1]["deictic"] = "As you see here"
        ev_timeline[4]["utterances"][0]["deictic"] = "As you see here on this chart"
        ev_timeline[8]["utterances"][1]["deictic"] = "looking back at this chart"

        ev_mp4 = sp / "Event_Recording_2026-10-14.mp4"
        print("Generating Event_Recording_2026-10-14.mp4 ...")
        ev_gt = build_video(
            ev_mp4, ev_timeline, "5G_RAN_Energy_Efficiency_RevB.pdf",
            "Ericsson Internal  |  1/1551-LZA 701 6001 Uen  Rev B  |  2026-09-20  |  Slide {page} / 12",
            tmp_cache / "ev", fps=12, target_bitrate="1100k",
        )
        # Anna exact copy
        shutil.copyfile(ev_mp4, anna / "Event_Recording_2026-10-14.mp4")

        # EricssonPlay trimmed + downscaled re-encode
        ep_mp4 = ep / "Event_Recording_2026-10-14_720p.mp4"
        print("Generating EricssonPlay re-encoded trimmed duplicate ...")
        subprocess.run([
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-ss", "5", "-i", str(ev_mp4),
            "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "650k",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(ep_mp4),
        ], check=True)

        # 3. Team Sync recording + Microsoft Teams VTT
        ts_timeline = [
            {
                "kind": "slide", "slide_key": "ts_01", "page_no": 1, "build": False,
                "utterances": [
                    {"speaker": "Speaker A", "label": "Anna Svensson", "text": "Hi Erik, thanks for joining the sprint sync. Our SharePoint training library reached ninety four percent storage quota this morning."},
                    {"speaker": "Speaker B", "label": "Erik Berg", "text": "Yeah, administrators are already warning they may start deleting older two hour course videos."},
                ],
            },
            {
                "kind": "slide", "slide_key": "ts_02", "page_no": 2, "build": False,
                "utterances": [
                    {"speaker": "Speaker A", "label": "Anna Svensson", "text": "Look at this slide: new Teams recordings ship with WebVTT transcripts, while legacy MP4 files need offline Whisper speech recognition linked to keyframes."},
                ],
            },
            {
                "kind": "slide", "slide_key": "ts_03", "page_no": 3, "build": False,
                "utterances": [
                    {"speaker": "Speaker B", "label": "Erik Berg", "text": "I will run the duplicate slide detector across OneDrive copies and verify offboarding safety before Friday."},
                ],
            },
        ]
        ts_mp4 = sp / "Team_Sync_2026-11-02.mp4"
        print("Generating Team_Sync_2026-11-02.mp4 + VTT ...")
        ts_gt = build_video(
            ts_mp4, ts_timeline, "Team_Sync_Deck",
            "Ericsson Internal  |  SPRINT-42  |  2026-11-02  |  Slide {page} / 3",
            tmp_cache / "ts", fps=10, target_bitrate="900k",
        )
        # Write Teams-format WebVTT
        def vts(t: float) -> str:
            h, r = divmod(t, 3600)
            m, s = divmod(r, 60)
            return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"
        vtt_lines = ["WEBVTT", ""]
        for tr in ts_gt["speaker_turns"]:
            vtt_lines += [f"{vts(tr['start'])} --> {vts(tr['end'])}", f"<v {tr['speaker']}>{tr['text']}</v>", ""]
        (sp / "Team_Sync_2026-11-02.vtt").write_text("\n".join(vtt_lines), encoding="utf-8")
    finally:
        shutil.rmtree(tmp_cache, ignore_errors=True)

    # 4. Ground truth JSON
    gt = {
        "videos": {
            "SharePoint_Training/Event_Recording_2026-10-14.mp4": ev_gt,
            "SharePoint_Training/Team_Sync_2026-11-02.mp4": ts_gt,
        },
        "revisions": {
            "5G_RAN_Energy_Efficiency_RevA.pdf -> 5G_RAN_Energy_Efficiency_RevB.pdf": {
                "identical_pages_in_B": [1, 2, 3, 4, 6, 7, 10, 11, 12],
                "modified_pages_in_B": [5, 8],
                "added_pages_in_B": [9],
                "removed_pages_from_A": [9],
            }
        },
        "shared_slides": {
            "Energy_RevB <-> Cloud_Native_Core": 4,
            "Cloud_Native_Core <-> Customer_Workshop_Draft": 3,
        },
        "duplicate_groups": {
            "exact_pdf_copies": [
                ["5G_RAN_Energy_Efficiency_RevA.pdf (SharePoint)", "5G_RAN_Energy_Efficiency_RevA.pdf (Erik)"],
                ["5G_RAN_Energy_Efficiency_RevB.pdf (SharePoint)", "5G_RAN_Energy_Efficiency_RevB (1).pdf (Anna)"],
                ["Cloud_Native_Core_Overview.pdf (SharePoint)", "Copy of Cloud_Native_Core_Overview.pdf (Erik)"],
            ],
            "content_pdf_copies": [
                ["Cloud_Native_Core_Overview.pdf (SharePoint)", "Cloud_Native_Core_Overview - Copy.pdf (Anna)"]
            ],
            "video_duplicates": [
                ["Event_Recording_2026-10-14.mp4 (SharePoint)", "Event_Recording_2026-10-14.mp4 (Anna)",
                 "Event_Recording_2026-10-14_720p.mp4 (EricssonPlay)"]
            ],
        },
        "offboarding": {
            "5G_RAN_Energy_Efficiency_RevB (1).pdf": {"status": "safe_delete", "reason": "Exact SHA-256 copy in SharePoint"},
            "Cloud_Native_Core_Overview - Copy.pdf": {"status": "safe_delete", "reason": "Re-saved PDF with identical text/content in SharePoint"},
            "Event_Recording_2026-10-14.mp4": {"status": "safe_delete", "reason": "Exact SHA-256 copy in SharePoint"},
            "Customer_Workshop_Draft.pdf": {"status": "partial", "reason": "3 slides shared with Cloud deck; 5 unique slides must be rescued"},
            "Personal_Notes_Q3.pdf": {"status": "unique", "reason": "Unique 4-page deck not present anywhere else"},
        },
    }
    gt_file.write_text(json.dumps(gt, indent=2), encoding="utf-8")

    # 5. Summary & sanity verification
    total_sz = 0
    print("\n=== Synthetic dataset generated ===")
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            sz = p.stat().st_size
            total_sz += sz
            rel = p.relative_to(OUT)
            extra = ""
            if p.suffix == ".pdf":
                d = fitz.open(p)
                extra = f"({len(d)} pages)"
                d.close()
            elif p.suffix == ".mp4":
                cap = cv2.VideoCapture(str(p))
                fps = cap.get(cv2.CAP_PROP_FPS) or 1
                nf = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                extra = f"({w}x{h}, {nf/fps:.1f}s)"
            print(f"  {str(rel):60s} {sz/1e6:7.2f} MB {extra}")
    print(f"Total dataset size: {total_sz/1e6:.2f} MB")


if __name__ == "__main__":
    main()
