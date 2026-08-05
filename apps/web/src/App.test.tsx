import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

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

test("renders header, nav, and API status", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/health")) {
        return jsonResponse({ status: "ok", version: "test" });
      }
      if (url.includes("/api/dashboard/stats")) {
        return jsonResponse({
          projects: 0,
          issues_total: 0,
          issues_by_status: {},
          issues_by_priority: {},
          overdue: 0,
          activity_last_7_days: 0,
        });
      }
      if (url.includes("/api/dashboard/activity")) {
        return jsonResponse([]);
      }
      return new Response("not found", { status: 404 });
    }),
  );

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(screen.getByText("Pulse")).toBeTruthy();
  expect(screen.getByText("Projects")).toBeTruthy();
  expect(await screen.findByText(/ok \(vtest\)/)).toBeTruthy();
  expect(await screen.findByText("Nothing has happened yet.")).toBeTruthy();
});
