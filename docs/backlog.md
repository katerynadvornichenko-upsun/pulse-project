# Phase 2 backlog

Each section below is one GitHub issue, sized for a single dispatched workflow
and a single PR with its own preview environment. Copy them as-is, or create
them with `gh issue create --title "..." --body-file <(...)`. Suggested labels:
`slice`, `backend` or `frontend`, and `dispatch-ready` once dependencies are
merged.

The dependency order is 1 → 2 → 3 for the backend, and 4 → 5 for the frontend.
Issue 4 only needs issue 1 merged.

---

## 1. Issues CRUD slice

**Labels:** slice, backend, dispatch-ready

The `Issue` model already exists in `apps/api/src/pulse/models.py` with
status, priority, due date, and a project foreign key. There is no API for it
yet. Add an `issues` feature slice following the conventions in `AGENTS.md`
and the reference implementation in `apps/api/src/pulse/features/projects/`.

Scope:

- Copy `apps/api/src/pulse/features/_template` to
  `apps/api/src/pulse/features/issues`.
- Endpoints: `GET /api/issues`, `POST /api/issues`, `GET /api/issues/{id}`,
  `PATCH /api/issues/{id}`, `DELETE /api/issues/{id}`.
- `GET /api/issues` accepts optional `project_id`, `status`, and `priority`
  query parameters as filters, combinable.
- Creating an issue against a nonexistent project returns 404, using
  `NotFoundError`.
- Every create, update, and delete records an `ActivityEvent`.
- Run `make gen-types` and commit the regenerated
  `apps/web/src/lib/api-types.gen.ts`.

Out of scope: labels on issues (issue 3), any frontend (issue 5).

No schema change is needed, so no migration.

Acceptance: both test suites green; slice tests cover the happy path, 404 on
missing issue and missing project, each filter, one validation failure (422),
and the ActivityEvent on create.

---

## 2. Issue status workflow

**Labels:** slice, backend

Depends on issue 1. Status changes are currently just field updates. Make
them explicit and auditable.

Scope:

- Add `POST /api/issues/{id}/status` accepting `{"status": "<value>"}`.
  Reject unknown values with 422 (Zod-equivalent: the `IssueStatus` enum
  already constrains this via the Pydantic schema).
- Moving to `done` or `cancelled` sets a new `closed_at` timestamp on the
  issue; moving back to an open status clears it. This needs a column on
  `Issue`, so follow the migration workflow in `AGENTS.md`.
- The `ActivityEvent` message records the old and new status, for example
  "Issue 'Fix login' moved from todo to in_progress".
- Remove `status` from the fields `PATCH /api/issues/{id}` accepts, so the
  status endpoint is the only way to change it.
- Run `make gen-types` and commit the result.

Acceptance: migration applies with `alembic upgrade head`; tests cover the
closed_at set/clear behavior, the 422 case, and the ActivityEvent message
content.

---

## 3. Labels slice

**Labels:** slice, backend

Depends on issue 1. `Label` and the `IssueLabel` link table already exist in
`apps/api/src/pulse/models.py`.

Scope:

- New `labels` feature slice with `GET /api/labels`, `POST /api/labels`,
  `PATCH /api/labels/{id}`, `DELETE /api/labels/{id}`. Label names are
  unique; creating a duplicate returns 409.
- `PUT /api/issues/{id}/labels` replaces the set of labels on an issue,
  accepting `{"label_ids": [...]}`. Unknown label ids return 404.
- Include labels in the issue read schema so `GET /api/issues` and
  `GET /api/issues/{id}` return them.
- `GET /api/issues` gains a `label` query filter (single label id).
- ActivityEvent on label create/delete and on label-set changes.
- Run `make gen-types` and commit the result.

No schema change is needed, so no migration.

Acceptance: tests cover uniqueness conflict, label replacement including the
empty list, the 404 case, and the filter.

---

## 4. Frontend: projects page

**Labels:** slice, frontend

Depends on issue 1 being merged only because it regenerates the shared types;
the endpoints used here already exist.

Scope:

- Replace the placeholder projects section on
  `apps/web/src/pages/HomePage.tsx` with a `/projects` route and page:
  list projects, create via a small form (name, description), delete with a
  confirmation step.
- Use TanStack Query mutations with invalidation; no manual refetching.
- Keep API access inside `apps/web/src/lib/api.ts`; components never call
  `fetch` directly.
- Navigation link in the header.

Acceptance: `npm run lint`, `npm run typecheck`, `npm test` green; a Vitest
test renders the page with stubbed fetch and exercises create and delete.

---

## 5. Frontend: issues list and detail

**Labels:** slice, frontend

Depends on issues 1 and 4 (and picks up labels display once issue 3 merges,
but do not block on it).

Scope:

- `/projects/:id` page showing the project's issues with status and priority
  badges, plus a create-issue form (title, priority, optional due date).
- Status and priority filters backed by the query parameters from issue 1.
- An issue row expands to a detail view allowing edit of title/description
  and deletion.
- Extend `apps/web/src/lib/api.ts` with the issue endpoints, typed from the
  generated file.

Acceptance: lint, typecheck, and tests green; tests cover rendering a list,
applying a filter, and creating an issue, all with stubbed fetch.
