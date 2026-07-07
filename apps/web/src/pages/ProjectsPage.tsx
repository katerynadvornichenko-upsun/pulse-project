import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../lib/api";

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects.list });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["projects"] });

  const createProject = useMutation({
    mutationFn: api.projects.create,
    onSuccess: () => {
      setName("");
      setDescription("");
      invalidate();
    },
  });

  const deleteProject = useMutation({
    mutationFn: api.projects.delete,
    onSuccess: () => {
      setConfirmingId(null);
      invalidate();
    },
  });

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          New project
        </h2>
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) {
              createProject.mutate({ name: name.trim(), description });
            }
          }}
        >
          <input
            className="rounded border border-slate-300 px-3 py-2 sm:w-56"
            placeholder="Name"
            aria-label="Project name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <input
            className="flex-1 rounded border border-slate-300 px-3 py-2"
            placeholder="Description (optional)"
            aria-label="Project description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <button
            type="submit"
            disabled={!name.trim() || createProject.isPending}
            className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-40"
          >
            Create
          </button>
        </form>
        {createProject.isError && (
          <p className="mt-2 text-sm text-red-600">Could not create the project.</p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Projects
        </h2>
        {projects.isPending && <p>Loading…</p>}
        {projects.isError && <p className="text-red-600">Failed to load projects</p>}
        {projects.data && projects.data.length === 0 && (
          <p className="text-slate-500">No projects yet. Create the first one above.</p>
        )}
        {projects.data && projects.data.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {projects.data.map((project) => (
              <li key={project.id} className="flex items-center gap-3 py-2">
                <div className="flex-1">
                  <span className="font-medium">{project.name}</span>
                  {project.description && (
                    <span className="ml-2 text-slate-500">{project.description}</span>
                  )}
                </div>
                {confirmingId === project.id ? (
                  <span className="flex items-center gap-2">
                    <button
                      className="rounded bg-red-600 px-3 py-1 text-sm text-white"
                      onClick={() => deleteProject.mutate(project.id)}
                      disabled={deleteProject.isPending}
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
                    onClick={() => setConfirmingId(project.id)}
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
