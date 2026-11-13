"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Copy,
  Layers,
  FileText,
  ArrowRight,
  ExternalLink,
  ChevronRight,
  Sparkles,
  GitCommit,
  Tag,
  CheckCircle2,
  Info,
} from "lucide-react";
import { api, formatBytes } from "@/lib/api";
import { DuplicatesData, CompareDetail, ComparePair } from "@/lib/types";
import { StatusBadge } from "@/components/Badge";
import Explain from "@/components/Explain";

export default function DuplicatesPage() {
  const [data, setData] = useState<DuplicatesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [compareDetail, setCompareDetail] = useState<CompareDetail | null>(null);
  const [selectedPair, setSelectedPair] = useState<ComparePair | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.getDuplicates();
        setData(res);
        if (res.relations && res.relations.length > 0) {
          const rel = res.relations[0];
          const cmp = await api.getCompare(rel.a.id, rel.b.id);
          setCompareDetail(cmp);
          const firstMod = cmp.pairs?.find((p: ComparePair) => p.relation === "modified");
          setSelectedPair(firstMod || cmp.pairs?.[0] || null);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 py-12 animate-pulse">
        <div className="h-8 bg-gray-100 rounded w-1/3"></div>
        <div className="h-4 bg-gray-100 rounded w-2/3"></div>
        <div className="h-48 bg-gray-100 rounded-xl"></div>
        <div className="h-64 bg-gray-100 rounded-xl"></div>
      </div>
    );
  }

  const exactGroups = data?.exact || [];
  const contentGroups = data?.content || [];
  const videoGroups = data?.video || [];
  const chains = data?.chains || [];
  const nameHints = data?.name_hints || [];
  const slideStats = data?.slide_stats;

  const totalExactReclaimable = exactGroups.reduce((acc, g) => acc + (g.reclaimable || 0), 0);
  const totalChainsSaved = chains.reduce((acc, c) => acc + ((c.full_bytes || 0) - (c.delta_bytes || 0)), 0);

  return (
    <div className="space-y-12 py-2 pb-24">
      {/* HEADER & INTRO */}
      <div className="space-y-2 border-b border-[#e5e5e5] pb-6">
        <h1 className="text-3xl font-bold tracking-tight text-black">Duplicates and versions</h1>
        <p className="text-base text-[#6b6b6b] max-w-3xl leading-relaxed">
          The same content often exists across personal and official storage. We identify duplicates, link revision chains, and store shared slides once.
        </p>
      </div>

      {/* TOP SUMMARY STATS */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs font-mono">
        <div className="p-4 rounded-xl border border-[#e5e5e5] bg-white space-y-1">
          <span className="text-[#6b6b6b] block font-sans text-[11px]">Exact file copies</span>
          <span className="text-xl font-bold text-black block">{exactGroups.length}</span>
          <span className="text-[#6b6b6b] text-[11px] block">{formatBytes(totalExactReclaimable)} safe to free</span>
        </div>
        <div className="p-4 rounded-xl border border-[#e5e5e5] bg-white space-y-1">
          <span className="text-[#6b6b6b] block font-sans text-[11px]">Revision chains</span>
          <span className="text-xl font-bold text-black block">{chains.length}</span>
          <span className="text-[#6b6b6b] text-[11px] block">{formatBytes(totalChainsSaved)} saved via deltas</span>
        </div>
        <div className="p-4 rounded-xl border border-[#e5e5e5] bg-white space-y-1">
          <span className="text-[#6b6b6b] block font-sans text-[11px]">Shared duplicate slides</span>
          <span className="text-xl font-bold text-black block">{slideStats?.shared_slides ?? "—"}</span>
          <span className="text-[#6b6b6b] text-[11px] block">
            {slideStats?.dedup_ratio ? `${(slideStats.dedup_ratio * 100).toFixed(1)}% dedup ratio` : "—"}
          </span>
        </div>
        <div className="p-4 rounded-xl border border-[#e5e5e5] bg-white space-y-1">
          <span className="text-[#6b6b6b] block font-sans text-[11px]">Filename variations</span>
          <span className="text-xl font-bold text-black block">{nameHints.length}</span>
          <span className="text-[#6b6b6b] text-[11px] block">Detected via naming rules</span>
        </div>
      </div>

      {/* 1. EXACT FILE COPIES */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-[#e5e5e5] pb-4">
          <div>
            <h2 className="text-xl font-bold text-black">1. Exact byte duplicates</h2>
            <p className="text-xs text-[#6b6b6b] mt-0.5">
              Files that have 100% identical contents. The official company copy is preserved; leaver personal copies are marked safe to delete.
            </p>
          </div>
          <span className="text-xs font-mono font-medium text-black px-2.5 py-1 rounded bg-gray-100 w-fit">
            {formatBytes(totalExactReclaimable)} can be freed
          </span>
        </div>

        <div className="space-y-4">
          {exactGroups.map((group, gIdx) => {
            const keepFile = group.files.find((f) => f.id === group.keep) || group.files[0];
            const duplicateFiles = group.files.filter((f) => f.id !== keepFile?.id);

            return (
              <div key={gIdx} className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50/50 space-y-3 text-xs">
                <div className="flex items-center justify-between font-mono text-[11px] text-[#6b6b6b]">
                  <span>Group {gIdx + 1}: {group.files.length} identical files</span>
                  <span className="font-semibold text-black">{formatBytes(group.reclaimable)} reclaimable</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                  {/* Kept Copy */}
                  <div className="p-3.5 rounded-lg border border-black bg-white space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-black uppercase tracking-wider">
                        Copy we keep
                      </span>
                      <StatusBadge status={keepFile?.governed ? "official" : "done"} label="Keep this copy" />
                    </div>
                    <Link
                      href={`/files/${keepFile?.id}`}
                      className="font-medium text-black hover:underline break-words block"
                    >
                      {keepFile?.name}
                    </Link>
                    <div className="text-[11px] text-[#6b6b6b] flex items-center justify-between font-mono">
                      <span>{keepFile?.source_name}</span>
                      <span>{formatBytes(keepFile?.size)}</span>
                    </div>
                  </div>

                  {/* Duplicate Copies */}
                  <div className="space-y-2">
                    {duplicateFiles.map((dup) => (
                      <div key={dup.id} className="p-3.5 rounded-lg border border-[#e5e5e5] bg-white space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] text-[#6b6b6b] font-medium uppercase tracking-wider">
                            Duplicate copy
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium border border-black text-black">
                            Safe to remove (0 B kept)
                          </span>
                        </div>
                        <Link
                          href={`/files/${dup.id}`}
                          className="font-medium text-black hover:underline break-words block"
                        >
                          {dup.name}
                        </Link>
                        <div className="text-[11px] text-[#6b6b6b] flex items-center justify-between font-mono">
                          <span>{dup.source_name}</span>
                          <span className="line-through">{formatBytes(dup.size)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 2. DECK REVISIONS & VISUAL SLIDE COMPARISON */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-[#e5e5e5] pb-4">
          <div>
            <h2 className="text-xl font-bold text-black">2. Deck revisions and slide comparison</h2>
            <p className="text-xs text-[#6b6b6b] mt-0.5">
              Comparing revisions of the SD-WAN presentation: Rev A (OneDrive leaver) vs Rev B (SharePoint governed).
            </p>
          </div>
          {compareDetail && (
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="px-2 py-0.5 rounded border border-[#e5e5e5] text-black">
                {compareDetail.identical} identical
              </span>
              <span className="px-2 py-0.5 rounded border border-black bg-black text-white">
                {compareDetail.modified} modified
              </span>
              <span className="px-2 py-0.5 rounded border border-[#e5e5e5] text-[#6b6b6b]">
                {compareDetail.removed.length} removed
              </span>
            </div>
          )}
        </div>

        {compareDetail && (
          <div className="space-y-6">
            {/* Slide Strip */}
            <div className="space-y-2">
              <span className="text-xs text-[#6b6b6b] block font-medium">
                Click any slide to view before, after, and visual difference:
              </span>
              <div className="flex gap-2 overflow-x-auto pb-3">
                {compareDetail.pairs.map((pair, idx) => {
                  const isSelected = selectedPair === pair;
                  const rel = pair.relation;
                  const slideObj = pair.b?.object_hash || pair.a?.object_hash;

                  let badgeLabel = "Same";
                  if (rel === "modified") badgeLabel = "Changed";
                  if (rel === "removed") badgeLabel = "Removed";
                  if (rel === "new") badgeLabel = "New";

                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setSelectedPair(pair)}
                      className={`flex-shrink-0 w-24 p-2 rounded-lg border text-left space-y-1.5 transition-all ${
                        isSelected
                          ? "border-black bg-gray-50 ring-1 ring-black"
                          : "border-[#e5e5e5] hover:border-black bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="font-mono text-[#6b6b6b]">#{idx + 1}</span>
                        <span
                          className={`px-1 rounded text-[9px] font-semibold ${
                            rel === "modified"
                              ? "bg-black text-white"
                              : rel === "removed"
                              ? "border border-[#6b6b6b] text-[#6b6b6b]"
                              : "text-[#6b6b6b]"
                          }`}
                        >
                          {badgeLabel}
                        </span>
                      </div>
                      <div className="aspect-[4/3] bg-gray-100 rounded overflow-hidden">
                        {slideObj ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={api.objectUrl(slideObj)}
                            alt={`Slide ${idx + 1}`}
                            className="w-full h-full object-cover"
                          />
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Selected Slide Detail Panel */}
            {selectedPair && (
              <div className="p-6 rounded-xl border border-[#e5e5e5] bg-gray-50/60 space-y-5">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <span className="text-xs font-semibold text-black">
                      {selectedPair.relation === "modified"
                        ? "Slide modified between revisions (visual differences outlined in red)"
                        : selectedPair.relation === "identical"
                        ? "Identical slide graphic across both presentations"
                        : "Slide presence change"}
                    </span>
                    <p className="text-[11px] text-[#6b6b6b]">
                      Previous (Rev A in OneDrive) → Current (Rev B in SharePoint)
                    </p>
                  </div>
                  <span className="px-2.5 py-1 rounded-md text-xs font-medium border border-black bg-white text-black capitalize">
                    {selectedPair.relation}
                  </span>
                </div>

                {/* 3-Panel View for Modified Slides */}
                {selectedPair.relation === "modified" && selectedPair.a && selectedPair.b ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* 1. Previous Revision */}
                      <div className="space-y-1.5">
                        <span className="text-xs font-semibold text-[#6b6b6b] block">
                          1. Previous (Rev A, Slide {selectedPair.a.page_no})
                        </span>
                        <div className="aspect-[4/3] bg-white rounded-lg border border-[#e5e5e5] overflow-hidden flex items-center justify-center">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={api.objectUrl(selectedPair.a.object_hash)}
                            alt="Previous slide"
                            className="w-full h-full object-contain"
                          />
                        </div>
                      </div>

                      {/* 2. Visual Diff with Red Bounding Boxes */}
                      <div className="space-y-1.5">
                        <span className="text-xs font-semibold text-black block">
                          2. Visual Difference (Changes Outlined)
                        </span>
                        <div className="aspect-[4/3] bg-white rounded-lg border border-black overflow-hidden flex items-center justify-center">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={api.diffImageUrl(selectedPair.a.id, selectedPair.b.id)}
                            alt="Visual difference"
                            className="w-full h-full object-contain"
                          />
                        </div>
                      </div>

                      {/* 3. Current Revision */}
                      <div className="space-y-1.5">
                        <span className="text-xs font-semibold text-[#6b6b6b] block">
                          3. Current (Rev B, Slide {selectedPair.b.page_no})
                        </span>
                        <div className="aspect-[4/3] bg-white rounded-lg border border-[#e5e5e5] overflow-hidden flex items-center justify-center">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={api.objectUrl(selectedPair.b.object_hash)}
                            alt="Current slide"
                            className="w-full h-full object-contain"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Text Diff Block */}
                    {selectedPair.text_diff && Array.isArray(selectedPair.text_diff) && (
                      <div className="p-3.5 rounded-lg border border-[#e5e5e5] bg-white text-xs font-mono space-y-1.5">
                        <span className="text-[11px] font-semibold text-black block font-sans">
                          Text differences between revisions:
                        </span>
                        <div className="space-y-0.5 text-[11px]">
                          {selectedPair.text_diff.map((td, i) => (
                            <div
                              key={i}
                              className={`px-2 py-0.5 rounded ${
                                td.op === "add"
                                  ? "bg-gray-100 text-black font-semibold"
                                  : td.op === "del"
                                  ? "text-[#6b6b6b] line-through"
                                  : "text-[#6b6b6b]"
                              }`}
                            >
                              <span className="mr-2 select-none">
                                {td.op === "add" ? "+" : td.op === "del" ? "−" : " "}
                              </span>
                              <span>{td.text}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  /* 2-Panel Side-by-Side View for Identical or Single Slides */
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                    <div className="space-y-2">
                      <span className="text-xs font-semibold text-[#6b6b6b] block">
                        Previous revision (Slide {selectedPair.a?.page_no || "—"})
                      </span>
                      <div className="aspect-[4/3] bg-white rounded-lg border border-[#e5e5e5] overflow-hidden flex items-center justify-center">
                        {selectedPair.a?.object_hash ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={api.objectUrl(selectedPair.a.object_hash)}
                            alt="Previous slide"
                            className="w-full h-full object-contain"
                          />
                        ) : (
                          <span className="text-xs text-[#6b6b6b]">Not present in previous revision</span>
                        )}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <span className="text-xs font-semibold text-black block">
                        Current revision (Slide {selectedPair.b?.page_no || "—"})
                      </span>
                      <div className="aspect-[4/3] bg-white rounded-lg border border-black overflow-hidden flex items-center justify-center">
                        {selectedPair.b?.object_hash ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={api.objectUrl(selectedPair.b.object_hash)}
                            alt="Current slide"
                            className="w-full h-full object-contain"
                          />
                        ) : (
                          <span className="text-xs text-[#6b6b6b]">Removed in current revision</span>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      {/* 3. SLIDES REUSED ACROSS DECKS */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-[#e5e5e5] pb-4">
          <div>
            <h2 className="text-xl font-bold text-black">3. Slides reused across decks</h2>
            <p className="text-xs text-[#6b6b6b] mt-0.5">
              Identical slide graphics across different presentations are stored only once in the shared catalog.
            </p>
          </div>
          <span className="text-xs font-mono text-black font-medium">
            {slideStats?.dedup_ratio ? `${(slideStats.dedup_ratio * 100).toFixed(1)}% deduplication ratio` : "—"}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-xs">
          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50">
            <span className="text-[#6b6b6b] block text-[11px]">Total slide pages</span>
            <span className="text-2xl font-bold font-mono text-black mt-1 block">
              {slideStats?.total_slides ?? "—"}
            </span>
            <span className="text-[#6b6b6b] block mt-0.5">Rendered from decks</span>
          </div>

          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50">
            <span className="text-[#6b6b6b] block text-[11px]">Unique slide pictures</span>
            <span className="text-2xl font-bold font-mono text-black mt-1 block">
              {slideStats?.unique_slides ?? "—"}
            </span>
            <span className="text-[#6b6b6b] block mt-0.5">Stored in shared catalog</span>
          </div>

          <div className="p-4 rounded-lg border border-black bg-black text-white">
            <span className="text-[#a3a3a3] block text-[11px]">Shared duplicate slides</span>
            <span className="text-2xl font-bold font-mono text-white mt-1 block">
              {slideStats?.shared_slides ?? "—"}
            </span>
            <span className="text-[#a3a3a3] block mt-0.5">Redundant images saved</span>
          </div>
        </div>
      </section>

      {/* 4. DOCUMENT REVISION CHAINS */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-[#e5e5e5] pb-4">
          <div>
            <h2 className="text-xl font-bold text-black">4. Document version chains</h2>
            <p className="text-xs text-[#6b6b6b] mt-0.5">
              Official document numbers tracked across revisions to enable delta storage.
            </p>
          </div>
          <span className="text-xs font-mono text-black font-medium">
            {chains.length} chain detected
          </span>
        </div>

        {chains.length > 0 ? (
          <div className="space-y-4">
            {chains.map((chain, cIdx) => {
              const deltaSaved = (chain.full_bytes || 0) - (chain.delta_bytes || 0);
              return (
                <div key={cIdx} className="p-5 rounded-lg border border-[#e5e5e5] bg-gray-50/50 space-y-4 text-xs">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <span className="font-mono text-[11px] text-[#6b6b6b] uppercase tracking-wider block">
                        Doc Number: {chain.doc_number || "Unnumbered"}
                      </span>
                      <h3 className="text-sm font-semibold text-black mt-0.5">{chain.title}</h3>
                    </div>
                    <div className="font-mono text-xs text-right">
                      <span className="text-[#6b6b6b] block text-[11px]">Delta storage saving</span>
                      <span className="font-bold text-black">{formatBytes(deltaSaved)}</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                    {chain.versions?.map((ver: any, vIdx: number) => (
                      <div
                        key={ver.id}
                        className={`p-3.5 rounded-lg border bg-white space-y-2 ${
                          ver.id === chain.latest ? "border-black" : "border-[#e5e5e5]"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-semibold text-black uppercase font-mono">
                            Revision {ver.revision || (vIdx === 0 ? "A" : "B")}
                          </span>
                          <StatusBadge
                            status={ver.governed ? "official" : "personal"}
                            label={ver.governed ? "Official copy" : "Leaver copy"}
                          />
                        </div>
                        <Link
                          href={`/files/${ver.id}`}
                          className="font-medium text-black hover:underline break-words block"
                        >
                          {ver.name}
                        </Link>
                        <div className="flex items-center justify-between text-[11px] text-[#6b6b6b] font-mono">
                          <span>{ver.source_name}</span>
                          <span>{formatBytes(ver.size)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-6 rounded-lg border border-[#e5e5e5] bg-gray-50 text-center text-xs text-[#6b6b6b]">
            No multi-version document chains detected.
          </div>
        )}
      </section>

      {/* 5. FILENAME VARIATIONS & HEURISTICS */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div className="border-b border-[#e5e5e5] pb-4">
          <h2 className="text-xl font-bold text-black">5. Detection heuristics</h2>
          <p className="text-xs text-[#6b6b6b] mt-0.5">
            Secondary detection rules for personal drive folders and modified copies.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-xs">
          {/* Filename Variations */}
          <div className="p-5 rounded-lg border border-[#e5e5e5] bg-white space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-black">Filename variations</span>
              <span className="font-mono text-xs text-[#6b6b6b]">{nameHints.length}</span>
            </div>
            <p className="text-[11px] text-[#6b6b6b] leading-relaxed">
              Files with names like <code className="bg-gray-100 px-1 py-0.5 rounded text-black">Copy of Brief.png</code> or <code className="bg-gray-100 px-1 py-0.5 rounded text-black">(1)</code> suffix.
            </p>
            <div className="space-y-2 pt-2">
              {nameHints.map((nh, i) => (
                <div key={i} className="p-2.5 rounded bg-gray-50 border border-[#e5e5e5] text-[11px] space-y-1">
                  <div className="font-medium text-black break-words">{nh.file?.name}</div>
                  <div className="text-[#6b6b6b] font-mono text-[10px]">
                    Canonical: {nh.canonical}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Near-Duplicate Content */}
          <div className="p-5 rounded-lg border border-[#e5e5e5] bg-white space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-black">Content text similarity</span>
              <span className="font-mono text-xs text-[#6b6b6b]">{contentGroups.length}</span>
            </div>
            <p className="text-[11px] text-[#6b6b6b] leading-relaxed">
              Text files with identical wording despite different container headers or file formats.
            </p>
            {contentGroups.length > 0 ? (
              <div className="space-y-2 pt-2">
                {contentGroups.map((cg, i) => (
                  <div key={i} className="p-2 rounded bg-gray-50 border border-[#e5e5e5]">
                    {cg.files.length} files
                  </div>
                ))}
              </div>
            ) : (
              <div className="pt-4 text-center text-[11px] text-[#6b6b6b]">
                No non-identical text matches detected.
              </div>
            )}
          </div>

          {/* Video Perceptual Matches */}
          <div className="p-5 rounded-lg border border-[#e5e5e5] bg-white space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-black">Video perceptual duplicates</span>
              <span className="font-mono text-xs text-[#6b6b6b]">{videoGroups.length}</span>
            </div>
            <p className="text-[11px] text-[#6b6b6b] leading-relaxed">
              Different video recordings or re-encodes of the same presentation talk.
            </p>
            {videoGroups.length > 0 ? (
              <div className="space-y-2 pt-2">
                {videoGroups.map((vg, i) => (
                  <div key={i} className="p-2 rounded bg-gray-50 border border-[#e5e5e5]">
                    {vg.files.length} videos
                  </div>
                ))}
              </div>
            ) : (
              <div className="pt-4 text-center text-[11px] text-[#6b6b6b]">
                All 3 video recordings are distinct presentations.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
