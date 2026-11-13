"use client";

import React, { useState, useRef, useEffect } from "react";
import { HelpCircle } from "lucide-react";
import { getExplanation } from "@/lib/glossary";

interface ExplainProps {
  term: string;
  children?: React.ReactNode;
  showIcon?: boolean;
}

export default function Explain({ term, children, showIcon = true }: ExplainProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLSpanElement>(null);
  const explanation = getExplanation(term);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  return (
    <span
      ref={containerRef}
      className="relative inline-flex items-center gap-0.5 align-baseline group"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {children ? <span>{children}</span> : <span>{term}</span>}
      {showIcon && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setOpen((prev) => !prev);
          }}
          className="inline-flex items-center justify-center text-[#6b6b6b] hover:text-black transition-colors ml-0.5 p-0.5 rounded focus:outline-none"
          aria-label={`Explain ${term}`}
        >
          <HelpCircle className="w-3.5 h-3.5 stroke-[1.5]" />
        </button>
      )}

      {open && (
        <span
          role="tooltip"
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-64 p-2.5 text-xs text-black bg-white border border-[#e5e5e5] rounded-lg shadow-lg pointer-events-none text-left font-sans font-normal normal-case leading-relaxed"
        >
          <span className="font-semibold block mb-0.5 text-black">{term}</span>
          <span className="text-[#6b6b6b] block">{explanation}</span>
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-[#e5e5e5]" />
        </span>
      )}
    </span>
  );
}
