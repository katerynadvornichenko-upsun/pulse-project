# Feature slice template

Copy this folder to create a new slice. Steps (paths relative to the project root):

1. `cp -r apps/api/src/pulse/features/_template apps/api/src/pulse/features/<name>`
2. Rename `thing` to your entity everywhere in the copied files.
3. If the slice needs new tables/columns, add them to `apps/api/src/pulse/models.py`
   and create a migration (see AGENTS.md → Migrations).
4. Register the router in `apps/api/src/pulse/main.py`.
5. Rename `test_thing.py.tmpl` to `test_<name>.py` and write real tests.
6. Regenerate frontend types: `make gen-types`.

This folder is excluded from test collection (`conftest.py: collect_ignore_glob`).
