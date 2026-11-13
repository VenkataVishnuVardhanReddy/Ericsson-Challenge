import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Distill — Ericsson Data Storage Optimization",
  description: "Ericsson's files got much smaller, and nothing important was lost.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.className}>
      <body className="min-h-screen bg-white text-black antialiased selection:bg-black selection:text-white">
        <Navbar />
        <main className="max-w-[1120px] mx-auto px-4 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
