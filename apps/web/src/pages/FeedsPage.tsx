import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, FEED_KINDS, type FeedKind } from "../lib/api";

export default function FeedsPage() {
  const queryClient = useQueryClient();
  const sources = useQuery({ queryKey: ["feed-sources"], queryFn: api.feeds.sources.list });

  const [name, setName] = useState("");
  const [kind, setKind] = useState<FeedKind>("rss");
  const [url, setUrl] = useState("");
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["feed-sources"] });

  const createSource = useMutation({
    mutationFn: api.feeds.sources.create,
    onSuccess: () => {
      setName("");
      setKind("rss");
      setUrl("");
      invalidate();
    },
  });

  const toggleSource = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.feeds.sources.setEnabled(id, enabled),
    onSuccess: invalidate,
  });

  const deleteSource = useMutation({
    mutationFn: api.feeds.sources.delete,
    onSuccess: () => {
      setConfirmingId(null);
      invalidate();
    },
  });

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          New feed source
        </h2>
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim() && url.trim()) {
              createSource.mutate({ name: name.trim(), kind, url: url.trim() });
            }
          }}
        >
          <input
            className="rounded border border-slate-300 px-3 py-2 sm:w-40"
            placeholder="Name"
            aria-label="Source name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <select
            className="rounded border border-slate-300 px-3 py-2"
            aria-label="Source kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as FeedKind)}
          >
            {FEED_KINDS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <input
            className="flex-1 rounded border border-slate-300 px-3 py-2"
            placeholder="URL"
            aria-label="Source URL"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
          <button
            type="submit"
            disabled={!name.trim() || !url.trim() || createSource.isPending}
            className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-40"
          >
            Add
          </button>
        </form>
        {createSource.isError && (
          <p className="mt-2 text-sm text-red-600">Could not add the source.</p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Sources
        </h2>
        {sources.isPending && <p>Loading…</p>}
        {sources.isError && <p className="text-red-600">Failed to load sources</p>}
        {sources.data && sources.data.length === 0 && (
          <p className="text-slate-500">No feed sources yet. Add the first one above.</p>
        )}
        {sources.data && sources.data.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {sources.data.map((source) => (
              <li key={source.id} className="flex items-center gap-3 py-2">
                <div className="flex-1">
                  <span className="font-medium">{source.name}</span>
                  <span className="ml-2 rounded-full border border-slate-300 px-2 py-0.5 text-xs text-slate-500">
                    {source.kind}
                  </span>
                  <span className="ml-2 break-all text-slate-500">{source.url}</span>
                </div>
                <button
                  className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:border-slate-400"
                  onClick={() =>
                    toggleSource.mutate({ id: source.id, enabled: !source.enabled })
                  }
                  disabled={toggleSource.isPending}
                >
                  {source.enabled ? "Disable" : "Enable"}
                </button>
                {confirmingId === source.id ? (
                  <span className="flex items-center gap-2">
                    <button
                      className="rounded bg-red-600 px-3 py-1 text-sm text-white"
                      onClick={() => deleteSource.mutate(source.id)}
                      disabled={deleteSource.isPending}
                    >
                      Confirm delete
                    </button>
                    <button
                      className="rounded border border-slate-300 px-3 py-1 text-sm"
                      onClick={() => setConfirmingId(null)}
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:border-red-400 hover:text-red-600"
                    onClick={() => setConfirmingId(source.id)}
                  >
                    Delete
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
