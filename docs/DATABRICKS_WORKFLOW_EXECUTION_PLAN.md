# Plan: Databricks Workflow Code Execution for Deep Agent

## Context

Today the Deep Agent framework can *generate* a codebase (via the `senior-developer` subagent → `write_project_file` → Unity Catalog Volume) but cannot *run* what it just wrote. The goal is to close that loop: after the agent generates a project, it can execute it on Databricks compute via the Databricks Python SDK and report results back into the conversation.

We add a thin "execute on Databricks" capability — three new tools wrapping `WorkspaceClient.jobs` — registered into the orchestrator and the senior-developer subagent, plus a small skill update telling the agent when to use them. No new external dependencies (`databricks-sdk` is already in `pyproject.toml:25`).

The generated project files already live at `/Volumes/aia_multi_agent_catalog/default/agent_projects/<slug>/...`. We submit one-time job runs that point at those Volume paths via `jobs.submit()` (Jobs Submit API → `SubmitRun`), poll with `jobs.get_run()`, and pull stdout via `jobs.get_run_output()`. Using `jobs.submit()` (one-time runs, no persisted job definition) keeps the workspace clean and avoids needing CRUD permissions on Jobs.

## Files to modify

### 1. New file — `app/backend/src/deep_agent/tools/workflows.py`

Three tools, all using the existing `get_workspace_client()` singleton from `app/backend/src/deep_agent/clients.py:9`:

- **`run_project_on_databricks(project_name: str, entry_file: str = "main.py", libraries: list[str] | None = None) -> str`**
  - Slugify `project_name` (duplicate the 4-line `_slugify` from `tools/projects.py:11` — duplication is acceptable here vs. introducing a shared module).
  - Build `python_file = f"{VOLUME_BASE}/{slug}/{entry_file}"`.
  - Call `WorkspaceClient().jobs.submit(run_name=f"deep-agent-{slug}", tasks=[...])` with a single task using:
    - `task_key="run"`,
    - `spark_python_task=jobs.SparkPythonTask(python_file=python_file)`,
    - compute: prefer **serverless** when `WORKFLOW_USE_SERVERLESS=true` (default) by setting an `environment_key` on the task and an `environments=[JobEnvironment(...)]` entry on the submit call; otherwise fall back to `existing_cluster_id=WORKFLOW_CLUSTER_ID`.
    - Optional `libraries=[compute.Library(pypi=compute.PythonPyPiLibrary(package=p)) for p in libraries]` when the caller passes any.
  - Persist the returned `run_id` into `runtime.threads` (`runtime.py:68`) under a `"workflow_runs"` dict so it survives across turns in the same thread (it does not survive process restart — this matches the existing thread-registry contract documented at `runtime.py:67`).
  - Return a string with `run_id`, the run page URL (`f"{DATABRICKS_HOST}/jobs/runs/{run_id}"`), and a hint to call `check_workflow_run`.

- **`check_workflow_run(run_id: int) -> str`**
  - `run = WorkspaceClient().jobs.get_run(run_id=run_id)`.
  - Return `life_cycle_state`, `result_state`, `state_message`, start/end time, and the run URL. Keep output compact (≤10 lines) so it doesn't blow up the agent context.

- **`get_workflow_run_output(run_id: int) -> str`**
  - Fetch the parent run, locate the single task's task-level `run_id`.
  - `out = WorkspaceClient().jobs.get_run_output(run_id=task_run_id)`.
  - Return stdout (truncated to ~4000 chars), `error` if present, and `error_trace` if present. Surface truncation explicitly so the agent knows to fetch more if needed.

All three tools are plain Python functions with docstrings — same convention as `tools/projects.py`. deepagents picks up the docstring as the tool description; the docstring **is** the contract the LLM sees.

### 2. `app/backend/src/deep_agent/config.py`

Append a new `# ============ Workflows ============` section after the Databricks block (around line 30):

```python
WORKFLOW_USE_SERVERLESS = os.environ.get("WORKFLOW_USE_SERVERLESS", "true").lower() == "true"
WORKFLOW_CLUSTER_ID = os.environ.get("WORKFLOW_CLUSTER_ID", "")
WORKFLOW_ENVIRONMENT_SPEC_VERSION = os.environ.get("WORKFLOW_ENVIRONMENT_SPEC_VERSION", "2")
WORKFLOW_DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("WORKFLOW_DEFAULT_TIMEOUT_SECONDS", "1800"))
```

