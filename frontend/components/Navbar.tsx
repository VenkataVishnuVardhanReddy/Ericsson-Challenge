"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Navbar() {
  const pathname = usePathname();

  const navItems = [
    { label: "Optimize", href: "/" },
    { label: "Duplicates & Revisions", href: "/duplicates" },
    { label: "Hybrid Search & QA", href: "/search" },
    { label: "Offboarding", href: "/offboarding" },
    { label: "How It Works", href: "/how-it-works" },
  ];

  return (
    <header className="border-b border-[#e5e5e5] bg-[#ffffff] sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
        <div className="flex items-center space-x-6">
          <Link href="/" className="flex items-center space-x-2">
            <span className="font-mono font-bold tracking-wider text-black text-sm">DISTILL</span>
            <span className="text-xs font-mono text-gray-500 border-l border-gray-300 pl-2">
              ERICSSON BUILD 2026
            </span>
          </Link>

          <nav className="hidden md:flex items-center space-x-1">
            {navItems.map((item) => {
              const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-1.5 text-xs font-mono transition-colors border ${
                    active
                      ? "border-black bg-black text-white"
                      : "border-transparent text-gray-600 hover:text-black hover:border-gray-200"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2 text-xs font-mono">
            <span className="w-2 h-2 rounded-full bg-green-600 inline-block animate-pulse"></span>
            <span className="text-gray-500">ENGINE ONLINE</span>
          </div>
          <span className="text-xs font-mono text-gray-400">CPU INT8</span>
        </div>
      </div>
    </header>
  );
}
