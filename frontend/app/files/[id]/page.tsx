"use client";

import React, { useState, useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ChevronLeft,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Video,
  FileText,
  Building2,
  User,
  Volume2,
  Layers,
  HelpCircle,
  Play,
  Pause,
  ExternalLink,
  ShieldCheck,
  Sparkles,
  Info,
  X,
} from "lucide-react";
import { api, formatBytes, formatDuration } from "@/lib/api";
import {
  FileItem,
  RecordingDetail,
  DocumentDetail,
  FileStages,
  FileIntegrity,
  StorageLevel,
  CheckedMoment,
  DeckManifest,
  SlideAppearances,
} from "@/lib/types";
import { StatusBadge } from "@/components/Badge";
import Explain from "@/components/Explain";

export default function FileDetailPage() {
  const params = useParams();
  const fileId = parseInt(params.id as string, 10);

  const [file, setFile] = useState<FileItem | null>(null);
  const [stages, setStages] = useState<FileStages | null>(null);
  const [integrity, setIntegrity] = useState<FileIntegrity | null>(null);
  const [recording, setRecording] = useState<RecordingDetail | null>(null);
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [manifest, setManifest] = useState<DeckManifest | null>(null);
  const [loading, setLoading] = useState(true);

  // Slide Life Story state (Beyond the brief)
  const [storySlide, setStorySlide] = useState<SlideAppearances | null>(null);
  const [storyOpen, setStoryOpen] = useState(false);
  const [storyLoading, setStoryLoading] = useState(false);

  const openSlideStory = async (slideId: number) => {
    setStoryLoading(true);
    setStoryOpen(true);
    try {
      const data = await api.getSlideAppearances(slideId);
      setStorySlide(data);
    } catch (err) {
      console.error(err);
    } finally {
      setStoryLoading(false);
    }
  };

  const [selectedLevel, setSelectedLevel] = useState<number>(4);
  const [logScale, setLogScale] = useState(false);
  const [copiedHash, setCopiedHash] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const [showAllSlides, setShowAllSlides] = useState(false);

  // Audio / Media Player State
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [activeSlideKey, setActiveSlideKey] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (isNaN(fileId)) return;
    async function load() {
      try {
        const files = await api.getFiles();
        const f = files.find((item) => item.id === fileId);
        if (f) setFile(f);

        const [stg, integ] = await Promise.all([
          api.getFileStages(fileId).catch(() => null),
          api.getFileIntegrity(fileId).catch(() => null),
        ]);
        setStages(stg);
        setIntegrity(integ);

        if (f?.kind === "video") {
          const rec = await api.getRecording(fileId).catch(() => null);
          setRecording(rec);
          if (rec?.keyframes?.[0]?.object_hash) {
            setActiveSlideKey(rec.keyframes[0].object_hash);
          }
        } else {
          const [doc, mnf] = await Promise.all([
            api.getDocument(fileId).catch(() => null),
            api.getDeckManifest(fileId).catch(() => null),
          ]);
          setDocument(doc);
          setManifest(mnf);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [fileId]);

  const copySha = () => {
    if (!file?.sha256) return;
    navigator.clipboard.writeText(file.sha256);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  if (loading) {
    return (
      <div className="py-20 space-y-6 animate-pulse max-w-[1120px] mx-auto">
        <div className="h-6 w-32 bg-gray-100 rounded"></div>
        <div className="h-10 w-2/3 bg-gray-100 rounded"></div>
        <div className="h-64 bg-gray-100 rounded-xl"></div>
      </div>
    );
  }

  if (!file) {
    return (
      <div className="py-20 text-center space-y-4">
        <p className="text-sm text-[#6b6b6b]">File not found.</p>
        <Link href="/files" className="text-xs font-medium text-black hover:underline">
          ← Back to files
        </Link>
      </div>
    );
  }

  const isVideo = file.kind === "video";
  const levels = stages?.levels || [];
  const currentLevelObj: StorageLevel | undefined = levels.find((l) => l.level === selectedLevel) || levels[levels.length - 1];

  const origBytes = file.size || 1;
  const curBytes = currentLevelObj?.bytes ?? origBytes;
  const savingPct = Math.max(0, Math.round((1 - curBytes / origBytes) * 100));

  // Determine active keyframe based on audio timestamp
  const keyframes = recording?.keyframes || [];
  const segments = recording?.segments || [];

  const handleAudioTimeUpdate = () => {
    if (!audioRef.current) return;
    const t = audioRef.current.currentTime;
    setCurrentTime(t);
    // Find matching keyframe for time t
    const match = keyframes.find((k) => {
      const intervals = Array.isArray(k.intervals) ? k.intervals : [];
      return intervals.some(([s, e]: [number, number]) => t >= s && t <= e);
    });
    if (match?.object_hash) {
      setActiveSlideKey(match.object_hash);
    }
  };

  const jumpToTime = (t: number) => {
    setCurrentTime(t);
    if (audioRef.current) {
      audioRef.current.currentTime = t;
      if (!isPlayingAudio) {
        audioRef.current.play().catch(() => {});
        setIsPlayingAudio(true);
      }
    }
    const match = keyframes.find((k) => {
      const intervals = Array.isArray(k.intervals) ? k.intervals : [];
      return intervals.some(([s, e]: [number, number]) => t >= s && t <= e);
    });
    if (match?.object_hash) {
      setActiveSlideKey(match.object_hash);
    }
  };

  return (
    <div className="space-y-12 py-2 max-w-[1120px] mx-auto pb-24">
      {/* NAVIGATION BACK */}
      <div>
        <Link
          href="/files"
          className="inline-flex items-center gap-1.5 text-xs text-[#6b6b6b] hover:text-black font-medium transition-colors"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          <span>Back to files</span>
        </Link>
      </div>

      {/* HEADER */}
      <div className="space-y-4 border-b border-[#e5e5e5] pb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-black break-words">
              {file.name}
            </h1>
            <div className="flex flex-wrap items-center gap-3 text-xs text-[#6b6b6b]">
              <StatusBadge
                status={file.governed ? "official" : "personal"}
                label={file.source_name || (file.governed ? "Official" : "Personal drive")}
              />
              <span>•</span>
              <span className="font-mono">Original: {formatBytes(file.size)}</span>
              {(file.policy || stages?.policy) && (
                <>
                  <span>•</span>
                  <span className="inline-block px-2.5 py-1 rounded-md text-xs font-mono font-medium border border-black bg-white text-black">
                    Policy: {file.policy || stages?.policy}
                  </span>
                </>
              )}
              {isVideo && recording?.recording?.duration && (
                <>
                  <span>•</span>
                  <span>Length: {formatDuration(recording.recording.duration)}</span>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#e5e5e5] bg-gray-50 text-xs font-medium text-black">
              <Check className="w-3.5 h-3.5" />
              <span>Original file unchanged</span>
              <span className="relative group ml-1">
                <button
                  type="button"
                  onClick={copySha}
                  className="text-[#6b6b6b] hover:text-black p-0.5"
                  title="Click to copy SHA-256 hash"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
                {copiedHash && (
                  <span className="absolute bottom-full right-0 mb-1 px-2 py-1 text-[11px] bg-black text-white rounded shadow text-nowrap">
                    Hash copied!
                  </span>
                )}
              </span>
            </span>
          </div>
        </div>
      </div>

      {/* PART 1 — HOW MUCH DO YOU WANT TO KEEP? (5-POSITION SLIDER) */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-8">
        <div>
          <span className="text-xs uppercase tracking-wider text-[#6b6b6b] font-semibold">Part 1</span>
          <h2 className="text-xl font-bold text-black mt-1">How much do you want to keep?</h2>
          <p className="text-sm text-[#6b6b6b] mt-0.5">
            Choose between full video, lightweight speech audio, or text and official slide links.
          </p>
        </div>

        {/* Big Size Headline for Selected Level */}
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-[#e5e5e5] pb-6">
          <div className="flex items-baseline gap-4">
            <span className="text-4xl sm:text-5xl font-bold font-mono text-black">
              {formatBytes(curBytes)}
            </span>
            <span className="text-lg text-[#6b6b6b] font-medium">
              {savingPct > 0 ? `${savingPct}% smaller than the original` : "Original size"}
            </span>
          </div>

          {currentLevelObj && !currentLevelObj.measured && (
            <div className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-md border border-[#e5e5e5] bg-gray-50 text-[#6b6b6b] w-fit">
              <Info className="w-3.5 h-3.5" />
              <span>Estimated only (not created for long videos)</span>
            </div>
          )}
        </div>

        {/* 5-Position Horizontal Slider */}
        <div className="space-y-4">
          <div className="relative pt-2">
            <input
              type="range"
              min={1}
              max={5}
              step={1}
              value={selectedLevel}
              onChange={(e) => setSelectedLevel(parseInt(e.target.value, 10))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-black"
            />
            <div className="grid grid-cols-5 text-center mt-3 text-xs">
              {[1, 2, 3, 4, 5].map((lvl) => {
                const lObj = levels.find((l) => l.level === lvl);
                const isSelected = selectedLevel === lvl;
                return (
                  <button
                    key={lvl}
                    type="button"
                    onClick={() => setSelectedLevel(lvl)}
                    className={`flex flex-col items-center transition-colors text-left ${
                      isSelected ? "text-black font-semibold" : "text-[#6b6b6b] hover:text-black"
                    }`}
                  >
                    <span className="text-[11px] font-mono text-[#6b6b6b]">Level {lvl}</span>
                    <span className="text-xs mt-0.5 leading-snug">{lObj?.name || `Level ${lvl}`}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Level Details: What you keep, What is removed, Files stored, How it was made */}
        {currentLevelObj && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 pt-4 border-t border-[#e5e5e5] text-xs">
            {/* What you keep */}
            <div className="space-y-2">
              <span className="font-semibold text-black uppercase tracking-wider text-[11px] block">
                What you keep
              </span>
              <ul className="space-y-1.5 text-[#6b6b6b]">
                {currentLevelObj.keep.map((k, idx) => (
                  <li key={idx} className="flex items-start gap-1.5">
                    <span className="text-black">•</span>
                    <span>{k}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* What is removed */}
            <div className="space-y-2">
              <span className="font-semibold text-black uppercase tracking-wider text-[11px] block">
                What is removed
              </span>
              <ul className="space-y-1.5 text-[#6b6b6b]">
                {currentLevelObj.removed.map((r, idx) => (
                  <li key={idx} className="flex items-start gap-1.5">
                    <span className="text-black">•</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Files stored */}
            <div className="space-y-2">
              <span className="font-semibold text-black uppercase tracking-wider text-[11px] block">
                Files stored
              </span>
              <div className="flex flex-wrap gap-1.5">
                {currentLevelObj.stored_files.map((sf, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#e5e5e5] bg-gray-50 text-[11px] font-mono text-black"
                  >
                    <span>{sf.name}</span>
                    <span className="text-[#6b6b6b]">({formatBytes(sf.bytes)})</span>
                  </span>
                ))}
              </div>
            </div>

            {/* How it was made */}
            <div className="space-y-2">
              <span className="font-semibold text-black uppercase tracking-wider text-[11px] block">
                How it was made
              </span>
              <div className="flex flex-wrap gap-1.5">
                {currentLevelObj.methods.map((m, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-[#e5e5e5] text-[11px] text-[#6b6b6b] bg-white"
                  >
                    <span className="text-black font-medium">{m.label}</span>
                    <span className="text-[#a3a3a3]">({m.type === "ai_model" ? "AI model" : "Algorithm"})</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Small Bar Chart of All 5 Levels with Log-scale Toggle */}
        <div className="pt-6 border-t border-[#e5e5e5] space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-black">Size comparison across all 5 levels</span>
            <button
              type="button"
              onClick={() => setLogScale(!logScale)}
              className="inline-flex items-center gap-1.5 text-[#6b6b6b] hover:text-black border border-[#e5e5e5] px-2.5 py-1 rounded"
            >
              <span>{logScale ? "Normal scale" : "Log scale"}</span>
              <span className="text-[10px] text-[#a3a3a3]">
                {logScale ? "(linear)" : "(makes small sizes visible)"}
              </span>
            </button>
          </div>

          <div className="grid grid-cols-5 gap-3 pt-2">
            {levels.map((lvl) => {
              const bytes = lvl.bytes || 1;
              const maxBytes = Math.max(...levels.map((l) => l.bytes || 1), 1);
              let pct = (bytes / maxBytes) * 100;
              if (logScale) {
                const logVal = Math.log10(Math.max(1, bytes));
                const logMax = Math.log10(Math.max(1, maxBytes));
                pct = Math.max(5, (logVal / logMax) * 100);
              }
              const isSelected = selectedLevel === lvl.level;

              return (
                <div
                  key={lvl.level}
                  onClick={() => setSelectedLevel(lvl.level)}
                  className={`p-3 rounded-lg border cursor-pointer transition-colors space-y-2 ${
                    isSelected ? "border-black bg-gray-50" : "border-[#e5e5e5] hover:border-black"
                  }`}
                >
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-medium text-black">Level {lvl.level}</span>
                    <span className="font-mono text-[#6b6b6b]">{formatBytes(lvl.bytes)}</span>
                  </div>
                  <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                    <div
                      style={{ width: `${Math.min(100, Math.max(2, pct))}%` }}
                      className={`h-full ${isSelected ? "bg-black" : "bg-[#6b6b6b]"}`}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* PART 2 — SEE WHAT'S KEPT AT THIS LEVEL */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div>
          <span className="text-xs uppercase tracking-wider text-[#6b6b6b] font-semibold">Part 2</span>
          <h2 className="text-xl font-bold text-black mt-1">See what is kept at this level</h2>
          <p className="text-sm text-[#6b6b6b] mt-0.5">
            Interactively preview the data retained at Level {selectedLevel}: {currentLevelObj?.name}.
          </p>
        </div>

        {/* VIDEO CONTENT PREVIEWS */}
        {isVideo && (
          <div>
            {/* LEVEL 1: ORIGINAL VIDEO */}
            {selectedLevel === 1 && (
              <div className="space-y-4">
                <div className="aspect-video bg-black rounded-lg overflow-hidden flex items-center justify-center">
                  <video
                    controls
                    className="w-full h-full"
                    src={api.videoUrl(file.id)}
                  >
                    Your browser does not support the video tag.
                  </video>
                </div>
                <p className="text-xs text-[#6b6b6b]">
                  Playing the original untouched recording: {formatBytes(origBytes)}.
                </p>
              </div>
            )}

            {/* LEVEL 2: SMALLER VIDEO */}
            {selectedLevel === 2 && (
              <div className="p-8 rounded-lg border border-[#e5e5e5] bg-gray-50 text-center space-y-3">
                <Video className="w-8 h-8 mx-auto text-[#6b6b6b]" />
                <h3 className="text-sm font-semibold text-black">Smaller video level</h3>
                <p className="text-xs text-[#6b6b6b] max-w-md mx-auto">
                  Re-encoded at 5 frames per second using H.264 (quality setting 32).
                  For this {formatDuration(recording?.recording?.duration)} presentation, Level 3 and 4 are recommended for 98%+ savings.
                </p>
                <button
                  type="button"
                  onClick={() => setSelectedLevel(3)}
                  className="px-4 py-2 rounded-lg bg-black text-white text-xs font-medium hover:bg-neutral-800"
                >
                  Switch to Level 3 (Audio + slides)
                </button>
              </div>
            )}

            {/* LEVEL 3, 4, 5: AUDIO PLAYER + SLIDE STRIP + TRANSCRIPT */}
            {selectedLevel >= 3 && (
              <div className="space-y-6">
                {/* Audio Player Bar (for Level 3) */}
                {selectedLevel === 3 && (
                  <div className="p-4 rounded-xl border border-black bg-black text-white flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => {
                          if (!audioRef.current) return;
                          if (isPlayingAudio) {
                            audioRef.current.pause();
                            setIsPlayingAudio(false);
                          } else {
                            audioRef.current.play().catch(() => {});
                            setIsPlayingAudio(true);
                          }
                        }}
                        className="w-10 h-10 rounded-full bg-white text-black flex items-center justify-center hover:bg-gray-200 transition-colors"
                      >
                        {isPlayingAudio ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                      </button>
                      <div>
                        <span className="text-sm font-semibold block text-white">Opus speech audio</span>
                        <span className="text-xs text-[#a3a3a3] font-mono">
                          {formatDuration(currentTime)} / {formatDuration(recording?.recording?.duration)} • 16 kbps
                        </span>
                      </div>
                    </div>

                    <audio
                      ref={audioRef}
                      src={api.audioUrl(file.id)}
                      onTimeUpdate={handleAudioTimeUpdate}
                      onEnded={() => setIsPlayingAudio(false)}
                      className="hidden"
                    />

                    <span className="text-xs text-[#a3a3a3] self-end sm:self-auto font-mono">
                      No video frames stored • Full speech preserved
                    </span>
                  </div>
                )}

                {/* Main Split: Left Side Slide Viewer / Right Side Transcript */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                  {/* Left: Current Slide Picture */}
                  <div className="lg:col-span-7 space-y-3">
                    <div className="border border-[#e5e5e5] rounded-xl overflow-hidden bg-gray-50 aspect-[16/10] flex items-center justify-center relative">
                      {activeSlideKey ? (
                        selectedLevel === 5 && keyframes.find((k) => k.object_hash === activeSlideKey)?.linked_slide ? (
                          <div className="p-8 text-center space-y-2">
                            <span className="text-xs text-[#6b6b6b] uppercase tracking-wider font-semibold">
                              Linked to official deck
                            </span>
                            <h4 className="text-base font-bold text-black">
                              {keyframes.find((k) => k.object_hash === activeSlideKey)?.linked_slide?.deck_name}
                            </h4>
                            <p className="text-xs text-[#6b6b6b]">
                              Slide page {keyframes.find((k) => k.object_hash === activeSlideKey)?.linked_slide?.page_no}
                            </p>
                            <span className="inline-block mt-2 px-3 py-1 bg-black text-white text-xs rounded-full">
                              Duplicate slide image not stored here
                            </span>
                          </div>
                        ) : (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={api.objectUrl(activeSlideKey)}
                            alt="Slide transition"
                            className="w-full h-full object-contain"
                          />
                        )
                      ) : (
                        <span className="text-xs text-[#6b6b6b]">Select a slide or sentence</span>
                      )}
                    </div>

                    <div className="flex items-center justify-between text-xs text-[#6b6b6b]">
                      <span>Active slide preview</span>
                      {activeSlideKey && (
                        <button
                          type="button"
                          onClick={() => {
                            const curKf = keyframes.find((k) => k.object_hash === activeSlideKey);
                            if (curKf) {
                              openSlideStory(curKf.slide_id || curKf.id);
                            }
                          }}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-[#e5e5e5] bg-white hover:bg-gray-100 text-black font-medium transition-colors"
                          title="Inspect where this slide appears across the archive"
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Slide life story</span>
                        </button>
                      )}
                    </div>

                    {/* Slide Thumbnail Strip */}
                    <div className="space-y-1.5">
                      <span className="text-xs text-[#6b6b6b] block font-medium">
                        Slide keyframes ({keyframes.length} visual moments)
                      </span>
                      <div className="flex gap-2 overflow-x-auto pb-2">
                        {keyframes.slice(0, 30).map((k) => {
                          const isActive = activeSlideKey === k.object_hash;
                          return (
                            <button
                              key={k.id}
                              type="button"
                              onClick={() => {
                                setActiveSlideKey(k.object_hash);
                                jumpToTime(k.start);
                              }}
                              className={`flex-shrink-0 w-20 aspect-video rounded border overflow-hidden transition-all ${
                                isActive ? "ring-2 ring-black border-transparent" : "border-[#e5e5e5] opacity-75 hover:opacity-100"
                              }`}
                            >
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={api.objectUrl(k.object_hash)}
                                alt={`Frame @ ${formatDuration(k.start)}`}
                                className="w-full h-full object-cover"
                              />
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  {/* Right: Interactive Transcript */}
                  <div className="lg:col-span-5 border border-[#e5e5e5] rounded-xl p-4 bg-white flex flex-col h-[460px]">
                    <div className="border-b border-[#e5e5e5] pb-2 mb-3 flex items-center justify-between text-xs">
                      <span className="font-semibold text-black">Transcript</span>
                      <span className="text-[#6b6b6b]">{segments.length} spoken segments</span>
                    </div>

                    <div className="flex-1 overflow-y-auto space-y-3 pr-1 text-xs">
                      {segments.map((s) => {
                        const isCurrent = currentTime >= s.start && currentTime <= s.end;
                        return (
                          <div
                            key={s.id}
                            onClick={() => jumpToTime(s.start)}
                            className={`p-2.5 rounded-lg cursor-pointer transition-colors border ${
                              isCurrent
                                ? "border-black bg-gray-50"
                                : "border-transparent hover:border-[#e5e5e5] hover:bg-gray-50/50"
                            }`}
                          >
                            <div className="flex items-center justify-between text-[11px] mb-1 font-mono text-[#6b6b6b]">
                              <span className="font-semibold text-black">{s.speaker}</span>
                              <span>{formatDuration(s.start)}</span>
                            </div>
                            <p className="text-black leading-relaxed">{s.text}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* DOCUMENT PREVIEWS & MANIFEST */}
        {!isVideo && (
          <div className="space-y-6">
            {manifest && (
              <div className="p-4 rounded-xl border border-[#e5e5e5] bg-gray-50 flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-xs">
                <div>
                  <span className="font-semibold text-black block text-sm">Document Storage Manifest</span>
                  <p className="text-[#6b6b6b] mt-0.5">
                    {manifest.stored_here_count} slides stored here ({formatBytes(manifest.size_after_bytes)}) • {manifest.shared_count} slides shared with other decks
                  </p>
                  {manifest.reason && (
                    <p className="text-[#6b6b6b] font-mono text-[11px] mt-1">
                      Reason: {manifest.reason}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded border border-black bg-white font-mono text-xs font-semibold text-black">
                    Policy: {manifest.policy}
                  </span>
                </div>
              </div>
            )}

            {manifest?.slides && manifest.slides.length > 0 ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between text-xs font-medium text-[#6b6b6b]">
                  <span>Ordered slide manifest ({manifest.slides.length} slides)</span>
                  <span className="text-[11px]">Click any thumbnail to inspect slide life story</span>
                </div>

                <div className="border border-[#e5e5e5] rounded-xl overflow-hidden bg-white divide-y divide-[#e5e5e5] max-h-[520px] overflow-y-auto">
                  {manifest.slides.map((s) => (
                    <div
                      key={s.slide_id}
                      className="p-3.5 flex items-center justify-between gap-4 hover:bg-gray-50/70 transition-colors"
                    >
                      <div className="flex items-center gap-3.5 min-w-0">
                        <span className="font-mono text-xs text-[#6b6b6b] w-8 flex-shrink-0">
                          #{s.page_no}
                        </span>
                        <button
                          type="button"
                          onClick={() => openSlideStory(s.slide_id)}
                          className="w-20 aspect-video rounded border border-[#e5e5e5] bg-gray-100 overflow-hidden flex-shrink-0 hover:ring-2 hover:ring-black transition-all"
                          title="Click to view slide life story"
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={api.objectUrl(s.object_hash)}
                            alt={s.title}
                            className="w-full h-full object-cover"
                          />
                        </button>
                        <div className="min-w-0">
                          <span className="font-medium text-xs text-black block truncate">
                            {s.title}
                          </span>
                          <div className="flex items-center gap-2 mt-1">
                            {s.stored_here ? (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono border border-black bg-black text-white">
                                stored here
                              </span>
                            ) : (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono border border-[#e5e5e5] bg-gray-100 text-black">
                                {s.status}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 flex-shrink-0">
                        <span className="font-mono text-xs text-[#6b6b6b]">
                          {s.stored_here ? formatBytes(s.bytes) : "0 B (ref)"}
                        </span>
                        <button
                          type="button"
                          onClick={() => openSlideStory(s.slide_id)}
                          className="px-2.5 py-1 rounded text-xs border border-[#e5e5e5] hover:bg-black hover:text-white hover:border-black transition-colors"
                        >
                          Life story
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : document?.slides && document.slides.length > 0 ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-[#6b6b6b] font-medium">
                    {document.slides.length} slides extracted as WebP
                  </span>
                  {document.slides.length > 8 && (
                    <button
                      type="button"
                      onClick={() => setShowAllSlides(!showAllSlides)}
                      className="text-xs text-[#6b6b6b] hover:text-black font-medium transition-colors border border-[#e5e5e5] px-3 py-1.5 rounded-lg"
                    >
                      {showAllSlides ? "Show first 8 slides" : `Show all ${document.slides.length} slides`}
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {(showAllSlides ? document.slides : document.slides.slice(0, 8)).map((s) => (
                    <div key={s.id} className="border border-[#e5e5e5] rounded-lg overflow-hidden bg-white space-y-1.5 p-2">
                      <div
                        className="aspect-[4/3] bg-gray-50 rounded overflow-hidden cursor-pointer hover:opacity-90 transition-opacity"
                        onClick={() => openSlideStory(s.id)}
                        title="Click to view slide life story"
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={api.objectUrl(s.object_hash)}
                          alt={`Slide ${s.page_no}`}
                          className="w-full h-full object-contain"
                        />
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-[#6b6b6b] px-1 font-mono">
                        <span>Page {s.page_no}</span>
                        <span>{formatBytes(s.bytes)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="border border-[#e5e5e5] rounded-xl p-4 bg-gray-50 text-xs text-[#6b6b6b] space-y-1">
                <span className="font-semibold text-black block">Extracted document content</span>
                <p>Text extracted and indexed for full-text and semantic search.</p>
              </div>
            )}

            <div className="pt-2">
              <a
                href={api.rawFileUrl(file.id)}
                download
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[#e5e5e5] text-xs font-medium text-black hover:bg-gray-50"
              >
                <span>Download original untouched file</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        )}
      </section>

      {/* PART 3 — WAS ANYTHING LOST? (INTEGRITY & RETENTION VERIFICATION) */}
      <section className="border border-[#e5e5e5] rounded-xl p-6 sm:p-8 bg-white space-y-6">
        <div>
          <span className="text-xs uppercase tracking-wider text-[#6b6b6b] font-semibold">Part 3</span>
          <h2 className="text-xl font-bold text-black mt-1">Was anything lost?</h2>
          <p className="text-sm text-[#6b6b6b] mt-0.5">
            We sampled 20 evenly spaced moments across the original recording to verify exactly what was preserved and prove nothing critical was discarded.
          </p>
        </div>

        {/* Result Lines with '?' Tooltip Explanations */}
        <div className="border border-[#e5e5e5] rounded-xl p-5 bg-white divide-y divide-[#e5e5e5] text-sm">
          {/* Line 1: Slide text kept */}
          <div className="py-3 first:pt-0 last:pb-0 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-black">Slide text kept:</span>
              <span className="font-mono text-black font-medium">
                {integrity?.text_kept_pct !== undefined && integrity?.text_kept_pct !== null
                  ? `${(integrity.text_kept_pct * 100).toFixed(1)}%`
                  : (integrity?.text_note || "—")}
              </span>
              <span className="text-xs text-[#6b6b6b]">
                ({integrity?.text_moments || 0} text moments)
              </span>
            </div>
            <span
              className="inline-flex items-center justify-center w-5 h-5 rounded-full border border-[#e5e5e5] text-[11px] font-mono text-[#6b6b6b] cursor-help hover:text-black hover:border-black transition-colors"
              title="Slide text kept: Measures whether characters and words visible on slides in the original video are present in the distilled text or linked presentation decks."
            >
              ?
            </span>
          </div>

          {/* Line 2: Pictures match (pixel comparison, no OCR) */}
          <div className="py-3 first:pt-0 last:pb-0 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-black">Pictures match (pixel comparison, no OCR):</span>
              <span className="font-mono text-black font-medium">
                {integrity?.visual_match_pct !== undefined && integrity?.visual_match_pct !== null
                  ? `${(integrity.visual_match_pct * 100).toFixed(1)}%`
                  : (integrity?.pictures_kept_pct !== undefined && integrity?.pictures_kept_pct !== null
                    ? `${(integrity.pictures_kept_pct * 100).toFixed(1)}%`
                    : (integrity?.picture_note || "—"))}
              </span>
              <span className="text-xs text-[#6b6b6b]">
                ({integrity?.frames_checked || 20} moments checked)
              </span>
            </div>
            <span
              className="inline-flex items-center justify-center w-5 h-5 rounded-full border border-[#e5e5e5] text-[11px] font-mono text-[#6b6b6b] cursor-help hover:text-black hover:border-black transition-colors"
              title="Pictures match: Compares original video frames against kept slide pictures using perceptual hashing (pHash distance <= 12) with presenter activity mask applied."
            >
              ?
            </span>
          </div>

          {/* Line 3: Moving video */}
          <div className="py-3 first:pt-0 last:pb-0 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-black">Moving video:</span>
              <span className="font-mono text-black font-medium">
                {integrity?.moving_video_pct !== undefined && integrity?.moving_video_pct !== null
                  ? `${(integrity.moving_video_pct * 100).toFixed(1)}%`
                  : "0.0%"}
              </span>
              <span className="text-xs text-[#6b6b6b]">
                of the recording — kept only in levels 1–2, by design
              </span>
            </div>
            <span
              className="inline-flex items-center justify-center w-5 h-5 rounded-full border border-[#e5e5e5] text-[11px] font-mono text-[#6b6b6b] cursor-help hover:text-black hover:border-black transition-colors"
              title="Moving video: Dynamic motion like live presenter cameras and animations. Levels 3–5 intentionally drop moving video to maximize storage savings while keeping all slide content and speech audio."
            >
              ?
            </span>
          </div>

          {/* Line 4: OCR reads official slide text correctly */}
          {integrity?.ocr_accuracy_pct !== undefined && integrity?.ocr_accuracy_pct !== null && (
            <div className="py-3 first:pt-0 last:pb-0 space-y-2">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-black">OCR reads official slide text correctly:</span>
                  <span className="font-mono text-black font-medium">
                    {(integrity.ocr_accuracy_pct * 100).toFixed(1)}%
                  </span>
                  <span className="text-xs text-[#6b6b6b]">
                    ({integrity?.ocr_slides_checked || 0} slides, checked against the original PDF text)
                  </span>
                </div>
                <span
                  className="inline-flex items-center justify-center w-5 h-5 rounded-full border border-[#e5e5e5] text-[11px] font-mono text-[#6b6b6b] cursor-help hover:text-black hover:border-black transition-colors"
                  title="OCR reads official slide text correctly: Measures word recall by checking whether clean words (>= 3 chars) from original presentation deck slides are accurately recognized in distilled slide pictures."
                >
                  ?
                </span>
              </div>

              {integrity.lowest_slides && integrity.lowest_slides.length > 0 && (
                <details className="text-xs group border-t border-[#e5e5e5] pt-2">
                  <summary className="font-medium text-black cursor-pointer hover:underline list-none flex items-center justify-between">
                    <span>View lowest scoring slides ({integrity.lowest_slides.length})</span>
                    <span className="text-[#6b6b6b] text-[11px] group-open:rotate-180 transition-transform">▼</span>
                  </summary>
                  <div className="mt-2.5 space-y-2 bg-gray-50 p-3 rounded-lg border border-[#e5e5e5]">
                    {integrity.lowest_slides.map((ls, i) => (
                      <div key={i} className="space-y-1 text-[11px] pb-2 last:pb-0 border-b last:border-b-0 border-[#e5e5e5]">
                        <div className="flex justify-between font-semibold text-black">
                          <span>Page {ls.page_no}</span>
                          <span className="font-mono">{ls.score_pct}% word recall</span>
                        </div>
                        <p className="text-[#6b6b6b]"><span className="font-medium text-black">Official text:</span> {ls.official_snippet}</p>
                        <p className="text-[#6b6b6b]"><span className="font-medium text-black">OCR reading:</span> {ls.ocr_snippet}</p>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
        </div>

        {/* Spot Check Report Link */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-lg border border-[#e5e5e5] bg-gray-50 text-xs">
          <div>
            <span className="font-semibold text-black block">Independent spot-check report</span>
            <span className="text-[#6b6b6b] block mt-0.5">
              Side-by-side comparison of 20 evenly-spaced moments across original and kept footage.
            </span>
          </div>
          <a
            href="/api/spot-check"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-black bg-white text-black font-medium hover:bg-gray-100 transition-colors self-start sm:self-auto whitespace-nowrap"
          >
            <span>Open spot check</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>

        {/* Plain Explanation Text */}
        <div className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50 text-xs text-[#6b6b6b] leading-relaxed">
          <p>
            Distill keeps 100% of the speech audio, transcript, and distinct slide screens. Moving camera feeds are retained in Levels 1–2 (playable video) and omitted from Levels 3–5 to achieve 99% storage reduction.
          </p>
          {integrity?.note && (
            <p className="mt-2 text-black font-medium">
              Note: {integrity.note}
            </p>
          )}
        </div>

        {/* Evidence Grid: Moment-by-Moment Verification */}
        {integrity?.moments && integrity.moments.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-black">
                Evidence: sample of checked moments
              </h3>
              <span className="text-xs font-mono text-[#6b6b6b]">
                {integrity.moments.length} moments verified
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {integrity.moments.slice(0, 8).map((m: CheckedMoment, idx: number) => {
                const isText = m.kind === "text";
                const isPic = m.kind === "picture";
                const isMotion = m.kind === "moving_video";

                return (
                  <div key={idx} className="p-4 rounded-lg border border-[#e5e5e5] bg-gray-50/50 space-y-3 text-xs">
                    {/* Header with Moment number, Timestamp, and Kind Badge */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-black">Moment {idx + 1}</span>
                        <span className="font-mono text-[#6b6b6b] text-[11px]">@{formatDuration(m.t)}</span>
                      </div>
                      <span className="border border-[#e5e5e5] bg-white px-2 py-0.5 rounded text-[10px] uppercase font-mono tracking-wider font-semibold text-black">
                        {isText ? "Text" : isPic ? "Picture" : "Moving video"}
                      </span>
                    </div>

                    {/* Comparison Images */}
                    <div className="grid grid-cols-2 gap-2">
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase tracking-wider text-[#6b6b6b] font-semibold block">
                          Original frame
                        </span>
                        <div className="aspect-video bg-black rounded overflow-hidden">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={api.frameUrl(file.id, m.t)}
                            alt={`Original @ ${m.t}s`}
                            className="w-full h-full object-cover"
                          />
                        </div>
                      </div>

                      <div className="space-y-1">
                        <span className="text-[10px] uppercase tracking-wider text-[#6b6b6b] font-semibold block">
                          Kept picture
                        </span>
                        <div className="aspect-video bg-black rounded overflow-hidden">
                          {m.kept_slide_object ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={api.objectUrl(m.kept_slide_object)}
                              alt="Kept picture"
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-400">
                              {isMotion ? "Not kept (moving video)" : "Missing"}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Coverage Line */}
                    {m.kept_time_range && (
                      <div className="text-[11px] font-mono text-[#6b6b6b]">
                        Kept picture covers {m.kept_time_range}
                        {m.linked_deck && (
                          <span className="block text-black font-sans text-xs mt-0.5">
                            Linked to official deck: {m.linked_deck}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Verification Details */}
                    <div className="space-y-1 pt-1 border-t border-[#e5e5e5] text-[11px]">
                      {isText && (
                        <div className="space-y-1">
                          <div className="font-medium text-black">
                            {m.found_count ?? 0} of {m.original_count ?? 0} characters found
                          </div>
                          {m.missing_words && m.missing_words.length > 0 && (
                            <div className="text-[#6b6b6b]">
                              <span className="font-medium text-black">Not found:</span>{" "}
                              {m.missing_words.slice(0, 10).join(", ")}
                            </div>
                          )}
                        </div>
                      )}

                      {isPic && (
                        <div className="font-medium text-black">
                          {m.hamming !== null && m.hamming !== undefined ? (
                            m.hamming <= 12 ? (
                              <span>Looks the same (distance {m.hamming} ≤ 12)</span>
                            ) : (
                              <span className="text-[#6b6b6b]">Looks different (distance {m.hamming} &gt; 12)</span>
                            )
                          ) : (
                            <span className="text-[#6b6b6b]">No picture match</span>
                          )}
                        </div>
                      )}

                      {isMotion && (
                        <div className="text-[#6b6b6b]">
                          <span className="font-medium text-black">Not kept in this level (moving video)</span>
                          {m.hamming !== null && m.hamming !== undefined && (
                            <span className="block text-[10px] font-mono text-[#a3a3a3]">
                              Camera motion detected between frames (motion score: {m.hamming})
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Spoken Text */}
                    {m.spoken_text && (
                      <div className="text-[#6b6b6b] text-[11px] italic pt-1 border-t border-[#e5e5e5]">
                        &quot;{m.spoken_text}&quot;
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* PART 4 — STEPS THAT RAN (COLLAPSED CHECKLIST) */}
      <section className="border border-[#e5e5e5] rounded-xl bg-white overflow-hidden">
        <button
          type="button"
          onClick={() => setShowSteps(!showSteps)}
          className="w-full p-6 text-left flex items-center justify-between hover:bg-gray-50 transition-colors"
        >
          <div>
            <span className="text-xs uppercase tracking-wider text-[#6b6b6b] font-semibold">Part 4</span>
            <h2 className="text-lg font-bold text-black mt-0.5">Steps that ran</h2>
            <p className="text-xs text-[#6b6b6b] mt-0.5">
              Processing checklist in plain words with what each step produced.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-[#6b6b6b]">
            <span>{showSteps ? "Hide details" : "Show details"}</span>
            {showSteps ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </button>

        {showSteps && (
          <div className="p-6 pt-0 border-t border-[#e5e5e5] divide-y divide-[#e5e5e5] text-xs">
            {(stages?.progress || stages?.stages || []).map((step, idx) => (
              <div key={idx} className="py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 rounded-full bg-black text-white flex items-center justify-center">
                    <Check className="w-3 h-3 stroke-[2.5]" />
                  </div>
                  <div>
                    <span className="font-semibold text-black">{step.name}</span>
                    {step.detail && (
                      <span className="text-[#6b6b6b] block text-[11px] mt-0.5">{step.detail}</span>
                    )}
                  </div>
                </div>
                <StatusBadge status="done" />
              </div>
            ))}
          </div>
        )}
      </section>

      {/* SLIDE LIFE STORY MODAL */}
      {storyOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-black rounded-2xl max-w-2xl w-full p-6 sm:p-8 shadow-2xl space-y-6 relative max-h-[90vh] overflow-y-auto">
            <button
              type="button"
              onClick={() => {
                setStoryOpen(false);
                setStorySlide(null);
              }}
              className="absolute top-6 right-6 p-1.5 rounded-lg border border-[#e5e5e5] hover:bg-gray-100 text-black transition-colors"
              title="Close modal"
            >
              <X className="w-4 h-4" />
            </button>

            <div>
              <span className="text-xs uppercase tracking-wider text-[#6b6b6b] font-mono font-semibold">
                Slide Life Story
              </span>
              <h3 className="text-xl font-bold text-black mt-1">
                {storySlide?.title || "Slide details"}
              </h3>
              <p className="text-xs text-[#6b6b6b] mt-0.5">
                Tracks everywhere this exact visual slide appears across official company decks and recorded meeting presentations.
              </p>
            </div>

            {storyLoading ? (
              <div className="py-12 text-center text-xs text-[#6b6b6b] space-y-2">
                <div className="w-6 h-6 border-2 border-black border-t-transparent rounded-full animate-spin mx-auto"></div>
                <p>Tracking slide appearances across archive...</p>
              </div>
            ) : storySlide ? (
              <div className="space-y-6">
                {/* Slide Preview */}
                <div className="aspect-video max-w-md mx-auto rounded-xl border border-[#e5e5e5] overflow-hidden bg-gray-50">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={api.objectUrl(storySlide.object_hash)}
                    alt={storySlide.title}
                    className="w-full h-full object-contain"
                  />
                </div>

                {/* Appearance 1: Document Decks */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-black uppercase tracking-wider text-[11px]">
                      Document Decks ({storySlide.decks?.length || 0})
                    </span>
                    <span className="text-[#6b6b6b]">Stored once in Content Addressable Storage</span>
                  </div>
                  {storySlide.decks && storySlide.decks.length > 0 ? (
                    <div className="border border-[#e5e5e5] rounded-xl divide-y divide-[#e5e5e5] text-xs">
                      {storySlide.decks.map((d, i) => (
                        <div key={i} className="p-3.5 flex items-center justify-between gap-4">
                          <div className="min-w-0 space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-black truncate">{d.name}</span>
                              {d.revision && (
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono border border-[#e5e5e5] bg-gray-50 text-black">
                                  Rev {d.revision}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 text-[#6b6b6b] text-[11px]">
                              <span>Page {d.page_no}</span>
                              <span>•</span>
                              <span>{d.source_name || (d.governed ? "SharePoint" : "OneDrive")}</span>
                            </div>
                          </div>
                          <Link
                            href={`/files/${d.file_id}`}
                            className="text-xs font-medium text-black hover:underline flex-shrink-0"
                          >
                            Open deck →
                          </Link>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-[#6b6b6b] italic">No document deck occurrences found.</p>
                  )}
                </div>

                {/* Appearance 2: Video Recordings */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-black uppercase tracking-wider text-[11px]">
                      Meeting Recordings ({storySlide.videos?.length || 0})
                    </span>
                    <span className="text-[#6b6b6b]">Presented live during recorded meetings</span>
                  </div>
                  {storySlide.videos && storySlide.videos.length > 0 ? (
                    <div className="border border-[#e5e5e5] rounded-xl divide-y divide-[#e5e5e5] text-xs">
                      {storySlide.videos.map((v, i) => (
                        <div key={i} className="p-3.5 flex items-center justify-between gap-4">
                          <div className="min-w-0 space-y-1">
                            <span className="font-semibold text-black block truncate">{v.video_name}</span>
                            <div className="flex items-center gap-2 text-[#6b6b6b] text-[11px]">
                              <span>Shown at {v.timestamp_str}</span>
                              <span>•</span>
                              <span>{v.source_name}</span>
                            </div>
                          </div>
                          {v.file_id === fileId ? (
                            <button
                              type="button"
                              onClick={() => {
                                setStoryOpen(false);
                                jumpToTime(v.timestamp);
                              }}
                              className="px-2.5 py-1 rounded text-xs border border-black bg-black text-white hover:bg-gray-800 transition-colors flex-shrink-0"
                            >
                              Jump to {v.timestamp_str}
                            </button>
                          ) : (
                            <Link
                              href={`/files/${v.file_id}`}
                              className="text-xs font-medium text-black hover:underline flex-shrink-0"
                            >
                              Open recording →
                            </Link>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-[#6b6b6b] italic">Not presented in any recorded video meetings.</p>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
