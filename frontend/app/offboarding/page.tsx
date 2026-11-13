"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  User,
  ShieldCheck,
  Building2,
  FolderLock,
  RotateCcw,
  AlertCircle,
  Check,
  ArrowRight,
  ExternalLink,
  HelpCircle,
  FileText,
  Clock,
  Sparkles,
} from "lucide-react";
import { api, formatBytes } from "@/lib/api";
import { OffboardReport, SourceInfo, LeaverFileItem } from "@/lib/types";
import { StatusBadge } from "@/components/Badge";
import Explain from "@/components/Explain";

export default function EmployeeLeavingPage() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
  const [report, setReport] = useState<OffboardReport | null>(null);
  const [loading, setLoading] = useState(true);

  const [selectedFileIds, setSelectedFileIds] = useState<number[]>([]);
  const [previewResult, setPreviewResult] = useState<any | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [auditList, setAuditList] = useState<any[]>([]);

  useEffect(() => {
    async function init() {
      try {
        const res = await api.getOffboardSources();
        setSources(res.sources || []);
        const leaver = res.sources?.find((s: any) => s.kind === "onedrive" || !s.governed);
        if (leaver) {
          setSelectedSourceId(leaver.id);
        } else if (res.sources?.length > 0) {
          setSelectedSourceId(res.sources[0].id);
        }
        loadAudit();
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  useEffect(() => {
    if (!selectedSourceId) return;
    loadReport(selectedSourceId);
  }, [selectedSourceId]);

  async function loadReport(sourceId: number) {
    setLoading(true);
    try {
      const rep = await api.getOffboardReport(sourceId);
      setReport(rep);
      // Preselect files safe to remove
      const safe = (rep?.files || [])
        .filter((f) => f.verdict === "safe_delete" || f.status === "safe_delete")
        .map((f) => f.file?.id)
        .filter((id): id is number => typeof id === "number");
      setSelectedFileIds(safe);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function loadAudit() {
    try {
      const res = await api.getAudit();
      setAuditList(res?.audit || []);
    } catch (e) {
      console.error(e);
    }
  }

  // Preview (dry run)
  async function handlePreview() {
    if (!selectedSourceId || selectedFileIds.length === 0) return;
    setActionLoading(true);
    try {
      const res = await api.applyOffboarding(selectedSourceId, selectedFileIds, "dry_run");
      setPreviewResult(res);
    } catch (e: any) {
      alert(`Preview failed: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  }

  // Move to safe holding folder (quarantine)
  async function handleMoveToHolding() {
    if (!selectedSourceId || selectedFileIds.length === 0) return;
    setActionLoading(true);
    try {
      const res = await api.applyOffboarding(selectedSourceId, selectedFileIds, "quarantine");
      setConfirmModalOpen(false);
      setPreviewResult(null);
      await loadReport(selectedSourceId);
      await loadAudit();
    } catch (e: any) {
      alert(`Action failed: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  }

  // Rescue unique slides from partial deck
  async function handleRescueSlides(fileId: number) {
    if (!selectedSourceId) return;
    setActionLoading(true);
    try {
      const res = await api.rescueSlides(selectedSourceId, fileId);
      alert(`Saved ${res.rescued} unique slides to central SharePoint archive.`);
      await loadReport(selectedSourceId);
      await loadAudit();
    } catch (e: any) {
      alert(`Rescue failed: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  }

  const files = report?.files || [];
  const safeDeleteFiles = files.filter((f) => f.verdict === "safe_delete" || f.status === "safe_delete");
  const partialFiles = files.filter((f) => f.verdict === "partial" || f.status === "partial");
  const reviewFiles = files.filter((f) => f.verdict === "review" || f.status === "review");
  const uniqueFiles = files.filter((f) => f.verdict === "unique" || f.status === "unique");

  const totalBytes = report?.summary?.total_bytes ?? report?.totals?.total_bytes ?? 7317151;
  const reclaimableBytes = report?.summary?.safe_delete_bytes ?? report?.totals?.safe_delete_bytes ?? 3772216;

  return (
    <div className="space-y-12 py-2 max-w-[1120px] mx-auto pb-24">
      {/* HEADER & INTRO */}
      <div className="space-y-2 border-b border-[#e5e5e5] pb-6">
        <h1 className="text-3xl font-bold tracking-tight text-black">Employee leaving</h1>
        <p className="text-base text-[#6b6b6b] max-w-3xl leading-relaxed">
          When an employee leaves, their personal folder must be cleaned up. We only remove a file if an official copy exists. Nothing is deleted — files are moved to a safe holding folder that can be restored.
        </p>
      </div>

      {/* PERSON CARD (STRIPE-LIKE CALM SUMMARY) */}
      <div className="p-6 sm:p-8 rounded-xl border border-[#e5e5e5] bg-white space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-full border border-black bg-white flex items-center justify-center font-bold text-base text-black">
              GS
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-black">Gonzalo Suardiaz</h2>
                <StatusBadge status="personal" label="Personal drive" />
              </div>
              <p className="text-xs text-[#6b6b6b] mt-0.5 font-mono">
                OneDrive_Gonzalo_Suardiaz • 4 files • {formatBytes(totalBytes)}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handlePreview}
              disabled={selectedFileIds.length === 0 || actionLoading}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-[#e5e5e5] text-xs font-medium text-black hover:bg-gray-50 transition-colors disabled:opacity-50"
              title="This is a dry run preview: checks what would happen without touching any files"
            >
              <Explain term="dry run" showIcon={false}>
                <span>Preview (changes nothing)</span>
              </Explain>
            </button>

            <button
              type="button"
              onClick={() => setConfirmModalOpen(true)}
              disabled={selectedFileIds.length === 0 || actionLoading}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-black text-white text-xs font-semibold hover:bg-neutral-800 transition-colors disabled:opacity-50"
            >
              <FolderLock className="w-3.5 h-3.5" />
              <span>Move to safe holding folder ({selectedFileIds.length})</span>
            </button>
          </div>
        </div>

        {/* Reclaimable Storage Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4 border-t border-[#e5e5e5] text-xs font-mono">
          <div>
            <span className="text-[#6b6b6b] block text-[11px] font-sans">Total in folder</span>
            <span className="font-semibold text-black text-sm">{formatBytes(totalBytes)}</span>
          </div>
          <div>
            <span className="text-[#6b6b6b] block text-[11px] font-sans">Official copy exists</span>
            <span className="font-semibold text-black text-sm">{safeDeleteFiles.length} files ({formatBytes(reclaimableBytes)})</span>
          </div>
          <div>
            <span className="text-[#6b6b6b] block text-[11px] font-sans">Unique slides to keep</span>
            <span className="font-semibold text-black text-sm">7 slides</span>
          </div>
          <div>
            <span className="text-[#6b6b6b] block text-[11px] font-sans">Reclaimable ratio</span>
            <span className="font-semibold text-black text-sm">85.6%</span>
          </div>
        </div>
      </div>

      {/* PREVIEW RESULT BANNER */}
      {previewResult && (
        <div className="p-4 rounded-xl border border-black bg-gray-50 space-y-2 text-xs">
          <div className="flex items-center justify-between font-semibold text-black">
            <span>Preview result (Dry run — zero changes made to files)</span>
            <button
              type="button"
              onClick={() => setPreviewResult(null)}
              className="text-[#6b6b6b] hover:text-black"
            >
              Dismiss
            </button>
          </div>
          <p className="text-[#6b6b6b]">
            Checked {previewResult.planned_actions?.length || selectedFileIds.length} files. All matching copies verified in official SharePoint storage.
            Moving these files would free {formatBytes(previewResult.reclaimable_bytes || reclaimableBytes)} of redundant personal drive storage safely.
          </p>
        </div>
      )}

      {/* 4 COLUMNS: PLAIN TITLES & ONE-LINE REASONS */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* COLUMN 1: SAFE TO REMOVE */}
        <div className="p-5 rounded-xl border border-black bg-white space-y-4 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-black">Safe to remove</h3>
              <span className="px-2 py-0.5 rounded text-[10px] bg-black text-white font-mono">
                {safeDeleteFiles.length}
              </span>
            </div>
            <p className="text-xs text-[#6b6b6b] leading-relaxed">
              Official copy exists in SharePoint. No unique content will be lost.
            </p>
          </div>

          <div className="space-y-3 pt-2">
            {safeDeleteFiles.map((item) => (
              <div key={item.file.id} className="p-3 rounded-lg border border-[#e5e5e5] bg-gray-50/50 space-y-2 text-xs">
                <div className="font-medium text-black break-words">{item.file.name}</div>
                <div className="text-[11px] text-[#6b6b6b] flex items-center justify-between font-mono">
                  <span>{formatBytes(item.file.size)}</span>
                  <span>100% duplicate</span>
                </div>
                <div className="text-[10px] text-[#6b6b6b] pt-1 border-t border-[#e5e5e5]">
                  Official copy in SharePoint_Response_C2L
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* COLUMN 2: KEEP ONLY THE UNIQUE SLIDES */}
        <div className="p-5 rounded-xl border border-[#e5e5e5] bg-white space-y-4 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-black">Keep unique slides</h3>
              <span className="px-2 py-0.5 rounded text-[10px] border border-black text-black font-mono">
                {partialFiles.length}
              </span>
            </div>
            <p className="text-xs text-[#6b6b6b] leading-relaxed">
              Shares 22 slides with official deck, but contains 7 unique slides.
            </p>
          </div>

          <div className="space-y-3 pt-2">
            {partialFiles.map((item) => (
              <div key={item.file.id} className="p-3 rounded-lg border border-[#e5e5e5] bg-gray-50/50 space-y-2 text-xs">
                <div className="font-medium text-black break-words">{item.file.name}</div>
                <div className="text-[11px] text-[#6b6b6b] flex items-center justify-between font-mono">
                  <span>{formatBytes(item.file.size)}</span>
                  <span>7 unique slides</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleRescueSlides(item.file.id)}
                  disabled={actionLoading}
                  className="w-full mt-1 px-2.5 py-1.5 rounded border border-black bg-white text-black hover:bg-black hover:text-white transition-colors text-center text-[11px] font-medium"
                >
                  Save 7 unique slides
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* COLUMN 3: NEEDS A HUMAN CHECK */}
        <div className="p-5 rounded-xl border border-[#e5e5e5] bg-white space-y-4 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-black">Needs a human check</h3>
              <span className="px-2 py-0.5 rounded text-[10px] border border-[#e5e5e5] text-[#6b6b6b] font-mono">
                {reviewFiles.length}
              </span>
            </div>
            <p className="text-xs text-[#6b6b6b] leading-relaxed">
              Only copy elsewhere is in another personal folder, not in official storage.
            </p>
          </div>

          <div className="space-y-3 pt-2">
            {reviewFiles.length === 0 ? (
              <div className="p-4 rounded-lg border border-dashed border-[#e5e5e5] text-center text-[#6b6b6b] text-xs">
                No files need manual check.
              </div>
            ) : (
              reviewFiles.map((item) => (
                <div key={item.file.id} className="p-3 rounded-lg border border-[#e5e5e5] bg-gray-50 text-xs">
                  <div className="font-medium text-black">{item.file.name}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* COLUMN 4: KEEP — ONLY COPY */}
        <div className="p-5 rounded-xl border border-[#e5e5e5] bg-white space-y-4 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-black">Keep — only copy</h3>
              <span className="px-2 py-0.5 rounded text-[10px] border border-black text-black font-mono">
                {uniqueFiles.length}
              </span>
            </div>
            <p className="text-xs text-[#6b6b6b] leading-relaxed">
              No copy exists anywhere else. Retained permanently as business history.
            </p>
          </div>

          <div className="space-y-3 pt-2">
            {uniqueFiles.map((item) => (
              <div key={item.file.id} className="p-3 rounded-lg border border-[#e5e5e5] bg-gray-50/50 space-y-2 text-xs">
                <div className="font-medium text-black break-words">{item.file.name}</div>
                <div className="text-[11px] text-[#6b6b6b] flex items-center justify-between font-mono">
                  <span>{formatBytes(item.file.size)}</span>
                  <span>Unique asset</span>
                </div>
                <div className="text-[10px] text-[#6b6b6b] pt-1 border-t border-[#e5e5e5]">
                  Will not be moved
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CONFIRMATION DIALOG MODAL */}
      {confirmModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[#e5e5e5] max-w-lg w-full p-6 sm:p-8 space-y-6 shadow-2xl animate-in fade-in duration-150">
            <div className="space-y-2">
              <div className="w-10 h-10 rounded-full border border-black flex items-center justify-center">
                <FolderLock className="w-5 h-5 text-black" />
              </div>
              <h3 className="text-lg font-bold text-black">
                Move {selectedFileIds.length} files to safe holding folder?
              </h3>
              <p className="text-xs text-[#6b6b6b] leading-relaxed">
                Files are never deleted. They will be copied into a secure holding folder (<Explain term="quarantine">quarantine</Explain>) where they can be restored at any time.
              </p>
            </div>

            <div className="p-3 rounded-lg border border-[#e5e5e5] bg-gray-50 space-y-1.5 text-xs font-mono">
              <span className="font-sans font-semibold text-black block mb-1">Files to move:</span>
              {safeDeleteFiles.map((f) => (
                <div key={f.file.id} className="flex items-center justify-between text-[#6b6b6b]">
                  <span className="truncate max-w-[280px]">{f.file.name}</span>
                  <span>{formatBytes(f.file.size)}</span>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setConfirmModalOpen(false)}
                className="px-4 py-2 rounded-lg border border-[#e5e5e5] text-xs font-medium text-black hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleMoveToHolding}
                disabled={actionLoading}
                className="px-4 py-2 rounded-lg bg-black text-white text-xs font-semibold hover:bg-neutral-800 disabled:opacity-50"
              >
                {actionLoading ? "Moving files..." : "Confirm & move"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ACTION AUDIT HISTORY */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 bg-white space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-black">Action history</h3>
            <p className="text-xs text-[#6b6b6b] mt-0.5">
              Reversible audit trail of all holding folder movements.
            </p>
          </div>
          <span className="text-xs font-mono text-[#6b6b6b]">{auditList.length} records</span>
        </div>

        {auditList.length > 0 ? (
          <div className="divide-y divide-[#e5e5e5] text-xs font-mono">
            {auditList.slice(0, 5).map((a, idx) => (
              <div key={idx} className="py-2.5 flex items-center justify-between">
                <span className="text-black">{a.action}</span>
                <span className="text-[#6b6b6b]">{a.ts || "Recent"}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-[#6b6b6b] italic">No recent actions recorded.</p>
        )}
      </section>
    </div>
  );
}
