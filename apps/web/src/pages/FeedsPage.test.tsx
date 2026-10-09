import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";

import type { FeedSource } from "../lib/api";
import FeedsPage from "./FeedsPage";

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

/** In-memory fake of the feed-sources API so invalidation-driven refetches
 * see the effect of writes just like against the real backend. */
function stubFeedsApi(initial: FeedSource[]) {
  const store = new Map(initial.map((source) => [source.id, source]));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/feeds/sources") && method === "GET") {
        return jsonResponse([...store.values()]);
      }
      if (url.endsWith("/api/feeds/sources") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        const source: FeedSource = {
          id: `id-${store.size + 1}`,
          name: body.name,
          kind: body.kind,
          url: body.url,
          enabled: true,
        };
        store.set(source.id, source);
        return jsonResponse(source, 201);
      }
      const idMatch = url.match(/\/api\/feeds\/sources\/([^/]+)$/);
      if (idMatch && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        const existing = store.get(idMatch[1])!;
        const updated = { ...existing, ...body };
        store.set(updated.id, updated);
        return jsonResponse(updated);
      }
      if (idMatch && method === "DELETE") {
        store.delete(idMatch[1]);
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
        <FeedsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const existing: FeedSource = {
  id: "id-1",
  name: "Existing",
  kind: "rss",
  url: "https://existing.example/feed",
  enabled: true,
};

test("shows an empty state with no sources", async () => {
  stubFeedsApi([]);
  renderPage();
  expect(await screen.findByText(/No feed sources yet/)).toBeTruthy();
});

test("creates a source and refreshes the list", async () => {
  stubFeedsApi([]);
  renderPage();
  await screen.findByText(/No feed sources yet/);

  fireEvent.change(screen.getByLabelText("Source name"), {
    target: { value: "GitHub" },
  });
  fireEvent.change(screen.getByLabelText("Source kind"), {
    target: { value: "github" },
  });
  fireEvent.change(screen.getByLabelText("Source URL"), {
    target: { value: "https://github.com/o/r" },
  });
  fireEvent.click(screen.getByText("Add"));

  expect(await screen.findByText("GitHub")).toBeTruthy();
  // Form resets after a successful create.
  expect((screen.getByLabelText("Source name") as HTMLInputElement).value).toBe("");
});

test("toggles a source's enabled state", async () => {
  const store = stubFeedsApi([existing]);
  renderPage();
  await screen.findByText("Existing");

  // Enabled source offers a Disable action.
  fireEvent.click(screen.getByText("Disable"));

  expect(await screen.findByText("Enable")).toBeTruthy();
  expect(store.get("id-1")!.enabled).toBe(false);
});

test("delete requires confirmation and removes the source", async () => {
  const store = stubFeedsApi([existing]);
  renderPage();
  await screen.findByText("Existing");

  fireEvent.click(screen.getByText("Delete"));
  // Nothing deleted yet; cancel backs out.
  expect(store.has("id-1")).toBe(true);
  fireEvent.click(screen.getByText("Cancel"));
  expect(screen.queryByText("Confirm delete")).toBeNull();

  fireEvent.click(screen.getByText("Delete"));
  fireEvent.click(screen.getByText("Confirm delete"));

  expect(await screen.findByText(/No feed sources yet/)).toBeTruthy();
  expect(store.has("id-1")).toBe(false);
});
