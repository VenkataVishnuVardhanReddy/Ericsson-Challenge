"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, formatBytes } from "@/lib/api";
import { OffboardReport, SourceInfo } from "@/lib/types";

export default function OffboardingPage() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
  const [report, setReport] = useState<OffboardReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [mode, setMode] = useState<"dry_run" | "quarantine">("dry_run");
  const [selectedFileIds, setSelectedFileIds] = useState<number[]>([]);
  const [actionResult, setActionResult] = useState<any | null>(null);
  const [confirmModal, setConfirmModal] = useState(false);
  const [rescueLoading, setRescueLoading] = useState<number | null>(null);

  useEffect(() => {
    api
      .getOffboardSources()
      .then((res) => {
        setSources(res.sources || []);
        const leaver = res.sources?.find((s: any) => s.kind === "onedrive" || !s.governed);
        if (leaver) {
          setSelectedSourceId(leaver.id);
        } else if (res.sources?.length > 0) {
          setSelectedSourceId(res.sources[0].id);
        }
      })
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedSourceId) return;
    setLoading(true);
    setActionResult(null);
    api
      .getOffboardReport(selectedSourceId)
      .then((rep) => {
        setReport(rep);
        // Pre-select files with verdict safe_delete
        const filesList = rep?.files || [];
        const safe = filesList
          .filter((f) => f.verdict === "safe_delete" || f.status === "safe_delete")
          .map((f) => f.file?.id)
          .filter((id): id is number => typeof id === "number");
        setSelectedFileIds(safe);
      })
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, [selectedSourceId]);

  const handleApply = async () => {
    if (!selectedSourceId || selectedFileIds.length === 0) return;
    setActionLoading(true);
    try {
      const res = await api.applyOffboarding(selectedSourceId, selectedFileIds, mode);
      setActionResult(res);
      setConfirmModal(false);
      // Reload report
      const updated = await api.getOffboardReport(selectedSourceId);
      setReport(updated);
    } catch (e: any) {
      alert(`Action failed: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRescue = async (fileId: number) => {
    if (!selectedSourceId) return;
    setRescueLoading(fileId);
    try {
      const res = await api.rescueSlides(selectedSourceId, fileId);
      alert(`Rescued ${res.rescued} unique slides to central governed SharePoint archive.`);
      const updated = await api.getOffboardReport(selectedSourceId);
      setReport(updated);
    } catch (e: any) {
      alert(`Rescue failed: ${e.message}`);
    } finally {
      setRescueLoading(null);
    }
  };

  const toggleSelectFile = (id: number) => {
    setSelectedFileIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border border-[#e5e5e5] bg-white p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-mono font-bold text-black">
              Employee Offboarding & Leaver Drive Quarantine
            </h1>
            <p className="text-xs text-gray-600 mt-1 max-w-3xl">
              When an employee departs, their personal OneDrive files are audited against central governed repositories
              (SharePoint & EricssonPlay). Files are deleted only when guaranteed duplicates exist in governed storage.
            </p>
          </div>

          {sources.length > 0 && (
            <div className="flex items-center space-x-2">
              <span className="text-xs font-mono text-gray-500 uppercase">SELECT LEAVER:</span>
              <select
                value={selectedSourceId || ""}
                onChange={(e) => setSelectedSourceId(Number(e.target.value))}
                className="border border-black px-3 py-1.5 text-xs font-mono bg-white font-bold"
              >
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.owner || s.name} ({s.kind.toUpperCase()})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Leaver Summary Cards */}
        {report && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-4 border-t border-[#e5e5e5] text-xs font-mono">
            <div className="border border-[#e5e5e5] p-3">
              <span className="text-gray-500 block text-[10px] uppercase">Total Files in Drive</span>
              <span className="text-lg font-bold text-black mt-1">
                {report.summary?.total_files ?? report.totals?.total_files ?? 0}
              </span>
              <span className="text-[10px] text-gray-400 block mt-0.5 font-sans">
                {formatBytes(report.summary?.total_bytes ?? report.totals?.total_bytes)} raw storage
              </span>
            </div>

            <div className="border border-green-600 bg-green-50/20 p-3">
              <span className="text-green-700 block text-[10px] uppercase font-bold">Safe to Delete</span>
              <span className="text-lg font-bold text-green-700 mt-1">
                {report.summary?.safe_delete_count ?? report.totals?.safe_delete_files ?? 0}
              </span>
              <span className="text-[10px] text-green-700 block mt-0.5">
                {formatBytes(report.summary?.safe_delete_bytes ?? report.totals?.safe_delete_bytes)} 100% duplicate
              </span>
            </div>

            <div className="border border-amber-600 bg-amber-50/20 p-3">
              <span className="text-amber-800 block text-[10px] uppercase font-bold">
                Partial / Unique
              </span>
              <span className="text-lg font-bold text-amber-800 mt-1">
                {(report.summary?.partial_count ?? report.totals?.partial_files ?? 0) +
                  (report.summary?.unique_count ?? report.totals?.unique_files ?? 0)}
              </span>
              <span className="text-[10px] text-amber-700 block mt-0.5">
                Contains unbacked-up slides
              </span>
            </div>

            <div className="border border-black bg-black text-white p-3">
              <span className="text-gray-400 block text-[10px] uppercase">Reclaimable Ratio</span>
              <span className="text-lg font-bold text-white mt-1">
                {report.summary?.reclaimable_pct ?? (report.totals?.reclaimable_pct ? Math.round(report.totals.reclaimable_pct * 100) : 0)}%
              </span>
              <span className="text-[10px] text-green-400 block mt-0.5 font-mono">
                {formatBytes(report.summary?.safe_delete_bytes ?? report.totals?.safe_delete_bytes)} reclaimable
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Action Bar */}
      <section className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 border border-[#e5e5e5] bg-white">
        <div className="flex items-center space-x-3 text-xs font-mono">
          <span className="text-gray-500 uppercase">POLICY MODE:</span>
          <label className="flex items-center space-x-1.5 cursor-pointer">
            <input
              type="radio"
              name="mode"
              checked={mode === "dry_run"}
              onChange={() => setMode("dry_run")}
              className="accent-black"
            />
            <span className="text-black font-semibold">DRY RUN (AUDIT LOG ONLY)</span>
          </label>
          <label className="flex items-center space-x-1.5 cursor-pointer">
            <input
              type="radio"
              name="mode"
              checked={mode === "quarantine"}
              onChange={() => setMode("quarantine")}
              className="accent-red-600"
            />
            <span className="text-red-600 font-semibold">QUARANTINE (SAFE ISOLATION)</span>
          </label>
        </div>

        <div className="flex items-center space-x-3">
          <span className="text-xs font-mono text-gray-500">
            {selectedFileIds.length} files selected
          </span>
          <button
            onClick={() => setConfirmModal(true)}
            disabled={selectedFileIds.length === 0 || actionLoading}
            className={`px-4 py-2 text-xs font-mono font-bold transition-colors border ${
              mode === "quarantine"
                ? "border-red-600 bg-red-600 text-white hover:bg-red-700"
                : "border-black bg-black text-white hover:bg-gray-800"
            } disabled:opacity-40`}
          >
            {mode === "quarantine" ? "EXECUTE QUARANTINE" : "RUN AUDIT DRY-RUN"}
          </button>
        </div>
      </section>

      {/* Action Result Notification */}
      {actionResult && (
        <div className="border border-black bg-gray-50 p-4 font-mono text-xs space-y-2">
          <div className="font-bold text-black uppercase">Operation Result:</div>
          <pre className="text-[11px] text-gray-800 overflow-x-auto">
            {JSON.stringify(actionResult, null, 2)}
          </pre>
        </div>
      )}

      {/* File Audit Table */}
      <section className="border border-[#e5e5e5] bg-white overflow-x-auto">
        <table className="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr className="border-b border-[#e5e5e5] bg-gray-50 text-gray-500 uppercase text-[10px]">
              <th className="py-2.5 px-4 font-normal w-10">
                <input
                  type="checkbox"
                  checked={
                    report?.files.length !== 0 &&
                    selectedFileIds.length === (report?.files.length || 0)
                  }
                  onChange={(e) => {
                    if (e.target.checked && report) {
                      setSelectedFileIds(report.files.map((f) => f.file.id));
                    } else {
                      setSelectedFileIds([]);
                    }
                  }}
                  className="accent-black"
                />
              </th>
              <th className="py-2.5 px-4 font-normal">File Name</th>
              <th className="py-2.5 px-3 font-normal">Size</th>
              <th className="py-2.5 px-3 font-normal">Verdict</th>
              <th className="py-2.5 px-3 font-normal">Governed Backup Source</th>
              <th className="py-2.5 px-3 font-normal">Reclaimable</th>
              <th className="py-2.5 px-4 font-normal text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#e5e5e5]">
            {report?.files.map((item) => {
              const f = item.file;
              const isSelected = selectedFileIds.includes(f.id);
              return (
                <tr key={f.id} className="hover:bg-gray-50/70 transition-colors">
                  <td className="py-3 px-4">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelectFile(f.id)}
                      className="accent-black"
                    />
                  </td>
                  <td className="py-3 px-4 max-w-xs truncate" title={f.name}>
                    <Link href={`/files/${f.id}`} className="font-semibold text-black hover:underline block">
                      {f.name}
                    </Link>
                    <span className="text-[10px] text-gray-500 font-sans block mt-0.5">{item.reason}</span>
                  </td>
                  <td className="py-3 px-3 text-gray-700 whitespace-nowrap">{formatBytes(f.size)}</td>
                  <td className="py-3 px-3 whitespace-nowrap">
                    {(() => {
                      const st = item.verdict || item.status;
                      return (
                        <span
                          className={`px-2 py-0.5 text-[10px] font-bold border uppercase ${
                            st === "safe_delete"
                              ? "border-green-600 text-green-700 bg-green-50"
                              : st === "partial"
                              ? "border-amber-600 text-amber-700 bg-amber-50"
                              : st === "review"
                              ? "border-purple-600 text-purple-700 bg-purple-50"
                              : "border-black text-black bg-gray-100"
                          }`}
                        >
                          {st === "safe_delete"
                            ? "SAFE TO DELETE"
                            : st === "partial"
                            ? "PARTIAL DUPLICATE"
                            : st === "review"
                            ? "REVIEW NEEDED"
                            : "UNIQUE ASSET"}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="py-3 px-3 whitespace-nowrap text-gray-600">
                    {item.matches && item.matches.length > 0 ? (
                      <span className="border border-gray-200 px-1.5 py-0.5 bg-gray-50 text-[10px]">
                        {item.matches[0].source_name} ({item.matches[0].name || "Identical"})
                      </span>
                    ) : (
                      <span className="text-gray-400">None</span>
                    )}
                  </td>
                  <td className="py-3 px-3 font-semibold whitespace-nowrap text-green-600">
                    {formatBytes(item.reclaimable_bytes)}
                  </td>
                  <td className="py-3 px-4 text-right whitespace-nowrap">
                    {item.verdict === "partial" ? (
                      <button
                        onClick={() => handleRescue(f.id)}
                        disabled={rescueLoading === f.id}
                        className="px-2.5 py-1 border border-amber-600 bg-amber-50 text-amber-900 text-[11px] hover:bg-amber-100 transition-colors"
                      >
                        {rescueLoading === f.id ? "RESCUING..." : "RESCUE SLIDES"}
                      </button>
                    ) : (
                      <Link
                        href={`/files/${f.id}`}
                        className="px-2.5 py-1 border border-black text-[11px] text-black hover:bg-black hover:text-white transition-colors"
                      >
                        DETAILS
                      </Link>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* Confirmation Modal */}
      {confirmModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-black max-w-md w-full p-6 space-y-4 font-mono text-xs">
            <div className="flex items-center space-x-2 text-red-600 font-bold uppercase text-sm">
              <span>CONFIRM OFFBOARDING ACTION</span>
            </div>

            <p className="text-gray-700 font-sans text-xs leading-relaxed">
              You are about to apply <strong>{mode.toUpperCase()}</strong> to {selectedFileIds.length} file(s).
              In quarantine mode, files are safely isolated in <code>.quarantine/</code> with SHA-256 audit logs and can be restored anytime.
            </p>

            <div className="p-3 bg-gray-50 border border-gray-200 text-black">
              Total storage to reclaim:{" "}
              <strong>
                {formatBytes(
                  report?.files
                    .filter((f) => selectedFileIds.includes(f.file.id))
                    .reduce((acc, curr) => acc + curr.reclaimable_bytes, 0)
                )}
              </strong>
            </div>

            <div className="flex justify-end space-x-2 pt-2">
              <button
                onClick={() => setConfirmModal(false)}
                className="px-4 py-2 border border-gray-300 text-gray-700 hover:border-black"
              >
                CANCEL
              </button>
              <button
                onClick={handleApply}
                disabled={actionLoading}
                className="px-4 py-2 border border-red-600 bg-red-600 text-white font-bold hover:bg-red-700"
              >
                {actionLoading ? "APPLYING..." : "PROCEED"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
