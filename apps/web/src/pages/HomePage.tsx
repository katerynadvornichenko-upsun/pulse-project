import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

export default function HomePage() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects.list });

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
          API status
        </h2>
        {health.isPending && <p>Checking…</p>}
        {health.isError && <p className="text-red-600">API unreachable</p>}
        {health.data && (
          <p className="text-green-700">
            {health.data.status} (v{health.data.version})
          </p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
          Projects
        </h2>
        {projects.isPending && <p>Loading…</p>}
        {projects.isError && <p className="text-red-600">Failed to load projects</p>}
        {projects.data && projects.data.length === 0 && (
          <p className="text-slate-500">No projects yet.</p>
        )}
        {projects.data && projects.data.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {projects.data.map((p) => (
              <li key={p.id} className="py-2">
                <span className="font-medium">{p.name}</span>
                {p.description && (
                  <span className="ml-2 text-slate-500">{p.description}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
