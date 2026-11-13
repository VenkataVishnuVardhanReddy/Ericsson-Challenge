"use client";

import { useRef, useState, useEffect } from "react";
import { api, formatDuration } from "@/lib/api";
import { Keyframe, Segment } from "@/lib/types";

interface Props {
  fileId: number;
  duration: number;
  keyframes: Keyframe[];
  segments: Segment[];
  hasAudio: boolean;
  recreated: { mode: string; bytes: number; url: string }[];
}

const DEICTIC_REGEX = /\b(as you (?:can )?see here|look at (?:this|the)|on this (?:slide|chart|graph|diagram)|here on the (?:left|right)|shown (?:here|above|below)|this (?:chart|graph|diagram|table|slide))\b/gi;

export default function RecreationPlayer({
  fileId,
  duration,
  keyframes,
  segments,
  hasAudio,
  recreated,
}: Props) {
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [viewMode, setViewMode] = useState<"audio_canvas" | "recreated_video">("audio_canvas");
  const [recreateLoading, setRecreateLoading] = useState(false);
  const [recreatedList, setRecreatedList] = useState(Array.isArray(recreated) ? recreated : []);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const transcriptContainerRef = useRef<HTMLDivElement | null>(null);

  // Active keyframe based on currentTime
  const activeKeyframe = keyframes.reduce<Keyframe | null>((prev, curr) => {
    if (curr.start <= currentTime && (!prev || curr.start > prev.start)) {
      return curr;
    }
    return prev;
  }, keyframes[0] || null);

  // Active segment
  const activeSegment = segments.find(
    (s) => currentTime >= s.start && currentTime <= s.end
  );

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const handleSeek = (newTime: number) => {
    setCurrentTime(newTime);
    if (audioRef.current) {
      audioRef.current.currentTime = newTime;
    }
  };

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleGenerateRecreation = async (mode: string) => {
    setRecreateLoading(true);
    try {
      const res = await api.recreateVideo(fileId, mode, true);
      setRecreatedList((prev) => [...prev.filter((r) => r.mode !== mode), res]);
      setViewMode("recreated_video");
    } catch (e: any) {
      alert(`Recreation failed: ${e.message}`);
    } finally {
      setRecreateLoading(false);
    }
  };

  return (
    <div className="border border-[#e5e5e5] bg-white p-6 space-y-6">
      {/* Player Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-[#e5e5e5] gap-4">
        <div>
          <h3 className="font-mono font-bold text-sm text-black uppercase tracking-wider">
            Distilled Video Recreation Engine (98%+ Storage Reduction)
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            Reconstructs original presentation experience from Opus speech audio (T2) and lossless CAS keyframes (T3).
          </p>
        </div>

        <div className="flex items-center space-x-2 font-mono text-xs">
          <button
            onClick={() => setViewMode("audio_canvas")}
            className={`px-3 py-1.5 border transition-colors ${
              viewMode === "audio_canvas"
                ? "border-black bg-black text-white"
                : "border-[#e5e5e5] text-gray-700 hover:border-black"
            }`}
          >
            CANVAS RECONSTRUCTION (T2+T3)
          </button>
          <button
            onClick={() => setViewMode("recreated_video")}
            className={`px-3 py-1.5 border transition-colors ${
              viewMode === "recreated_video"
                ? "border-black bg-black text-white"
                : "border-[#e5e5e5] text-gray-700 hover:border-black"
            }`}
          >
            RENDERED MP4 (ON-DEMAND)
          </button>
        </div>
      </div>

      {viewMode === "audio_canvas" ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Visual Presentation Canvas */}
          <div className="lg:col-span-7 flex flex-col space-y-3">
            <div className="relative aspect-video bg-black flex items-center justify-center border border-[#e5e5e5] overflow-hidden">
              {activeKeyframe?.image_key ? (
                <img
                  src={api.objectUrl(activeKeyframe.image_key)}
                  alt="Slide Keyframe"
                  className="w-full h-full object-contain"
                />
              ) : (
                <img
                  src={api.frameUrl(fileId, currentTime)}
                  alt="Video Frame"
                  className="w-full h-full object-contain"
                />
              )}

              {/* Timestamp Overlay */}
              <div className="absolute top-2 left-2 bg-black/80 text-white font-mono text-[10px] px-2 py-0.5 border border-gray-700">
                {formatDuration(currentTime)} / {formatDuration(duration)}
              </div>

              {/* Speaker Overlay */}
              {activeSegment && (
                <div className="absolute bottom-2 left-2 bg-black/80 text-white font-mono text-xs px-2.5 py-1 border border-gray-700">
                  <span className="text-gray-400 mr-1.5">SPEAKER:</span>
                  <span className="font-semibold text-white">{activeSegment.speaker || "Unknown"}</span>
                </div>
              )}
            </div>

            {/* Playback Controls & Scrubber */}
            <div className="border border-[#e5e5e5] p-3 space-y-2 bg-gray-50/50">
              {hasAudio && (
                <audio
                  ref={audioRef}
                  src={api.audioUrl(fileId)}
                  onTimeUpdate={handleTimeUpdate}
                  onEnded={() => setIsPlaying(false)}
                />
              )}

              <div className="flex items-center space-x-3">
                <button
                  onClick={togglePlay}
                  className="px-3 py-1 border border-black bg-black text-white text-xs font-mono hover:bg-gray-800"
                >
                  {isPlaying ? "PAUSE" : "PLAY AUDIO"}
                </button>

                <div className="flex-1 flex items-center space-x-2">
                  <input
                    type="range"
                    min={0}
                    max={duration || 100}
                    step={0.5}
                    value={currentTime}
                    onChange={(e) => handleSeek(parseFloat(e.target.value))}
                    className="w-full accent-black cursor-pointer"
                  />
                </div>

                <div className="text-xs font-mono text-gray-600 whitespace-nowrap">
                  {formatDuration(currentTime)} / {formatDuration(duration)}
                </div>
              </div>
            </div>

            {/* Slide Moments Strip */}
            <div className="space-y-1">
              <span className="text-[10px] font-mono uppercase text-gray-500">
                Keyframe Slide Transitions ({keyframes.length} moments detected)
              </span>
              <div className="flex space-x-2 overflow-x-auto pb-2 pt-1">
                {keyframes.map((kf, i) => (
                  <button
                    key={kf.id || i}
                    onClick={() => handleSeek(kf.start)}
                    className={`flex-shrink-0 w-24 border p-1 text-left transition-colors ${
                      activeKeyframe?.id === kf.id
                        ? "border-black bg-black text-white"
                        : "border-[#e5e5e5] bg-white text-black hover:border-gray-400"
                    }`}
                  >
                    <div className="aspect-video bg-gray-100 overflow-hidden mb-1">
                      {kf.image_key && (
                        <img
                          src={api.objectUrl(kf.image_key)}
                          alt={`Moment ${i + 1}`}
                          className="w-full h-full object-cover"
                        />
                      )}
                    </div>
                    <div className="text-[9px] font-mono truncate">{formatDuration(kf.start)}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Time-Linked Speech Transcript */}
          <div className="lg:col-span-5 flex flex-col h-[520px] border border-[#e5e5e5] bg-white">
            <div className="p-3 border-b border-[#e5e5e5] bg-gray-50 flex items-center justify-between">
              <span className="text-xs font-mono uppercase text-gray-600">
                Time-Linked Speech Transcript
              </span>
              <span className="text-[10px] font-mono text-gray-500">
                {segments.length} segments
              </span>
            </div>

            <div ref={transcriptContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4 text-xs font-mono">
              {segments.map((seg, idx) => {
                const isActive = currentTime >= seg.start && currentTime <= seg.end;
                const text = seg?.text || "";
                const parts = text.split(DEICTIC_REGEX);

                return (
                  <div
                    key={seg.id || idx}
                    onClick={() => handleSeek(seg.start)}
                    className={`p-2.5 cursor-pointer border transition-colors ${
                      isActive
                        ? "border-black bg-gray-100 text-black font-semibold"
                        : "border-transparent hover:border-gray-200 text-gray-700"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1 text-[10px] text-gray-500">
                      <span className="font-bold text-black uppercase">{seg.speaker || "Speaker"}</span>
                      <span>{formatDuration(seg.start)}</span>
                    </div>
                    <p className="leading-relaxed font-sans text-xs">
                      {parts.map((p, pIdx) =>
                        p && p.match(DEICTIC_REGEX) ? (
                          <span
                            key={pIdx}
                            className="bg-amber-100 border-b border-amber-500 text-amber-900 px-1 py-0.5 rounded-none font-medium"
                            title="Deictic reference linked to visible slide"
                          >
                            {p}
                          </span>
                        ) : (
                          p
                        )
                      )}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* Recreated Video Tab */
        <div className="border border-[#e5e5e5] p-6 space-y-4">
          <div className="flex items-center justify-between pb-4 border-b border-[#e5e5e5]">
            <div>
              <h4 className="text-xs font-mono uppercase text-black font-bold">
                Rendered MP4 Recreation
              </h4>
              <p className="text-xs text-gray-500 mt-0.5">
                On-demand compilation of slides + Opus audio into standard MP4 for legacy players.
              </p>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => handleGenerateRecreation("audio_slides")}
                disabled={recreateLoading}
                className="px-3 py-1.5 border border-black bg-black text-white text-xs font-mono hover:bg-gray-800 disabled:opacity-50"
              >
                {recreateLoading ? "COMPILING VIDEO..." : "RECREATE (SLIDES + AUDIO)"}
              </button>
            </div>
          </div>

          {recreatedList.length > 0 ? (
            <div className="space-y-4">
              <video
                controls
                src={api.recreatedVideoUrl(fileId, recreatedList[0].mode)}
                className="w-full max-h-[500px] bg-black border border-[#e5e5e5]"
              />
              <div className="flex items-center justify-between text-xs font-mono text-gray-500">
                <span>Mode: {recreatedList[0].mode}</span>
                <a
                  href={api.recreatedVideoUrl(fileId, recreatedList[0].mode)}
                  download
                  className="underline text-black hover:text-gray-700"
                >
                  Download Recreated MP4
                </a>
              </div>
            </div>
          ) : (
            <div className="py-16 text-center text-xs font-mono text-gray-500 border border-dashed border-[#e5e5e5]">
              No rendered video file compiled yet. Click "RECREATE (SLIDES + AUDIO)" to render on demand.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
