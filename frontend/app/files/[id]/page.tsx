"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, formatBytes } from "@/lib/api";
import { FileItem, RecordingDetail, DocumentDetail } from "@/lib/types";
import RecreationPlayer from "@/components/RecreationPlayer";
import IntegrityChecklist from "@/components/IntegrityChecklist";

export default function FileDetailPage() {
  const params = useParams();
  const router = useRouter();
  const fileId = parseInt(params.id as string, 10);

  const [file, setFile] = useState<FileItem | null>(null);
  const [recording, setRecording] = useState<RecordingDetail | null>(null);
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [activeTier, setActiveTier] = useState<string>("T3");

  useEffect(() => {
    if (isNaN(fileId)) return;

    const loadDetail = async () => {
      try {
        const files = await api.getFiles();
        const f = files.find((item) => item.id === fileId);
        if (!f) return;
        setFile(f);

        if (f.kind === "video") {
          const rec = await api.getRecording(fileId);
          setRecording(rec);
        } else {
          const doc = await api.getDocument(fileId);
          setDocument(doc);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };

    loadDetail();
  }, [fileId]);

  const copyHash = () => {
    if (!file?.sha256) return;
    navigator.clipboard.writeText(file.sha256);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="py-24 text-center font-mono text-sm text-gray-500">
        LOADING FILE REDUCTION JOURNEY...
      </div>
    );
  }

  if (!file) {
    return (
      <div className="py-24 text-center font-mono text-sm text-red-600">
        FILE NOT FOUND
      </div>
    );
  }

  // Tiers calculation
  const origSize = file.size || 0;
  let tiersJson: any = null;
  try {
    if (recording?.recording?.tiers) {
      tiersJson = typeof recording.recording.tiers === "string"
        ? JSON.parse(recording.recording.tiers)
        : recording.recording.tiers;
    }
  } catch (e) {
    console.error("Failed to parse tiers:", e);
  }
  const tiersList: { name: string; bytes: number; desc: string; saving: string }[] = [];

  if (file.kind === "video") {
    const rawBytes = origSize || 1;
    const t0Bytes = rawBytes;
    const t1Bytes = tiersJson?.tiers?.find((t: any) => t.name?.startsWith("T1"))?.bytes || Math.round(rawBytes * 0.35);
    const t2Bytes = tiersJson?.tiers?.find((t: any) => t.name?.startsWith("T2"))?.bytes || Math.round(rawBytes * 0.08);
    const t3Bytes = tiersJson?.tiers?.find((t: any) => t.name?.startsWith("T3"))?.bytes || Math.round(rawBytes * 0.02);
    const t4Bytes = tiersJson?.tiers?.find((t: any) => t.name?.startsWith("T4"))?.bytes || Math.round(rawBytes * 0.0005);

    tiersList.push(
      {
        name: "T0: Raw Video",
        bytes: t0Bytes,
        desc: "Original MP4 recording from source",
        saving: "0%",
      },
      {
        name: "T1: High-Efficiency Video",
        bytes: t1Bytes,
        desc: "Re-encoded AV1/x264 720p/1080p CRF 28",
        saving: `${Math.round((1 - t1Bytes / rawBytes) * 100)}%`,
      },
      {
        name: "T2: Audio + Slide Moments",
        bytes: t2Bytes,
        desc: "Opus audio 24kbps + perceptual keyframes",
        saving: `${Math.round((1 - t2Bytes / rawBytes) * 100)}%`,
      },
      {
        name: "T3: Lossless Text & Slide Packet",
        bytes: t3Bytes,
        desc: "WebP slide archive + timestamps + FTS5 index",
        saving: `${((1 - t3Bytes / rawBytes) * 100).toFixed(1)}%`,
      },
      {
        name: "T4: Pure Text & Prompts",
        bytes: t4Bytes,
        desc: "ASCII transcript + AI visual recreate prompts",
        saving: `${((1 - t4Bytes / rawBytes) * 100).toFixed(2)}%`,
      }
    );
  } else {
    const rawBytes = origSize || 1;
    const slideBytes = document?.slides?.reduce((acc, s) => acc + (s?.bytes || 0), 0) || rawBytes;
    const textBytes = document?.chunks?.reduce((acc, c) => acc + (c?.text?.length || 0), 0) || 5000;

    tiersList.push(
      {
        name: "T0: Original File",
        bytes: rawBytes,
        desc: `Raw ${(file.ext || "").toUpperCase()} document`,
        saving: "0%",
      },
      {
        name: "T2: Lossless WebP Slides",
        bytes: slideBytes,
        desc: "High-resolution perceptual slide renders",
        saving: `${Math.max(0, Math.round((1 - slideBytes / rawBytes) * 100))}%`,
      },
      {
        name: "T3: Deduplicated CAS Deck",
        bytes: Math.round(slideBytes * 0.7),
        desc: "Content-addressable shared slide hashes",
        saving: `${Math.max(0, Math.round((1 - (slideBytes * 0.7) / rawBytes) * 100))}%`,
      },
      {
        name: "T4: Full-Text Chunks",
        bytes: textBytes,
        desc: "Structured vector embeddings + OCR text",
        saving: `${((1 - textBytes / rawBytes) * 100).toFixed(1)}%`,
      }
    );
  }

  return (
    <div className="space-y-8">
      {/* File Header */}
      <div className="border border-[#e5e5e5] bg-white p-6">
        <div className="flex items-center space-x-2 text-xs font-mono text-gray-500 mb-2">
          <Link href="/" className="hover:text-black">
            OPTIMIZE
          </Link>
          <span>/</span>
          <span className="text-black uppercase">{file.kind}</span>
        </div>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-mono font-bold text-black">{file.name}</h1>
            <div className="flex flex-wrap items-center gap-3 mt-2 text-xs font-mono">
              <span
                className={`px-2 py-0.5 border ${
                  file.governed
                    ? "border-black bg-black text-white"
                    : "border-amber-600 text-amber-700 bg-amber-50"
                }`}
              >
                {file.source_name}
              </span>
              <span className="text-gray-500">
                RAW: <strong className="text-black">{formatBytes(file.size)}</strong>
              </span>
              <span className="text-gray-400">|</span>
              <div className="flex items-center space-x-1.5">
                <span className="text-gray-500">SHA-256:</span>
                <span className="text-black bg-gray-100 px-1.5 py-0.5">{file.sha256}</span>
                <button
                  onClick={copyHash}
                  className="px-2 py-0.5 border border-[#e5e5e5] text-gray-600 hover:border-black text-[10px]"
                >
                  {copied ? "COPIED" : "COPY"}
                </button>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <a
              href={api.rawFileUrl(file.id)}
              download={file.name}
              className="px-3 py-1.5 border border-[#e5e5e5] text-xs font-mono text-black hover:border-black"
            >
              DOWNLOAD RAW
            </a>
          </div>
        </div>
      </div>

      {/* 5 Storage Tiers Visualized */}
      <section className="space-y-3">
        <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500">
          5-Tier Storage Cascade (Selectable Retention Footprint)
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {tiersList.map((tier, idx) => (
            <div
              key={idx}
              className={`border p-3.5 flex flex-col justify-between transition-colors ${
                tier.name.startsWith(activeTier)
                  ? "border-black bg-black text-white"
                  : "border-[#e5e5e5] bg-white text-black hover:border-gray-400"
              }`}
            >
              <div>
                <div className="flex items-center justify-between text-[10px] font-mono mb-1">
                  <span className={tier.name.startsWith(activeTier) ? "text-gray-300" : "text-gray-500"}>
                    TIER {idx}
                  </span>
                  {tier.saving !== "0%" && (
                    <span className="font-bold text-green-500">-{tier.saving}</span>
                  )}
                </div>
                <div className="font-mono font-bold text-xs truncate" title={tier.name}>
                  {tier.name}
                </div>
                <div
                  className={`text-[11px] mt-1 line-clamp-2 ${
                    tier.name.startsWith(activeTier) ? "text-gray-300" : "text-gray-500"
                  }`}
                >
                  {tier.desc}
                </div>
              </div>

              <div className="mt-4 pt-2 border-t border-gray-200/40 flex items-baseline justify-between font-mono">
                <span className="text-sm font-bold">{formatBytes(tier.bytes)}</span>
                <button
                  onClick={() => setActiveTier(tier.name.substring(0, 2))}
                  className={`text-[10px] underline uppercase ${
                    tier.name.startsWith(activeTier) ? "text-gray-200" : "text-gray-600"
                  }`}
                >
                  {tier.name.startsWith(activeTier) ? "ACTIVE" : "SELECT"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Interactive Recreation Player (for Video) */}
      {file.kind === "video" && recording && (
        <RecreationPlayer
          fileId={file.id}
          duration={recording.recording?.duration || 0}
          keyframes={recording.keyframes || []}
          segments={recording.segments || []}
          hasAudio={recording.has_audio}
          recreated={Array.isArray(recording.recreated) ? recording.recreated : []}
        />
      )}

      {/* Document Slide Gallery (for PDF/PPTX) */}
      {file.kind !== "video" && document && (
        <div className="border border-[#e5e5e5] bg-white p-6 space-y-4">
          <div className="flex items-center justify-between pb-4 border-b border-[#e5e5e5]">
            <div>
              <h3 className="font-mono font-bold text-sm text-black uppercase tracking-wider">
                Extracted Slide Moments & Vector Chunks
              </h3>
              <p className="text-xs text-gray-500 mt-0.5">
                {document.slides?.length || 0} individual slide vectors indexed with pHash & FTS5 full-text.
              </p>
            </div>
            <span className="text-xs font-mono text-gray-500">
              {document.chunks?.length || 0} text chunks
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {document.slides?.map((slide) => (
              <div key={slide.id} className="border border-[#e5e5e5] p-2 bg-gray-50/50 space-y-2">
                <div className="aspect-video bg-white border border-[#e5e5e5] overflow-hidden">
                  <img
                    src={api.objectUrl(slide.object_hash || slide.content_id)}
                    alt={`Slide ${slide.page_no}`}
                    className="w-full h-full object-contain"
                  />
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="font-bold text-black">SLIDE {slide.page_no}</span>
                  <span className="text-gray-400">{formatBytes(slide.bytes)}</span>
                </div>
                <p className="text-[10px] text-gray-600 font-sans line-clamp-2">
                  {slide.text || "No text on slide"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* "Nothing Was Lost" Panel */}
      <IntegrityChecklist fileId={file.id} />
    </div>
  );
}
