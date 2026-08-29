"use client";

import { useState, useEffect, useMemo } from "react";
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
  Compass,
  Award,
  FastForward,
  CheckCircle,
  Activity,
  BarChart3,
  Sliders,
  History,
} from "lucide-react";
import {
  api,
  DashboardResponse,
  ExplanationResponse,
  ProfileResponse,
  ProgressEventInput,
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

interface AssessmentModalState {
  courseId: string;
  courseTitle: string;
  isOpen: boolean;
}

export default function Home() {
  const [goal, setGoal] = useState("");
  const [weeklyHours, setWeeklyHours] = useState(8);
  const [healthStatus, setHealthStatus] = useState<{ status: string; service: string } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [profileResult, setProfileResult] = useState<ProfileResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Roadmap State (Day 3)
  const [roadmapResult, setRoadmapResult] = useState<RoadmapResponse | null>(null);
  const [isLoadingRoadmap, setIsLoadingRoadmap] = useState(false);
  const [roadmapError, setRoadmapError] = useState<string | null>(null);

  // Dashboard State (Day 4 Checkpoint 5)
  const [dashboardResult, setDashboardResult] = useState<DashboardResponse | null>(null);
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  // UI-Only Weekly Commitment Slider (Day 4 Section 8)
  const [weeklyCommitmentHours, setWeeklyCommitmentHours] = useState(8);

  // Grounded Explainer Modal State (Day 3)
  const [explanationModal, setExplanationModal] = useState<ExplanationModalState | null>(null);

  // Lightweight Assessment / Progress Modal State (Day 5 Checkpoint 1)
  const [assessmentModal, setAssessmentModal] = useState<AssessmentModalState | null>(null);
  const [assessmentScore, setAssessmentScore] = useState<string>("90");
  const [difficultyFeedback, setDifficultyFeedback] = useState<"too_easy" | "just_right" | "too_hard" | "">("");
  const [isSubmittingProgress, setIsSubmittingProgress] = useState(false);
  const [progressModalError, setProgressModalError] = useState<string | null>(null);
  const [progressSuccessMessage, setProgressSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    api.getHealth()
      .then((data) => setHealthStatus(data))
      .catch(() => setHealthStatus(null));
  }, []);

  // Synchronize initial weeklyCommitmentHours from the learner's ProfileResponse
  useEffect(() => {
    if (profileResult?.weekly_hours) {
      setWeeklyCommitmentHours(profileResult.weekly_hours);
    }
  }, [profileResult]);

  const loadDashboardData = async (learnerId: string) => {
    setIsLoadingDashboard(true);
    setDashboardError(null);
    try {
      const dbData = await api.getDashboard(learnerId);
      setDashboardResult(dbData);
    } catch (err: any) {
      setDashboardError(err.message || "Failed to load learner progress dashboard.");
    } finally {
      setIsLoadingDashboard(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setRoadmapResult(null);
    setRoadmapError(null);
    setDashboardResult(null);
    setDashboardError(null);

    try {
      // 1. Analyze Profile (POST /api/profile)
      const res = await api.createProfile({
        goal,
        weekly_hours: weeklyHours,
      });
      setProfileResult(res);
      setWeeklyCommitmentHours(res.weekly_hours || weeklyHours || 8);

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

      // 3. Fetch Initial Dashboard Analytics (GET /api/dashboard/{learner_id})
      await loadDashboardData(res.learner_id);
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
    setDashboardResult(null);
    setDashboardError(null);
    setErrorMessage(null);
    setExplanationModal(null);
    setAssessmentModal(null);
    setGoal("");
  };

  const handleOpenAssessmentModal = (courseId: string, courseTitle: string) => {
    setAssessmentModal({
      courseId,
      courseTitle,
      isOpen: true,
    });
    setAssessmentScore("90");
    setDifficultyFeedback("just_right");
    setProgressModalError(null);
    setProgressSuccessMessage(null);
  };

  const handleCloseAssessmentModal = () => {
    if (isSubmittingProgress) return;
    setAssessmentModal(null);
    setProgressModalError(null);
    setProgressSuccessMessage(null);
  };

  const handleSubmitProgress = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profileResult || !assessmentModal) return;

    const scoreNum = parseFloat(assessmentScore);
    if (isNaN(scoreNum) || scoreNum < 0 || scoreNum > 100) {
      setProgressModalError("Please enter a valid assessment score between 0 and 100.");
      return;
    }

    setIsSubmittingProgress(true);
    setProgressModalError(null);
    setProgressSuccessMessage(null);

    try {
      const payload: ProgressEventInput = {
        learner_id: profileResult.learner_id,
        course_id: assessmentModal.courseId,
        assessment_score: scoreNum,
        difficulty_feedback: difficultyFeedback ? (difficultyFeedback as "too_easy" | "just_right" | "too_hard") : undefined,
      };

      const res = await api.recordProgress(payload);

      // Refresh server state (Roadmap & Dashboard)
      const [updatedRoadmap, updatedDashboard] = await Promise.all([
        api.getRoadmap(profileResult.learner_id),
        api.getDashboard(profileResult.learner_id),
      ]);

      setRoadmapResult(updatedRoadmap);
      setDashboardResult(updatedDashboard);

      let feedbackMsg = res.adaptation_details?.message || "Progress recorded successfully.";
      if (res.adaptation_applied === "mastery_skip" && res.adaptation_details?.skipped_course_id) {
        feedbackMsg = `High score (${scoreNum.toFixed(1)}%) demonstrated mastery! Course completed and redundant downstream course was fast-tracked.`;
      } else if (res.adaptation_applied === "mastery") {
        feedbackMsg = `High score (${scoreNum.toFixed(1)}%) demonstrated mastery! Competency marked known.`;
      } else if (res.adaptation_applied === "remediation" && res.adaptation_details?.inserted_course_id) {
        feedbackMsg = `Score (${scoreNum.toFixed(1)}%) indicated need for reinforcement. Remedial course inserted into roadmap.`;
      }

      setProgressSuccessMessage(feedbackMsg);

      setTimeout(() => {
        setAssessmentModal(null);
        setIsSubmittingProgress(false);
        setProgressSuccessMessage(null);
      }, 1600);
    } catch (err: any) {
      setProgressModalError(err.message || "Failed to record progress event. Please try again.");
      setIsSubmittingProgress(false);
    }
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

  // Dynamic weekly pace calculations (UI-only)
  const totalRoadmapHours = useMemo(() => {
    if (dashboardResult) {
      return dashboardResult.phase_progress.reduce((acc, p) => acc + p.estimated_hours, 0);
    }
    return roadmapResult?.total_estimated_hours || 0;
  }, [dashboardResult, roadmapResult]);

  const dynamicTotalWeeks = useMemo(() => {
    if (weeklyCommitmentHours <= 0 || totalRoadmapHours <= 0) return 0;
    return Math.ceil(totalRoadmapHours / weeklyCommitmentHours);
  }, [totalRoadmapHours, weeklyCommitmentHours]);

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

      {/* Results View: Profile Analysis + Dashboard + Phased Roadmap */}
      {profileResult && (
        <div className="space-y-10 animate-in fade-in duration-300">
          {/* Top Bar with Reset Action */}
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-bold text-slate-100">Learner Profile & Dashboard</h2>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => loadDashboardData(profileResult.learner_id)}
                disabled={isLoadingDashboard}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
                title="Refresh dashboard analytics"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingDashboard ? "animate-spin text-teal-400" : ""}`} />
                <span>Refresh Data</span>
              </button>
              <button
                onClick={handleReset}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Analyze Another Goal</span>
              </button>
            </div>
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
              <span className="text-xs text-slate-400 font-medium">Base Weekly Commitment</span>
              <p className="text-lg font-bold text-slate-100 flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-cyan-400" />
                {profileResult.weekly_hours} hrs/week
              </p>
              <span className="text-xs text-slate-500">Intake preference</span>
            </div>

            <div className="space-y-1">
              <span className="text-xs text-slate-400 font-medium">Estimated Pace Timeline</span>
              <p className="text-lg font-bold text-slate-100 flex items-center gap-1.5">
                <Calendar className="w-4 h-4 text-cyan-400" />
                {dynamicTotalWeeks > 0 ? `${dynamicTotalWeeks} Weeks` : `${profileResult.timeframe_months} Months`}
              </p>
              <span className="text-xs text-slate-500">
                @ {weeklyCommitmentHours} hrs/week active slider
              </span>
            </div>
          </div>

          {/* ========================================================================= */}
          {/* DAY 4 CHECKPOINT 5: LEARNER DASHBOARD SECTION                             */}
          {/* ========================================================================= */}
          <div className="space-y-6 pt-4 border-t border-slate-800/80">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-teal-400" />
                <h3 className="text-xl font-bold text-slate-100">Adaptive Progress Dashboard</h3>
              </div>
              {dashboardResult && (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-teal-500/10 text-teal-300 border border-teal-500/20">
                  Current Milestone: {dashboardResult.current_phase_name}
                </span>
              )}
            </div>

            {/* Dashboard Loading State */}
            {isLoadingDashboard && (
              <div className="p-8 rounded-2xl bg-slate-900/40 border border-slate-800 flex flex-col items-center justify-center space-y-3 text-center">
                <RefreshCw className="w-6 h-6 animate-spin text-teal-400" />
                <p className="text-sm font-medium text-slate-300">
                  Aggregating learner progress and skill mastery radar...
                </p>
              </div>
            )}

            {/* Dashboard Error State */}
            {dashboardError && (
              <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-start gap-3">
                <AlertCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
                <div>
                  <p className="font-semibold text-rose-200">Dashboard Unavailable</p>
                  <p className="text-xs text-rose-300/90 mt-1">{dashboardError}</p>
                </div>
              </div>
            )}

            {dashboardResult && (
              <div className="space-y-6">
                {/* 1. Progress Overview & Metric Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* Genuine Progress Card */}
                  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-3">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span className="font-medium flex items-center gap-1.5 text-emerald-400">
                        <CheckCircle className="w-4 h-4" />
                        Genuine Completion
                      </span>
                      <span className="font-mono bg-emerald-500/10 text-emerald-300 px-2 py-0.5 rounded">
                        {dashboardResult.completed_courses} / {dashboardResult.total_courses} done
                      </span>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <p className="text-3xl font-black text-slate-100">
                        {dashboardResult.overall_progress_percentage}%
                      </p>
                    </div>
                    <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-emerald-500 h-full rounded-full transition-all duration-500"
                        style={{ width: `${dashboardResult.overall_progress_percentage}%` }}
                      />
                    </div>
                    <p className="text-[11px] text-slate-500 leading-tight">
                      Courses successfully assessed and completed by learner.
                    </p>
                  </div>

                  {/* Effective Progress Card */}
                  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-3">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span className="font-medium flex items-center gap-1.5 text-cyan-400">
                        <FastForward className="w-4 h-4" />
                        Effective Pacing
                      </span>
                      <span className="font-mono bg-cyan-500/10 text-cyan-300 px-2 py-0.5 rounded">
                        {dashboardResult.completed_courses + dashboardResult.skipped_courses} / {dashboardResult.total_courses}
                      </span>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <p className="text-3xl font-black text-slate-100">
                        {dashboardResult.effective_progress_percentage}%
                      </p>
                    </div>
                    <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-gradient-to-r from-cyan-500 to-teal-400 h-full rounded-full transition-all duration-500"
                        style={{ width: `${dashboardResult.effective_progress_percentage}%` }}
                      />
                    </div>
                    <p className="text-[11px] text-slate-500 leading-tight">
                      Milestone pacing including {dashboardResult.skipped_courses} fast-tracked course(s).
                    </p>
                  </div>

                  {/* Fast-Track Count Card */}
                  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-2 flex flex-col justify-between">
                    <div className="space-y-1">
                      <span className="text-xs text-slate-400 font-medium flex items-center gap-1.5 text-amber-400">
                        <Award className="w-4 h-4" />
                        Adaptive Fast-Tracks
                      </span>
                      <p className="text-2xl font-bold text-slate-100">
                        {dashboardResult.skipped_courses}{" "}
                        <span className="text-sm font-normal text-slate-400">Skipped</span>
                      </p>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Bypassed downstream redundant courses via deterministic &gt;85% mastery assessments.
                    </p>
                  </div>

                  {/* Active Phase Milestone Card */}
                  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-2 flex flex-col justify-between">
                    <div className="space-y-1">
                      <span className="text-xs text-slate-400 font-medium flex items-center gap-1.5 text-teal-400">
                        <Milestone className="w-4 h-4" />
                        Active Phase
                      </span>
                      <p className="text-2xl font-bold text-teal-400">
                        {dashboardResult.current_phase_name}
                      </p>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Current sequential milestone in prerequisite progression.
                    </p>
                  </div>
                </div>

                {/* 2. Interactive Weekly Commitment Slider (UI-Only) */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Sliders className="w-4 h-4 text-teal-400" />
                      <h4 className="text-sm font-bold text-slate-200">Interactive Weekly Commitment Slider</h4>
                    </div>
                    <div className="text-xs text-slate-400">
                      Current Pace: <strong className="text-teal-400 font-bold">{weeklyCommitmentHours} hrs/week</strong>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <input
                      id="dashboard-hours"
                      type="range"
                      min={2}
                      max={40}
                      step={1}
                      value={weeklyCommitmentHours}
                      onChange={(e) => setWeeklyCommitmentHours(Number(e.target.value))}
                      className="w-full h-2.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-teal-500"
                    />
                    <div className="flex justify-between text-xs text-slate-500">
                      <span>2 hrs/wk (Casual)</span>
                      <span>10 hrs/wk (Standard)</span>
                      <span>20 hrs/wk (Part-time)</span>
                      <span>40 hrs/wk (Full-time)</span>
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                    <div className="text-slate-400">
                      Total Estimated Curriculum: <strong className="text-slate-200">{totalRoadmapHours} hours</strong> across {dashboardResult.total_courses} courses
                    </div>
                    <div className="flex items-center gap-2 text-teal-300 font-semibold bg-teal-500/10 px-3 py-1 rounded-lg border border-teal-500/20">
                      <Clock className="w-3.5 h-3.5" />
                      <span>Adjusted Roadmap Completion: ~{dynamicTotalWeeks} Weeks</span>
                    </div>
                  </div>
                </div>

                {/* 3. Next Recommended Action Hero Banner */}
                <div className="bg-gradient-to-r from-teal-950/40 via-slate-900/60 to-slate-900/40 border border-teal-500/30 rounded-2xl p-6 shadow-xl backdrop-blur space-y-4">
                  <div className="flex items-center gap-2 text-teal-400 text-xs font-bold uppercase tracking-wider">
                    <Compass className="w-4 h-4" />
                    Next Recommended Action
                  </div>

                  {dashboardResult.next_recommended_action ? (
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-teal-300 bg-teal-500/20 px-2 py-0.5 rounded text-xs font-bold">
                            Phase {dashboardResult.next_recommended_action.phase_number} • Course #{dashboardResult.next_recommended_action.sequence_order}
                          </span>
                          <span className="capitalize text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                            {dashboardResult.next_recommended_action.status}
                          </span>
                        </div>
                        <h4 className="text-lg font-bold text-slate-100">
                          {dashboardResult.next_recommended_action.title}
                        </h4>
                        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                          <span>Primary Skill: <strong className="text-teal-400">{dashboardResult.next_recommended_action.primary_skill}</strong></span>
                          <span>•</span>
                          <span>Duration: {dashboardResult.next_recommended_action.duration_hours} hrs</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0 flex-wrap sm:flex-nowrap">
                        <button
                          type="button"
                          onClick={() => handleWhyThis(dashboardResult.next_recommended_action!.course_id, dashboardResult.next_recommended_action!.title)}
                          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-teal-300 text-xs font-semibold transition-colors border border-slate-700"
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Why this?</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleOpenAssessmentModal(dashboardResult.next_recommended_action!.course_id, dashboardResult.next_recommended_action!.title)}
                          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-bold transition-all shadow-md shadow-teal-500/20"
                        >
                          <Award className="w-3.5 h-3.5" />
                          <span>Submit Assessment</span>
                        </button>
                        {dashboardResult.next_recommended_action.url && (
                          <a
                            href={dashboardResult.next_recommended_action.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors border border-slate-700"
                          >
                            <span>Open</span>
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center space-y-1">
                      <CheckCircle2 className="w-6 h-6 text-emerald-400 mx-auto" />
                      <p className="text-sm font-semibold text-slate-200">You&apos;re caught up!</p>
                      <p className="text-xs text-slate-400">
                        No actionable course is currently available. All milestone prerequisites are satisfied or completed.
                      </p>
                    </div>
                  )}
                </div>

                {/* 4. Skill Mastery Radar / Competency Grid */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Activity className="w-4 h-4 text-teal-400" />
                      <h4 className="text-base font-bold text-slate-100">Skill Mastery Radar</h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Authoritative Competency Evaluation
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {dashboardResult.skill_mastery_radar.map((skill) => (
                      <div
                        key={skill.skill_id}
                        className="bg-slate-900/50 border border-slate-800/90 rounded-xl p-4 space-y-2.5"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-mono font-bold text-slate-200 truncate">
                            {skill.skill_name}
                          </span>
                          <span
                            className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                              skill.status === "known"
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                                : skill.status === "in_progress"
                                ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/30"
                                : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                            }`}
                          >
                            {skill.status}
                          </span>
                        </div>

                        <div className="space-y-1">
                          <div className="flex justify-between text-[11px] text-slate-400">
                            <span>Mastery Score</span>
                            <span className="font-mono text-slate-200 font-bold">{skill.mastery_score.toFixed(1)}%</span>
                          </div>
                          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${
                                skill.status === "known"
                                  ? "bg-emerald-500"
                                  : skill.status === "in_progress"
                                  ? "bg-cyan-500"
                                  : "bg-amber-500"
                              }`}
                              style={{ width: `${Math.min(100, Math.max(0, skill.mastery_score))}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 5. Phase Milestone Progress Breakdown */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Milestone className="w-4 h-4 text-teal-400" />
                      <h4 className="text-base font-bold text-slate-100">Phase Milestone Progress</h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Calculated using active {weeklyCommitmentHours} hrs/week commitment
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {dashboardResult.phase_progress.map((phase) => {
                      const phaseWeeks = Math.ceil(phase.estimated_hours / (weeklyCommitmentHours || 8));
                      const isComplete = phase.completed_courses + phase.skipped_courses >= phase.total_courses && phase.total_courses > 0;
                      return (
                        <div
                          key={phase.phase_number}
                          className={`rounded-xl p-4 space-y-3 border transition-all ${
                            phase.is_unlocked
                              ? "bg-slate-900/70 border-slate-800 shadow-sm"
                              : "bg-slate-950/60 border-slate-800/60 opacity-70"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <h5 className="text-sm font-bold text-slate-100">{phase.phase_name}</h5>
                            <span
                              className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full flex items-center gap-1 ${
                                isComplete
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                                  : phase.is_unlocked
                                  ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/30"
                                  : "bg-slate-800 text-slate-400 border border-slate-700"
                              }`}
                            >
                              {isComplete ? "Completed" : phase.is_unlocked ? "Unlocked" : "Locked"}
                            </span>
                          </div>

                          <div className="text-xs text-slate-400 space-y-1">
                            <div className="flex justify-between">
                              <span>Progress:</span>
                              <span className="font-mono text-slate-200">
                                {phase.completed_courses} done, {phase.skipped_courses} skipped ({phase.total_courses} total)
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span>Workload:</span>
                              <span className="font-mono text-slate-200">
                                {phase.estimated_hours} hrs (~{phaseWeeks} wks)
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* 6. Recent Progress Events History */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <History className="w-4 h-4 text-teal-400" />
                      <h4 className="text-base font-bold text-slate-100">Recent Progress & Assessment Events</h4>
                    </div>
                  </div>

                  {dashboardResult.recent_events.length > 0 ? (
                    <div className="bg-slate-900/40 border border-slate-800 rounded-xl divide-y divide-slate-800/60 overflow-hidden">
                      {dashboardResult.recent_events.map((evt, idx) => (
                        <div key={idx} className="p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                          <div className="space-y-0.5">
                            <p className="font-semibold text-slate-200">{evt.course_title}</p>
                            <p className="text-[11px] text-slate-500">{new Date(evt.timestamp).toLocaleString()}</p>
                          </div>

                          <div className="flex items-center gap-2">
                            {evt.assessment_score !== null && evt.assessment_score !== undefined && (
                              <span className={`px-2 py-0.5 rounded font-mono font-bold ${
                                evt.assessment_score > 85
                                  ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                                  : evt.assessment_score < 50
                                  ? "bg-rose-500/10 text-rose-300 border border-rose-500/20"
                                  : "bg-cyan-500/10 text-cyan-300 border border-cyan-500/20"
                              }`}>
                                Score: {evt.assessment_score.toFixed(1)}%
                              </span>
                            )}
                            {evt.difficulty_feedback && (
                              <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 capitalize">
                                Feedback: {evt.difficulty_feedback.replace("_", " ")}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 text-center text-xs text-slate-500">
                      No progress events recorded yet. Complete course assessments to see adaptive updates here.
                    </div>
                  )}
                </div>
              </div>
            )}
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
                    ~{dynamicTotalWeeks > 0 ? dynamicTotalWeeks : roadmapResult.total_estimated_weeks} Weeks @ {weeklyCommitmentHours}h/wk
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
                        <span>~{phase.estimated_hours} Hours (~{Math.ceil(phase.estimated_hours / (weeklyCommitmentHours || 8))} Wks)</span>
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
                              : course.status === "done"
                              ? "bg-emerald-950/20 border-emerald-500/30"
                              : course.status === "skipped"
                              ? "bg-slate-900/40 border-slate-800/40 opacity-60"
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

                            <div className="flex items-center justify-between pt-1 gap-2">
                              <button
                                type="button"
                                onClick={() => handleWhyThis(course.course_id, course.title)}
                                className="inline-flex items-center gap-1 text-xs font-semibold text-teal-400 hover:text-teal-300 transition-colors"
                              >
                                <Sparkles className="w-3.5 h-3.5" />
                                <span>Why this?</span>
                              </button>

                              <div className="flex items-center gap-2">
                                {(course.status === "available" || course.status === "in_progress") && (
                                  <button
                                    type="button"
                                    onClick={() => handleOpenAssessmentModal(course.course_id, course.title)}
                                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-teal-500/10 hover:bg-teal-500/20 text-teal-300 text-[11px] font-semibold transition-colors border border-teal-500/30"
                                    title="Submit assessment score to adapt roadmap"
                                  >
                                    <Award className="w-3 h-3 text-teal-400" />
                                    <span>Assess</span>
                                  </button>
                                )}

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

      {/* Lightweight Assessment / Progress Submission Modal (Day 5 Checkpoint 1) */}
      {assessmentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 relative">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-teal-500/10 border border-teal-500/30 text-teal-400 text-[11px] font-bold uppercase tracking-wider">
                  <Award className="w-3 h-3" />
                  Course Assessment & Progress
                </div>
                <h4 className="text-lg font-bold text-slate-100 line-clamp-1">
                  {assessmentModal.courseTitle}
                </h4>
              </div>
              <button
                type="button"
                onClick={handleCloseAssessmentModal}
                disabled={isSubmittingProgress}
                className="text-slate-400 hover:text-slate-200 p-1 rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-50"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {progressSuccessMessage ? (
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm space-y-2 text-center py-6">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto" />
                <p className="font-bold text-emerald-200">Progress Recorded!</p>
                <p className="text-xs text-emerald-300/90 leading-relaxed">{progressSuccessMessage}</p>
              </div>
            ) : (
              <form onSubmit={handleSubmitProgress} className="space-y-4">
                {progressModalError && (
                  <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
                    <span>{progressModalError}</span>
                  </div>
                )}

                <div className="space-y-2">
                  <label htmlFor="assessment-score-input" className="block text-xs font-semibold text-slate-200">
                    Assessment Score (0 – 100%)
                  </label>
                  <div className="relative">
                    <input
                      id="assessment-score-input"
                      type="number"
                      min="0"
                      max="100"
                      step="0.5"
                      required
                      value={assessmentScore}
                      onChange={(e) => setAssessmentScore(e.target.value)}
                      disabled={isSubmittingProgress}
                      className="w-full rounded-xl bg-slate-950 border border-slate-800 px-4 py-2.5 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 text-sm font-mono"
                      placeholder="e.g. 92.5"
                    />
                    <span className="absolute right-4 top-2.5 text-xs text-slate-500 font-mono">%</span>
                  </div>
                  <div className="flex justify-between text-[11px] text-slate-500">
                    <span className="text-rose-400/80">&lt;50% triggers remediation</span>
                    <span className="text-emerald-400/80">&gt;85% triggers mastery</span>
                  </div>
                </div>

                <div className="space-y-2">
                  <label htmlFor="difficulty-feedback-select" className="block text-xs font-semibold text-slate-200">
                    Difficulty Feedback (Optional)
                  </label>
                  <select
                    id="difficulty-feedback-select"
                    value={difficultyFeedback}
                    onChange={(e) => setDifficultyFeedback(e.target.value as any)}
                    disabled={isSubmittingProgress}
                    className="w-full rounded-xl bg-slate-950 border border-slate-800 px-3 py-2.5 text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500"
                  >
                    <option value="">No feedback</option>
                    <option value="too_easy">Too Easy (Paced below current skill)</option>
                    <option value="just_right">Just Right (Appropriate challenge)</option>
                    <option value="too_hard">Too Hard (Prerequisites felt weak)</option>
                  </select>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={handleCloseAssessmentModal}
                    disabled={isSubmittingProgress}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmittingProgress}
                    className="inline-flex items-center gap-2 px-5 py-2 rounded-xl bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-bold transition-all shadow-md shadow-teal-500/20 disabled:opacity-50"
                  >
                    {isSubmittingProgress ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Recording...</span>
                      </>
                    ) : (
                      <>
                        <CheckCircle className="w-3.5 h-3.5" />
                        <span>Submit Score</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
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