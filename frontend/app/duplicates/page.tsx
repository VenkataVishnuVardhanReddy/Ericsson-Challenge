"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, formatBytes } from "@/lib/api";
import { DuplicatesData, DeckRelation } from "@/lib/types";

export default function DuplicatesPage() {
  const [data, setData] = useState<DuplicatesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedRelation, setSelectedRelation] = useState<DeckRelation | null>(null);
  const [selectedPair, setSelectedPair] = useState<any | null>(null);
  const [comparisonDetail, setComparisonDetail] = useState<any | null>(null);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    api
      .getDuplicates()
      .then((res) => {
        setData(res);
        if (res.relations && res.relations.length > 0) {
          setSelectedRelation(res.relations[0]);
        }
      })
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedRelation) return;
    setComparing(true);
    api
      .getCompare(selectedRelation.a.id, selectedRelation.b.id)
      .then((res) => {
        setComparisonDetail(res);
        const mod = res.pairs?.find((p: any) => p.relation === "modified");
        setSelectedPair(mod || res.pairs?.[0] || null);
      })
      .catch((e) => console.error(e))
      .finally(() => setComparing(false));
  }, [selectedRelation]);

  if (loading) {
    return (
      <div className="py-24 text-center font-mono text-sm text-gray-500">
        ANALYZING PERCEPTUAL DUPLICATES & REVISION CHAINS...
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="border border-[#e5e5e5] bg-white p-6">
        <h1 className="text-xl font-mono font-bold text-black">
          Duplicate Detection & Presentation Revision Chains
        </h1>
        <p className="text-xs text-gray-600 mt-1 max-w-3xl">
          Content-addressable slide hashing identifies exact and modified revisions across disparate sources,
          isolating delta modifications with perceptual bounding boxes.
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-4 border-t border-[#e5e5e5] text-xs font-mono">
          <div>
            <span className="text-gray-500 block text-[10px] uppercase">Exact Groups</span>
            <span className="text-lg font-bold text-black">{data?.exact?.length || 0}</span>
          </div>
          <div>
            <span className="text-gray-500 block text-[10px] uppercase">Content Matches</span>
            <span className="text-lg font-bold text-black">{data?.content?.length || 0}</span>
          </div>
          <div>
            <span className="text-gray-500 block text-[10px] uppercase">Video Perceptual Dups</span>
            <span className="text-lg font-bold text-black">{data?.video?.length || 0}</span>
          </div>
          <div>
            <span className="text-gray-500 block text-[10px] uppercase">Revision Chains</span>
            <span className="text-lg font-bold text-black">{data?.chains?.length || 0}</span>
          </div>
        </div>
      </div>

      {/* Revision Chains Visualization */}
      {data?.chains && data.chains.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500">
            Deck Version Chains (Detected Lineage)
          </h2>
          <div className="border border-[#e5e5e5] bg-white p-4 space-y-4">
            {data.chains.map((chain, cIdx) => (
              <div key={cIdx} className="space-y-2">
                <div className="text-xs font-mono font-bold text-black">
                  DOCUMENT #{chain.doc_number || "C2L-ARCH"} ({chain.versions.length} REVISIONS)
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  {chain.versions.map((ver, vIdx) => (
                    <div key={ver.id} className="flex items-center space-x-3">
                      <div className="border border-[#e5e5e5] p-3 bg-gray-50/50 min-w-[200px]">
                        <div className="flex items-center justify-between text-[10px] font-mono mb-1">
                          <span className="px-1.5 py-0.2 border border-black bg-black text-white">
                            REV {ver.revision || `v${vIdx + 1}`}
                          </span>
                          <span className="text-gray-500">{ver.source_name}</span>
                        </div>
                        <div className="font-mono text-xs font-semibold text-black truncate" title={ver.name}>
                          {ver.name}
                        </div>
                        <div className="text-[10px] font-mono text-gray-500 mt-1">
                          {formatBytes(ver.size)}
                        </div>
                      </div>
                      {vIdx < chain.versions.length - 1 && (
                        <div className="font-mono text-xs text-gray-400">→</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Visual Slide Diff Viewer */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500">
            Visual Slide Diff Viewer (Red Delta Bounding Box)
          </h2>
          {data?.relations && data.relations.length > 1 && (
            <select
              value={selectedRelation ? `${selectedRelation.a.id}_${selectedRelation.b.id}` : ""}
              onChange={(e) => {
                const [aId, bId] = e.target.value.split("_").map(Number);
                const rel = data.relations.find((r) => r.a.id === aId && r.b.id === bId);
                if (rel) setSelectedRelation(rel);
              }}
              className="border border-[#e5e5e5] px-3 py-1 text-xs font-mono bg-white"
            >
              {data.relations.map((r, i) => (
                <option key={i} value={`${r.a.id}_${r.b.id}`}>
                  Compare: {r.a.name} vs {r.b.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {selectedRelation && comparisonDetail && (
          <div className="border border-[#e5e5e5] bg-white p-6 space-y-6">
            {/* Slide Comparison Selector */}
            <div className="flex items-center space-x-2 overflow-x-auto pb-2 border-b border-[#e5e5e5]">
              <span className="text-[10px] font-mono text-gray-500 uppercase flex-shrink-0 mr-2">
                SLIDE PAIRS:
              </span>
              {comparisonDetail.pairs?.map((pair: any, pIdx: number) => {
                const isMod = pair.relation === "modified";
                const isSel = selectedPair === pair;
                return (
                  <button
                    key={pIdx}
                    onClick={() => setSelectedPair(pair)}
                    className={`px-2.5 py-1 text-xs font-mono border whitespace-nowrap transition-colors ${
                      isSel
                        ? "border-black bg-black text-white"
                        : isMod
                        ? "border-amber-600 bg-amber-50 text-amber-900"
                        : "border-[#e5e5e5] text-gray-600 hover:border-gray-400"
                    }`}
                  >
                    Slide {pair.page_a || pair.page_b} [{pair.relation.toUpperCase()}]
                  </button>
                );
              })}
            </div>

            {/* Side-by-Side Images & Delta */}
            {selectedPair && (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Left: Deck A Slide */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="font-bold text-black">{selectedRelation.a.name}</span>
                      <span className="text-gray-500">Slide {selectedPair.page_a}</span>
                    </div>
                    <div className="aspect-video bg-gray-50 border border-[#e5e5e5] overflow-hidden flex items-center justify-center">
                      {selectedPair.a?.image_key && (
                        <img
                          src={api.objectUrl(selectedPair.a.image_key)}
                          alt="Slide A"
                          className="w-full h-full object-contain"
                        />
                      )}
                    </div>
                  </div>

                  {/* Right: Deck B Slide */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="font-bold text-black">{selectedRelation.b.name}</span>
                      <span className="text-gray-500">Slide {selectedPair.page_b}</span>
                    </div>
                    <div className="aspect-video bg-gray-50 border border-[#e5e5e5] overflow-hidden flex items-center justify-center">
                      {selectedPair.b?.image_key && (
                        <img
                          src={api.objectUrl(selectedPair.b.image_key)}
                          alt="Slide B"
                          className="w-full h-full object-contain"
                        />
                      )}
                    </div>
                  </div>

                  {/* Middle/Diff: Red Delta Bounding Box */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="font-bold text-red-600">PERCEPTUAL DELTA</span>
                      <span className="text-gray-500">
                        {selectedPair.hamming !== undefined ? `Hamming: ${selectedPair.hamming}` : "DIFF"}
                      </span>
                    </div>
                    <div className="aspect-video bg-gray-900 border border-red-600 overflow-hidden flex items-center justify-center relative">
                      {selectedPair.a?.id && selectedPair.b?.id ? (
                        <img
                          src={api.diffImageUrl(selectedPair.a.id, selectedPair.b.id)}
                          alt="Perceptual Delta Diff"
                          className="w-full h-full object-contain"
                        />
                      ) : (
                        <span className="text-xs font-mono text-gray-400">Identical slide</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Text Diff View */}
                {selectedPair.text_diff && (
                  <div className="border border-[#e5e5e5] p-4 bg-gray-50 space-y-2">
                    <h4 className="text-xs font-mono uppercase text-gray-600 font-bold">
                      Extracted Text Modifications (Unified Diff)
                    </h4>
                    <pre className="text-xs font-mono text-gray-800 whitespace-pre-wrap overflow-x-auto bg-white p-3 border border-gray-200">
                      {selectedPair.text_diff}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Video Perceptual Duplicates */}
      {data?.video && data.video.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500">
            Video Duplicates Across Platforms (Audio & Perceptual Keyframe Match)
          </h2>
          <div className="space-y-3">
            {data.video.map((group, idx) => (
              <div key={idx} className="border border-[#e5e5e5] bg-white p-5 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#e5e5e5] pb-3">
                  <div>
                    <span className="text-xs font-mono text-gray-500">MATCH GROUP #{idx + 1}</span>
                    <h3 className="font-mono font-bold text-sm text-black">
                      {group.byte_identical ? "Byte-Identical Binary Duplicate" : "Perceptual Recording Match (Same Presentation)"}
                    </h3>
                  </div>
                  <div className="text-right font-mono">
                    <span className="text-[10px] text-gray-500 block">RECLAIMABLE BYTES</span>
                    <span className="text-sm font-bold text-green-600 font-mono">
                      {formatBytes(group.reclaimable)}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {group.files.map((file) => {
                    const isKeep = file.id === group.keep;
                    return (
                      <div
                        key={file.id}
                        className={`p-3 border ${
                          isKeep
                            ? "border-green-600 bg-green-50/20"
                            : "border-red-600 bg-red-50/20"
                        }`}
                      >
                        <div className="flex items-center justify-between text-[10px] font-mono mb-1">
                          <span
                            className={`px-1.5 py-0.5 border ${
                              isKeep
                                ? "border-green-600 text-green-700 bg-green-50 font-bold"
                                : "border-red-600 text-red-700 bg-red-50 font-bold"
                            }`}
                          >
                            {isKeep ? "KEEP MASTER COPY (GOVERNED)" : "SAFE TO DELETE (REDUNDANT)"}
                          </span>
                          <span className="text-gray-500">{file.source_name}</span>
                        </div>
                        <div className="font-mono text-xs font-semibold text-black truncate" title={file.name}>
                          {file.name}
                        </div>
                        <div className="text-[10px] font-mono text-gray-500 mt-1">
                          Size: {formatBytes(file.size)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
