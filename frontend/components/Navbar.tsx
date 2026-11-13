"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Loader2, Check } from "lucide-react";
import { api } from "@/lib/api";

export default function Navbar() {
  const pathname = usePathname();
  const [backendStatus, setBackendStatus] = useState<"running" | "offline" | "processing">("running");
  const [activeJobsCount, setActiveJobsCount] = useState<number>(0);

  useEffect(() => {
    let timer: NodeJS.Timeout;

    async function checkStatus() {
      try {
        const res = await api.getJobs();
        const running = res?.jobs?.filter((j: any) => j.status === "processing" || j.status === "running") || [];
        if (running.length > 0) {
          setBackendStatus("processing");
          setActiveJobsCount(running.length);
        } else {
          setBackendStatus("running");
          setActiveJobsCount(0);
        }
      } catch (err) {
        setBackendStatus("offline");
        setActiveJobsCount(0);
      }
    }

    checkStatus();
    timer = setInterval(checkStatus, activeJobsCount > 0 ? 3000 : 8000);
    return () => clearInterval(timer);
  }, [activeJobsCount]);

  const navItems = [
    { label: "Overview", href: "/" },
    { label: "Files", href: "/files" },
    { label: "Duplicates", href: "/duplicates" },
    { label: "Search", href: "/search" },
    { label: "Employee leaving", href: "/offboarding" },
    { label: "How it works", href: "/how-it-works" },
  ];

  return (
    <header className="border-b border-[#e5e5e5] bg-white sticky top-0 z-50">
      <div className="max-w-[1120px] mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center space-x-8">
          <Link href="/" className="flex items-center space-x-2">
            <span className="font-semibold tracking-tight text-black text-base">Distill</span>
            <span className="text-xs text-[#6b6b6b] border-l border-[#e5e5e5] pl-2 font-mono">
              Ericsson Build 2026
            </span>
          </Link>

          <nav className="hidden md:flex items-center space-x-1">
            {navItems.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                    active
                      ? "bg-black text-white font-medium"
                      : "text-[#6b6b6b] hover:text-black hover:bg-gray-100"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center space-x-3 text-xs">
          {backendStatus === "processing" ? (
            <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full border border-black bg-white text-black font-medium">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>Processing {activeJobsCount} file{activeJobsCount > 1 ? "s" : ""}...</span>
            </div>
          ) : backendStatus === "running" ? (
            <div className="flex items-center space-x-1.5 text-[#6b6b6b]">
              <span className="w-2 h-2 rounded-full bg-black inline-block"></span>
              <span>Backend running</span>
            </div>
          ) : (
            <div className="flex items-center space-x-1.5 text-[#6b6b6b]">
              <span className="w-2 h-2 rounded-full border border-black inline-block"></span>
              <span>Backend offline</span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
