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
  Lock,
  Unlock,
  HelpCircle,
  X,
  Milestone,
} from "lucide-react";
import {
  api,
  ExplanationResponse,
  ProfileResponse,
  RecommendedCourse,
  RoadmapResponse,
} from "@/lib/api";

interface ExplanationModalState {
  courseId: string;
  courseTitle: string;
  data?: ExplanationResponse;
  error?: string;
  loading: boolean;
}

export default function Home() {
  const [goal, setGoal] = useState("");
  const [weeklyHours, setWeeklyHours] = useState(8);
  const [healthStatus, setHealthStatus] = useState<{ status: string; service: string } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [profileResult, setProfileResult] = useState<ProfileResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Roadmap State (Day 3 Step 3)
  const [roadmapResult, setRoadmapResult] = useState<RoadmapResponse | null>(null);
  const [isLoadingRoadmap, setIsLoadingRoadmap] = useState(false);
  const [roadmapError, setRoadmapError] = useState<string | null>(null);

  // Grounded Explainer Modal State (Day 3 Step 4 + Step 3)
  const [explanationModal, setExplanationModal] = useState<ExplanationModalState | null>(null);

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
    setRoadmapResult(null);
    setRoadmapError(null);

    try {
      // 1. Analyze Profile (POST /api/profile)
      const res = await api.createProfile({
        goal,
        weekly_hours: weeklyHours,
      });
      setProfileResult(res);

      // 2. Fetch Sequenced Roadmap (GET /api/roadmap/{learner_id})
      setIsLoadingRoadmap(true);
      try {
        const rm = await api.getRoadmap(res.learner_id);
        setRoadmapResult(rm);
      } catch (rmErr: any) {
        setRoadmapError(rmErr.message || "Failed to load sequenced learning roadmap.");
      } finally {
        setIsLoadingRoadmap(false);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to analyze learning goal. Please check server connection.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    setProfileResult(null);
    setRoadmapResult(null);
    setRoadmapError(null);
    setErrorMessage(null);
    setExplanationModal(null);
    setGoal("");
  };

  const handleWhyThis = async (courseId: string, courseTitle: string) => {
    if (!profileResult) return;

    setExplanationModal({
      courseId,
      courseTitle,
      loading: true,
    });

    try {
      const exp = await api.getExplanation(profileResult.learner_id, courseId);
      setExplanationModal({
        courseId,
        courseTitle,
        data: exp,
        loading: false,
      });
    } catch (err: any) {
      const is503 = err.message && (err.message.includes("503") || err.message.includes("temporarily unavailable"));
      const msg = is503
        ? "Explanation service is temporarily unavailable. Please try again."
        : (err.message || "Failed to generate grounded explanation.");

      setExplanationModal({
        courseId,
        courseTitle,
        error: msg,
        loading: false,
      });
    }
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
          Describe your career goal in natural language. CourseTide extracts your profile, detects your skill gaps, sequences courses into phased prerequisite milestones, and provides grounded AI explanations.
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
                placeholder="e.g., I want to become a Machine Learning Engineer. I already know Python and statistics, and have 10 hours a week."
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
                      <span>Analyzing Goal & Sequencing Roadmap...</span>
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

      {/* Results View: Profile Analysis + Skill Gaps + Roadmap Timeline + Recommendations */}
      {profileResult && (
        <div className="space-y-10 animate-in fade-in duration-300">
          {/* Top Bar with Reset Action */}
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-bold text-slate-100">Learner Profile & Roadmap</h2>
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
                  These terms are not in the canonical Machine Learning taxonomy. CourseTide prioritized closing your recognized core gaps.
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
                {roadmapResult?.total_estimated_weeks
                  ? `${roadmapResult.total_estimated_weeks} Weeks`
                  : `${profileResult.timeframe_months} Months`}
              </p>
              <span className="text-xs text-slate-500">
                {roadmapResult ? "Calculated from sequenced roadmap" : "Target completion"}
              </span>
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
              {profileResult.gap_skills.length > 0 ? (
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
              ) : (
                <p className="text-xs text-emerald-400 font-medium">All role requirements already satisfied!</p>
              )}
            </div>
          </div>

          {/* ROADMAP TIMELINE SECTION (Day 3 Step 3) */}
          <div className="space-y-6 pt-4 border-t border-slate-800/80">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <Milestone className="w-5 h-5 text-teal-400" />
                  <h3 className="text-xl font-bold text-slate-100">Phased Learning Roadmap</h3>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Topologically sorted via prerequisite DAG: Phase 1 foundations unlock subsequent specialized milestones.
                </p>
              </div>

              {roadmapResult && (
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-slate-400">
                    Total: <strong className="text-slate-200">{roadmapResult.total_courses} courses</strong> ({roadmapResult.total_estimated_hours} hrs)
                  </span>
                  <span className="text-teal-400 bg-teal-500/10 px-2.5 py-1 rounded-full border border-teal-500/20 font-semibold">
                    ~{roadmapResult.total_estimated_weeks} Weeks @ {profileResult.weekly_hours}h/wk
                  </span>
                </div>
              )}
            </div>

            {/* Roadmap Loading State */}
            {isLoadingRoadmap && (
              <div className="p-8 rounded-2xl bg-slate-900/40 border border-slate-800 flex flex-col items-center justify-center space-y-3 text-center">
                <RefreshCw className="w-6 h-6 animate-spin text-teal-400" />
                <p className="text-sm font-medium text-slate-300">
                  Sequencing prerequisite paths and building milestone timeline...
                </p>
              </div>
            )}

            {/* Roadmap Error State */}
            {roadmapError && (
              <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-start gap-3">
                <AlertCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
                <div>
                  <p className="font-semibold text-rose-200">Roadmap Generation Error</p>
                  <p className="text-xs text-rose-300/90 mt-1">{roadmapError}</p>
                </div>
              </div>
            )}

            {/* Zero-Gap Roadmap State */}
            {roadmapResult && roadmapResult.phases.length === 0 && (
              <div className="p-6 rounded-2xl bg-slate-900/40 border border-slate-800 text-center space-y-2">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto" />
                <h4 className="text-base font-bold text-slate-200">No Prerequisite Gaps to Close</h4>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  You already possess all required skills for the <strong className="text-teal-300">{profileResult.role_name}</strong> profile. No additional sequenced roadmap courses are currently required.
                </p>
              </div>
            )}

            {/* Phased Roadmap Timeline */}
            {roadmapResult && roadmapResult.phases.length > 0 && (
              <div className="space-y-8 relative before:absolute before:inset-0 before:left-4 before:top-4 before:bottom-4 before:w-0.5 before:bg-gradient-to-b before:from-teal-500 before:via-cyan-500/40 before:to-slate-800 hidden sm:block">
                {roadmapResult.phases.map((phase) => (
                  <div key={phase.phase_number} className="relative pl-10 space-y-4">
                    {/* Phase Timeline Marker */}
                    <div
                      className={`absolute left-1.5 top-0 w-6 h-6 rounded-full border-2 flex items-center justify-center text-xs font-bold ${
                        phase.phase_number === 1
                          ? "bg-teal-500 border-teal-300 text-slate-950 shadow-md shadow-teal-500/30"
                          : "bg-slate-900 border-slate-700 text-slate-400"
                      }`}
                    >
                      {phase.phase_number}
                    </div>

                    {/* Phase Header Card */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-4 rounded-xl bg-slate-900/80 border border-slate-800/90">
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-base font-bold text-slate-100">{phase.phase_name}</h4>
                          <span
                            className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full flex items-center gap-1 ${
                              phase.phase_number === 1
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                                : "bg-slate-800 text-slate-400 border border-slate-700"
                            }`}
                          >
                            {phase.phase_number === 1 ? (
                              <>
                                <Unlock className="w-3 h-3" />
                                <span>Available</span>
                              </>
                            ) : (
                              <>
                                <Lock className="w-3 h-3" />
                                <span>Locked</span>
                              </>
                            )}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-1.5 pt-1.5">
                          {phase.skills.map((skill) => (
                            <span
                              key={skill}
                              className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800/80 text-slate-300 border border-slate-700/60"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="text-xs text-slate-400 sm:text-right shrink-0">
                        <span className="block font-semibold text-slate-200">{phase.courses.length} Courses</span>
                        <span>~{phase.estimated_hours} Hours</span>
                      </div>
                    </div>

                    {/* Course Cards in Phase */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {phase.courses.map((course) => (
                        <div
                          key={course.course_id}
                          className={`rounded-xl p-4 flex flex-col justify-between space-y-3 transition-all border ${
                            course.status === "available"
                              ? "bg-slate-900/70 border-slate-800 hover:border-teal-500/40 shadow-sm"
                              : "bg-slate-950/60 border-slate-800/60 opacity-80"
                          }`}
                        >
                          <div className="space-y-2">
                            {/* Sequence Number & Status */}
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-mono text-teal-400 font-bold bg-teal-500/10 px-2 py-0.5 rounded">
                                #{course.sequence_order}
                              </span>
                              <span className="text-[11px] text-slate-400">{course.source || "CourseTide"}</span>
                            </div>

                            {/* Title */}
                            <h5 className="text-sm font-bold text-slate-100 line-clamp-2">
                              {course.title}
                            </h5>

                            {/* Meta pills */}
                            <div className="flex items-center gap-2 text-[11px] text-slate-400">
                              <span className="capitalize px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                                {course.difficulty}
                              </span>
                              <span>•</span>
                              <span>{course.duration_hours} hrs</span>
                            </div>
                          </div>

                          {/* Covered Skills + Why This Button */}
                          <div className="pt-2 border-t border-slate-800/80 space-y-2.5">
                            <div className="flex flex-wrap gap-1">
                              {course.covered_skills.map((s) => (
                                <span
                                  key={s}
                                  className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-teal-300"
                                >
                                  {s}
                                </span>
                              ))}
                            </div>

                            <div className="flex items-center justify-between pt-1">
                              <button
                                type="button"
                                onClick={() => handleWhyThis(course.course_id, course.title)}
                                className="inline-flex items-center gap-1 text-xs font-semibold text-teal-400 hover:text-teal-300 transition-colors"
                              >
                                <Sparkles className="w-3.5 h-3.5" />
                                <span>Why this?</span>
                              </button>

                              {course.url && (
                                <a
                                  href={course.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-slate-500 hover:text-slate-300 transition-colors"
                                  title="Open Course Resource"
                                >
                                  <ExternalLink className="w-3.5 h-3.5" />
                                </a>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recommended Courses Section (Day 2 Original) */}
          <div className="space-y-4 pt-4 border-t border-slate-800/80">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold text-slate-100">Catalog Match Candidates</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Semantic embeddings & gap-recall candidate list ranked prior to prerequisite sequencing
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

                  {/* Covered Gap Skills + Explainer Trigger */}
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
                    <div className="pt-1 flex justify-end">
                      <button
                        type="button"
                        onClick={() => handleWhyThis(course.id, course.title)}
                        className="inline-flex items-center gap-1 text-xs text-teal-400/90 hover:text-teal-300 font-medium transition-colors"
                      >
                        <Sparkles className="w-3 h-3" />
                        <span>Why this?</span>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* "Why this?" Grounded Explainer Modal (Day 3 Step 4 + Step 3) */}
      {explanationModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 relative">
            {/* Close Button */}
            <button
              type="button"
              onClick={() => setExplanationModal(null)}
              className="absolute right-4 top-4 text-slate-400 hover:text-slate-200 transition-colors p-1"
            >
              <X className="w-5 h-5" />
            </button>

            {/* Modal Header */}
            <div className="flex items-center gap-2 text-teal-400 text-sm font-semibold">
              <Sparkles className="w-4 h-4" />
              <span>Why This Recommendation?</span>
            </div>

            {/* Course Title */}
            <div>
              <h3 className="text-lg font-bold text-slate-100 leading-snug">
                {explanationModal.courseTitle}
              </h3>
            </div>

            {/* Modal Body */}
            {explanationModal.loading && (
              <div className="py-8 flex flex-col items-center justify-center space-y-3 text-center">
                <RefreshCw className="w-6 h-6 animate-spin text-teal-400" />
                <p className="text-xs text-slate-400">
                  Generating grounded explanation using Gemini model chain...
                </p>
              </div>
            )}

            {explanationModal.error && (
              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
                <div>
                  <p className="font-semibold text-amber-200">Notice</p>
                  <p className="mt-0.5 leading-relaxed">{explanationModal.error}</p>
                </div>
              </div>
            )}

            {explanationModal.data && (
              <div className="space-y-4">
                {/* Meta badges */}
                <div className="flex flex-wrap gap-2">
                  <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-teal-500/10 text-teal-300 border border-teal-500/20">
                    {explanationModal.data.phase_name}
                  </span>
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                    Primary: {explanationModal.data.primary_skill}
                  </span>
                </div>

                {/* Grounded Explanation Text */}
                <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-slate-200 text-sm leading-relaxed">
                  <p>{explanationModal.data.explanation}</p>
                </div>

                <p className="text-[11px] text-slate-500 italic">
                  Grounded in your active skill gaps, prerequisite graph dependencies, and target role competencies.
                </p>
              </div>
            )}

            {/* Modal Footer */}
            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={() => setExplanationModal(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-colors"
              >
                Close
              </button>
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
            <span>Prerequisite Sequencer</span>
          </div>
          <p className="text-xs text-slate-400">
            Topological sorting over canonical DAGs, milestone phase grouping, and grounded Gemini explanation chain.
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
