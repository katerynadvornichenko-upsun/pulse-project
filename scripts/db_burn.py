"""CPU burn for autoscaling tests, run inside the api container over stdin:

    upsun ssh --app api '.venv/bin/python - 4 600 DATABASE_REPLICA_URL' < scripts/db_burn.py

Arguments: workers, duration in seconds, env var holding the database URL
(DATABASE_REPLICA_URL to heat the replica, DATABASE_URL for the primary).
Each worker loops a server-side generate_series count, pinning roughly one
core on the database. Read-only; creates no tables, writes nothing.
"""

import os
import sys
import threading
import time

import psycopg

workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 600
env_var = sys.argv[3] if len(sys.argv) > 3 else "DATABASE_REPLICA_URL"

url = os.environ[env_var]
deadline = time.time() + duration
print(f"burning {env_var} host with {workers} workers for {duration}s", flush=True)


# A single large generate_series would materialize its rows to a tuplestore
# and spill gigabytes into pgsql_tmp (DiskFull on small disks). The cross
# join keeps each materialized side at 10k rows (kilobytes) while the join
# streams 100M rows through count(*): pure CPU, no disk.
QUERY = """
SELECT count(*)
FROM generate_series(1, 10000) a
CROSS JOIN generate_series(1, 10000) b
"""


def burn() -> None:
    while time.time() < deadline:
        with psycopg.connect(url) as conn:
            conn.execute(QUERY)
        print(".", end="", flush=True)


threads = [threading.Thread(target=burn) for _ in range(workers)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print("\ndone")
