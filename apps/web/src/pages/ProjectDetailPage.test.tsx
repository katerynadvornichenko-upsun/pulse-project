import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, expect, test, vi } from "vitest";

import type { Issue } from "../lib/api";
import ProjectDetailPage from "./ProjectDetailPage";

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

function makeIssue(overrides: Partial<Issue>): Issue {
  return {
    id: "issue-1",
    title: "An issue",
    description: "",
    status: "backlog",
    priority: "medium",
    due_date: null,
    closed_at: null,
    project_id: "project-1",
    labels: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** In-memory fake honoring the status/priority filters, so filter changes
 * are observable through refetched results. */
function stubApi(initialIssues: Issue[]) {
  const issues = new Map(initialIssues.map((issue) => [issue.id, issue]));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      const method = init?.method ?? "GET";

      if (url.pathname === "/api/projects/project-1" && method === "GET") {
        return jsonResponse({
          id: "project-1",
          name: "Pulse",
          description: "",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        });
      }
      if (url.pathname === "/api/issues" && method === "GET") {
        let result = [...issues.values()];
        const status = url.searchParams.get("status");
        const priority = url.searchParams.get("priority");
        if (status) result = result.filter((issue) => issue.status === status);
        if (priority) result = result.filter((issue) => issue.priority === priority);
        return jsonResponse(result);
      }
      if (url.pathname === "/api/issues" && method === "POST") {
        const body = JSON.parse(String(init?.body));
        const issue = makeIssue({
          id: `issue-${issues.size + 1}`,
          title: body.title,
          priority: body.priority ?? "medium",
          due_date: body.due_date ?? null,
        });
        issues.set(issue.id, issue);
        return jsonResponse(issue, 201);
      }
      return new Response("not found", { status: 404 });
    }),
  );
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/projects/project-1"]}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders the project's issues with badges and labels", async () => {
  stubApi([
    makeIssue({
      id: "issue-1",
      title: "Ship the thing",
      status: "in_progress",
      priority: "high",
      labels: [{ id: "label-1", name: "bug", color: "#ff0000" }],
    }),
  ]);
  renderPage();

  expect(await screen.findByText("Pulse")).toBeTruthy();
  // Scope to the row: the filter dropdowns contain the same words.
  const row = (await screen.findByText("Ship the thing")).closest("li")!;
  expect(within(row).getByText("in progress")).toBeTruthy();
  expect(within(row).getByText("high")).toBeTruthy();
  expect(within(row).getByText("bug")).toBeTruthy();
});

test("status filter narrows the list via the query parameter", async () => {
  stubApi([
    makeIssue({ id: "issue-1", title: "Open one", status: "todo" }),
    makeIssue({ id: "issue-2", title: "Done one", status: "done" }),
  ]);
  renderPage();
  expect(await screen.findByText("Open one")).toBeTruthy();
  expect(screen.getByText("Done one")).toBeTruthy();

  fireEvent.change(screen.getByLabelText("Filter by status"), {
    target: { value: "done" },
  });

  expect(await screen.findByText("Done one")).toBeTruthy();
  expect(screen.queryByText("Open one")).toBeNull();
});

test("creates an issue and shows it in the list", async () => {
  stubApi([]);
  renderPage();
  expect(await screen.findByText("No issues match.")).toBeTruthy();

  fireEvent.change(screen.getByLabelText("Issue title"), {
    target: { value: "Brand new" },
  });
  fireEvent.change(screen.getByLabelText("Issue priority"), {
    target: { value: "urgent" },
  });
  fireEvent.click(screen.getByText("Create"));

  const row = (await screen.findByText("Brand new")).closest("li")!;
  expect(within(row).getByText("urgent")).toBeTruthy();
  // Form resets after a successful create.
  expect((screen.getByLabelText("Issue title") as HTMLInputElement).value).toBe("");
});
