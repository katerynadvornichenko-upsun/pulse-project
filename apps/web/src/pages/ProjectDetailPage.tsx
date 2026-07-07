import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import type { Issue, IssuePriority, IssueStatus } from "../lib/api";
import { ISSUE_PRIORITIES, ISSUE_STATUSES, api } from "../lib/api";

const STATUS_STYLES: Record<IssueStatus, string> = {
  backlog: "bg-slate-100 text-slate-700",
  todo: "bg-blue-100 text-blue-800",
  in_progress: "bg-amber-100 text-amber-800",
  done: "bg-green-100 text-green-800",
  cancelled: "bg-slate-200 text-slate-500",
};

const PRIORITY_STYLES: Record<IssuePriority, string> = {
  low: "bg-slate-100 text-slate-600",
  medium: "bg-sky-100 text-sky-800",
  high: "bg-orange-100 text-orange-800",
  urgent: "bg-red-100 text-red-800",
};

function Badge({ label, className }: { label: string; className: string }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${className}`}>
      {label.replace("_", " ")}
    </span>
  );
}

function IssueDetail({ issue, projectId }: { issue: Issue; projectId: string }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(issue.title);
  const [description, setDescription] = useState(issue.description);
  const [confirming, setConfirming] = useState(false);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["issues", projectId] });

  const save = useMutation({
    mutationFn: () => api.issues.update(issue.id, { title: title.trim(), description }),
    onSuccess: invalidate,
  });
  const setStatus = useMutation({
    mutationFn: (status: IssueStatus) => api.issues.setStatus(issue.id, status),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: () => api.issues.delete(issue.id),
    onSuccess: invalidate,
  });

  return (
    <div className="mt-2 space-y-2 rounded border border-slate-200 bg-slate-50 p-3">
      <input
        className="w-full rounded border border-slate-300 px-3 py-2"
        aria-label="Issue title"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <textarea
        className="w-full rounded border border-slate-300 px-3 py-2"
        aria-label="Issue description"
        rows={3}
        placeholder="Description"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />
      <div className="flex flex-wrap items-center gap-2">
        <button
          className="rounded bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-40"
          disabled={!title.trim() || save.isPending}
          onClick={() => save.mutate()}
        >
          Save
        </button>
        <label className="ml-2 text-sm text-slate-500">
          Status{" "}
          <select
            className="rounded border border-slate-300 px-2 py-1 text-sm"
            value={issue.status}
            onChange={(event) => setStatus.mutate(event.target.value as IssueStatus)}
          >
            {ISSUE_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status.replace("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <span className="flex-1" />
        {confirming ? (
          <>
            <button
              className="rounded bg-red-600 px-3 py-1 text-sm text-white"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
            >
              Confirm delete
            </button>
            <button
              className="rounded border border-slate-300 px-3 py-1 text-sm"
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:border-red-400 hover:text-red-600"
            onClick={() => setConfirming(true)}
          >
            Delete
          </button>
        )}
      </div>
      {(save.isError || setStatus.isError || remove.isError) && (
        <p className="text-sm text-red-600">The last change failed. Try again.</p>
      )}
    </div>
  );
}

export default function ProjectDetailPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<IssueStatus | "">("");
  const [priorityFilter, setPriorityFilter] = useState<IssuePriority | "">("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<IssuePriority>("medium");
  const [dueDate, setDueDate] = useState("");

  const project = useQuery({
    queryKey: ["project", id],
    queryFn: () => api.projects.get(id),
  });
  const issues = useQuery({
    queryKey: ["issues", id, statusFilter, priorityFilter],
    queryFn: () =>
      api.issues.list({
        project_id: id,
        status: statusFilter || undefined,
        priority: priorityFilter || undefined,
      }),
  });

  const createIssue = useMutation({
    mutationFn: () =>
      api.issues.create({
        title: title.trim(),
        project_id: id,
        priority,
        due_date: dueDate ? `${dueDate}T00:00:00Z` : undefined,
      }),
    onSuccess: () => {
      setTitle("");
      setDueDate("");
      setPriority("medium");
      queryClient.invalidateQueries({ queryKey: ["issues", id] });
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-baseline gap-3">
        <Link to="/projects" className="text-sm text-slate-500 hover:text-slate-900">
          ← Projects
        </Link>
        <h2 className="text-lg font-semibold">
          {project.data?.name ?? (project.isPending ? "Loading…" : "Project")}
        </h2>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          New issue
        </h3>
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (title.trim()) createIssue.mutate();
          }}
        >
          <input
            className="flex-1 rounded border border-slate-300 px-3 py-2"
            placeholder="Title"
            aria-label="Issue title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <select
            className="rounded border border-slate-300 px-2 py-2"
            aria-label="Issue priority"
            value={priority}
            onChange={(event) => setPriority(event.target.value as IssuePriority)}
          >
            {ISSUE_PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <input
            type="date"
            className="rounded border border-slate-300 px-2 py-2"
            aria-label="Due date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
          />
          <button
            type="submit"
            disabled={!title.trim() || createIssue.isPending}
            className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-40"
          >
            Create
          </button>
        </form>
        {createIssue.isError && (
          <p className="mt-2 text-sm text-red-600">Could not create the issue.</p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h3 className="text-sm font-medium uppercase tracking-wide text-slate-500">
            Issues
          </h3>
          <span className="flex-1" />
          <select
            className="rounded border border-slate-300 px-2 py-1 text-sm"
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as IssueStatus | "")}
          >
            <option value="">All statuses</option>
            {ISSUE_STATUSES.map((value) => (
              <option key={value} value={value}>
                {value.replace("_", " ")}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-slate-300 px-2 py-1 text-sm"
            aria-label="Filter by priority"
            value={priorityFilter}
            onChange={(event) =>
              setPriorityFilter(event.target.value as IssuePriority | "")
            }
          >
            <option value="">All priorities</option>
            {ISSUE_PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>

        {issues.isPending && <p>Loading…</p>}
        {issues.isError && <p className="text-red-600">Failed to load issues</p>}
        {issues.data && issues.data.length === 0 && (
          <p className="text-slate-500">No issues match.</p>
        )}
        {issues.data && issues.data.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {issues.data.map((issue) => (
              <li key={issue.id} className="py-2">
                <button
                  className="flex w-full items-center gap-2 text-left"
                  onClick={() =>
                    setExpandedId(expandedId === issue.id ? null : issue.id)
                  }
                >
                  <span className="flex-1 font-medium">{issue.title}</span>
                  {issue.labels.map((label) => (
                    <span
                      key={label.id}
                      className="rounded-full border border-slate-300 px-2 py-0.5 text-xs"
                    >
                      {label.name}
                    </span>
                  ))}
                  {issue.due_date && (
                    <span className="text-xs text-slate-500">
                      due {issue.due_date.slice(0, 10)}
                    </span>
                  )}
                  <Badge label={issue.priority} className={PRIORITY_STYLES[issue.priority]} />
                  <Badge label={issue.status} className={STATUS_STYLES[issue.status]} />
                </button>
                {expandedId === issue.id && (
                  <IssueDetail issue={issue} projectId={id} />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
