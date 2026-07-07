import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";

import type { Project } from "../lib/api";
import ProjectsPage from "./ProjectsPage";

afterEach(() => {
  // Auto-cleanup needs vitest globals, which this project doesn't enable.
  cleanup();
  vi.restoreAllMocks();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** In-memory fake of the projects API, so invalidation-driven refetches see
 * the effect of writes just like against the real backend. */
function stubProjectsApi(initial: Project[]) {
  const store = new Map(initial.map((project) => [project.id, project]));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/projects") && method === "GET") {
        return jsonResponse([...store.values()]);
      }
      if (url.endsWith("/api/projects") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        const project: Project = {
          id: `id-${store.size + 1}`,
          name: body.name,
          description: body.description ?? "",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        store.set(project.id, project);
        return jsonResponse(project, 201);
      }
      const deleteMatch = url.match(/\/api\/projects\/([^/]+)$/);
      if (deleteMatch && method === "DELETE") {
        store.delete(deleteMatch[1]);
        return new Response(null, { status: 204 });
      }
      return new Response("not found", { status: 404 });
    }),
  );
  return store;
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const existing: Project = {
  id: "id-1",
  name: "Existing",
  description: "already here",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

test("lists projects", async () => {
  stubProjectsApi([existing]);
  renderPage();
  expect(await screen.findByText("Existing")).toBeTruthy();
  expect(screen.getByText("already here")).toBeTruthy();
});

test("creates a project and refreshes the list", async () => {
  stubProjectsApi([]);
  renderPage();
  expect(await screen.findByText(/No projects yet/)).toBeTruthy();

  fireEvent.change(screen.getByLabelText("Project name"), {
    target: { value: "Fresh" },
  });
  fireEvent.change(screen.getByLabelText("Project description"), {
    target: { value: "brand new" },
  });
  fireEvent.click(screen.getByText("Create"));

  expect(await screen.findByText("Fresh")).toBeTruthy();
  // Form resets after a successful create.
  expect((screen.getByLabelText("Project name") as HTMLInputElement).value).toBe("");
});

test("delete requires confirmation and removes the project", async () => {
  const store = stubProjectsApi([existing]);
  renderPage();
  await screen.findByText("Existing");

  fireEvent.click(screen.getByText("Delete"));
  // Nothing deleted yet; cancel backs out.
  expect(store.has("id-1")).toBe(true);
  fireEvent.click(screen.getByText("Cancel"));
  expect(screen.queryByText("Confirm delete")).toBeNull();

  fireEvent.click(screen.getByText("Delete"));
  fireEvent.click(screen.getByText("Confirm delete"));

  expect(await screen.findByText(/No projects yet/)).toBeTruthy();
  expect(store.has("id-1")).toBe(false);
});
