"use client";

import { useQuery } from "@tanstack/react-query";

import type {
  Dashboard,
  DiffResponse,
  Evaluation,
  Me,
  Repository,
  Task,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

let csrf: string | null = null;

export class ApiError extends Error {
  category: string;
  correlationId?: string;
  constructor(message: string, category: string, correlationId?: string) {
    super(message);
    this.category = category;
    this.correlationId = correlationId;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method !== "GET" && method !== "HEAD") {
    headers.set("Content-Type", "application/json");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const res = await fetch(`${BASE}/api${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = body?.error ?? {};
    throw new ApiError(err.message ?? res.statusText, err.category ?? "infra", err.correlation_id);
  }
  return body as T;
}

export const api = {
  me: () => request<Me>("/auth/me"),
  dashboard: () => request<Dashboard>("/dashboard"),
  repositories: () => request<Repository[]>("/repositories"),
  githubRepos: () => request<Repository[]>("/repositories/github"),
  connectRepo: (github_repo_id: number) =>
    request<Repository>("/repositories/connect", {
      method: "POST",
      body: JSON.stringify({ github_repo_id }),
    }),
  indexRepo: (id: string, branch: string) =>
    request(`/repositories/${id}/index`, { method: "POST", body: JSON.stringify({ branch }) }),
  branches: (id: string) => request<string[]>(`/repositories/${id}/branches`),
  tasks: () => request<Task[]>("/tasks"),
  task: (id: string) => request<Task>(`/tasks/${id}`),
  createTask: (payload: Record<string, unknown>) =>
    request<Task>("/tasks", { method: "POST", body: JSON.stringify(payload) }),
  runTask: (id: string) => request(`/tasks/${id}/run`, { method: "POST" }),
  cancelTask: (id: string) => request(`/tasks/${id}/cancel`, { method: "POST" }),
  diff: (id: string) => request<DiffResponse>(`/tasks/${id}/diff`),
  review: (id: string) => request<Record<string, unknown>>(`/tasks/${id}/review`),
  approve: (id: string, create_pr: boolean) =>
    request<Task>(`/tasks/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ create_pr, confirm: true }),
    }),
  run: (id: string) => request<Record<string, unknown>>(`/runs/${id}`),
  evaluations: () => request<Evaluation[]>("/evaluations"),
  runEvaluation: (payload: Record<string, unknown>) =>
    request<Evaluation>("/evaluations/run", { method: "POST", body: JSON.stringify(payload) }),
  pullRequests: () => request<Record<string, unknown>[]>("/pull-requests"),
};

export function setCsrf(token: string) {
  csrf = token;
}

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const me = await api.me();
      setCsrf(me.csrf_token);
      return me;
    },
    retry: false,
  });
}

export function useDashboard() {
  return useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
}
export function useRepositories() {
  return useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
}
export function useTasks() {
  return useQuery({ queryKey: ["tasks"], queryFn: api.tasks, refetchInterval: 5000 });
}
export function useTask(id: string) {
  return useQuery({ queryKey: ["task", id], queryFn: () => api.task(id), refetchInterval: 4000 });
}
export function useDiff(id: string, enabled: boolean) {
  return useQuery({ queryKey: ["diff", id], queryFn: () => api.diff(id), enabled });
}
export function useEvaluations() {
  return useQuery({ queryKey: ["evaluations"], queryFn: api.evaluations, refetchInterval: 6000 });
}
