import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

export default function HomePage() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const stats = useQuery({ queryKey: ["dashboard-stats"], queryFn: api.dashboard.stats });
  const activity = useQuery({
    queryKey: ["dashboard-activity"],
    queryFn: () => api.dashboard.activity(20),
  });

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-500">
        API status:{" "}
        {health.isPending && "checking…"}
        {health.isError && <span className="text-red-600">unreachable</span>}
        {health.data && (
          <span className="text-green-700">
            {health.data.status} (v{health.data.version})
          </span>
        )}
      </p>

      {stats.isError && <p className="text-red-600">Failed to load dashboard stats</p>}
      {stats.data && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="Projects" value={stats.data.projects} />
            <StatCard label="Issues" value={stats.data.issues_total} />
            <StatCard label="Overdue" value={stats.data.overdue} />
            <StatCard label="Events (7d)" value={stats.data.activity_last_7_days} />
          </div>

          {Object.keys(stats.data.issues_by_status).length > 0 && (
            <section className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
                Issues by status
              </h2>
              <div className="flex flex-wrap gap-2">
                {Object.entries(stats.data.issues_by_status).map(([status, count]) => (
                  <span
                    key={status}
                    className="rounded-full border border-slate-300 px-3 py-1 text-sm"
                  >
                    {status.replace("_", " ")}: <strong>{count}</strong>
                  </span>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
          Recent activity
        </h2>
        {activity.isPending && <p>Loading…</p>}
        {activity.isError && <p className="text-red-600">Failed to load activity</p>}
        {activity.data && activity.data.length === 0 && (
          <p className="text-slate-500">Nothing has happened yet.</p>
        )}
        {activity.data && activity.data.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {activity.data.map((event) => (
              <li key={event.id} className="flex items-baseline gap-3 py-2">
                <span className="flex-1 text-sm">{event.message}</span>
                <time
                  className="whitespace-nowrap text-xs text-slate-500"
                  dateTime={event.created_at}
                >
                  {new Date(event.created_at).toLocaleString()}
                </time>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
