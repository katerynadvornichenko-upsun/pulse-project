import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => {
  vi.restoreAllMocks();
});

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

test("renders header and API status", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/health")) {
        return jsonResponse({ status: "ok", version: "test" });
      }
      if (url.endsWith("/api/projects")) {
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
  expect(await screen.findByText(/ok \(vtest\)/)).toBeTruthy();
  expect(await screen.findByText("No projects yet.")).toBeTruthy();
});
