# Testing replica autoscaling

How to trigger and observe horizontal autoscaling of the `postgresql-replica`
service. Autoscaling reacts to the replica's own CPU and/or RAM crossing the
thresholds you configure, so the load has to reach the replica, not the
primary. Two ways to do that, in increasing order of directness.

## Before you start

1. Deploy the dashboard endpoint (`GET /api/dashboard/stats`): it's the only
   route served from the replica (`ReadSessionDep`). Everything else reads
   from the primary and won't move the replica's metrics.
2. Enable autoscaling on the replica service: Console → your environment →
   Configure resources → `postgresql-replica` → set CPU and/or memory
   thresholds and the min/max replica count. Low thresholds make the test
   cheaper and faster to trigger.
3. Confirm the replica disk was sized to match the primary
   (`upsun resources:set`); it starts at 256MB.

## Option A: HTTP load through the app

Closest to real traffic: seed data, then run concurrent reads against the
dashboard endpoint.

```sh
cd apps/api
# once: create rows for the aggregates to scan
uv run python ../../scripts/loadtest.py --base-url https://<env-url> --seed 5000
# then: sustained read load (10 minutes, 50 concurrent clients)
uv run python ../../scripts/loadtest.py --base-url https://<env-url> \
    --concurrency 50 --duration 600
```

Raise `--concurrency` (or run the script from two terminals) if the replica
CPU stays under your threshold. Note the ceiling on this approach: the api
container may saturate before the replica does, since each request costs the
app more than the query costs the database. If the api hits 100% CPU while
the replica idles, use option B or grow api resources first.

## Option B: SQL load directly on the replica

Bypasses the app entirely; the cheapest way to pin the replica's CPU.

```sh
upsun tunnel:single --relationship postgresql-replica --port 30001
```

Then, in a few parallel terminals (each session burns one CPU core with
generate_series, no tables or writes involved):

```sh
psql "postgresql://<user>:<password>@127.0.0.1:30001/main" -c \
  "SELECT count(*) FROM generate_series(1, 200000000);"
```

Credentials come from `upsun relationships` (the `postgresql-replica` entry).
For a more realistic profile, run pgbench in select-only mode: initialize it
against the primary (`upsun tunnel:single --relationship postgresql`, then
`pgbench -i -s 50 ...`), wait for the tables to replicate, and point
`pgbench -S -c 20 -T 600` at the replica tunnel. RAM-triggered scaling is
easiest to provoke with a large sort: `SELECT * FROM generate_series(1, 5e7)
ORDER BY random() LIMIT 10;` with `work_mem`-heavy settings.

## Watching it scale

- Console → environment → Configure resources shows the current instance
  count of `postgresql-replica`, and Metrics shows its CPU/RAM against time.
- `upsun activity:list --limit 10` — scaling shows up as resource-update
  activities; `upsun activity:log <id>` for detail.
- `upsun resources:get` prints per-service instance counts from the CLI.

Expected sequence: replica CPU/RAM climbs past the threshold, an autoscaling
activity appears, the instance count increases with no redeployment, and
load per instance drops. After the load stops, watch for the scale-down
after the cooldown period.

## Cleanup

- Stop the load (Ctrl+C, close tunnels).
- Loadtest data is identifiable: projects are named `loadtest-*`. Delete
  them via `DELETE /api/projects/{id}` (cascades to their issues), or leave
  them as dashboard fodder.
- If you lowered autoscaling thresholds for the test, restore them.
