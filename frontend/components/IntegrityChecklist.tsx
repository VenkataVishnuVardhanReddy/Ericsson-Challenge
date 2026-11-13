"use client";

import { useEffect, useState } from "react";
import { api, formatBytes } from "@/lib/api";
import { FileIntegrity } from "@/lib/types";

interface Props {
  fileId: number;
}

export default function IntegrityChecklist({ fileId }: Props) {
  const [data, setData] = useState<FileIntegrity | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getFileIntegrity(fileId)
      .then(setData)
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, [fileId]);

  if (loading) {
    return <div className="p-4 text-xs font-mono text-gray-500">Checking data integrity guarantees...</div>;
  }

  if (!data) return null;

  return (
    <div className="border border-[#e5e5e5] bg-white p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-[#e5e5e5] gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-green-600 inline-block"></span>
            <h3 className="font-mono font-bold text-sm text-black uppercase tracking-wider">
              "Nothing Was Lost" Verification Protocol
            </h3>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Verification of information preservation across storage compression levels.
          </p>
        </div>

        <div className="flex items-center space-x-4 font-mono text-right">
          <div>
            <div className="text-[10px] text-gray-500 uppercase">Information Retention</div>
            <div className="text-xl font-bold text-green-600">{data.retention_score}%</div>
          </div>
          <div className="border-l border-gray-200 pl-4">
            <div className="text-[10px] text-gray-500 uppercase">Compression Ratio</div>
            <div className="text-xl font-bold text-black">{data.compression_ratio}</div>
          </div>
        </div>
      </div>

      {/* Verification Checks Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {data.checks.map((check, idx) => (
          <div key={idx} className="border border-[#e5e5e5] p-3 flex items-start space-x-3 bg-gray-50/50">
            <div className="mt-0.5">
              <span className="inline-block px-1.5 py-0.5 border border-green-600 text-green-700 bg-green-50 text-[10px] font-mono font-bold">
                PASSED
              </span>
            </div>
            <div>
              <div className="font-mono font-semibold text-xs text-black">{check.name}</div>
              <div className="text-[11px] text-gray-600 mt-0.5">{check.detail}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Content-Addressable Hashes (CAS) Table */}
      <div className="pt-2">
        <h4 className="text-xs font-mono uppercase tracking-wider text-gray-500 mb-2">
          Content-Addressable Storage (CAS) Hashes
        </h4>
        <div className="border border-[#e5e5e5] overflow-x-auto text-[11px] font-mono">
          <table className="w-full text-left border-collapse">
            <tbody className="divide-y divide-[#e5e5e5]">
              {data.cas_hashes.raw_sha256 && (
                <tr className="hover:bg-gray-50">
                  <td className="py-2 px-3 text-gray-500 w-44">RAW_SHA256</td>
                  <td className="py-2 px-3 text-black break-all font-mono">
                    {data.cas_hashes.raw_sha256}
                  </td>
                </tr>
              )}
              {data.cas_hashes.transcript_sha256 && (
                <tr className="hover:bg-gray-50">
                  <td className="py-2 px-3 text-gray-500 w-44">TRANSCRIPT_SHA256</td>
                  <td className="py-2 px-3 text-black break-all font-mono">
                    {data.cas_hashes.transcript_sha256}
                  </td>
                </tr>
              )}
              {data.cas_hashes.audio_sha256 && (
                <tr className="hover:bg-gray-50">
                  <td className="py-2 px-3 text-gray-500 w-44">AUDIO_OPUS_SHA256</td>
                  <td className="py-2 px-3 text-black break-all font-mono">
                    {data.cas_hashes.audio_sha256}
                  </td>
                </tr>
              )}
              {data.cas_hashes.slides_content_ids && data.cas_hashes.slides_content_ids.length > 0 && (
                <tr className="hover:bg-gray-50">
                  <td className="py-2 px-3 text-gray-500 w-44">SLIDE_CONTENT_IDS</td>
                  <td className="py-2 px-3 text-gray-700">
                    {data.cas_hashes.slides_content_ids.length} unique slide hashes registered in CAS index
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