### 3. `app/backend/src/deep_agent/agent/builder.py`

- Add import (line 17–21 block): `from deep_agent.tools.workflows import check_workflow_run, get_workflow_run_output, run_project_on_databricks`.
- Append the three new tools to `ORCHESTRATOR_TOOLS` (`builder.py:25-37`) immediately after `list_project_files` so workflow tools cluster with project tools.

### 4. `app/backend/src/deep_agent/agent/subagents.py`

- Add the same import.
- Extend `senior_developer["tools"]` (`subagents.py:37`) to include the three new tools. Keep the other subagents unchanged — only senior-developer should execute code.

### 5. `skills/senior-developer/SKILL.md`

Insert a new step **8.5 (Optional Execute)** between current steps 8 (Deliver) and the Guidelines section (`SKILL.md:34-39`):

> **8.5 Run it (when applicable).** If the user asked to *execute*, *run*, *test*, or *try* the project — or the project is a standalone script with a clear entry point — call `run_project_on_databricks(project_slug, entry_file)`. Then poll `check_workflow_run(run_id)` until the run reaches a terminal state (`TERMINATED`, `INTERNAL_ERROR`, `SKIPPED`). On success, call `get_workflow_run_output(run_id)` and report stdout + result_state to the user. On failure, surface the error and offer to fix and re-run. Do **not** run the project unsolicited if it requires inputs the user hasn't provided.

This keeps execution opt-in via user intent and prevents surprise compute spend.

## Reused functions / paths

- `get_workspace_client()` — `app/backend/src/deep_agent/clients.py:9` (same auth as existing Volume writes; nothing new needed).
- `_slugify()` — `tools/projects.py:11` (duplicate the 4-line helper into `tools/workflows.py`).
- `VOLUME_BASE` — `config.py:27` (already points at the project artifact root).
- `runtime.threads` — `runtime.py:68` (existing in-memory thread-keyed state; natural home for run_id tracking).

## Verification

End-to-end manual test on a running backend:

```bash
cd app/backend && uvicorn deep_agent.main:app --reload
```

In the chat UI, send: *"Build a Python project that prints the first 10 Fibonacci numbers and then run it on Databricks."*

Expected sequence:
1. `name_project("fibonacci")` + `write_project_file(...)` for `main.py` and `README.md`.
2. `run_project_on_databricks("fibonacci", "main.py")` → returns a run_id and URL.
3. `check_workflow_run(run_id)` → eventually `TERMINATED / SUCCESS`.
4. `get_workflow_run_output(run_id)` → stdout containing the 10 Fibonacci numbers.
5. Agent reports the output back in chat.

Sanity checks:
- Open the run URL in the Databricks workspace — confirm the run appears under Workflows → Job runs.
- Set `WORKFLOW_USE_SERVERLESS=false` and `WORKFLOW_CLUSTER_ID=<an existing cluster>` and rerun to confirm the cluster path works.
- Failure path: write a project that raises (e.g., `raise ValueError("boom")`), run it, confirm `get_workflow_run_output` surfaces the traceback cleanly.

Negative checks:
- Calling `run_project_on_databricks` on a non-existent slug should return a clean error from the Jobs API (file not found in Volume) — confirm the tool's `try/except` produces a readable message rather than a stack trace into the chat.

## Out of scope (deliberately)

- Persistent jobs (CRUD via `jobs.create`) — `jobs.submit` (one-time runs) is sufficient and avoids permission complexity.
- Notebook tasks — `spark_python_task` covers current code-gen output (plain `.py` files in a Volume). Add a sibling tool later if the agent starts generating notebooks.
- Multi-task workflows / DAGs — single-task runs only for v1. The `tasks=[...]` shape leaves room to extend without API changes.
- Streaming logs back to the chat — `get_workflow_run_output` after termination is the v1 contract; live streaming would need a separate SSE channel in `api/chat.py`.
- Persisting `run_id` across process restarts — current `runtime.threads` is intentionally in-memory; matches the existing contract at `runtime.py:67`.
