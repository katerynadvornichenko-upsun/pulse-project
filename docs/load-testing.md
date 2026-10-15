# Load testing the database

How to put load on the `postgresql` service and observe how it behaves. Two
ways to do that, in increasing order of directness.

## Before you start

> **Run this on a preview environment, never on `main`.** Every option below
> loads the one `postgresql` service, which holds the live data. A test that
> fills the disk or pins the CPU on a preview environment costs nothing; on
> `main` it stops writes for the whole app.

### 1. Create the throwaway environment through GitHub

This project uses Upsun's GitHub integration, so GitHub owns the
environments: `upsun branch` and `upsun environment:delete` are refused.
Create the environment by opening a pull request instead.

```sh
git switch -c load-test
git commit --allow-empty -m "Load test environment (do not merge)"
git push -u origin load-test
```

Then open a **draft** pull request from `load-test` on GitHub. Upsun builds
an environment for it named `pr-<number>`, with its own copy of the
database. Confirm it exists and is active:

```sh
upsun environment:list
```

### 2. Pin every command to that environment

Without `-e`, the CLI targets whatever environment it infers, which can be
`main`. Set the environment once and pass it to every `upsun` command below:

```sh
ENV=pr-<number>
```

### 3. Record the baseline

1. Deploy the dashboard endpoint (`GET /api/dashboard/stats`): it runs
   whole-table aggregate queries, so it's the cheapest route to push the
   database's CPU from the app.
2. Note the current resources of the `postgresql` service
   (`upsun resources:get -e "$ENV"`) so you can compare before and after,
   and restore them if you change anything during the test.

## Option A: HTTP load through the app

Closest to real traffic: seed data, then run concurrent reads against the
dashboard endpoint. Get the URL with `upsun environment:url -e "$ENV"`.

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

Bypasses the app entirely; the cheapest way to pin the database's CPU. The
simplest route needs no tunnel. Run it from the repository root (if you just
ran Option A, you're still in `apps/api`):

```sh
cd "$(git rev-parse --show-toplevel)"
upsun ssh -e "$ENV" --app api '.venv/bin/python - 4 600 DATABASE_URL' < scripts/db_burn.py
```

That runs 4 workers for 10 minutes. To do the same by hand, open a tunnel:

```sh
upsun tunnel:single -e "$ENV" --relationship postgresql --port 30001
```

Then, in a few parallel terminals, run the same query `scripts/db_burn.py`
uses (each session pins roughly one CPU core):

```sh
psql "postgresql://<user>:<password>@127.0.0.1:30001/main" -c \
  "SELECT count(*) FROM generate_series(1, 10000) a CROSS JOIN generate_series(1, 10000) b;"
```

Credentials come from `upsun relationships -e "$ENV"` (the `postgresql`
entry).

Don't swap in a single large series such as
`SELECT count(*) FROM generate_series(1, 200000000)`, or a big sort such as
`ORDER BY random()` over millions of rows. Both materialize their rows and
spill gigabytes of temporary files into the database's disk (`pgsql_tmp`).
On a small disk that ends in `DiskFull`, and writes then fail for the whole
environment until the files are cleaned up. The cross join above keeps each
side at 10,000 rows, so it uses CPU, not disk.

For a more realistic profile, use pgbench in select-only mode. Its setup
writes `pgbench_*` tables into the database, which is one more reason to use
a throwaway environment: initialize through the tunnel (`pgbench -i -s 50 ...`),
then run `pgbench -S -c 20 -T 600` against it.

## Watching it

- Console → the `pr-<number>` environment → Configure resources shows the
  current resources of `postgresql`, and Metrics shows its CPU/RAM against
  time.
- `upsun resources:get -e "$ENV"` prints per-service resources from the CLI.
- `upsun activity:list -e "$ENV" --limit 10` and
  `upsun activity:log -e "$ENV" <id>` show any resource-update activities.

If the database stays pinned under realistic load, grow its resources with
`upsun resources:set -e "$ENV"`, then carry the numbers over to production
deliberately.

## Cleanup

- Stop the load (Ctrl+C, close tunnels).
- Close the draft pull request on GitHub and delete the `load-test` branch
  there. The integration then removes the `pr-<number>` environment, and with
  it any `loadtest-*` data and `pgbench_*` tables.
- Locally: `git switch main && git branch -D load-test`.
