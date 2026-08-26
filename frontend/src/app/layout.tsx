import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CourseTide — AI-Powered Personalized Learning Path",
  description: "Navigate your career path with AI-driven skill-gap detection, prerequisite sequencing, and grounded learning recommendations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen flex flex-col antialiased">
        <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-lg bg-teal-500 flex items-center justify-center font-bold text-slate-950 text-lg shadow-md shadow-teal-500/20">
                C
              </div>
              <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-teal-400 to-cyan-400 bg-clip-text text-transparent">
                CourseTide
              </span>
              <span className="text-xs uppercase tracking-wider px-2 py-0.5 rounded bg-teal-500/10 text-teal-400 border border-teal-500/20 font-medium">
                Day 1 Foundation
              </span>
            </div>
            <nav className="flex items-center space-x-6 text-sm font-medium text-slate-400">
              <span className="hover:text-slate-200 cursor-pointer transition-colors">Roadmap</span>
              <span className="hover:text-slate-200 cursor-pointer transition-colors">Skill Gap</span>
              <span className="hover:text-slate-200 cursor-pointer transition-colors">Dashboard</span>
            </nav>
          </div>
        </header>

        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>

        <footer className="border-t border-slate-900 bg-slate-950/50 py-6 text-center text-xs text-slate-500">
          CourseTide © 2026 — Grounded AI Learning Path Recommender
        </footer>
      </body>
    </html>
  );
}
