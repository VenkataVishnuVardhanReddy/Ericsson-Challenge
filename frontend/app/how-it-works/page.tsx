"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PipelineInfo } from "@/lib/types";

export default function HowItWorksPage() {
  const [info, setInfo] = useState<PipelineInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getPipelineInfo()
      .then(setInfo)
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-10">
      {/* Page Header */}
      <div className="border border-[#e5e5e5] bg-white p-6">
        <span className="text-[10px] font-mono uppercase tracking-widest text-gray-500 block mb-1">
          Technical Whitepaper & Pitch Strategy
        </span>
        <h1 className="text-2xl font-mono font-bold text-black">
          Distill: Enterprise Data Storage Optimization
        </h1>
        <p className="text-xs text-gray-600 mt-2 max-w-3xl leading-relaxed">
          Comprehensive architecture, mathematical guarantees, scenario-based storage savings projections,
          and AI data strategy designed for Ericsson internal operations.
        </p>
      </div>

      {/* 4 Core Pillars Grid */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* The Problem */}
        <div className="border border-[#e5e5e5] bg-white p-6 space-y-3">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-red-600 inline-block"></span>
            <h2 className="font-mono font-bold text-sm text-black uppercase tracking-wider">
              1. The Enterprise Problem
            </h2>
          </div>
          <ul className="text-xs text-gray-700 font-sans space-y-2 leading-relaxed list-disc pl-4">
            <li>
              <strong>Storage Bloat:</strong> Hundreds of gigabytes of recurring multi-hour meeting recordings
              and duplicated presentation revisions consume massive quota across SharePoint, OneDrive, and EricssonPlay.
            </li>
            <li>
              <strong>Permanent Data Loss:</strong> Under quota pressure, admins permanently delete older files.
              Valuable domain knowledge, decisions, and future AI training data are permanently destroyed.
            </li>
            <li>
              <strong>Orphan Leaver Files:</strong> Departing employees download central files to personal laptops
              and re-upload to personal OneDrives, creating unmonitored duplicates and dark storage silos.
            </li>
          </ul>
        </div>

        {/* The Solution */}
        <div className="border border-[#e5e5e5] bg-white p-6 space-y-3">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-green-600 inline-block"></span>
            <h2 className="font-mono font-bold text-sm text-black uppercase tracking-wider">
              2. The Distill Solution
            </h2>
          </div>
          <ul className="text-xs text-gray-700 font-sans space-y-2 leading-relaxed list-disc pl-4">
            <li>
              <strong>5-Tier Storage Cascade:</strong> Replaces heavy raw video (1 GB+) with time-linked text,
              lossless slide keyframes, and Opus speech audio (20 MB), slashing footprint by 98%+.
            </li>
            <li>
              <strong>Lossless "Nothing Was Lost" Protocol:</strong> Mathematical proof verifying 100% speech transcript
              coverage, OCR text retention, speaker attribution, and on-demand video recreation.
            </li>
            <li>
              <strong>Content-Addressable Deduplication:</strong> Slide-level perceptual hashing (pHash) indexes
              individual pages, sharing identical slide vectors across revision decks.
            </li>
          </ul>
        </div>

        {/* Scenario-Based Percentage Savings */}
        <div className="border border-[#e5e5e5] bg-white p-6 space-y-3">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-black inline-block"></span>
            <h2 className="font-mono font-bold text-sm text-black uppercase tracking-wider">
              3. Scenario-Based Volume Savings
            </h2>
          </div>
          <div className="text-xs text-gray-700 font-sans space-y-2 leading-relaxed">
            <p>
              In an Ericsson department generating <strong>100 meetings/month</strong> (~12 TB raw/year):
            </p>
            <div className="border border-gray-200 p-3 bg-gray-50 font-mono text-[11px] space-y-1">
              <div className="flex justify-between">
                <span>Raw Uncompressed Volume:</span>
                <span className="font-bold">12,000 GB / year</span>
              </div>
              <div className="flex justify-between text-green-700">
                <span>Distilled T3 Packet Volume:</span>
                <span className="font-bold">240 GB / year (98.0% SAVING)</span>
              </div>
              <div className="flex justify-between text-black font-semibold pt-1 border-t border-gray-200">
                <span>Net Enterprise Storage Freed:</span>
                <span>11,760 GB / year</span>
              </div>
            </div>
            <p className="text-[11px] text-gray-500">
              When someone leaves, 94%+ of their personal OneDrive volume is safely reclaimed by pruning verified
              duplicates while preserving unique unpublished drafts.
            </p>
          </div>
        </div>

        {/* Future-Proof AI Strategy */}
        <div className="border border-[#e5e5e5] bg-white p-6 space-y-3">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-black inline-block"></span>
            <h2 className="font-mono font-bold text-sm text-black uppercase tracking-wider">
              4. Future-Proof AI Strategy
            </h2>
          </div>
          <ul className="text-xs text-gray-700 font-sans space-y-2 leading-relaxed list-disc pl-4">
            <li>
              <strong>AI Training Flywheel:</strong> Raw videos cannot be ingested by LLMs. Distill converts them into
              clean, tokenized JSONL datasets with PII redaction, ready for internal model fine-tuning.
            </li>
            <li>
              <strong>RAG Grounding:</strong> FTS5 full-text + vector embeddings enable enterprise AI agents to answer
              employee queries with exact second-by-second video citations and slide numbers.
            </li>
            <li>
              <strong>Regulatory Compliance:</strong> Automated PII anonymization and audit trails guarantee compliance
              with EU GDPR and enterprise data governance policies.
            </li>
          </ul>
        </div>
      </section>

      {/* System Architecture & Live Engine Specs */}
      <section className="border border-[#e5e5e5] bg-white p-6 space-y-4">
        <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500">
          Engine Runtime Architecture & Model Registry
        </h2>

        {loading ? (
          <div className="text-xs font-mono text-gray-500">Loading system pipeline information...</div>
        ) : info ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 font-mono text-xs">
            {/* Models */}
            <div className="border border-[#e5e5e5] p-4 bg-gray-50/50 space-y-2">
              <span className="text-[10px] text-gray-500 uppercase font-bold block mb-2">
                ACTIVE AI & ML MODELS
              </span>
              <div>
                <span className="text-gray-500 block text-[10px]">SPEECH TRANSCRIPTION:</span>
                <span className="text-black font-semibold">{info.models.transcription}</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">SPEAKER DIARIZATION:</span>
                <span className="text-black font-semibold">{info.models.diarization}</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">OPTICAL CHARACTER RECOGNITION:</span>
                <span className="text-black font-semibold">{info.models.ocr}</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">SEMANTIC EMBEDDINGS:</span>
                <span className="text-black font-semibold">{info.models.embeddings}</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">LOCAL LLM:</span>
                <span className="text-black font-semibold">{info.models.llm}</span>
              </div>
            </div>

            {/* Versions & Hardware */}
            <div className="border border-[#e5e5e5] p-4 bg-gray-50/50 space-y-2">
              <span className="text-[10px] text-gray-500 uppercase font-bold block mb-2">
                SOFTWARE & ENVIRONMENT
              </span>
              <div>
                <span className="text-gray-500 block text-[10px]">PYTHON RUNTIME:</span>
                <span className="text-black">{info.versions.python}</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">TORCH:</span>
                <span className="text-black">{info.versions.torch}</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">OPENCV:</span>
                <span className="text-black">{info.versions.opencv}</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">FFMPEG:</span>
                <span className="text-black truncate block">{info.versions.ffmpeg}</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">DEPLOYMENT TARGET:</span>
                <span className="text-black font-semibold">{info.environment}</span>
              </div>
            </div>

            {/* Thresholds & Security */}
            <div className="border border-[#e5e5e5] p-4 bg-gray-50/50 space-y-2">
              <span className="text-[10px] text-gray-500 uppercase font-bold block mb-2">
                ALGORITHMIC THRESHOLDS
              </span>
              <div>
                <span className="text-gray-500 block text-[10px]">IDENTICAL SLIDE HAMMING:</span>
                <span className="text-black font-semibold">&le; {info.thresholds.identical_hamming} bits</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">MODIFIED SLIDE HAMMING:</span>
                <span className="text-black font-semibold">&le; {info.thresholds.modified_hamming} bits</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">VIDEO SIMILARITY:</span>
                <span className="text-black font-semibold">&ge; {info.thresholds.video_similarity * 100}%</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">TRANSCRIPT SIMILARITY:</span>
                <span className="text-black font-semibold">&ge; {info.thresholds.transcript_similarity * 100}%</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">SECURE ALLOWED ROOTS:</span>
                <span className="text-black text-[10px] break-all block">
                  {info.allowed_roots.length} restricted roots enforced
                </span>
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
