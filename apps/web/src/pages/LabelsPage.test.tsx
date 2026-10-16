import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";

import type { Label } from "../lib/api";
import LabelsPage from "./LabelsPage";

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

/** In-memory fake of the labels API, including the 409 on duplicate names. */
function stubLabelsApi(initial: Label[]) {
  const store = new Map(initial.map((label) => [label.id, label]));
  const requests: { method: string; url: string; body: unknown }[] = [];
  const nameTaken = (name: string, exceptId?: string) =>
    [...store.values()].some((label) => label.name === name && label.id !== exceptId);
  const conflict = (name: string) =>
    jsonResponse({ detail: `Label '${name}' already exists` }, 409);

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body: unknown = init?.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ method, url, body });

      if (url.endsWith("/api/labels") && method === "GET") {
        const sorted = [...store.values()].sort((a, b) => a.name.localeCompare(b.name));
        return jsonResponse(sorted);
      }
      if (url.endsWith("/api/labels") && method === "POST") {
        const data = body as { name: string; color?: string };
        if (nameTaken(data.name)) return conflict(data.name);
        const label: Label = {
          id: `id-${store.size + 1}`,
          name: data.name,
          color: data.color ?? "#808080",
        };
        store.set(label.id, label);
        return jsonResponse(label, 201);
      }
      const match = url.match(/\/api\/labels\/([^/]+)$/);
      if (match && store.has(match[1])) {
        const id = match[1];
        if (method === "PATCH") {
          const data = body as { name?: string; color?: string };
          if (data.name !== undefined && nameTaken(data.name, id)) {
            return conflict(data.name);
          }
          const updated = { ...store.get(id)!, ...data };
          store.set(id, updated);
          return jsonResponse(updated);
        }
        if (method === "DELETE") {
          store.delete(id);
          return new Response(null, { status: 204 });
        }
      }
      return new Response("not found", { status: 404 });
    }),
  );
  return { store, requests };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LabelsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const bug: Label = { id: "id-1", name: "bug", color: "#ff0000" };

test("lists labels with a colour swatch", async () => {
  stubLabelsApi([bug, { id: "id-2", name: "feature", color: "#00ff00" }]);
  renderPage();
  expect(await screen.findByText("bug")).toBeTruthy();
  expect(screen.getByText("feature")).toBeTruthy();
  const swatch = screen.getByTestId("label-swatch-id-1");
  expect(swatch.style.backgroundColor).toBe("rgb(255, 0, 0)");
});

test("creates a label with the chosen colour", async () => {
  const { store, requests } = stubLabelsApi([]);
  renderPage();
  expect(await screen.findByText(/No labels yet/)).toBeTruthy();

  fireEvent.change(screen.getByLabelText("Label name"), {
    target: { value: "urgent" },
  });
  fireEvent.change(screen.getByLabelText("Label colour"), {
    target: { value: "#123abc" },
  });
  fireEvent.click(screen.getByText("Create"));

  expect(await screen.findByText("urgent")).toBeTruthy();
  expect((screen.getByLabelText("Label name") as HTMLInputElement).value).toBe("");
  const post = requests.find((r) => r.method === "POST");
  expect(post?.body).toEqual({ name: "urgent", color: "#123abc" });
  expect(store.size).toBe(1);
});

test("shows a readable message when the name already exists", async () => {
  const { store } = stubLabelsApi([bug]);
  renderPage();
  await screen.findByText("bug");

  fireEvent.change(screen.getByLabelText("Label name"), {
    target: { value: "bug" },
  });
  fireEvent.click(screen.getByText("Create"));

  expect(await screen.findByText("A label with that name already exists")).toBeTruthy();
  expect(store.size).toBe(1);
});

test("renames a label inline with a PATCH of only the changed field", async () => {
  const { store, requests } = stubLabelsApi([bug]);
  renderPage();
  await screen.findByText("bug");

  fireEvent.click(screen.getByText("Edit"));
  fireEvent.change(screen.getByLabelText("Edit label name"), {
    target: { value: "defect" },
  });
  fireEvent.click(screen.getByText("Save"));

  expect(await screen.findByText("defect")).toBeTruthy();
  expect(screen.queryByText("bug")).toBeNull();
  expect(screen.queryByLabelText("Edit label name")).toBeNull();
  const patch = requests.find((r) => r.method === "PATCH");
  expect(patch?.url).toMatch(/\/api\/labels\/id-1$/);
  expect(patch?.body).toEqual({ name: "defect" });
  expect(store.get("id-1")?.name).toBe("defect");
});

test("recolours a label inline", async () => {
  const { store, requests } = stubLabelsApi([bug]);
  renderPage();
  await screen.findByText("bug");

  fireEvent.click(screen.getByText("Edit"));
  fireEvent.change(screen.getByLabelText("Edit label colour"), {
    target: { value: "#0000ff" },
  });
  fireEvent.click(screen.getByText("Save"));

  await screen.findByText("Edit");
  const patch = requests.find((r) => r.method === "PATCH");
  expect(patch?.body).toEqual({ color: "#0000ff" });
  expect(store.get("id-1")?.color).toBe("#0000ff");
});

test("renaming to an existing name shows the duplicate message", async () => {
  stubLabelsApi([bug, { id: "id-2", name: "feature", color: "#00ff00" }]);
  renderPage();
  await screen.findByText("bug");

  fireEvent.click(screen.getAllByText("Edit")[0]);
  fireEvent.change(screen.getByLabelText("Edit label name"), {
    target: { value: "feature" },
  });
  fireEvent.click(screen.getByText("Save"));

  expect(await screen.findByText("A label with that name already exists")).toBeTruthy();
  // Edit mode stays open so the user can fix the name.
  expect(screen.getByLabelText("Edit label name")).toBeTruthy();
});

test("delete requires confirmation and removes the label", async () => {
  const { store } = stubLabelsApi([bug]);
  renderPage();
  await screen.findByText("bug");

  fireEvent.click(screen.getByText("Delete"));
  // Nothing deleted yet; cancel backs out.
  expect(store.has("id-1")).toBe(true);
  fireEvent.click(screen.getByText("Cancel"));
  expect(screen.queryByText("Confirm delete")).toBeNull();

  fireEvent.click(screen.getByText("Delete"));
  fireEvent.click(screen.getByText("Confirm delete"));

  expect(await screen.findByText(/No labels yet/)).toBeTruthy();
  expect(store.has("id-1")).toBe(false);
});
