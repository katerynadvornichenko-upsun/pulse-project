# Load testing the database

How to put load on the `postgresql` service and observe how it behaves. Two
ways to do that, in increasing order of directness.

## Before you start

> **Run this on a preview environment, never on `main`.** Every option below
> loads the one `postgresql` service, which holds the live data. Each Upsun
> branch gets its own copy of the database, so create a throwaway branch for
> the test (`upsun branch load-test`) and delete it afterwards. A test that fills the disk or pins the CPU there costs nothing;
> on `main` it stops writes for the whole app.

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

Bypasses the app entirely; the cheapest way to pin the database's CPU. On
the preview environment (see the warning above), the simplest route needs no
tunnel:

```sh
upsun ssh --app api '.venv/bin/python - 4 600 DATABASE_URL' < scripts/db_burn.py
```

That runs 4 workers for 10 minutes. To do the same by hand, open a tunnel:

```sh
upsun tunnel:single --relationship postgresql --port 30001
```

Then, in a few parallel terminals, run the same query `scripts/db_burn.py`
uses (each session pins roughly one CPU core):

```sh
psql "postgresql://<user>:<password>@127.0.0.1:30001/main" -c \
  "SELECT count(*) FROM generate_series(1, 10000) a CROSS JOIN generate_series(1, 10000) b;"
```

Credentials come from `upsun relationships` (the `postgresql` entry).

Don't swap in a single large series such as
`SELECT count(*) FROM generate_series(1, 200000000)`, or a big sort such as
`ORDER BY random()` over millions of rows. Both materialize their rows and
spill gigabytes of temporary files into the database's disk (`pgsql_tmp`).
On a small disk that ends in `DiskFull`, and because this is the primary,
writes fail for the whole environment until the files are cleaned up. The
cross join above keeps each side at 10,000 rows, so it uses CPU, not disk.

For a more realistic profile, use pgbench in select-only mode. Its setup
writes `pgbench_*` tables into the database, which is one more reason to use
a throwaway branch: initialize through the tunnel (`pgbench -i -s 50 ...`),
then run `pgbench -S -c 20 -T 600` against it.

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
- Delete the throwaway branch's environment
  (`upsun environment:delete load-test`). That also removes any `loadtest-*`
  data and `pgbench_*` tables with it.
- Loadtest data is identifiable: projects are named `loadtest-*`. Delete
  them via `DELETE /api/projects/{id}` (cascades to their issues), or leave
  them as dashboard fodder.
- If you changed resources for the test, restore them.
