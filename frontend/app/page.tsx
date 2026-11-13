"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, formatBytes } from "@/lib/api";
import { OverviewData, FileItem } from "@/lib/types";
import StagesTimeline from "@/components/StagesTimeline";

export default function OptimizeDashboard() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [ov, fl] = await Promise.all([api.getOverview(), api.getFiles()]);
      setOverview(ov);
      setFiles(fl);
    } catch (e: any) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleScan = async () => {
    setActionLoading("scan");
    try {
      const res = await api.scanSources();
      setActionMsg(`Discovered ${res.total} files across sources.`);
      await loadData();
    } catch (e: any) {
      setActionMsg(`Scan failed: ${e.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleProcess = async () => {
    setActionLoading("process");
    try {
      const res = await api.processQueue(undefined, true);
      setActionMsg(`Queued ${res.queued} files for background processing.`);
      await loadData();
    } catch (e: any) {
      setActionMsg(`Process failed: ${e.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleBenchmark = async () => {
    setActionLoading("benchmark");
    try {
      const res = await api.runBenchmark();
      setActionMsg(`Benchmark completed. Evaluated against official ground truth.`);
      await loadData();
    } catch (e: any) {
      setActionMsg(`Benchmark: ${e.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading && !overview) {
    return (
      <div className="py-24 text-center font-mono text-sm text-gray-500">
        LOADING DISTILL ENGINE STATE...
      </div>
    );
  }

  const storage = overview?.storage;
  const totalRaw = storage?.total_bytes || 0;
  const optimized = storage?.optimized_total_bytes || 0;
  const savingPct = storage?.total_saving_pct != null
    ? (storage.total_saving_pct * 100).toFixed(1)
    : "0.0";
  const savedBytes = Math.max(0, totalRaw - optimized);

  const fileList = Array.isArray(files) ? files : [];
  const filteredFiles = fileList.filter((f) => {
    if (!f) return false;
    if (filter === "all") return true;
    if (filter === "video") return f.kind === "video";
    if (filter === "docs") return f.kind === "pdf" || f.kind === "pptx";
    if (filter === "leaver") return f.source_name?.toLowerCase().includes("onedrive") || !f.governed;
    return true;
  });

  return (
    <div className="space-y-8">
      {/* Action Banner Message */}
      {actionMsg && (
        <div className="border border-black bg-black text-white px-4 py-2 text-xs font-mono flex items-center justify-between">
          <span>{actionMsg}</span>
          <button onClick={() => setActionMsg(null)} className="text-gray-400 hover:text-white">
            [CLOSE]
          </button>
        </div>
      )}

      {/* Hero Metric Section: Waterfall & Total Savings */}
      <section className="border border-[#e5e5e5] bg-white p-6">
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 pb-6 border-b border-[#e5e5e5]">
          <div>
            <div className="text-xs font-mono text-gray-500 uppercase tracking-widest mb-1">
              Ericsson Data Storage Optimization
            </div>
            <div className="flex items-baseline space-x-4">
              <span className="text-5xl font-mono font-bold tracking-tight text-black">
                {savingPct}%
              </span>
              <span className="text-sm font-mono text-green-600 font-semibold uppercase">
                Storage Reduction Confirmed
              </span>
            </div>
            <p className="text-xs text-gray-600 mt-2 max-w-xl">
              Distilled {overview?.counts?.files || fileList.length || 0} enterprise assets across SharePoint, EricssonPlay, and
              OneDrive into content-addressable lossless text, perceptual keyframes, and CAS slide vectors.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleScan}
              disabled={actionLoading !== null}
              className="px-4 py-2 border border-black text-xs font-mono text-black hover:bg-gray-100 disabled:opacity-50 transition-colors"
            >
              {actionLoading === "scan" ? "SCANNING..." : "SCAN SOURCES"}
            </button>
            <button
              onClick={handleProcess}
              disabled={actionLoading !== null}
              className="px-4 py-2 border border-black bg-black text-xs font-mono text-white hover:bg-gray-900 disabled:opacity-50 transition-colors"
            >
              {actionLoading === "process" ? "PROCESSING..." : "PROCESS QUEUE"}
            </button>
            <button
              onClick={handleBenchmark}
              disabled={actionLoading !== null}
              className="px-4 py-2 border border-[#e5e5e5] text-xs font-mono text-gray-700 hover:border-black transition-colors"
            >
              {actionLoading === "benchmark" ? "BENCHMARKING..." : "RUN BENCHMARK"}
            </button>
          </div>
        </div>

        {/* Waterfall Breakdown */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 pt-6">
          <div className="border border-[#e5e5e5] p-3">
            <div className="text-[10px] font-mono text-gray-500 uppercase">1. Raw Total</div>
            <div className="text-lg font-mono font-bold text-black mt-1">{formatBytes(totalRaw)}</div>
            <div className="text-[10px] text-gray-500 mt-0.5">Original input volume</div>
          </div>
          <div className="border border-[#e5e5e5] p-3">
            <div className="text-[10px] font-mono text-gray-500 uppercase">2. Video Distillation</div>
            <div className="text-lg font-mono font-bold text-black mt-1">
              -{formatBytes(
                overview?.storage?.tier_totals?.T0
                  ? (overview.storage.tier_totals.T0 - (overview.storage.tier_totals.T3 || 0))
                  : 0
              )}
            </div>
            <div className="text-[10px] text-gray-500 mt-0.5">T0 raw to T3 packet</div>
          </div>
          <div className="border border-[#e5e5e5] p-3">
            <div className="text-[10px] font-mono text-gray-500 uppercase">3. Slide Deduplication</div>
            <div className="text-lg font-mono font-bold text-black mt-1">
              -{formatBytes(overview?.storage?.dedup_savings?.doc_slide_cas_bytes || 0)}
            </div>
            <div className="text-[10px] text-gray-500 mt-0.5">Unique slide CAS</div>
          </div>
          <div className="border border-[#e5e5e5] p-3">
            <div className="text-[10px] font-mono text-gray-500 uppercase">4. Duplicate Pruning</div>
            <div className="text-lg font-mono font-bold text-black mt-1">
              -{formatBytes(overview?.total_reclaimable_bytes || 0)}
            </div>
            <div className="text-[10px] text-gray-500 mt-0.5">Leaver drive safe delete</div>
          </div>
          <div className="border border-black bg-black text-white p-3">
            <div className="text-[10px] font-mono text-gray-400 uppercase">5. Distilled Footprint</div>
            <div className="text-lg font-mono font-bold text-white mt-1">{formatBytes(optimized)}</div>
            <div className="text-[10px] text-green-400 mt-0.5 font-mono">
              Net saved: {formatBytes(savedBytes)}
            </div>
          </div>
        </div>
      </section>

      {/* 3 Source Buckets Side-by-Side */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500">
            Source Repositories (Governed vs Unregulated)
          </h2>
          <span className="text-xs font-mono text-gray-500">
            {overview?.counts?.sources || overview?.sources?.length || 0} CONNECTED SOURCES
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {overview?.sources && overview.sources.map((src) => {
            const isLeaver = src.kind === "onedrive" || !src.governed;
            return (
              <div
                key={src.id}
                className={`border p-4 flex flex-col justify-between ${
                  isLeaver ? "border-amber-600 bg-amber-50/20" : "border-[#e5e5e5] bg-white"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span
                      className={`text-[10px] font-mono uppercase px-1.5 py-0.5 border ${
                        src.governed
                          ? "border-black bg-black text-white"
                          : "border-amber-600 text-amber-700 bg-amber-50"
                      }`}
                    >
                      {src.governed ? "GOVERNED SOURCE OF TRUTH" : "UNREGULATED LEAVER DRIVE"}
                    </span>
                    <span className="text-xs font-mono text-gray-500 uppercase">{src.kind}</span>
                  </div>
                  <h3 className="font-mono font-bold text-sm text-black truncate" title={src.name}>
                    {src.name}
                  </h3>
                  <div className="text-xs text-gray-500 mt-1 truncate font-mono">
                    {src.owner ? `Owner: ${src.owner}` : "Central Repository"}
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-[#e5e5e5] grid grid-cols-2 gap-2 text-xs font-mono">
                  <div>
                    <span className="text-gray-500 block text-[10px]">TOTAL FILES</span>
                    <span className="font-semibold text-black">{src.file_count || 0}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 block text-[10px]">RAW SIZE</span>
                    <span className="font-semibold text-black">{formatBytes(src.bytes)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 block text-[10px]">VIDEOS / DOCS</span>
                    <span className="text-gray-800">
                      {src.videos || 0}v / {src.docs || 0}d
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500 block text-[10px]">STATUS</span>
                    <span className="text-green-600 font-semibold">{src.done || 0} PROCESSED</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Asset Inventory Table */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center space-x-2">
            <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500">Asset Inventory</h2>
            <span className="text-xs font-mono text-gray-400">({files.length} items)</span>
          </div>

          <div className="flex items-center space-x-1 border border-[#e5e5e5] p-0.5 bg-white text-xs font-mono">
            {[
              { id: "all", label: "ALL" },
              { id: "video", label: "VIDEOS" },
              { id: "docs", label: "DOCUMENTS" },
              { id: "leaver", label: "LEAVER DRIVE" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setFilter(tab.id)}
                className={`px-3 py-1 transition-colors ${
                  filter === tab.id ? "bg-black text-white" : "text-gray-600 hover:text-black"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="border border-[#e5e5e5] bg-white overflow-x-auto">
          <table className="w-full text-left text-xs font-mono border-collapse">
            <thead>
              <tr className="border-b border-[#e5e5e5] bg-gray-50 text-gray-500 uppercase text-[10px]">
                <th className="py-2.5 px-4 font-normal">Asset Name</th>
                <th className="py-2.5 px-3 font-normal">Source</th>
                <th className="py-2.5 px-3 font-normal">Kind</th>
                <th className="py-2.5 px-3 font-normal">Raw Size</th>
                <th className="py-2.5 px-3 font-normal">Pipeline Stages</th>
                <th className="py-2.5 px-3 font-normal">Status</th>
                <th className="py-2.5 px-4 font-normal text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e5e5e5]">
              {filteredFiles.map((file) => (
                <tr key={file.id} className="hover:bg-gray-50/70 transition-colors">
                  <td className="py-3 px-4 font-semibold text-black max-w-xs truncate" title={file.name}>
                    <Link href={`/files/${file.id}`} className="hover:underline flex items-center space-x-2">
                      <span>{file.name}</span>
                    </Link>
                    <span className="block text-[10px] text-gray-400 font-normal truncate mt-0.5">
                      {file.sha256 ? `${file.sha256.substring(0, 16)}...` : file.rel_path}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-gray-600 whitespace-nowrap">
                    <span
                      className={`inline-block px-1.5 py-0.5 border text-[10px] ${
                        file.governed
                          ? "border-gray-300 text-gray-700 bg-gray-50"
                          : "border-amber-600 text-amber-700 bg-amber-50"
                      }`}
                    >
                      {file.source_name || "Unknown"}
                    </span>
                  </td>
                  <td className="py-3 px-3 uppercase text-gray-600 whitespace-nowrap">{file.kind}</td>
                  <td className="py-3 px-3 text-black whitespace-nowrap">{formatBytes(file.size)}</td>
                  <td className="py-3 px-3">
                    <StagesTimeline fileId={file.id} initialStatus={file.status} />
                  </td>
                  <td className="py-3 px-3 whitespace-nowrap">
                    <span
                      className={`px-2 py-0.5 text-[10px] uppercase font-bold border ${
                        file.status === "done"
                          ? "border-green-600 text-green-700 bg-green-50"
                          : file.status === "error"
                          ? "border-red-600 text-red-700 bg-red-50"
                          : file.status === "skipped"
                          ? "border-gray-300 text-gray-500 bg-gray-50"
                          : "border-black text-black bg-gray-100"
                      }`}
                    >
                      {file.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right whitespace-nowrap">
                    <Link
                      href={`/files/${file.id}`}
                      className="px-2.5 py-1 border border-black text-[11px] text-black hover:bg-black hover:text-white transition-colors"
                    >
                      INSPECT
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
