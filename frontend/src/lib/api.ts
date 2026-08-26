/**
 * CourseTide API Client
 * Typed client for communicating with the FastAPI backend service.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ProfileInput {
  name?: string;
  email?: string;
  goal: string;
  weekly_hours?: number;
}

export interface ProgressEventInput {
  learner_id: string;
  course_id: string;
  difficulty_feedback?: "too_easy" | "just_right" | "too_hard";
  assessment_score?: number;
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
    const errorBody = await response.text();
    throw new Error(`API Request Error [${response.status}] ${response.statusText}: ${errorBody}`);
  }

  return response.json();
}

export const api = {
  // Health
  getHealth: () => request<{ status: string; service: string; version: string }>("/health"),

  // Profile Intake (POST /api/profile)
  createProfile: (data: ProfileInput) =>
    request<any>("/api/profile", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Skill Gap (GET /api/skill-gap/{learner_id})
  getSkillGap: (learnerId: string) =>
    request<any>(`/api/skill-gap/${learnerId}`),

  // Roadmap (GET /api/roadmap/{learner_id})
  getRoadmap: (learnerId: string) =>
    request<any>(`/api/roadmap/${learnerId}`),

  // Grounded Explanation (GET /api/explain/{learner_id}/{course_id})
  getExplanation: (learnerId: string, courseId: string) =>
    request<any>(`/api/explain/${learnerId}/${courseId}`),

  // Adaptive Progress (POST /api/progress)
  recordProgress: (data: ProgressEventInput) =>
    request<any>("/api/progress", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Dashboard (GET /api/dashboard/{learner_id})
  getDashboard: (learnerId: string) =>
    request<any>(`/api/dashboard/${learnerId}`),
};
