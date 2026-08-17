// Thin typed wrapper over fetch. Types come from the generated OpenAPI file —
// regenerate with `make gen-types` (repo root) after changing API schemas.
import type { components } from "./api-types.gen";

export type Project = components["schemas"]["ProjectRead"];
export type DashboardStats = components["schemas"]["DashboardStats"];
export type ActivityEvent = components["schemas"]["ActivityEventRead"];
export type Issue = components["schemas"]["IssueRead"];
export type Label = components["schemas"]["LabelRead"];
export type IssueStatus = components["schemas"]["IssueStatus"];
export type IssuePriority = components["schemas"]["IssuePriority"];
export type FeedItem = components["schemas"]["FeedItemRead"];
export type FeedSource = components["schemas"]["FeedSourceRead"];
export type FeedKind = components["schemas"]["FeedKind"];
export type Health = { status: string; version: string };

export const FEED_KINDS: FeedKind[] = ["rss", "github"];

export const ISSUE_STATUSES: IssueStatus[] = [
  "backlog",
  "todo",
  "in_progress",
  "done",
  "cancelled",
];
export const ISSUE_PRIORITIES: IssuePriority[] = ["low", "medium", "high", "urgent"];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed with ${res.status}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export interface IssueFilters {
  project_id?: string;
  status?: IssueStatus;
  priority?: IssuePriority;
  label?: string;
}

function withQuery(path: string, params: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  const qs = query.toString();
  return qs ? `${path}?${qs}` : path;
}

export const api = {
  health: () => request<Health>("/api/health"),
  dashboard: {
    stats: () => request<DashboardStats>("/api/dashboard/stats"),
    activity: (limit = 20) =>
      request<ActivityEvent[]>(`/api/dashboard/activity?limit=${limit}`),
  },
  feeds: {
    items: (limit = 20) => request<FeedItem[]>(`/api/feeds/items?limit=${limit}`),
    sources: {
      list: () => request<FeedSource[]>("/api/feeds/sources"),
      create: (data: { name: string; kind: FeedKind; url: string }) =>
        request<FeedSource>("/api/feeds/sources", {
          method: "POST",
          body: JSON.stringify(data),
        }),
      setEnabled: (id: string, enabled: boolean) =>
        request<FeedSource>(`/api/feeds/sources/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ enabled }),
        }),
      delete: (id: string) =>
        request<void>(`/api/feeds/sources/${id}`, { method: "DELETE" }),
    },
  },
  projects: {
    list: () => request<Project[]>("/api/projects"),
    get: (id: string) => request<Project>(`/api/projects/${id}`),
    create: (data: { name: string; description?: string }) =>
      request<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  },
  issues: {
    list: (filters: IssueFilters = {}) =>
      request<Issue[]>(withQuery("/api/issues", { ...filters })),
    create: (data: {
      title: string;
      project_id: string;
      description?: string;
      priority?: IssuePriority;
      due_date?: string | null;
    }) => request<Issue>("/api/issues", { method: "POST", body: JSON.stringify(data) }),
    update: (
      id: string,
      data: { title?: string; description?: string; priority?: IssuePriority },
    ) =>
      request<Issue>(`/api/issues/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    setStatus: (id: string, status: IssueStatus) =>
      request<Issue>(`/api/issues/${id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      }),
    delete: (id: string) => request<void>(`/api/issues/${id}`, { method: "DELETE" }),
  },
};
