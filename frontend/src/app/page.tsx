"use client";

import { useState, useEffect } from "react";
import { Sparkles, Compass, CheckCircle2, ArrowRight, ShieldCheck, Database, Layers } from "lucide-react";

export default function Home() {
  const [goal, setGoal] = useState("");
  const [weeklyHours, setWeeklyHours] = useState(8);
  const [healthStatus, setHealthStatus] = useState<{ status: string; service: string } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => setHealthStatus(data))
      .catch(() => setHealthStatus(null));
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) return;
    setIsSubmitting(true);
    // Day 1 skeleton handler
    setTimeout(() => {
      setIsSubmitting(false);
      alert("Goal input registered! Recommender pipeline & path sequencing will activate in Day 2.");
    }, 600);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-12">
      {/* Hero Section */}
      <div className="text-center space-y-4 pt-6">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-teal-500/10 border border-teal-500/30 text-teal-400 text-xs font-semibold uppercase tracking-wider">
          <Sparkles className="w-3.5 h-3.5" />
          AI-Powered Career Navigator
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-slate-100">
          Personalized Learning Paths,{" "}
          <span className="bg-gradient-to-r from-teal-400 to-cyan-400 bg-clip-text text-transparent">
            Grounded in Reality
          </span>
        </h1>
        <p className="text-lg text-slate-400 max-w-2xl mx-auto">
          Describe your career goal in natural language. CourseTide detects your skill gaps, sequences prerequisite-aware milestones, and explains why every course belongs on your path.
        </p>
      </div>

      {/* Goal Intake Form */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-xl backdrop-blur">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <label htmlFor="goal" className="block text-sm font-medium text-slate-200">
              What is your target career or learning goal?
            </label>
            <textarea
              id="goal"
              rows={3}
              className="w-full rounded-xl bg-slate-950/80 border border-slate-800 px-4 py-3 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 transition-all resize-none text-sm leading-relaxed"
              placeholder="e.g., I want to become a Machine Learning Engineer. I have basic Python and math knowledge, and want to learn deep learning and MLOps."
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 items-center">
            <div className="space-y-2">
              <label htmlFor="hours" className="block text-sm font-medium text-slate-200">
                Weekly commitment: <span className="text-teal-400 font-semibold">{weeklyHours} hours/week</span>
              </label>
              <input
                id="hours"
                type="range"
                min={2}
                max={40}
                step={1}
                value={weeklyHours}
                onChange={(e) => setWeeklyHours(Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-teal-500"
              />
              <div className="flex justify-between text-xs text-slate-500">
                <span>2 hrs (Casual)</span>
                <span>20 hrs (Part-time)</span>
                <span>40 hrs (Full-time)</span>
              </div>
            </div>

            <div className="flex sm:justify-end">
              <button
                type="submit"
                disabled={isSubmitting || !goal.trim()}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-teal-500 hover:bg-teal-400 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed text-slate-950 font-semibold text-sm transition-all shadow-lg shadow-teal-500/20"
              >
                <span>Generate Learning Roadmap</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* System Foundation Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-teal-400 text-sm font-semibold">
            <Database className="w-4 h-4" />
            <span>Seed Catalog Ingestion</span>
          </div>
          <p className="text-xs text-slate-400">
            48 curated resources, 22 taxonomy skills, 74 course-skill relations, and 384-d pgvector embeddings ready.
          </p>
        </div>

        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-teal-400 text-sm font-semibold">
            <Layers className="w-4 h-4" />
            <span>Prerequisite DAG</span>
          </div>
          <p className="text-xs text-slate-400">
            Authoritative skill-level sequencing engine from prerequisites.json with multi-phase grouping.
          </p>
        </div>

        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-teal-400 text-sm font-semibold">
            <ShieldCheck className="w-4 h-4" />
            <span>Backend Service</span>
          </div>
          <p className="text-xs text-slate-400">
            FastAPI server status:{" "}
            <span className={healthStatus ? "text-emerald-400 font-medium" : "text-amber-400 font-medium"}>
              {healthStatus ? "Connected (Healthy)" : "Awaiting Server Launch"}
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}
