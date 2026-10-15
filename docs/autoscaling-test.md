# Load testing the database

How to put load on the `postgresql` service and observe how it behaves. Two
ways to do that, in increasing order of directness.

## Before you start

1. Deploy the dashboard endpoint (`GET /api/dashboard/stats`): it runs
   whole-table aggregate queries, so it's the cheapest route to push the
   database's CPU from the app.
2. Note the current resources of the `postgresql` service
   (`upsun resources:get`) so you can compare before and after, and restore
   them if you change anything during the test.

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

Raise `--concurrency` (or run the script from two terminals) if the database
CPU stays low. Note the ceiling on this approach: the api container may
saturate before the database does, since each request costs the app more
than the query costs the database. If the api hits 100% CPU while the
database idles, use option B or grow api resources first.

## Option B: SQL load directly on the database

Bypasses the app entirely; the cheapest way to pin the database's CPU.

```sh
upsun tunnel:single --relationship postgresql --port 30001
```

Then, in a few parallel terminals (each session burns one CPU core with
generate_series, no tables or writes involved):

```sh
psql "postgresql://<user>:<password>@127.0.0.1:30001/main" -c \
  "SELECT count(*) FROM generate_series(1, 200000000);"
```

Credentials come from `upsun relationships` (the `postgresql` entry). You can
also run `scripts/db_burn.py` inside the api container, which does the same
thing without a tunnel. For a more realistic profile, run pgbench in
select-only mode: initialize it through the tunnel (`pgbench -i -s 50 ...`),
then run `pgbench -S -c 20 -T 600` against it. Memory pressure is easiest to
provoke with a large sort: `SELECT * FROM generate_series(1, 5e7)
ORDER BY random() LIMIT 10;` with `work_mem`-heavy settings.

## Watching it

- Console → environment → Configure resources shows the current resources
  of `postgresql`, and Metrics shows its CPU/RAM against time.
- `upsun resources:get` prints per-service resources from the CLI.
- `upsun activity:list --limit 10` and `upsun activity:log <id>` show any
  resource-update activities.

If the database stays pinned under realistic load, grow its resources with
`upsun resources:set`.

## Cleanup

- Stop the load (Ctrl+C, close tunnels).
- Loadtest data is identifiable: projects are named `loadtest-*`. Delete
  them via `DELETE /api/projects/{id}` (cascades to their issues), or leave
  them as dashboard fodder.
- If you changed resources for the test, restore them.
