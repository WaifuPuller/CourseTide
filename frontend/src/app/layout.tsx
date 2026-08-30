import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CourseTide — AI-Powered Personalized Learning Path",
  description: "Navigate your career path with AI-driven skill-gap detection, prerequisite sequencing, and grounded learning recommendations.",
  icons: {
    icon: "/course-tide-emblem.png",
    shortcut: "/course-tide-emblem.png",
    apple: "/course-tide-emblem.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#1A0706] text-[#F3EEE8] min-h-screen flex flex-col antialiased selection:bg-[#DD0200]/30 selection:text-[#F3EEE8]">
        <header className="border-b border-[#55100D]/80 bg-[#1A0706]/90 backdrop-blur sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <img
                src="/course-tide-emblem.png"
                alt="CourseTide Logo"
                className="w-8 h-8 object-contain rounded-md"
              />
              <span className="text-xl font-bold tracking-tight text-[#F3EEE8]">
                Course<span className="text-[#DD0200]">Tide</span>
              </span>
              <span className="text-[10px] uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-[#DD0200]/15 text-[#DD0200] border border-[#DD0200]/30 font-bold">
                ADAPTIVE LEARNING
              </span>
            </div>
            <nav className="flex items-center space-x-6 text-sm font-medium text-[#D9D9D9]">
              <span className="hover:text-[#F3EEE8] cursor-pointer transition-colors">Roadmap</span>
              <span className="hover:text-[#F3EEE8] cursor-pointer transition-colors">Skill Gap</span>
              <span className="hover:text-[#F3EEE8] cursor-pointer transition-colors">Dashboard</span>
            </nav>
          </div>
        </header>

        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>

        <footer className="border-t border-[#55100D]/80 bg-[#1A0706] py-8 text-center text-xs text-[#D9D9D9]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col items-center space-y-4">
            <div className="flex items-center space-x-2">
              <img
                src="/course-tide-emblem.png"
                alt="CourseTide Logo"
                className="w-7 h-7 object-contain"
              />
              <span className="text-sm font-bold text-[#F3EEE8]">
                Course<span className="text-[#DD0200]">Tide</span>
              </span>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-[#D9D9D9]">
                Made by <span className="font-bold text-[#F3EEE8]">Aaditya Singh</span>
              </p>
              <div className="flex items-center justify-center space-x-4 pt-1 text-xs">
                <a
                  href="https://www.linkedin.com/in/aaditya-singh-408968357/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#D9D9D9] hover:text-[#DD0200] transition-colors font-medium underline underline-offset-4 decoration-[#55100D] hover:decoration-[#DD0200]"
                >
                  LinkedIn
                </a>
                <span className="text-[#55100D]">•</span>
                <a
                  href="https://github.com/WaifuPuller"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#D9D9D9] hover:text-[#DD0200] transition-colors font-medium underline underline-offset-4 decoration-[#55100D] hover:decoration-[#DD0200]"
                >
                  GitHub
                </a>
                <span className="text-[#55100D]">•</span>
                <a
                  href="https://github.com/WaifuPuller/CourseTide"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#D9D9D9] hover:text-[#DD0200] transition-colors font-medium underline underline-offset-4 decoration-[#55100D] hover:decoration-[#DD0200]"
                >
                  CourseTide Repository
                </a>
              </div>
            </div>
            <p className="text-[11px] text-[#8C8380] pt-2">
              CourseTide © 2026 — Grounded AI Learning Path Recommender
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
