/**
 * CourseTide API Client
 * Typed client for communicating with the FastAPI backend service.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || (typeof window !== "undefined" ? "" : "http://localhost:8000");

export interface ProfileInput {
  name?: string;
  email?: string;
  goal: string;
  weekly_hours?: number;
}

export interface RecommendedCourse {
  id: string;
  title: string;
  description?: string;
  difficulty: string;
  duration_hours: number;
  resource_type: string;
  domain: string;
  source?: string;
  url?: string;
  learning_outcomes?: string;
  primary_skill?: string;
  all_skills: string[];
  covered_gap_skills: string[];
  match_score: number;
  semantic_similarity: number;
  gap_coverage_ratio: number;
}

export interface ProfileResponse {
  learner_id: string;
  name?: string;
  email?: string;
  goal: string;
  target_role: string;
  role_name: string;
  weekly_hours: number;
  timeframe_months: number;
  known_skills: string[];
  gap_skills: string[];
  unrecognized_skills: string[];
  match_percentage: number;
  recommended_courses: RecommendedCourse[];
  parsed_goal?: Record<string, any>;
}

export interface SkillGapResponse {
  learner_id: string;
  target_role: string;
  role_name: string;
  required_skills: string[];
  known_skills: string[];
  gap_skills: string[];
  recommended_optional_skills: string[];
  total_required_count: number;
  known_count: number;
  gap_count: number;
  match_percentage: number;
}

export interface RoadmapCourse {
  course_id: string;
  title: string;
  difficulty: string;
  duration_hours: number;
  domain: string;
  source?: string;
  url?: string;
  primary_skill?: string;
  covered_skills: string[];
  phase_number: number;
  sequence_order: number;
  status: "available" | "locked" | "in_progress" | "done" | "skipped" | string;
  match_score?: number;
}

export interface RoadmapPhase {
  phase_number: number;
  phase_name: string;
  skills: string[];
  courses: RoadmapCourse[];
  estimated_hours: number;
}

export interface RoadmapResponse {
  learner_id: string;
  target_role: string;
  role_name: string;
  total_courses: number;
  total_estimated_hours: number;
  total_estimated_weeks: number;
  phases: RoadmapPhase[];
}

export interface ExplanationResponse {
  learner_id: string;
  course_id: string;
  course_title: string;
  primary_skill: string;
  phase_number: number;
  phase_name: string;
  explanation: string;
}

export interface ProgressEventInput {
  learner_id: string;
  course_id: string;
  difficulty_feedback?: "too_easy" | "just_right" | "too_hard";
  assessment_score?: number;
}

export interface ProgressEventResponse {
  event_id: string;
  status: string;
  adaptation: {
    adaptation_applied: "none" | "fast_track" | "remediation" | string;
    message: string;
    mastered_skill?: string | null;
    skipped_course_id?: string | null;
    inserted_course_id?: string | null;
  };
}

export interface NextRecommendedAction {
  course_id: string;
  title: string;
  phase_number: number;
  sequence_order: number;
  status: "available" | "in_progress" | string;
  duration_hours: number;
  primary_skill: string;
  url?: string;
}

export interface SkillMasteryRadarItem {
  skill_id: string;
  skill_name: string;
  status: "known" | "in_progress" | "gap" | string;
  mastery_score: number;
  is_required: boolean;
}

export interface PhaseProgressItem {
  phase_number: number;
  phase_name: string;
  total_courses: number;
  completed_courses: number;
  skipped_courses: number;
  is_unlocked: boolean;
  estimated_hours: number;
}

export interface RecentEventItem {
  course_id: string;
  course_title: string;
  assessment_score?: number;
  difficulty_feedback?: string;
  timestamp: string;
}

export interface DashboardResponse {
  learner_id: string;
  target_role: string;
  role_name: string;
  overall_progress_percentage: number;
  effective_progress_percentage: number;
  total_courses: number;
  completed_courses: number;
  skipped_courses: number;
  current_phase_number: number;
  current_phase_name: string;
  next_recommended_action?: NextRecommendedAction | null;
  skill_mastery_radar: SkillMasteryRadarItem[];
  phase_progress: PhaseProgressItem[];
  recent_events: RecentEventItem[];
}

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let errorDetail = response.statusText;
    try {
      const errorBody = await response.json();
      errorDetail = errorBody.detail || JSON.stringify(errorBody);
    } catch {
      errorDetail = await response.text();
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export const api = {
  // Health
  getHealth: () => request<{ status: string; service: string; version: string }>("/health"),

  // Profile Intake (POST /api/profile)
  createProfile: (data: ProfileInput) =>
    request<ProfileResponse>("/api/profile", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Skill Gap (GET /api/skill-gap/{learner_id})
  getSkillGap: (learnerId: string) =>
    request<SkillGapResponse>(`/api/skill-gap/${learnerId}`),

  // Roadmap (GET /api/roadmap/{learner_id})
  getRoadmap: (learnerId: string) =>
    request<RoadmapResponse>(`/api/roadmap/${learnerId}`),

  // Grounded Explanation (GET /api/explain/{learner_id}/{course_id})
  getExplanation: (learnerId: string, courseId: string) =>
    request<ExplanationResponse>(`/api/explain/${learnerId}/${courseId}`),

  // Adaptive Progress (POST /api/progress)
  recordProgress: (data: ProgressEventInput) =>
    request<ProgressEventResponse>("/api/progress", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Dashboard (GET /api/dashboard/{learner_id})
  getDashboard: (learnerId: string) =>
    request<DashboardResponse>(`/api/dashboard/${learnerId}`),
};