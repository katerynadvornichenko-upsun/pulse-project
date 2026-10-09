import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";

import HomePage from "./HomePage";

afterEach(() => {
  // Auto-cleanup needs vitest globals, which this project doesn't enable.
  cleanup();
  vi.restoreAllMocks();
});

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function stubDashboard() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/health")) {
        return jsonResponse({ status: "ok", version: "test" });
      }
      if (url.includes("/api/dashboard/stats")) {
        return jsonResponse({
          projects: 2,
          issues_total: 7,
          issues_by_status: { backlog: 3, in_progress: 2, done: 2 },
          issues_by_priority: { medium: 5, high: 2 },
          overdue: 1,
          activity_last_7_days: 12,
        });
      }
      if (url.includes("/api/dashboard/activity")) {
        return jsonResponse([
          {
            id: "event-1",
            entity_type: "issue",
            entity_id: "issue-1",
            action: "status_changed",
            message: "Issue 'Fix login' moved from todo to in_progress",
            created_at: "2026-07-07T10:00:00Z",
          },
          {
            id: "event-2",
            entity_type: "dashboard",
            entity_id: "roll-1",
            action: "rollup",
            message: "Daily rollup: 2 projects, 7 issues (5 open, 1 overdue)",
            created_at: "2026-07-07T03:00:00Z",
          },
        ]);
      }
      if (url.includes("/api/feeds/items")) {
        return jsonResponse(feedItems);
      }
      return new Response("not found", { status: 404 });
    }),
  );
}

let feedItems: unknown[] = [];

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders stat cards and the status breakdown", async () => {
  stubDashboard();
  renderPage();

  const projectsCard = (await screen.findByText("Projects")).closest("div")!;
  expect(within(projectsCard).getByText("2")).toBeTruthy();
  const issuesCard = screen.getByText("Issues").closest("div")!;
  expect(within(issuesCard).getByText("7")).toBeTruthy();
  const overdueCard = screen.getByText("Overdue").closest("div")!;
  expect(within(overdueCard).getByText("1")).toBeTruthy();

  expect(await screen.findByText(/in progress:/)).toBeTruthy();
});

test("renders the activity timeline newest data as returned", async () => {
  stubDashboard();
  renderPage();

  expect(
    await screen.findByText("Issue 'Fix login' moved from todo to in_progress"),
  ).toBeTruthy();
  expect(screen.getByText(/Daily rollup: 2 projects/)).toBeTruthy();
});

test("renders the From your feeds section with items", async () => {
  feedItems = [
    {
      id: "item-1",
      source_id: "src-1",
      source_name: "Django Blog",
      title: "Django 6.0 released",
      url: "https://example.com/django-6",
      summary: "",
      published_at: "2026-07-07T09:00:00Z",
      fetched_at: "2026-07-07T09:05:00Z",
    },
  ];
  stubDashboard();
  renderPage();

  const link = (await screen.findByText("Django 6.0 released")) as HTMLAnchorElement;
  expect(link.getAttribute("href")).toBe("https://example.com/django-6");
  expect(screen.getByText("Django Blog")).toBeTruthy();
});

test("shows an empty state when there are no feed items", async () => {
  feedItems = [];
  stubDashboard();
  renderPage();

  expect(await screen.findByText(/No feed items yet/)).toBeTruthy();
});
