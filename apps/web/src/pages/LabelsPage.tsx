import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, isConflict, type Label, type LabelUpdate } from "../lib/api";

const DEFAULT_COLOR = "#808080";
const DUPLICATE_MESSAGE = "A label with that name already exists";

export default function LabelsPage() {
  const queryClient = useQueryClient();
  const labels = useQuery({ queryKey: ["labels"], queryFn: api.labels.list });

  const [name, setName] = useState("");
  const [color, setColor] = useState(DEFAULT_COLOR);

  const createLabel = useMutation({
    mutationFn: api.labels.create,
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["labels"] });
    },
  });

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          New label
        </h2>
        <form
          className="flex flex-col gap-2 sm:flex-row sm:items-center"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) {
              createLabel.mutate({ name: name.trim(), color });
            }
          }}
        >
          <input
            className="flex-1 rounded border border-slate-300 px-3 py-2"
            placeholder="Name"
            aria-label="Label name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <input
            type="color"
            className="h-10 w-14 rounded border border-slate-300"
            aria-label="Label colour"
            value={color}
            onChange={(event) => setColor(event.target.value)}
          />
          <button
            type="submit"
            disabled={!name.trim() || createLabel.isPending}
            className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-40"
          >
            Create
          </button>
        </form>
        {createLabel.isError && (
          <p className="mt-2 text-sm text-red-600">
            {isConflict(createLabel.error)
              ? DUPLICATE_MESSAGE
              : "Could not create the label."}
          </p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Labels
        </h2>
        {labels.isPending && <p>Loading…</p>}
        {labels.isError && <p className="text-red-600">Failed to load labels</p>}
        {labels.data && labels.data.length === 0 && (
          <p className="text-slate-500">No labels yet. Create the first one above.</p>
        )}
        {labels.data && labels.data.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {labels.data.map((label) => (
              <LabelRow key={label.id} label={label} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function LabelRow({ label }: { label: Label }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState(label.name);
  const [draftColor, setDraftColor] = useState(label.color);
  const [confirming, setConfirming] = useState(false);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["labels"] });
    // Issues embed their labels, so a rename or delete changes those too.
    queryClient.invalidateQueries({ queryKey: ["issues"] });
  };

  const updateLabel = useMutation({
    mutationFn: (data: LabelUpdate) => api.labels.update(label.id, data),
    onSuccess: () => {
      setEditing(false);
      invalidate();
    },
  });

  const deleteLabel = useMutation({
    mutationFn: () => api.labels.delete(label.id),
    onSuccess: () => {
      setConfirming(false);
      invalidate();
    },
  });

  const startEditing = () => {
    setDraftName(label.name);
    setDraftColor(label.color);
    updateLabel.reset();
    setEditing(true);
  };

  const save = () => {
    const changes: LabelUpdate = {};
    const trimmed = draftName.trim();
    if (trimmed && trimmed !== label.name) changes.name = trimmed;
    if (draftColor.toLowerCase() !== label.color.toLowerCase()) {
      changes.color = draftColor;
    }
    if (Object.keys(changes).length === 0) {
      setEditing(false);
      return;
    }
    updateLabel.mutate(changes);
  };

  const error = (updateLabel.isError || deleteLabel.isError) && (
    <p className="mt-1 text-sm text-red-600">
      {isConflict(updateLabel.error)
        ? DUPLICATE_MESSAGE
        : "The last change failed. Try again."}
    </p>
  );

  if (editing) {
    return (
      <li className="py-2">
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <input
            className="flex-1 rounded border border-slate-300 px-3 py-1"
            aria-label="Edit label name"
            value={draftName}
            onChange={(event) => setDraftName(event.target.value)}
          />
          <input
            type="color"
            className="h-8 w-12 rounded border border-slate-300"
            aria-label="Edit label colour"
            value={draftColor}
            onChange={(event) => setDraftColor(event.target.value)}
          />
          <button
            type="submit"
            disabled={!draftName.trim() || updateLabel.isPending}
            className="rounded bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-40"
          >
            Save
          </button>
          <button
            type="button"
            className="rounded border border-slate-300 px-3 py-1 text-sm"
            onClick={() => {
              updateLabel.reset();
              setEditing(false);
            }}
          >
            Cancel
          </button>
        </form>
        {error}
      </li>
    );
  }

  return (
    <li className="py-2">
      <div className="flex items-center gap-3">
        <span
          data-testid={`label-swatch-${label.id}`}
          title={label.color}
          className="inline-block h-4 w-4 rounded-full border border-slate-200"
          style={{ backgroundColor: label.color }}
        />
        <span className="flex-1 font-medium">{label.name}</span>
        <button
          className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:text-slate-900"
          onClick={startEditing}
        >
          Edit
        </button>
        {confirming ? (
          <span className="flex items-center gap-2">
            <button
              className="rounded bg-red-600 px-3 py-1 text-sm text-white"
              onClick={() => deleteLabel.mutate()}
              disabled={deleteLabel.isPending}
            >
              Confirm delete
            </button>
            <button
              className="rounded border border-slate-300 px-3 py-1 text-sm"
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:border-red-400 hover:text-red-600"
            onClick={() => setConfirming(true)}
          >
            Delete
          </button>
        )}
      </div>
      {error}
    </li>
  );
}
