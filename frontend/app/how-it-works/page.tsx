"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Laptop,
  ArrowRight,
  ShieldCheck,
  Check,
  HelpCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import { PipelineInfo } from "@/lib/types";
import { GLOSSARY } from "@/lib/glossary";

export default function HowItWorksPage() {
  const [info, setInfo] = useState<PipelineInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.getPipelineInfo();
        setInfo(res);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const pipelineSteps = [
    {
      step: "Scan & verify",
      does: "Finds files in SharePoint, Ericsson Play and OneDrive, computing unique fingerprints",
      tool: "SHA-256 cryptographic hashing",
      type: "Simple algorithm",
      offline: "Yes",
    },
    {
      step: "Speech to text",
      does: "Transcribes every spoken sentence with word-level timestamps",
      tool: info?.models?.transcription || "Whisper base (runs offline on the laptop CPU)",
      type: "AI model",
      offline: "Yes",
    },
    {
      step: "Who spoke",
      does: "Identifies and groups who was speaking throughout the audio",
      tool: info?.models?.diarization || "pyannote + WeSpeaker speaker detection (offline)",
      type: "AI model",
      offline: "Yes",
    },
    {
      step: "Read slide text",
      does: "Extracts letters, numbers, and titles visible on screen or in deck pages",
      tool: info?.models?.ocr || "RapidOCR (offline)",
      type: "AI model",
      offline: "Yes",
    },
    {
      step: "Slide pictures",
      does: "Saves visual slide moments at high resolution with minimal file size",
      tool: info?.models?.slides || "WebP images, quality 70",
      type: "Simple algorithm",
      offline: "Yes",
    },
    {
      step: "Speech audio",
      does: "Extracts and compresses human speech audio into a lightweight stream",
      tool: info?.models?.audio || "Opus speech audio, 16 kbps",
      type: "Simple algorithm",
      offline: "Yes",
    },
    {
      step: "Summary",
      does: "Selects 3 to 5 key representative sentences from the talk",
      tool: info?.models?.summary || "Picks key sentences (no AI)",
      type: "Simple algorithm",
      offline: "Yes",
    },
    {
      step: "Search by exact words",
      does: "Indexes every word for instant keyword search",
      tool: info?.models?.exact_search || "SQLite full-text search",
      type: "Simple algorithm",
      offline: "Yes",
    },
    {
      step: "Search by meaning",
      does: "Enables natural language semantic search across spoken ideas",
      tool: info?.models?.embeddings || "all-MiniLM-L6-v2 (offline)",
      type: "AI model",
      offline: "Yes",
    },
  ];

  return (
    <div className="space-y-12 py-2 max-w-[1120px] mx-auto pb-24">
      {/* HEADER & CORE STATEMENT */}
      <div className="space-y-3 border-b border-[#e5e5e5] pb-6">
        <h1 className="text-3xl font-bold tracking-tight text-black">How it works</h1>
        <p className="text-lg font-medium text-black">
          Everything runs offline on a normal laptop. No data leaves the machine.
        </p>
        <p className="text-sm text-[#6b6b6b] leading-relaxed max-w-3xl">
          Distill reduces storage footprint by separating moving video into slide pictures and clear speech audio, deduplicating identical slides across decks, and verifying that nothing was lost.
        </p>
      </div>

      {/* SECTION 1: BLACK AND WHITE FLOWCHART DIAGRAM */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div>
          <h2 className="text-xl font-bold text-black">Architecture diagram</h2>
          <p className="text-xs text-[#6b6b6b] mt-0.5">
            The end-to-end pipeline from source scanning to verification and clean-up.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 pt-2 text-xs">
          {/* Step 1 */}
          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50/50 space-y-2">
            <span className="font-mono text-[#6b6b6b] block text-[11px]">Step 1</span>
            <span className="font-semibold text-black text-sm block">Find files</span>
            <p className="text-[#6b6b6b] leading-relaxed">
              Scans SharePoint, Ericsson Play, and personal OneDrive folders. Computes SHA-256 fingerprints.
            </p>
          </div>

          {/* Step 2 */}
          <div className="p-4 rounded-lg border border-black bg-white space-y-2">
            <span className="font-mono text-[#6b6b6b] block text-[11px]">Step 2</span>
            <span className="font-semibold text-black text-sm block">Make smaller</span>
            <p className="text-[#6b6b6b] leading-relaxed">
              <strong>Videos:</strong> slides + Opus audio.<br />
              <strong>Documents:</strong> pages to WebP + extracted text.
            </p>
          </div>

          {/* Step 3 */}
          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50/50 space-y-2">
            <span className="font-mono text-[#6b6b6b] block text-[11px]">Step 3</span>
            <span className="font-semibold text-black text-sm block">Link official decks</span>
            <p className="text-[#6b6b6b] leading-relaxed">
              Slides identical to official master decks become references, freeing duplicate image storage.
            </p>
          </div>

          {/* Step 4 */}
          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50/50 space-y-2">
            <span className="font-mono text-[#6b6b6b] block text-[11px]">Step 4</span>
            <span className="font-semibold text-black text-sm block">Check nothing lost</span>
            <p className="text-[#6b6b6b] leading-relaxed">
              Picks 20 random moments in original videos and checks that screen text matches kept slides.
            </p>
          </div>

          {/* Step 5 */}
          <div className="p-4 rounded-lg border border-black bg-black text-white space-y-2">
            <span className="font-mono text-[#a3a3a3] block text-[11px]">Step 5</span>
            <span className="font-semibold text-white text-sm block">Search & clean-up</span>
            <p className="text-[#a3a3a3] leading-relaxed">
              Instant search across all spoken words and safe leaver folder offboarding with zero data loss.
            </p>
          </div>
        </div>
      </section>

      {/* SECTION 2: TOOLS & PIPELINE TABLE */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div>
          <h2 className="text-xl font-bold text-black">Pipeline steps & honest tools</h2>
          <p className="text-xs text-[#6b6b6b] mt-0.5">
            Every step is implemented with standard open-source tools running CPU-only on your laptop.
          </p>
        </div>

        <div className="border border-[#e5e5e5] rounded-lg overflow-hidden">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[#e5e5e5] bg-gray-50 text-[#6b6b6b] uppercase text-[11px]">
                <th className="py-3 px-4">Step</th>
                <th className="py-3 px-4">What it does</th>
                <th className="py-3 px-4">Tool</th>
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4 text-center">Runs offline?</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e5e5e5]">
              {pipelineSteps.map((row, idx) => (
                <tr key={idx} className="hover:bg-gray-50/60 transition-colors">
                  <td className="py-3 px-4 font-semibold text-black whitespace-nowrap">
                    {row.step}
                  </td>
                  <td className="py-3 px-4 text-[#6b6b6b] max-w-sm">
                    {row.does}
                  </td>
                  <td className="py-3 px-4 font-mono text-black">
                    {row.tool}
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap">
                    <span className="px-2 py-0.5 rounded border border-[#e5e5e5] text-[#6b6b6b] text-[11px]">
                      {row.type}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-center font-medium text-black">
                    <span className="inline-flex items-center gap-1">
                      <Check className="w-3.5 h-3.5" />
                      <span>{row.offline}</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* SECTION 3: COMPREHENSIVE GLOSSARY */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div>
          <h2 className="text-xl font-bold text-black">Plain-English glossary</h2>
          <p className="text-xs text-[#6b6b6b] mt-0.5">
            Every technical term used across Distill explained in one simple sentence.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          {Object.entries(GLOSSARY).map(([term, explanation]) => (
            <div key={term} className="p-3.5 rounded-lg border border-[#e5e5e5] bg-gray-50/40 space-y-1 text-xs">
              <span className="font-semibold text-black block">{term}</span>
              <p className="text-[#6b6b6b] leading-relaxed">{explanation}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
