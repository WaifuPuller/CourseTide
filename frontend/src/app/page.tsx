"use client";

import { useState, useEffect } from "react";
import {
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Clock,
  Calendar,
  BookOpen,
  ArrowRight,
  ShieldCheck,
  Database,
  Layers,
  ChevronRight,
  TrendingUp,
  Tag,
  ExternalLink,
  RefreshCw,
} from "lucide-react";
import { api, ProfileResponse, RecommendedCourse } from "@/lib/api";

export default function Home() {
  const [goal, setGoal] = useState("");
  const [weeklyHours, setWeeklyHours] = useState(8);
  const [healthStatus, setHealthStatus] = useState<{ status: string; service: string } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [profileResult, setProfileResult] = useState<ProfileResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    api.getHealth()
      .then((data) => setHealthStatus(data))
      .catch(() => setHealthStatus(null));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const res = await api.createProfile({
        goal,
        weekly_hours: weeklyHours,
      });
      setProfileResult(res);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to analyze learning goal. Please check server connection.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    setProfileResult(null);
    setErrorMessage(null);
    setGoal("");
  };

  return (
    <div className="max-w-5xl mx-auto space-y-12 pb-12">
      {/* Hero Header */}
      <div className="text-center space-y-4 pt-4">
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
        <p className="text-base sm:text-lg text-slate-400 max-w-2xl mx-auto">
          Describe your career goal in natural language. CourseTide extracts your profile, detects your skill gaps, and recommends high-impact courses using 384-d semantic vectors and gap recall.
        </p>
      </div>

      {/* Goal Intake Form (Shown if no result yet) */}
      {!profileResult && (
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
                placeholder="e.g., I want to become a Machine Learning Engineer. I already know Python and pandas, and can dedicate 10 hours a week."
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
              />
              <div className="flex flex-wrap gap-2 pt-1 text-xs text-slate-500">
                <span>Quick examples:</span>
                <button
                  type="button"
                  onClick={() => setGoal("I want to become an ML Engineer. I have Python and statistics background and have 10 hours a week.")}
                  className="text-teal-400/80 hover:text-teal-300 underline underline-offset-2"
                >
                  ML Engineer (Intermediate)
                </button>
                <span>•</span>
                <button
                  type="button"
                  onClick={() => setGoal("I want to be a Data Scientist. I know Python, linear algebra, and SQL.")}
                  className="text-teal-400/80 hover:text-teal-300 underline underline-offset-2"
                >
                  Data Scientist (With Unrecognized Skill)
                </button>
                <span>•</span>
                <button
                  type="button"
                  onClick={() => setGoal("I want to become an MLOps Engineer. I know Python, Git, and Docker.")}
                  className="text-teal-400/80 hover:text-teal-300 underline underline-offset-2"
                >
                  MLOps Engineer
                </button>
              </div>
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
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Analyzing Goal & Vector Matches...</span>
                    </>
                  ) : (
                    <>
                      <span>Analyze Profile & Recommend</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </div>

            {errorMessage && (
              <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-start gap-3">
                <AlertCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
                <div>
                  <p className="font-semibold text-rose-200">Analysis Error</p>
                  <p className="text-xs text-rose-300/90 mt-1">{errorMessage}</p>
                </div>
              </div>
            )}
          </form>
        </div>
      )}

      {/* Results View: Profile Analysis + Skill Gaps + Recommendations */}
      {profileResult && (
        <div className="space-y-8 animate-in fade-in duration-300">
          {/* Top Bar with Reset Action */}
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-bold text-slate-100">Learner Profile & Recommendations</h2>
            <button
              onClick={handleReset}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Analyze Another Goal</span>
            </button>
          </div>

          {/* Unrecognized Skills Warning Banner */}
          {profileResult.unrecognized_skills && profileResult.unrecognized_skills.length > 0 && (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-sm flex items-start gap-3">
              <AlertCircle className="w-5 h-5 shrink-0 text-amber-400 mt-0.5" />
              <div>
                <p className="font-semibold text-amber-200">
                  Unrecognized Skill Notice:{" "}
                  <span className="font-mono text-xs bg-amber-500/20 px-1.5 py-0.5 rounded">
                    {profileResult.unrecognized_skills.join(", ")}
                  </span>
                </p>
                <p className="text-xs text-amber-300/80 mt-1">
                  These terms are not in the current Machine Learning taxonomy. CourseTide will prioritize closing your recognized core gaps.
                </p>
              </div>
            </div>
          )}

          {/* Profile Overview Card */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="space-y-1">
              <span className="text-xs text-slate-400 font-medium">Target Role</span>
              <p className="text-lg font-bold text-teal-400">{profileResult.role_name}</p>
              <span className="inline-block text-[11px] px-2 py-0.5 rounded-full bg-teal-500/10 text-teal-300 border border-teal-500/20">
                {profileResult.target_role}
              </span>
            </div>

            <div className="space-y-1">
              <span className="text-xs text-slate-400 font-medium">Readiness Match</span>
              <div className="flex items-baseline gap-2">
                <p className="text-2xl font-black text-slate-100">{profileResult.match_percentage}%</p>
                <span className="text-xs text-slate-500">
                  ({profileResult.known_skills.length} of {profileResult.known_skills.length + profileResult.gap_skills.length} skills)
                </span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-gradient-to-r from-teal-500 to-emerald-400 h-full rounded-full"
                  style={{ width: `${profileResult.match_percentage}%` }}
                />
              </div>
            </div>

            <div className="space-y-1">
              <span className="text-xs text-slate-400 font-medium">Weekly Study Commitment</span>
              <p className="text-lg font-bold text-slate-100 flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-cyan-400" />
                {profileResult.weekly_hours} hrs/week
              </p>
              <span className="text-xs text-slate-500">Self-paced schedule</span>
            </div>

            <div className="space-y-1">
              <span className="text-xs text-slate-400 font-medium">Estimated Timeframe</span>
              <p className="text-lg font-bold text-slate-100 flex items-center gap-1.5">
                <Calendar className="w-4 h-4 text-cyan-400" />
                {profileResult.timeframe_months} Months
              </p>
              <span className="text-xs text-slate-500">Target completion</span>
            </div>
          </div>

          {/* Skill Breakdown: Known vs Gaps */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Known Skills */}
            <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-emerald-400 text-sm font-semibold">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Known Skills ({profileResult.known_skills.length})</span>
                </div>
                <span className="text-xs text-emerald-400/80 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                  Mastered
                </span>
              </div>
              {profileResult.known_skills.length > 0 ? (
                <div className="flex flex-wrap gap-2 pt-1">
                  {profileResult.known_skills.map((skill) => (
                    <span
                      key={skill}
                      className="px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500 italic">No previous experience detected. Complete novice onboarding.</p>
              )}
            </div>

            {/* Skill Gaps */}
            <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-amber-400 text-sm font-semibold">
                  <TrendingUp className="w-4 h-4" />
                  <span>Target Skill Gaps ({profileResult.gap_skills.length})</span>
                </div>
                <span className="text-xs text-amber-400/80 bg-amber-500/10 px-2 py-0.5 rounded-full">
                  To Learn
                </span>
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                {profileResult.gap_skills.map((skill) => (
                  <span
                    key={skill}
                    className="px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Recommended Courses Section */}
          <div className="space-y-4 pt-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold text-slate-100">Recommended Learning Courses</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Ranked using 384-d semantic vectors + learner gap recall formula (Score = 0.50×Sim + 0.35×GapRecall + 0.15×Primary)
                </p>
              </div>
              <span className="text-xs text-teal-400 bg-teal-500/10 px-2.5 py-1 rounded-full border border-teal-500/20 font-medium">
                Top {profileResult.recommended_courses.length} MVP Courses
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {profileResult.recommended_courses.map((course) => (
                <div
                  key={course.id}
                  className="bg-slate-900/70 border border-slate-800 hover:border-teal-500/40 rounded-xl p-5 flex flex-col justify-between space-y-4 transition-all hover:shadow-lg hover:shadow-teal-500/5 group"
                >
                  <div className="space-y-2.5">
                    {/* Source & Match Score Header */}
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400 font-medium">{course.source || "CourseTide"}</span>
                      <span className="font-bold text-teal-400 bg-teal-500/10 px-2 py-0.5 rounded-full border border-teal-500/20">
                        {course.match_score}% Match
                      </span>
                    </div>

                    {/* Course Title */}
                    <h4 className="text-base font-bold text-slate-100 group-hover:text-teal-300 transition-colors line-clamp-2">
                      {course.title}
                    </h4>

                    {/* Description */}
                    {course.description && (
                      <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                        {course.description}
                      </p>
                    )}

                    {/* Meta info: Difficulty, Hours, Type */}
                    <div className="flex items-center gap-2 pt-1 text-[11px] text-slate-400">
                      <span className="capitalize px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                        {course.difficulty}
                      </span>
                      <span>•</span>
                      <span>{course.duration_hours} hrs</span>
                      <span>•</span>
                      <span className="capitalize">{course.resource_type}</span>
                    </div>
                  </div>

                  {/* Covered Gap Skills */}
                  <div className="pt-2 border-t border-slate-800/80 space-y-2">
                    <div className="text-[11px] text-slate-400 flex items-center justify-between">
                      <span>Covered Gap Skills:</span>
                      <span className="text-teal-400 font-medium">{course.covered_gap_skills.length} match</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {course.covered_gap_skills.map((skill) => (
                        <span
                          key={skill}
                          className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-300 border border-teal-500/20"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* System Status Grid Footer */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-8 border-t border-slate-800/80">
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-teal-400 text-sm font-semibold">
            <Database className="w-4 h-4" />
            <span>Neon PostgreSQL & pgvector</span>
          </div>
          <p className="text-xs text-slate-400">
            48 courses, 22 taxonomy skills, 74 course-skill relations with 384-d dense vector embeddings active.
          </p>
        </div>

        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-teal-400 text-sm font-semibold">
            <Layers className="w-4 h-4" />
            <span>Recommender Core</span>
          </div>
          <p className="text-xs text-slate-400">
            Goal parser, deterministic skill-gap engine, and hybrid gap-recall vector ranking fully integrated.
          </p>
        </div>

        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-teal-400 text-sm font-semibold">
            <ShieldCheck className="w-4 h-4" />
            <span>Backend Service</span>
          </div>
          <p className="text-xs text-slate-400">
            FastAPI status:{" "}
            <span className={healthStatus ? "text-emerald-400 font-medium" : "text-amber-400 font-medium"}>
              {healthStatus ? "Connected (Healthy)" : "Awaiting Server Launch"}
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}
