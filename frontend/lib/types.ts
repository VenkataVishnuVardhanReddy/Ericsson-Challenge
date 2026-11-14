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
  size_after_bytes?: number;
  saved_pct?: number;
}

export interface FileItem {
  id: number;
  source_id: number;
  source_name?: string;
  source_kind?: string;
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
  size_after_bytes?: number;
  saved_pct?: number;
  policy?: string;
  reason?: string;
  slide_count?: number;
}

export interface WaterfallData {
  original_bytes: number;
  video_original_bytes?: number;
  video_after_bytes?: number;
  video_reduction_bytes: number;
  duplicate_file_bytes: number;
  slide_dedup_bytes: number;
  final_bytes: number;
  savings_pct: number;
  formula: string;
  measured: boolean;
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
  waterfall?: WaterfallData;
  storage: {
    total_bytes: number;
    video_bytes: number;
    doc_bytes: number;
    optimized_total_bytes: number;
    total_saving_pct: number;
    waterfall?: WaterfallData;
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
    unique_content_ids?: number;
    shared_content_ids?: number;
    unique_slides?: number;
    shared_slides?: number;
    dedup_ratio?: number;
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

export interface StorageLevelMethod {
  label: string;
  type: "ai_model" | "algorithm";
}

export interface LevelContentItem {
  path: string;
  kind: "slides" | "audio" | "text" | "voices" | "manifest" | "reference" | "delta" | "video";
  bytes: number;
  count?: number;
  url: string;
}

export interface LevelContentsResponse {
  file_id: number;
  level: number;
  level_name: string;
  total_bytes: number;
  files: LevelContentItem[];
}

export interface ReferenceRecord {
  type: "reference";
  points_to: {
    source: string;
    name: string;
    sha256: string;
  };
  original_bytes: number;
}

export interface StorageLevel {
  level: number;
  name: string;
  plain_description: string;
  bytes: number;
  measured: boolean;
  keep: string[];
  removed: string[];
  stored_files: { name: string; bytes: number }[];
  methods: StorageLevelMethod[];
}

export interface FileStages {
  file_id: number;
  status: string;
  policy?: string;
  levels?: StorageLevel[];
  progress?: StageItem[];
  stages: StageItem[];
}

export interface SlideManifestItem {
  slide_id: number;
  page_no: number;
  title: string;
  status: string;
  stored_here: boolean;
  shared_deck?: string | null;
  shared_page?: number | null;
  object_hash?: string;
  bytes: number;
}

export interface DeckManifest {
  file_id: number;
  name: string;
  revision?: string | null;
  policy: string;
  reason: string;
  total_slides: number;
  stored_here_count: number;
  shared_count: number;
  original_bytes: number;
  size_after_bytes: number;
  slides: SlideManifestItem[];
}

export interface DeckAppearance {
  slide_id: number;
  file_id: number;
  name: string;
  title: string;
  revision?: string | null;
  page_no: number;
  governed: boolean;
  source_name: string;
  object_hash?: string;
}

export interface VideoAppearance {
  keyframe_id: number;
  file_id: number;
  video_name: string;
  video_title: string;
  source_name: string;
  timestamp: number;
  timestamp_str: string;
  end: number;
  object_hash?: string;
}

export interface SlideAppearances {
  slide_id: number;
  page_no: number;
  title: string;
  object_hash?: string;
  content_id: string;
  decks: DeckAppearance[];
  videos: VideoAppearance[];
}

export interface IntegrityCheck {
  name: string;
  status: "passed" | "pending" | "failed";
  detail: string;
}

export interface CheckedMoment {
  t: number;
  kind?: "text" | "picture" | "moving_video";
  original_count?: number;
  found_count?: number;
  missing_count?: number;
  original_words?: string[];
  found_words?: string[];
  missing_words?: string[];
  hamming?: number | null;
  kept_slide_object?: string | null;
  kept_time_range?: string | null;
  linked_deck?: string | null;
  spoken_text?: string;
}

export interface FileIntegrity {
  file_id: number;
  level?: number;
  name: string;
  original_size: number;
  distilled_size: number;
  compression_ratio: string;
  retention_score?: number | null;
  status?: "measured" | "estimated" | "proven" | "not_measured" | "error";
  verification_badge?: string;
  verification_detail?: string;
  method?: string;
  slides_identical?: number;
  total_slides?: number;
  psnr_avg?: number | null;
  audio_check?: {
    audio_exists: boolean;
    duration_original: number;
    duration_audio: number;
    duration_diff_sec: number;
    duration_match: boolean;
    speech_duration: number;
    speech_covered_pct: number;
    segments_count: number;
  } | null;
  text_kept_pct?: number | null;
  text_moments?: number;
  text_note?: string | null;
  pictures_kept_pct?: number | null;
  picture_moments?: number;
  picture_note?: string | null;
  visual_match_pct?: number | null;
  ocr_accuracy_pct?: number | null;
  ocr_slides_checked?: number;
  lowest_slides?: Array<{
    page_no: number;
    score_pct: number;
    official_snippet: string;
    ocr_snippet: string;
  }>;
  moving_video_pct?: number | null;
  moving_moments?: number;
  ignored_words?: string[];
  frames_checked?: number;
  moments?: CheckedMoment[];
  main_speakers?: number;
  transcript_words?: number;
  speech_confidence?: number | null;
  slides_kept?: number;
  slides_linked?: number;
  note?: string | null;
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
  intervals?: any;
  object_hash: string;
  bytes: number;
  phash: string;
  ocr_text: string;
  is_slide: number;
  description: string;
  image_key?: string;
  slide_id?: number | null;
  matched_slide_id?: number | null;
  linked_slide?: any;
}

export interface Segment {
  id: number;
  start: number;
  end: number;
  speaker: string;
  text: string;
  deictic?: string | null;
}

export interface RecordingDetail {
  file: FileItem;
  recording: {
    duration: number;
    width: number;
    height: number;
    fps: number;
    screen_retention?: number;
    tiers: any;
    notes_md?: string;
    slide_prompts_md?: string;
    summary?: string;
    retention?: any;
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
  title?: string | null;
}

export interface ChunkItem {
  id: number;
  kind: string;
  title: string;
  text: string;
}

export interface DocumentDetail {
  file: FileItem;
  slides: SlideItem[];
  chunks: ChunkItem[];
}

export interface DuplicateGroup {
  level: "exact" | "content" | "video";
  sha256?: string;
  text_hash?: string;
  reclaimable: number;
  keep: number;
  files: FileItem[];
  similarity?: number;
}

export interface DeckRelation {
  a: FileItem;
  b: FileItem;
  score: number;
  common_slides: number;
  identical_slides: number;
  modified_slides: number;
  unique_to_a: number;
  unique_to_b: number;
}

export interface RevisionChain {
  chain_id: number;
  doc_number: string | null;
  title: string;
  versions: FileItem[];
  relations: DeckRelation[];
}

export interface SlideStats {
  total_slides: number;
  unique_slides: number;
  shared_slides: number;
  dedup_ratio: number;
}

export interface DuplicatesData {
  exact: DuplicateGroup[];
  content: DuplicateGroup[];
  video: DuplicateGroup[];
  relations: DeckRelation[];
  chains: any[];
  shared_slides: any[];
  slide_stats: SlideStats;
  name_hints: any[];
}

export interface ComparePair {
  a: SlideItem | null;
  b: SlideItem | null;
  relation: "identical" | "modified" | "new" | "removed";
  text_diff?: Array<{ op: "same" | "add" | "del"; text: string }>;
}

export interface CompareDetail {
  a: FileItem;
  b: FileItem;
  identical: number;
  modified: number;
  new: number;
  removed: SlideItem[];
  a_pages: number;
  b_pages: number;
  pairs: ComparePair[];
}

export interface SearchResult {
  id: number;
  file_id: number;
  kind: string;
  name: string;
  source: string;
  start: number | null;
  end: number | null;
  title: string;
  snippet: string;
  image: string | null;
  score: number;
  ref_id?: number | null;
  page_no?: number | null;
}

export interface LeaverFileMatch {
  file_id: number;
  name: string;
  rel_path?: string;
  source_name: string;
  governed: boolean;
  match_type: "exact" | "content" | "slides";
}

export interface LeaverFileItem {
  file: FileItem;
  verdict: "safe_delete" | "partial" | "unique" | "review";
  status?: string;
  reason: string;
  reclaimable_bytes: number;
  matches: LeaverFileMatch[];
  unique_slides_count?: number;
  shared_slides_count?: number;
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

export interface PipelineInfo {
  models: Record<string, string>;
  versions: Record<string, string>;
  thresholds: Record<string, number>;
  allowed_roots: string[];
  environment: string;
}
