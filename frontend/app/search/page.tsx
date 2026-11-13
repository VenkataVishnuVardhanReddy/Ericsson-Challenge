"use client";

import { useState } from "react";
import Link from "next/link";
import { api, formatDuration } from "@/lib/api";
import { SearchResult } from "@/lib/types";

export default function SearchQAPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [filterKind, setFilterKind] = useState("all");

  // AI QA states
  const [question, setQuestion] = useState("");
  const [qaAnswer, setQaAnswer] = useState<string | null>(null);
  const [qaCitations, setQaCitations] = useState<any[]>([]);
  const [qaLoading, setQaLoading] = useState(false);

  // Corpus Export states
  const [exportFmt, setExportFmt] = useState("jsonl");
  const [redactPii, setRedactPii] = useState(true);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;
    setSearchLoading(true);
    try {
      const res = await api.search(query, 25, filterKind);
      setResults(res.results || []);
    } catch (e: any) {
      console.error(e);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleAskAI = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setQaLoading(true);
    setQaAnswer(null);
    setQaCitations([]);
    try {
      const res = await api.aiAsk(question, 6);
      setQaAnswer(res.answer);
      setQaCitations(res.citations || []);
    } catch (e: any) {
      setQaAnswer(`Failed to query LLM engine: ${e.message}`);
    } finally {
      setQaLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="border border-[#e5e5e5] bg-white p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-mono font-bold text-black">
              Hybrid Search & Grounded AI Intelligence
            </h1>
            <p className="text-xs text-gray-600 mt-1 max-w-2xl">
              Query distilled audio transcripts, OCR slide texts, and chunk embeddings simultaneously with strict source attribution.
            </p>
          </div>

          {/* Export Corpus Pill */}
          <div className="flex items-center space-x-2 border border-[#e5e5e5] p-2 bg-gray-50/60 text-xs font-mono">
            <label className="flex items-center space-x-1 cursor-pointer">
              <input
                type="checkbox"
                checked={redactPii}
                onChange={(e) => setRedactPii(e.target.checked)}
                className="accent-black"
              />
              <span className="text-[10px] text-gray-600 uppercase">REDACT PII</span>
            </label>
            <select
              value={exportFmt}
              onChange={(e) => setExportFmt(e.target.value)}
              className="border border-[#e5e5e5] bg-white px-2 py-0.5 text-[10px] font-mono"
            >
              <option value="jsonl">JSONL</option>
              <option value="markdown">MARKDOWN</option>
            </select>
            <a
              href={api.exportCorpusUrl(exportFmt, redactPii)}
              download
              className="px-2.5 py-1 bg-black text-white text-[10px] hover:bg-gray-800 transition-colors"
            >
              EXPORT AI CORPUS
            </a>
          </div>
        </div>
      </div>

      {/* Grounded AI QA Box */}
      <section className="border border-black bg-white p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-black inline-block"></span>
            <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-black">
              Grounded AI Question Answering (Strict RAG with Citations)
            </h2>
          </div>
          <span className="text-[10px] font-mono text-gray-500 uppercase">OLLAMA / HEURISTIC RAG</span>
        </div>

        <form onSubmit={handleAskAI} className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a technical question across all meetings and documents (e.g. 'What are the main architecture goals of C2L?')..."
            className="flex-1 border border-[#e5e5e5] px-4 py-2.5 text-xs font-mono focus:outline-none focus:border-black"
          />
          <button
            type="submit"
            disabled={qaLoading}
            className="px-5 py-2.5 border border-black bg-black text-white text-xs font-mono hover:bg-gray-800 disabled:opacity-50"
          >
            {qaLoading ? "SYNTHESIZING..." : "ASK ARCHIVE"}
          </button>
        </form>

        {qaAnswer && (
          <div className="border border-[#e5e5e5] bg-gray-50 p-4 space-y-3 font-mono text-xs">
            <div className="text-[10px] text-gray-500 uppercase font-bold">Answer:</div>
            <div className="font-sans text-xs leading-relaxed text-black whitespace-pre-wrap">
              {qaAnswer}
            </div>

            {qaCitations.length > 0 && (
              <div className="pt-2 border-t border-gray-200">
                <span className="text-[10px] text-gray-500 uppercase block mb-1.5">
                  Verified Evidence Citations:
                </span>
                <div className="flex flex-wrap gap-2">
                  {qaCitations.map((cit, idx) => (
                    <Link
                      key={idx}
                      href={`/files/${cit.file_id}`}
                      className="px-2 py-1 border border-black bg-white text-black text-[10px] font-mono hover:bg-black hover:text-white transition-colors"
                    >
                      [{cit.file_name} — {cit.kind?.toUpperCase()} {cit.page_no ? `p.${cit.page_no}` : ""}]
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Hybrid Search Bar */}
      <section className="space-y-4">
        <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search keyword, slide topic, error code, speaker quote, or phrase..."
            className="flex-1 border border-[#e5e5e5] px-4 py-2.5 text-xs font-mono focus:outline-none focus:border-black"
          />
          <div className="flex gap-2">
            <select
              value={filterKind}
              onChange={(e) => setFilterKind(e.target.value)}
              className="border border-[#e5e5e5] px-3 py-2 text-xs font-mono bg-white"
            >
              <option value="all">ALL KINDS</option>
              <option value="video">VIDEOS</option>
              <option value="slide">SLIDES</option>
              <option value="document">DOCUMENTS</option>
            </select>
            <button
              type="submit"
              disabled={searchLoading}
              className="px-5 py-2 border border-black bg-black text-white text-xs font-mono hover:bg-gray-800 disabled:opacity-50"
            >
              {searchLoading ? "SEARCHING..." : "SEARCH"}
            </button>
          </div>
        </form>

        {/* Search Results List */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs font-mono text-gray-500">
            <span>RESULTS ({results.length})</span>
            {query && <span>QUERY: "{query}"</span>}
          </div>

          <div className="space-y-3">
            {results.map((item, idx) => (
              <div
                key={idx}
                className="border border-[#e5e5e5] bg-white p-4 flex flex-col sm:flex-row items-start justify-between gap-4 hover:border-black transition-colors"
              >
                <div className="flex items-start space-x-4 flex-1">
                  {item.image_key && (
                    <div className="w-28 aspect-video bg-gray-100 border border-[#e5e5e5] flex-shrink-0 overflow-hidden">
                      <img
                        src={api.objectUrl(item.image_key)}
                        alt="Slide Thumbnail"
                        className="w-full h-full object-cover"
                      />
                    </div>
                  )}

                  <div className="space-y-1">
                    <div className="flex items-center space-x-2 text-[10px] font-mono">
                      <span className="px-1.5 py-0.2 border border-black bg-black text-white uppercase">
                        {item.kind}
                      </span>
                      <span className="text-gray-500">{item.source_name}</span>
                      {item.timestamp !== undefined && (
                        <span className="text-gray-700 font-bold">
                          AT {formatDuration(item.timestamp)}
                        </span>
                      )}
                      {item.speaker && (
                        <span className="text-gray-600">[{item.speaker}]</span>
                      )}
                    </div>

                    <Link
                      href={`/files/${item.file_id}`}
                      className="font-mono text-xs font-bold text-black hover:underline block"
                    >
                      {item.file_name}
                    </Link>

                    <p
                      className="text-xs text-gray-700 font-sans line-clamp-2 leading-relaxed"
                      dangerouslySetInnerHTML={{ __html: item.snippet || item.text }}
                    />
                  </div>
                </div>

                <div className="text-right flex-shrink-0">
                  <Link
                    href={`/files/${item.file_id}`}
                    className="px-3 py-1 border border-black text-[11px] font-mono hover:bg-black hover:text-white transition-colors"
                  >
                    JUMP TO MOMENT
                  </Link>
                </div>
              </div>
            ))}

            {results.length === 0 && !searchLoading && query && (
              <div className="py-12 text-center text-xs font-mono text-gray-500 border border-dashed border-[#e5e5e5]">
                No matching results found for "{query}". Try broader terms.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
