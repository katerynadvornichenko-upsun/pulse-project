# Upsun Cloud performance agent

The performance agent runs as an Upsun Cloud task, declared under the
top-level `tasks` key in `.upsun/config.yaml`. Use this runbook to set it up
and run it against Pulse.

## 1. What it is

The agent combines profiling data, traffic, and the source code into a report
of the top bottlenecks, each with a suggested diff. It needs no local
install; the only credential is an LLM provider API key.

Upstream docs:
https://developer.upsun.com/docs/get-started/ai/upsun-cloud-performance-agent

## 2. One-time key setup (project admin)

A project admin creates the API key as a sensitive project variable. This
happens outside the repo:

```sh
upsun variable:create -p <project-id> --level project --name env:ANTHROPIC_API_KEY \
    --value "<key>" --sensitive true --visible-runtime true
```

Never commit the key, and never pass it inline in a task run's variables.
If a run fails because the credential is missing, this step has not been
done yet.

## 3. Running from the Console

1. Open the environment overview in the Upsun Console.
2. On the Tasks card, pick `performance-agent`.
3. Set `AGENT_APPLICATION` to `api` or `queue` (see section 5) and start the
   run.

## 4. Running from the CLI

For the `api` app:

```sh
upsun e:curl -p <project-id> -e <env> -X POST /tasks/performance-agent/run \
  --json '{"variables":{"env":{"AGENT_APPLICATION":"api"}}}'
```

For the `queue` worker:

```sh
upsun e:curl -p <project-id> -e <env> -X POST /tasks/performance-agent/run \
  --json '{"variables":{"env":{"AGENT_APPLICATION":"queue"}}}'
```

## 5. Targets

Run the agent against `api` and `queue` only. The `web` app is a static
build, so the agent has nothing useful to profile there.

## 6. Cost guard

`MAX_BUDGET_USD` defaults to 5 USD per run. To change it, pass it in the same
`variables.env` object:

```sh
upsun e:curl -p <project-id> -e <env> -X POST /tasks/performance-agent/run \
  --json '{"variables":{"env":{"AGENT_APPLICATION":"api","MAX_BUDGET_USD":"10"}}}'
```

## 7. Profiling limit

Without the continuous profiling add-on, the agent only sees the last 15
minutes of data. A thin report usually means low recent traffic, not a broken
setup. Generate traffic against the target first, or enable the add-on.
