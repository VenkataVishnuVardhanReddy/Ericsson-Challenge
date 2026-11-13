import {
  OverviewData,
  FileItem,
  FileStages,
  FileIntegrity,
  RecordingDetail,
  DocumentDetail,
  DuplicatesData,
  OffboardReport,
  SearchResult,
  PipelineInfo,
} from "./types";

const API_BASE = typeof window !== "undefined" ? "" : (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000");

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`API Error ${res.status}: ${errorText || res.statusText}`);
  }
  return res.json();
}

export const api = {
  getOverview: async (): Promise<OverviewData | null> => {
    try {
      return await fetchJson<OverviewData>("/api/overview");
    } catch (e) {
      console.error("Failed to load overview:", e);
      return null;
    }
  },

  getFiles: async (): Promise<FileItem[]> => {
    try {
      const res = await fetchJson<any>("/api/files");
      if (Array.isArray(res)) return res;
      if (res && Array.isArray(res.files)) return res.files;
      return [];
    } catch (e) {
      console.error("Failed to load files:", e);
      return [];
    }
  },

  getFileStages: (id: number) => fetchJson<FileStages>(`/api/files/${id}/stages`),

  getFileIntegrity: (id: number) => fetchJson<FileIntegrity>(`/api/files/${id}/integrity`),

  getRecording: (id: number) => fetchJson<RecordingDetail>(`/api/recordings/${id}`),

  getDocument: (id: number) => fetchJson<DocumentDetail>(`/api/documents/${id}`),

  getDuplicates: () => fetchJson<DuplicatesData>("/api/duplicates"),

  getCompare: (aId: number, bId: number) => fetchJson<any>(`/api/compare/${aId}/${bId}`),

  search: (q: string, k = 20, kind?: string) => {
    const params = new URLSearchParams({ q, k: String(k) });
    if (kind && kind !== "all") params.set("kind", kind);
    return fetchJson<{ query: string; results: SearchResult[] }>(`/api/search?${params.toString()}`);
  },

  aiAsk: (question: string, k = 6) =>
    fetchJson<{ answer: string; citations: any[] }>("/api/ai/ask", {
      method: "POST",
      body: JSON.stringify({ question, k }),
    }),

  exportCorpusUrl: (fmt = "jsonl", redact = true) =>
    `${API_BASE}/api/ai/export?fmt=${fmt}&redact_pii=${redact}&download=true`,

  getOffboardSources: () => fetchJson<{ sources: any[] }>("/api/offboard"),

  getOffboardReport: (sourceId: number) => fetchJson<OffboardReport>(`/api/offboard/${sourceId}`),

  applyOffboarding: (sourceId: number, fileIds: number[], mode: "dry_run" | "quarantine") =>
    fetchJson<any>(`/api/offboard/${sourceId}/apply`, {
      method: "POST",
      body: JSON.stringify({ file_ids: fileIds, mode }),
    }),

  rescueSlides: (sourceId: number, fileId: number) =>
    fetchJson<any>(`/api/offboard/${sourceId}/rescue/${fileId}`, {
      method: "POST",
    }),

  scanSources: (roots?: string[]) =>
    fetchJson<{ discovered: any[]; total: number }>("/api/scan", {
      method: "POST",
      body: JSON.stringify({ roots }),
    }),

  processQueue: (fileIds?: number[], all = false) =>
    fetchJson<{ queued: number; job_ids: string[] }>("/api/process", {
      method: "POST",
      body: JSON.stringify({ file_ids: fileIds, all }),
    }),

  getPipelineInfo: () => fetchJson<PipelineInfo>("/api/pipeline/info"),

  runBenchmark: () => fetchJson<any>("/api/benchmark"),

  objectUrl: (key: string) => `${API_BASE}/api/objects/${key}`,

  rawFileUrl: (id: number) => `${API_BASE}/api/files/${id}/raw`,

  audioUrl: (id: number) => `${API_BASE}/api/recordings/${id}/audio`,

  frameUrl: (id: number, t: number) => `${API_BASE}/api/recordings/${id}/frame?t=${t}`,

  diffImageUrl: (slideA: number, slideB: number) => `${API_BASE}/api/diff-image/${slideA}/${slideB}`,

  recreatedVideoUrl: (id: number, mode = "audio_slides") =>
    `${API_BASE}/api/recordings/${id}/recreated?mode=${mode}`,

  recreateVideo: (id: number, mode = "audio_slides", force = false) =>
    fetchJson<any>(`/api/recordings/${id}/recreate?mode=${mode}&force=${force}`, {
      method: "POST",
    }),
};

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 1 ? 2 : 1)} ${units[i]}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "00:00";
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  if (hrs > 0) {
    return `${hrs.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}
