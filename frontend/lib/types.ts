export interface SourceInfo {
  id: number;
  name: string;
  root_path: string;
  kind: string;
  owner: string | null;
  governed: boolean;
  file_count?: number;
  bytes?: number;
  videos?: number;
  docs?: number;
  done?: number;
}

export interface FileItem {
  id: number;
  source_id: number;
  source_name?: string;
  governed?: boolean;
  name: string;
  rel_path: string;
  ext: string;
  kind: "video" | "pdf" | "pptx" | "transcript" | "other";
  size: number;
  sha256: string;
  mtime: number;
  status: "new" | "queued" | "processing" | "done" | "error" | "skipped";
  error: string | null;
  title?: string;
  author?: string;
  doc_date?: string;
  doc_number?: string;
  revision?: string;
}

export interface OverviewData {
  counts: {
    sources: number;
    files: number;
    videos: number;
    docs: number;
    done: number;
    processing: number;
    errors: number;
    chunks: number;
    keyframes: number;
    segments: number;
  };
  files_by_status: {
    new: number;
    queued: number;
    processing: number;
    done: number;
    error: number;
    skipped: number;
  };
  total_reclaimable_bytes: number;
  duplicate_groups: number;
  storage: {
    total_bytes: number;
    video_bytes: number;
    doc_bytes: number;
    optimized_total_bytes: number;
    total_saving_pct: number;
    tier_totals: {
      T0: number;
      T1: number;
      T2: number;
      T3: number;
      T4: number;
    };
    dedup_savings: {
      exact_bytes: number;
      content_bytes: number;
      video_perceptual_bytes: number;
      doc_slide_cas_bytes: number;
    };
  };
  retention: {
    mean_screen_text_retained: number | null;
    recordings_verified: number;
  };
  slide_stats: {
    total_slides: number;
    unique_content_ids: number;
    shared_content_ids: number;
  };
  revision_chains: number;
  sources: SourceInfo[];
  ollama_available: boolean;
  diarization_available: boolean;
}

export interface StageItem {
  name: string;
  status: "done" | "running" | "pending" | "error";
  detail?: string | null;
}

export interface FileStages {
  file_id: number;
  status: string;
  stages: StageItem[];
}

export interface IntegrityCheck {
  name: string;
  status: "passed" | "pending" | "failed";
  detail: string;
}

export interface FileIntegrity {
  file_id: number;
  name: string;
  original_size: number;
  distilled_size: number;
  compression_ratio: string;
  retention_score: number;
  checks: IntegrityCheck[];
  cas_hashes: {
    raw_sha256?: string;
    transcript_sha256?: string | null;
    audio_sha256?: string | null;
    slides_content_ids?: string[];
  };
}

export interface Keyframe {
  id: number;
  idx: number;
  start: number;
  end: number;
  intervals?: string;
  object_hash: string;
  bytes: number;
  phash: string;
  ocr_text: string;
  is_slide: number;
  description: string;
  image_key?: string;
  matched_slide_id?: number | null;
}

export interface Segment {
  id: number;
  start: number;
  end: number;
  speaker: string;
  text: string;
}

export interface RecordingDetail {
  file: FileItem;
  recording: {
    duration: number;
    width: number;
    height: number;
    fps: number;
    screen_retention: number;
    tiers: string;
    notes_md?: string;
    slide_prompts_md?: string;
    summary?: string;
  };
  keyframes: Keyframe[];
  segments: Segment[];
  manifest?: Record<string, any>;
  has_audio: boolean;
  recreated: { mode: string; bytes: number; url: string }[];
}

export interface SlideItem {
  id: number;
  file_id: number;
  page_no: number;
  content_id: string;
  phash: string;
  dhash?: string;
  ahash?: string;
  text: string;
  bytes: number;
  image_key?: string;
  object_hash?: string;
}

export interface ChunkItem {
  id: number;
  file_id: number;
  kind: string;
  title: string;
  text: string;
}

export interface DocumentDetail {
  file: FileItem;
  slides: SlideItem[];
  chunks: ChunkItem[];
}

export interface DeckRelation {
  a: FileItem;
  b: FileItem;
  exact_match: boolean;
  identical_slides: number;
  modified_slides: number;
  a_only_slides: number;
  b_only_slides: number;
  diff_pairs: {
    page_a: number;
    page_b: number;
    relation: "identical" | "modified" | "added" | "deleted";
    hamming?: number;
  }[];
}

export interface VersionChain {
  doc_number: string;
  versions: FileItem[];
  revisions: string[];
}

export interface DuplicateGroup {
  hash?: string;
  keep: number;
  reclaimable: number;
  files: FileItem[];
  similarity?: number;
  byte_identical?: boolean;
}

export interface DuplicatesData {
  exact: DuplicateGroup[];
  content: DuplicateGroup[];
  video: DuplicateGroup[];
  relations: DeckRelation[];
  chains: VersionChain[];
  shared_slides: { content_id: string; count: number; slide_ids: number[] }[];
  slide_stats: {
    total_slides: number;
    unique_content_ids: number;
  };
  name_hints: any[];
}

export interface LeaverFileMatch {
  source_name: string;
  governed: boolean;
  rel_path?: string;
  name?: string;
  similarity?: number;
  identical_slides?: number;
  total_slides?: number;
}

export interface LeaverFileItem {
  file: FileItem;
  verdict: "safe_delete" | "partial" | "unique" | "review";
  status?: string;
  reason: string;
  reclaimable_bytes: number;
  matches: LeaverFileMatch[];
  unique_slides_count?: number;
}

export interface OffboardReport {
  source: SourceInfo;
  files: LeaverFileItem[];
  totals?: any;
  summary: {
    total_files: number;
    safe_delete_count: number;
    partial_count: number;
    unique_count: number;
    review_count: number;
    total_bytes: number;
    safe_delete_bytes: number;
    reclaimable_bytes: number;
    reclaimable_pct: number;
  };
}

export interface SearchResult {
  id: number;
  file_id: number;
  file_name: string;
  file_rel_path: string;
  source_name: string;
  kind: string;
  title: string;
  text: string;
  snippet: string;
  score: number;
  timestamp?: number;
  slide_id?: number;
  image_key?: string;
  speaker?: string;
}

export interface PipelineInfo {
  models: {
    transcription: string;
    diarization: string;
    ocr: string;
    embeddings: string;
    llm: string;
  };
  versions: {
    python: string;
    torch: string;
    ffmpeg: string;
    opencv: string;
  };
  thresholds: {
    identical_hamming: number;
    modified_hamming: number;
    video_similarity: number;
    transcript_similarity: number;
  };
  allowed_roots: string[];
  environment: string;
}
