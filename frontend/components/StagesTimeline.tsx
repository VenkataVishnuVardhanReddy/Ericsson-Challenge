"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { FileStages } from "@/lib/types";

interface Props {
  fileId: number;
  initialStatus: string;
}

export default function StagesTimeline({ fileId, initialStatus }: Props) {
  const [data, setData] = useState<FileStages | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const fetchStages = async () => {
      try {
        const res = await api.getFileStages(fileId);
        if (active) setData(res);
      } catch (e) {
        // quiet error
      }
    };
    fetchStages();
    // Poll if processing
    let timer: any = null;
    if (initialStatus === "processing" || initialStatus === "new") {
      timer = setInterval(fetchStages, 3000);
    }
    return () => {
      active = false;
      if (timer) clearInterval(timer);
    };
  }, [fileId, initialStatus]);

  if (!data || !data.stages || data.stages.length === 0) {
    return (
      <div className="flex items-center space-x-1">
        <span className="text-[10px] font-mono text-gray-400 uppercase">{initialStatus}</span>
      </div>
    );
  }

  const doneCount = data.stages.filter((s) => s.status === "done").length;
  const totalStages = data.stages.length;
  const pct = Math.round((doneCount / totalStages) * 100);

  return (
    <div className="flex flex-col space-y-1 min-w-[140px]">
      <div className="flex items-center justify-between text-[10px] font-mono">
        <span className="text-gray-600">
          {doneCount}/{totalStages} STAGES
        </span>
        <span className={pct === 100 ? "text-green-600 font-bold" : "text-gray-500"}>{pct}%</span>
      </div>
      <div className="flex items-center space-x-0.5 w-full bg-gray-100 h-1.5 rounded-none overflow-hidden">
        {data.stages.map((stage, idx) => {
          let bg = "bg-gray-200";
          if (stage.status === "done") bg = "bg-black";
          else if (stage.status === "running") bg = "bg-amber-600 animate-pulse";
          else if (stage.status === "error") bg = "bg-red-600";
          return (
            <div
              key={idx}
              className={`h-full flex-1 ${bg}`}
              title={`${stage.name}: ${stage.status}${stage.detail ? ` (${stage.detail})` : ""}`}
            />
          );
        })}
      </div>
    </div>
  );
}
