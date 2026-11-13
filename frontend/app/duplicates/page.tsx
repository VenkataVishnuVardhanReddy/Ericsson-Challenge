"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Copy,
  Layers,
  FileText,
  Building2,
  User,
  ArrowRight,
  ExternalLink,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { api, formatBytes } from "@/lib/api";
import { DuplicatesData, DeckRelation, CompareDetail, ComparePair } from "@/lib/types";
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
          const firstMod = cmp.pairs?.find((p: any) => p.relation === "modified");
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
  const totalExactReclaimable = exactGroups.reduce((acc, g) => acc + (g.reclaimable || 0), 0);

  return (
    <div className="space-y-12 py-2 pb-24">
      {/* HEADER & INTRO */}
      <div className="space-y-2 border-b border-[#e5e5e5] pb-6">
        <h1 className="text-3xl font-bold tracking-tight text-black">Duplicates and versions</h1>
        <p className="text-base text-[#6b6b6b] max-w-3xl leading-relaxed">
          The same content often exists in several places. We keep one official copy and show what can be freed.
        </p>
      </div>

      {/* 1. EXACT COPY */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-[#e5e5e5] pb-4">
          <div>
            <h2 className="text-xl font-bold text-black">Exact copy</h2>
            <p className="text-xs text-[#6b6b6b] mt-0.5">
              Byte-identical copies found across different folders (e.g. Brief.png and Copy of Brief.png).
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
                  <div className="p-3 rounded-lg border border-black bg-white space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-black uppercase tracking-wider">
                        Copy we keep
                      </span>
                      <StatusBadge status={keepFile?.governed ? "official" : "done"} label="Keep this copy" />
                    </div>
                    <div className="font-medium text-black break-words">{keepFile?.name}</div>
                    <div className="text-[11px] text-[#6b6b6b] flex items-center justify-between font-mono">
                      <span>{keepFile?.source_name}</span>
                      <span>{formatBytes(keepFile?.size)}</span>
                    </div>
                  </div>

                  {/* Duplicate Copies */}
                  <div className="space-y-2">
                    {duplicateFiles.map((dup) => (
                      <div key={dup.id} className="p-3 rounded-lg border border-[#e5e5e5] bg-white space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] text-[#6b6b6b] font-medium uppercase tracking-wider">
                            Duplicate copy
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium border border-black text-black">
                            Safe to remove
                          </span>
                        </div>
                        <div className="font-medium text-black break-words">{dup.name}</div>
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

      {/* 2. NEW VERSION OF A DECK */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-[#e5e5e5] pb-4">
          <div>
            <h2 className="text-xl font-bold text-black">New version of a deck</h2>
            <p className="text-xs text-[#6b6b6b] mt-0.5">
              Comparing revisions of the SD-WAN deck: final.pptx → final2.pptx.
            </p>
          </div>
          {compareDetail && (
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="px-2 py-0.5 rounded border border-[#e5e5e5] text-black">
                {compareDetail.summary.identical} identical
              </span>
              <span className="px-2 py-0.5 rounded border border-black bg-black text-white">
                {compareDetail.summary.modified} changed
              </span>
              <span className="px-2 py-0.5 rounded border border-[#e5e5e5] text-[#6b6b6b]">
                {compareDetail.summary.unique_to_a} removed
              </span>
            </div>
          )}
        </div>

        {compareDetail && (
          <div className="space-y-6">
            {/* Version Strip: Slide-by-Slide Thumbnails */}
            <div className="space-y-2">
              <span className="text-xs text-[#6b6b6b] block font-medium">
                Click any slide to view differences:
              </span>
              <div className="flex gap-2 overflow-x-auto pb-3">
                {compareDetail.pairs.map((pair, idx) => {
                  const isSelected = selectedPair === pair;
                  const rel = pair.relation;

                  let badgeLabel = "Same";
                  if (rel === "modified") badgeLabel = "Changed";
                  if (rel === "unique_a") badgeLabel = "Removed";
                  if (rel === "unique_b") badgeLabel = "New";

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
                              : rel === "unique_a"
                              ? "border border-[#6b6b6b] text-[#6b6b6b]"
                              : "text-[#6b6b6b]"
                          }`}
                        >
                          {badgeLabel}
                        </span>
                      </div>
                      <div className="aspect-[4/3] bg-gray-100 rounded overflow-hidden">
                        {pair.b?.content_id || pair.a?.content_id ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={`http://127.0.0.1:8000/api/objects/${pair.b?.content_id || pair.a?.content_id}`}
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

            {/* Before / After Slide Viewer with Outlined Difference */}
            {selectedPair && (
              <div className="p-6 rounded-xl border border-[#e5e5e5] bg-gray-50/60 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <span className="text-xs font-semibold text-black">
                      Slide comparison: {selectedPair.relation === "modified" ? "Slide modified in newer version" : "Slide details"}
                    </span>
                    <p className="text-[11px] text-[#6b6b6b]">
                      Differences between previous version (Rev A) and current version (Rev B).
                    </p>
                  </div>
                  <span className="px-2.5 py-1 rounded-md text-xs font-medium border border-black bg-white text-black capitalize">
                    {selectedPair.relation}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                  {/* Previous Version */}
                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-[#6b6b6b] block">
                      Previous: {compareDetail.a.name} (Slide {selectedPair.page_a || "—"})
                    </span>
                    <div className="aspect-[4/3] bg-white rounded-lg border border-[#e5e5e5] overflow-hidden flex items-center justify-center">
                      {selectedPair.a?.content_id ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={`http://127.0.0.1:8000/api/objects/${selectedPair.a.content_id}`}
                          alt="Previous slide"
                          className="w-full h-full object-contain"
                        />
                      ) : (
                        <span className="text-xs text-[#6b6b6b]">Not present in previous version</span>
                      )}
                    </div>
                  </div>

                  {/* Current Version */}
                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-black block">
                      Current: {compareDetail.b.name} (Slide {selectedPair.page_b || "—"})
                    </span>
                    <div className="aspect-[4/3] bg-white rounded-lg border border-black overflow-hidden flex items-center justify-center">
                      {selectedPair.b?.content_id ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={`http://127.0.0.1:8000/api/objects/${selectedPair.b.content_id}`}
                          alt="Current slide"
                          className="w-full h-full object-contain"
                        />
                      ) : (
                        <span className="text-xs text-[#6b6b6b]">Removed in current version</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Text Difference If Modified */}
                {selectedPair.text_diff && (
                  <div className="mt-4 p-3 rounded-lg border border-[#e5e5e5] bg-white text-xs font-mono space-y-1">
                    <span className="text-[11px] font-semibold text-black block font-sans">
                      Text changes:
                    </span>
                    <pre className="text-[#6b6b6b] whitespace-pre-wrap leading-relaxed text-[11px]">
                      {selectedPair.text_diff}
                    </pre>
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
            <h2 className="text-xl font-bold text-black">Slides reused across decks</h2>
            <p className="text-xs text-[#6b6b6b] mt-0.5">
              Identical slide graphics across different presentations are stored only once in the shared catalog.
            </p>
          </div>
          <span className="text-xs font-mono text-black font-medium">
            35.5% deduplication ratio
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-xs">
          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50">
            <span className="text-[#6b6b6b] block text-[11px]">Total slide pages</span>
            <span className="text-2xl font-bold font-mono text-black mt-1 block">124</span>
            <span className="text-[#6b6b6b] block mt-0.5">Rendered from decks</span>
          </div>

          <div className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50">
            <span className="text-[#6b6b6b] block text-[11px]">Unique slide pictures</span>
            <span className="text-2xl font-bold font-mono text-black mt-1 block">80</span>
            <span className="text-[#6b6b6b] block mt-0.5">Stored in shared catalog</span>
          </div>

          <div className="p-4 rounded-lg border border-black bg-black text-white">
            <span className="text-[#a3a3a3] block text-[11px]">Shared duplicate slides</span>
            <span className="text-2xl font-bold font-mono text-white mt-1 block">44</span>
            <span className="text-[#a3a3a3] block mt-0.5">Redundant images saved</span>
          </div>
        </div>
      </section>
    </div>
  );
}
