// Thin typed wrapper over fetch. Types come from the generated OpenAPI file —
// regenerate with `make gen-types` (repo root) after changing API schemas.
import type { paths } from "./api-types.gen";

export type Project =
  paths["/api/projects"]["get"]["responses"]["200"]["content"]["application/json"][number];
export type Health =
  paths["/api/health"]["get"]["responses"]["200"]["content"]["application/json"];

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

export const api = {
  health: () => request<Health>("/api/health"),
  projects: {
    list: () => request<Project[]>("/api/projects"),
    create: (data: { name: string; description?: string }) =>
      request<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  },
};
