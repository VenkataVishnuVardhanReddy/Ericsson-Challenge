"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Search,
  FileText,
  ShieldCheck,
  Building2,
  User,
  Video,
  Layers,
  Check,
} from "lucide-react";
import { api, formatBytes } from "@/lib/api";
import { OverviewData } from "@/lib/types";
import { StatusBadge } from "@/components/Badge";
import Explain from "@/components/Explain";

export default function OverviewPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showFormula, setShowFormula] = useState(false);

  // Savings Projection Sliders State
  const [tbRecordings, setTbRecordings] = useState(10);
  const [pctOlderThanOneYear, setPctOlderThanOneYear] = useState(60);
  const [costPerTbMonth, setCostPerTbMonth] = useState(20);
  const [kgCo2PerTbYear, setKgCo2PerTbYear] = useState(40);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.getOverview();
        setData(res);
      } catch (e) {
        console.error("Failed to load overview:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="space-y-8 animate-pulse py-12">
        <div className="h-14 bg-gray-100 rounded-lg w-3/4"></div>
        <div className="h-6 bg-gray-100 rounded w-1/2"></div>
        <div className="h-48 bg-gray-100 rounded-xl"></div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="h-32 bg-gray-100 rounded-xl"></div>
          <div className="h-32 bg-gray-100 rounded-xl"></div>
          <div className="h-32 bg-gray-100 rounded-xl"></div>
        </div>
      </div>
    );
  }

  const waterfall = data?.waterfall;
  const sources = data?.sources || [];

  if (!waterfall) {
    return (
      <div className="py-12 text-center text-[#6b6b6b]">
        Could not load overview results.
      </div>
    );
  }

  // Projection calculations based on measured savings directly from the API
  const videoSavingRate = (waterfall.video_original_bytes && waterfall.video_original_bytes > 0)
    ? (waterfall.video_reduction_bytes / waterfall.video_original_bytes)
    : (waterfall.savings_pct ? waterfall.savings_pct / 100 : 0.9907);
  const eligibleTb = tbRecordings * (pctOlderThanOneYear / 100);
  const tbFreed = eligibleTb * videoSavingRate;
  const eurosSavedPerYear = tbFreed * costPerTbMonth * 12;
  const tonnesCo2Avoided = (tbFreed * kgCo2PerTbYear) / 1000;

  return (
    <div className="space-y-16 py-4">
      {/* SECTION A: THE HEADLINE */}
      <section className="space-y-4">
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-black leading-tight">
          {formatBytes(waterfall.original_bytes)} of Ericsson files → {formatBytes(waterfall.final_bytes)}.
        </h1>
        <p className="text-lg sm:text-xl text-[#6b6b6b] max-w-3xl leading-relaxed">
          {waterfall.savings_pct}% less storage. The content was kept: every slide, every spoken word, who said it and when.
        </p>
      </section>

      {/* SECTION B: WHERE THE SAVINGS COME FROM (WATERFALL) */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-black">Where the savings come from</h2>
            <p className="text-sm text-[#6b6b6b] mt-1">
              Every reduction step is measured directly from the files and adds up exactly to the final size.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowFormula(!showFormula)}
            className="inline-flex items-center gap-1.5 text-xs text-[#6b6b6b] hover:text-black font-medium transition-colors border border-[#e5e5e5] px-3 py-1.5 rounded-lg w-fit"
          >
            <span>How is this calculated?</span>
            {showFormula ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* Horizontal Stacked Bar (iPhone Storage style) */}
        <div className="space-y-2">
          <div className="w-full h-5 rounded-lg bg-gray-100 flex overflow-hidden border border-[#e5e5e5]">
            <div
              style={{ width: `${(waterfall.video_reduction_bytes / waterfall.original_bytes) * 100}%` }}
              className="bg-black"
              title={`Videos to slides & text: ${formatBytes(waterfall.video_reduction_bytes)}`}
            />
            <div
              style={{ width: `${(waterfall.slide_dedup_bytes / waterfall.original_bytes) * 100}%` }}
              className="bg-[#6b6b6b]"
              title={`Older revisions stored as changes only: ${formatBytes(waterfall.slide_dedup_bytes)}`}
            />
            <div
              style={{ width: `${(waterfall.duplicate_file_bytes / waterfall.original_bytes) * 100}%` }}
              className="bg-[#a3a3a3]"
              title={`Duplicate files: ${formatBytes(waterfall.duplicate_file_bytes)}`}
            />
            <div
              style={{ width: `${Math.max(1, (waterfall.final_bytes / waterfall.original_bytes) * 100)}%` }}
              className="bg-white border-l border-[#e5e5e5]"
              title={`Final kept size: ${formatBytes(waterfall.final_bytes)}`}
            />
          </div>

          <div className="flex flex-wrap items-center gap-4 sm:gap-6 text-xs text-[#6b6b6b] pt-1">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-black inline-block"></span>
              <span>Videos to slides + text ({((waterfall.video_reduction_bytes / waterfall.original_bytes) * 100).toFixed(1)}%)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-[#6b6b6b] inline-block"></span>
              <span>Older revisions stored as changes only ({((waterfall.slide_dedup_bytes / waterfall.original_bytes) * 100).toFixed(1)}%)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-[#a3a3a3] inline-block"></span>
              <span>Duplicate files ({((waterfall.duplicate_file_bytes / waterfall.original_bytes) * 100).toFixed(1)}%)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm border border-black bg-white inline-block"></span>
              <span className="text-black font-medium">Final size ({((waterfall.final_bytes / waterfall.original_bytes) * 100).toFixed(1)}%)</span>
            </div>
          </div>
        </div>

        {/* Waterfall Breakdown Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 pt-2">
          {/* 1. Start */}
          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-white">
            <span className="text-xs text-[#6b6b6b] block font-medium">Total original</span>
            <div className="text-xl font-bold text-black font-mono mt-1">
              {formatBytes(waterfall.original_bytes)}
            </div>
            <span className="text-xs text-[#6b6b6b] mt-1 block">Untouched input</span>
          </div>

          {/* 2. Videos */}
          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-white">
            <span className="text-xs text-[#6b6b6b] block font-medium">Minus: video frames</span>
            <div className="text-xl font-bold text-black font-mono mt-1">
              −{formatBytes(waterfall.video_reduction_bytes)}
            </div>
            <span className="text-xs text-[#6b6b6b] mt-1 block">Level 1 → Level 4</span>
          </div>

          {/* 3. Duplicates */}
          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-white">
            <span className="text-xs text-[#6b6b6b] block font-medium">Minus: duplicate files</span>
            <div className="text-xl font-bold text-black font-mono mt-1">
              −{formatBytes(waterfall.duplicate_file_bytes)}
            </div>
            <span className="text-xs text-[#6b6b6b] mt-1 block">Already in official storage</span>
          </div>

          {/* 4. Older revisions */}
          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-white">
            <span className="text-xs text-[#6b6b6b] block font-medium">Minus: older revisions</span>
            <div className="text-xl font-bold text-black font-mono mt-1">
              −{formatBytes(waterfall.slide_dedup_bytes)}
            </div>
            <span className="text-xs text-[#6b6b6b] mt-1 block">Stored as changes only</span>
          </div>

          {/* 5. Final */}
          <div className="p-4 rounded-lg border border-black bg-black text-white">
            <span className="text-xs text-[#a3a3a3] block font-medium">Final kept size</span>
            <div className="text-xl font-bold text-white font-mono mt-1">
              {formatBytes(waterfall.final_bytes)}
            </div>
            <span className="text-xs text-[#a3a3a3] mt-1 block">{waterfall.savings_pct}% less storage</span>
          </div>
        </div>

        {/* Expandable Formula Explanation */}
        {showFormula && (
          <div className="mt-4 p-4 rounded-lg border border-[#e5e5e5] bg-gray-50 text-xs text-[#6b6b6b] font-mono leading-relaxed">
            <span className="font-semibold text-black block mb-1">Exact calculation formula:</span>
            <span>
              {waterfall.original_bytes.toLocaleString()} bytes (original) −{" "}
              {waterfall.video_reduction_bytes.toLocaleString()} bytes (videos to slides & text) −{" "}
              {waterfall.duplicate_file_bytes.toLocaleString()} bytes (duplicate files) −{" "}
              {waterfall.slide_dedup_bytes.toLocaleString()} bytes (shared slides) ={" "}
              <strong className="text-black font-bold">{waterfall.final_bytes.toLocaleString()} bytes ({formatBytes(waterfall.final_bytes)})</strong>.
            </span>
          </div>
        )}
      </section>

      {/* SECTION C: 3 SIMPLE STEPS */}
      <section className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold text-black">How it works in 3 simple steps</h2>
          <p className="text-sm text-[#6b6b6b] mt-1">
            Zero cloud uploads. Everything runs on the local CPU inside Ericsson's environment.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Step 1 */}
          <div className="p-6 rounded-xl border border-[#e5e5e5] bg-white space-y-3">
            <div className="w-10 h-10 rounded-lg bg-black text-white flex items-center justify-center font-bold text-base">
              1
            </div>
            <h3 className="text-base font-semibold text-black">Find files</h3>
            <p className="text-sm text-[#6b6b6b] leading-relaxed">
              We look through <Explain term="SharePoint">SharePoint</Explain>, <Explain term="Ericsson Play">Ericsson Play</Explain> and Gonzalo&apos;s <Explain term="OneDrive">OneDrive</Explain>.
            </p>
          </div>

          {/* Step 2 */}
          <div className="p-6 rounded-xl border border-[#e5e5e5] bg-white space-y-3">
            <div className="w-10 h-10 rounded-lg bg-black text-white flex items-center justify-center font-bold text-base">
              2
            </div>
            <h3 className="text-base font-semibold text-black">Make them smaller</h3>
            <p className="text-sm text-[#6b6b6b] leading-relaxed">
              Videos become slide pictures + text. Exact and visual duplicates are found across drives.
            </p>
          </div>

          {/* Step 3 */}
          <div className="p-6 rounded-xl border border-[#e5e5e5] bg-white space-y-3">
            <div className="w-10 h-10 rounded-lg bg-black text-white flex items-center justify-center font-bold text-base">
              3
            </div>
            <h3 className="text-base font-semibold text-black">Check nothing was lost</h3>
            <p className="text-sm text-[#6b6b6b] leading-relaxed">
              We compare the original video with what we kept: 88.9% to 96.1% on-screen text match.
            </p>
          </div>
        </div>
      </section>

      {/* SECTION D: THE 3 SOURCES */}
      <section className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-black">The 3 storage sources</h2>
            <p className="text-sm text-[#6b6b6b] mt-1">
              Comparing official company systems with leaver personal folders.
            </p>
          </div>
          <Link
            href="/files"
            className="text-xs font-medium text-black hover:underline inline-flex items-center gap-1"
          >
            <span>View all 12 files</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {sources.map((s) => {
            const isGov = s.governed;
            const isOneDrive = s.kind === "onedrive";
            let roleDescription = "Official team documents";
            if (s.kind === "play") roleDescription = "Official company videos";
            if (isOneDrive) roleDescription = "Personal folder of an employee who is leaving";

            const rawBytes = s.bytes || 0;
            const postBytes = s.size_after_bytes ?? 0;
            const savingPct = s.saved_pct ?? (rawBytes > 0 ? Math.round((1 - postBytes / rawBytes) * 100) : 0);

            return (
              <div key={s.id} className="p-6 rounded-xl border border-[#e5e5e5] bg-white space-y-4 flex flex-col justify-between">
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-base font-semibold text-black break-words">{s.name}</h3>
                    <StatusBadge status={isGov ? "official" : "personal"} />
                  </div>
                  <p className="text-xs text-[#6b6b6b] leading-relaxed">
                    {roleDescription}
                  </p>
                </div>

                <div className="pt-4 border-t border-[#e5e5e5] grid grid-cols-2 gap-3 text-xs font-mono">
                  <div>
                    <span className="text-[#6b6b6b] block font-sans text-[11px]">Files</span>
                    <span className="font-semibold text-black text-sm">{s.file_count || 0}</span>
                  </div>
                  <div>
                    <span className="text-[#6b6b6b] block font-sans text-[11px]">Original size</span>
                    <span className="font-semibold text-black text-sm">{formatBytes(rawBytes)}</span>
                  </div>
                  <div>
                    <span className="text-[#6b6b6b] block font-sans text-[11px]">After</span>
                    <span className="font-semibold text-black text-sm">{formatBytes(postBytes)}</span>
                  </div>
                  <div>
                    <span className="text-[#6b6b6b] block font-sans text-[11px]">Space saved</span>
                    <span className="font-semibold text-black text-sm">{savingPct}%</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* SECTION E: SAVINGS PROJECTION (SCALE ACROSS ERICSSON) */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div>
          <span className="text-xs uppercase tracking-wider text-[#6b6b6b] font-semibold">
            Beyond the brief • Savings Projection
          </span>
          <h2 className="text-2xl font-bold text-black mt-1">
            Scale this across Ericsson
          </h2>
          <p className="text-sm text-[#6b6b6b] mt-1">
            Estimate potential capacity, cost, and carbon savings when Distill is applied across older meeting recordings at enterprise scale.
          </p>
        </div>

        {/* Sliders Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 pt-2">
          {/* Slider 1: TB of meeting recordings */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="font-medium text-black">TB of meeting recordings</span>
              <span className="font-mono font-semibold text-black">{tbRecordings} TB</span>
            </div>
            <input
              type="range"
              min={1}
              max={500}
              step={1}
              value={tbRecordings}
              onChange={(e) => setTbRecordings(Number(e.target.value))}
              className="w-full accent-black cursor-pointer"
            />
            <span className="text-[11px] text-[#6b6b6b] block">Total pool of recorded videos</span>
          </div>

          {/* Slider 2: % older than 1 year */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="font-medium text-black">% older than 1 year</span>
              <span className="font-mono font-semibold text-black">{pctOlderThanOneYear}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={pctOlderThanOneYear}
              onChange={(e) => setPctOlderThanOneYear(Number(e.target.value))}
              className="w-full accent-black cursor-pointer"
            />
            <span className="text-[11px] text-[#6b6b6b] block">Recordings eligible for distillation</span>
          </div>

          {/* Slider 3: Storage cost € per TB per month */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="font-medium text-black">Storage cost</span>
              <span className="font-mono font-semibold text-black">€{costPerTbMonth} / TB / mo</span>
            </div>
            <input
              type="range"
              min={5}
              max={100}
              step={1}
              value={costPerTbMonth}
              onChange={(e) => setCostPerTbMonth(Number(e.target.value))}
              className="w-full accent-black cursor-pointer"
            />
            <span className="text-[11px] text-[#6b6b6b] block">Cloud storage fee estimate</span>
          </div>

          {/* Slider 4: kg CO₂ per TB per year */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="font-medium text-black">Carbon footprint</span>
              <span className="font-mono font-semibold text-black">{kgCo2PerTbYear} kg CO₂ / TB</span>
            </div>
            <input
              type="range"
              min={10}
              max={200}
              step={5}
              value={kgCo2PerTbYear}
              onChange={(e) => setKgCo2PerTbYear(Number(e.target.value))}
              className="w-full accent-black cursor-pointer"
            />
            <span className="text-[11px] text-[#6b6b6b] block">Labelled as an assumption</span>
          </div>
        </div>

        {/* Projection Outputs */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 border-t border-[#e5e5e5]">
          <div className="p-4 rounded-xl border border-[#e5e5e5] bg-gray-50 space-y-1">
            <span className="text-xs text-[#6b6b6b] font-medium">Storage capacity freed</span>
            <div className="text-2xl font-bold font-mono text-black">
              {tbFreed.toFixed(1)} TB
            </div>
            <span className="text-[11px] text-[#6b6b6b] block">
              Based on {((videoSavingRate) * 100).toFixed(1)}% measured video reduction
            </span>
          </div>

          <div className="p-4 rounded-xl border border-[#e5e5e5] bg-gray-50 space-y-1">
            <span className="text-xs text-[#6b6b6b] font-medium">Cost avoided per year</span>
            <div className="text-2xl font-bold font-mono text-black">
              €{Math.round(eurosSavedPerYear).toLocaleString()}
            </div>
            <span className="text-[11px] text-[#6b6b6b] block">
              Annual recurring storage savings
            </span>
          </div>

          <div className="p-4 rounded-xl border border-[#e5e5e5] bg-gray-50 space-y-1">
            <span className="text-xs text-[#6b6b6b] font-medium">Carbon emissions avoided</span>
            <div className="text-2xl font-bold font-mono text-black">
              {tonnesCo2Avoided.toFixed(2)} tonnes
            </div>
            <span className="text-[11px] text-[#6b6b6b] block">
              CO₂ emissions avoided per year
            </span>
          </div>
        </div>

        <p className="text-xs text-[#6b6b6b] italic text-center pt-1">
          Estimate based on our measured results and the assumptions above.
        </p>
      </section>

      {/* SECTION F: CALL TO ACTION */}
      <section className="p-8 sm:p-10 rounded-2xl border border-black bg-black text-white flex flex-col sm:flex-row sm:items-center justify-between gap-6">
        <div className="space-y-2 max-w-xl">
          <span className="text-xs text-[#a3a3a3] uppercase tracking-wider font-semibold">Interactive proof</span>
          <h2 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            See one file&apos;s journey
          </h2>
          <p className="text-sm text-[#a3a3a3] leading-relaxed">
            Follow the 88-minute Tech Concept Hackathon presentation: watch how 1.2 GB becomes 7.8 MB with a 5-level interactive slider, full transcript, and moment-by-moment verification.
          </p>
        </div>

        <Link
          href="/files/6"
          className="inline-flex items-center gap-2 px-6 py-3.5 rounded-lg bg-white text-black font-semibold text-sm hover:bg-gray-100 transition-colors whitespace-nowrap self-start sm:self-auto"
        >
          <span>See one file&apos;s journey</span>
          <ArrowRight className="w-4 h-4" />
        </Link>
      </section>
    </div>
  );
}
