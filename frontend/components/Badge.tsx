import React from "react";
import { Check, Loader2, AlertCircle, User, Building2 } from "lucide-react";

interface StatusBadgeProps {
  status: "done" | "working" | "problem" | "personal" | "official" | string;
  label?: string;
  className?: string;
}

export function StatusBadge({ status, label, className = "" }: StatusBadgeProps) {
  const norm = status.toLowerCase();

  if (norm === "done") {
    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-black text-white ${className}`}>
        <Check className="w-3.5 h-3.5 stroke-[2.5]" />
        <span>{label || "Done"}</span>
      </span>
    );
  }

  if (norm === "working" || norm === "processing" || norm === "queued") {
    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border border-black bg-white text-black ${className}`}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        <span>{label || "Working"}</span>
      </span>
    );
  }

  if (norm === "problem" || norm === "error") {
    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border border-black bg-white text-black ${className}`}>
        <AlertCircle className="w-3.5 h-3.5 stroke-[2]" />
        <span>{label || "Problem"}</span>
      </span>
    );
  }

  if (norm === "personal" || norm === "onedrive" || norm === "personal drive") {
    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border border-dashed border-[#6b6b6b] bg-white text-black ${className}`}>
        <User className="w-3.5 h-3.5" />
        <span>{label || "Personal drive"}</span>
      </span>
    );
  }

  if (norm === "official" || norm === "governed" || norm === "sharepoint" || norm === "play") {
    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-black text-white ${className}`}>
        <Building2 className="w-3.5 h-3.5" />
        <span>{label || "Official"}</span>
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border border-[#e5e5e5] text-[#6b6b6b] ${className}`}>
      <span>{label || status}</span>
    </span>
  );
}
