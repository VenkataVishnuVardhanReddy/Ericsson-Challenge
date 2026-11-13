"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Search,
  Sparkles,
  HelpCircle,
  Video,
  FileText,
  Clock,
  ArrowRight,
  ExternalLink,
} from "lucide-react";
import { api, formatDuration } from "@/lib/api";
import { SearchResult } from "@/lib/types";
import Explain from "@/components/Explain";

function HighlightedText({ text, query }: { text: string; query: string }) {
  if (!query.trim() || !text) return <span>{text}</span>;

  const terms = query
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length > 1);

  if (terms.length === 0) return <span>{text}</span>;

  const pattern = new RegExp(
    `(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi"
  );
  const parts = text.split(pattern);

  return (
    <span>
      {parts.map((part, i) =>
        terms.includes(part.toLowerCase()) ? (
          <mark key={i} className="bg-gray-200 text-black px-0.5 rounded font-medium">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </span>
  );
}

export default function SearchPage() {
  const [activeTab, setActiveTab] = useState<"search" | "qa">("search");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Question answering state
  const [question, setQuestion] = useState("");
  const [qaAnswer, setQaAnswer] = useState<string | null>(null);
  const [qaCitations, setQaCitations] = useState<any[]>([]);
  const [qaLoading, setQaLoading] = useState(false);

  const exampleChips = [
    "SD-WAN",
    "Ericsson Response",
    "GraalVM native image",
    "Ahead-of-Time compilation",
    "Hackathon",
  ];

  const handleSearch = async (searchQuery: string) => {
    const q = searchQuery.trim();
    if (!q) return;
    setSearchLoading(true);
    try {
      const res = await api.search(q, 25);
      setResults(res.results || []);
    } catch (e) {
      console.error(e);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleAskQuestion = async (qText: string) => {
    const q = qText.trim();
    if (!q) return;
    setQaLoading(true);
    setQaAnswer(null);
    setQaCitations([]);
    try {
      const res = await api.aiAsk(q, 6);
      setQaAnswer(res.answer);
      setQaCitations(res.citations || []);
    } catch (e: any) {
      setQaAnswer("Failed to retrieve matching sentences.");
    } finally {
      setQaLoading(false);
    }
  };

  return (
    <div className="space-y-8 py-2 max-w-[1120px] mx-auto pb-24">
      {/* HEADER & INTRO */}
      <div className="space-y-2 border-b border-[#e5e5e5] pb-6">
        <h1 className="text-3xl font-bold tracking-tight text-black">Search</h1>
        <p className="text-base text-[#6b6b6b] max-w-3xl leading-relaxed">
          Search every meeting, video and document at once — by exact words or by meaning.
        </p>
      </div>

      {/* TABS: SEARCH VS ASK A QUESTION */}
      <div className="flex border-b border-[#e5e5e5] text-xs">
        <button
          type="button"
          onClick={() => setActiveTab("search")}
          className={`px-4 py-2.5 font-medium border-b-2 transition-colors ${
            activeTab === "search"
              ? "border-black text-black font-semibold"
              : "border-transparent text-[#6b6b6b] hover:text-black"
          }`}
        >
          Search files & transcripts
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("qa")}
          className={`px-4 py-2.5 font-medium border-b-2 transition-colors ${
            activeTab === "qa"
              ? "border-black text-black font-semibold"
              : "border-transparent text-[#6b6b6b] hover:text-black"
          }`}
        >
          Ask a question
        </button>
      </div>

      {/* TAB 1: SEARCH */}
      {activeTab === "search" && (
        <div className="space-y-6">
          {/* Search Box */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSearch(query);
            }}
            className="flex flex-col sm:flex-row gap-3"
          >
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-[#6b6b6b]" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search spoken sentences, slide titles, keywords..."
                className="w-full pl-10 pr-4 py-3 rounded-xl border border-[#e5e5e5] text-sm text-black placeholder:text-[#6b6b6b] focus:outline-none focus:border-black"
              />
            </div>
            <button
              type="submit"
              disabled={searchLoading}
              className="px-6 py-3 rounded-xl bg-black text-white text-xs font-semibold hover:bg-neutral-800 transition-colors disabled:opacity-50"
            >
              {searchLoading ? "Searching..." : "Search"}
            </button>
          </form>

          {/* Example Chips */}
          <div className="flex flex-wrap items-center gap-2 text-xs text-[#6b6b6b]">
            <span>Try searching:</span>
            {exampleChips.map((chip, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setQuery(chip);
                  handleSearch(chip);
                }}
                className="px-2.5 py-1 rounded-md border border-[#e5e5e5] bg-gray-50 text-black hover:border-black transition-colors"
              >
                {chip}
              </button>
            ))}
          </div>

          {/* Results List */}
          <div className="space-y-3 pt-4">
            <div className="flex items-center justify-between text-xs text-[#6b6b6b]">
              <span>Results ({results.length})</span>
              {query && <span className="font-mono">Query: &quot;{query}&quot;</span>}
            </div>

            {results.length > 0 ? (
              <div className="space-y-3">
                {results.map((item, idx) => {
                  const targetTime = item.start ?? 0;
                  return (
                    <div
                      key={idx}
                      className="p-4 rounded-xl border border-[#e5e5e5] bg-white hover:border-black transition-colors flex flex-col sm:flex-row items-start justify-between gap-4"
                    >
                      <div className="flex items-start gap-4 flex-1">
                        {item.image && (
                          <div className="w-24 sm:w-28 aspect-video bg-gray-100 rounded-lg border border-[#e5e5e5] overflow-hidden flex-shrink-0">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={`http://127.0.0.1:8000/api/objects/${item.image}`}
                              alt="Slide preview"
                              className="w-full h-full object-cover"
                            />
                          </div>
                        )}

                        <div className="space-y-1.5 flex-1 text-xs">
                          <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-[#6b6b6b]">
                            <span className="font-semibold text-black">{item.name}</span>
                            {item.start !== null && (
                              <span>• {formatDuration(item.start)}</span>
                            )}
                            {item.page_no && <span>• Slide page {item.page_no}</span>}
                          </div>

                          <p className="text-black text-sm leading-relaxed">
                            <HighlightedText text={item.snippet || item.title} query={query} />
                          </p>
                        </div>
                      </div>

                      <div className="flex-shrink-0 self-end sm:self-center">
                        <Link
                          href={`/files/${item.file_id}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#e5e5e5] text-xs font-medium text-black hover:border-black transition-colors"
                        >
                          <span>Open file</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : query && !searchLoading ? (
              <div className="p-12 text-center border border-dashed border-[#e5e5e5] rounded-xl text-xs text-[#6b6b6b]">
                No matching results found for &quot;{query}&quot;. Try one of the example chips above.
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* TAB 2: ASK A QUESTION */}
      {activeTab === "qa" && (
        <div className="space-y-6">
          <div className="p-4 rounded-xl border border-[#e5e5e5] bg-gray-50/70 text-xs text-[#6b6b6b] space-y-1">
            <span className="font-semibold text-black block">Honest question answering</span>
            <p>
              Answers are built from the original sentences (no AI writing). We find the exact sentences matching your question from the distilled transcripts and slides.
            </p>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAskQuestion(question);
            }}
            className="flex flex-col sm:flex-row gap-3"
          >
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What is the benefit of GraalVM native image?"
              className="flex-1 px-4 py-3 rounded-xl border border-[#e5e5e5] text-sm text-black placeholder:text-[#6b6b6b] focus:outline-none focus:border-black"
            />
            <button
              type="submit"
              disabled={qaLoading}
              className="px-6 py-3 rounded-xl bg-black text-white text-xs font-semibold hover:bg-neutral-800 transition-colors disabled:opacity-50"
            >
              {qaLoading ? "Finding sentences..." : "Ask question"}
            </button>
          </form>

          {/* Example Questions */}
          <div className="flex flex-wrap items-center gap-2 text-xs text-[#6b6b6b]">
            <span>Try asking:</span>
            {[
              "What is Ahead-of-Time compilation in GraalVM?",
              "What is Ericsson Response?",
              "What happened in the SD-WAN presentation?",
            ].map((q, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setQuestion(q);
                  handleAskQuestion(q);
                }}
                className="px-2.5 py-1 rounded-md border border-[#e5e5e5] bg-gray-50 text-black hover:border-black transition-colors"
              >
                {q}
              </button>
            ))}
          </div>

          {/* QA Answer & Sentences Box */}
          {qaAnswer && (
            <div className="p-6 rounded-xl border border-black bg-white space-y-4 text-xs">
              <div>
                <span className="text-[11px] font-semibold text-[#6b6b6b] uppercase tracking-wider block">
                  Original sentences found:
                </span>
                <div className="mt-2 text-sm text-black whitespace-pre-line leading-relaxed">
                  {qaAnswer}
                </div>
              </div>

              {qaCitations.length > 0 && (
                <div className="pt-4 border-t border-[#e5e5e5] space-y-2">
                  <span className="font-semibold text-black block text-[11px]">Sources:</span>
                  <div className="space-y-1.5">
                    {qaCitations.map((c, idx) => (
                      <div key={idx} className="flex items-center justify-between text-[#6b6b6b]">
                        <span>
                          [{c.idx}] {c.name} {c.time_label && `(${c.time_label})`}
                        </span>
                        <Link
                          href={`/files/${c.file_id}`}
                          className="text-black hover:underline font-medium ml-2"
                        >
                          View file →
                        </Link>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
