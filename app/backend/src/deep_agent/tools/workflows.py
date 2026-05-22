"""Workflow tools — execute generated projects on Databricks via Jobs API.

Databricks job tasks cannot reference Python files that live in a Unity Catalog
Volume directly. Before submitting a run we copy every project file from
`{VOLUME_BASE}/<slug>/` to a workspace directory (`/Workspace/...`) and point
the SparkPythonTask at the workspace path with source=WORKSPACE.
"""

import re

from databricks.sdk.service import compute, jobs, workspace

from deep_agent.clients import get_workspace_client
from deep_agent.config import (
    DATABRICKS_HOST,
    VOLUME_BASE,
    WORKFLOW_CLUSTER_ID,
    WORKFLOW_DEFAULT_TIMEOUT_SECONDS,
    WORKFLOW_ENVIRONMENT_SPEC_VERSION,
    WORKFLOW_USE_SERVERLESS,
    WORKFLOW_WORKSPACE_BASE,
)
from deep_agent.runtime import threads


_OUTPUT_TRUNCATE_CHARS = 4000
_ENVIRONMENT_KEY = "default_env"
_PROJECT_MARKER = ".project"


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    return slug.strip("-")


def _run_url(run_id: int) -> str:
    host = DATABRICKS_HOST.rstrip("/")
    if not host:
        return f"(set DATABRICKS_HOST to see run URL) run_id={run_id}"
    return f"{host}/jobs/runs/{run_id}"


def _workspace_base_dir() -> str:
    """Return the workspace dir under which project folders are staged."""
    if WORKFLOW_WORKSPACE_BASE:
        return WORKFLOW_WORKSPACE_BASE.rstrip("/")
    me = get_workspace_client().current_user.me()
    user = me.user_name or "deep-agent"
    return f"/Workspace/Users/{user}/deep_agent_projects"


def _stage_volume_to_workspace(slug: str) -> tuple[str, list[str]]:
    """Copy all files from {VOLUME_BASE}/<slug>/ into the workspace.

    Returns (workspace_project_dir, copied_filenames).
    """
    ws = get_workspace_client()
    volume_dir = f"{VOLUME_BASE}/{slug}"
    workspace_dir = f"{_workspace_base_dir()}/{slug}"

    ws.workspace.mkdirs(workspace_dir)

    entries = list(ws.files.list_directory_contents(volume_dir + "/"))
    copied: list[str] = []
    for entry in entries:
        if entry.is_directory:
            continue
        name = entry.name
        if name == _PROJECT_MARKER:
            continue
        src = f"{volume_dir}/{name}"
        dst = f"{workspace_dir}/{name}"
        content = ws.files.download(src).contents.read()
        ws.workspace.upload(
            dst,
            content,
            format=workspace.ImportFormat.RAW,
            overwrite=True,
        )
        copied.append(name)
    return workspace_dir, copied


def _build_task(python_file: str, libraries: list[str] | None) -> jobs.SubmitTask:
    task_kwargs = {
        "task_key": "run",
        "spark_python_task": jobs.SparkPythonTask(
            python_file=python_file,
            source=jobs.Source.WORKSPACE,
        ),
        "timeout_seconds": WORKFLOW_DEFAULT_TIMEOUT_SECONDS,
    }
    if libraries:
        task_kwargs["libraries"] = [
            compute.Library(pypi=compute.PythonPyPiLibrary(package=p)) for p in libraries
        ]
    if WORKFLOW_USE_SERVERLESS:
        task_kwargs["environment_key"] = _ENVIRONMENT_KEY
    elif WORKFLOW_CLUSTER_ID:
        task_kwargs["existing_cluster_id"] = WORKFLOW_CLUSTER_ID
    else:
        raise RuntimeError(
            "No compute configured: set WORKFLOW_USE_SERVERLESS=true "
            "or WORKFLOW_CLUSTER_ID=<cluster-id>."
        )
    return jobs.SubmitTask(**task_kwargs)


def _build_environments() -> list[jobs.JobEnvironment] | None:
    if not WORKFLOW_USE_SERVERLESS:
        return None
    return [
        jobs.JobEnvironment(
            environment_key=_ENVIRONMENT_KEY,
            spec=compute.Environment(
                client=WORKFLOW_ENVIRONMENT_SPEC_VERSION,
            ),
        )
    ]


def run_project_on_databricks(
    project_name: str,
    entry_file: str = "main.py",
    libraries: list[str] | None = None,
    thread_id: str | None = None,
) -> str:
    """Submit a project to run as a Databricks workflow (one-time job run).

    Call this AFTER the project files have been written via write_project_file().
    All files in the project's Volume folder are first copied to a workspace
    directory (Databricks job tasks cannot reference Volume paths directly),
    then a one-time job run is submitted against the workspace entry file.
    Compute defaults to serverless; set WORKFLOW_USE_SERVERLESS=false and
    WORKFLOW_CLUSTER_ID=<id> to use an existing cluster instead.

    Args:
        project_name: The project slug (e.g., 'csv-parser-cli').
        entry_file: The Python file to execute (default: 'main.py').
        libraries: Optional list of PyPI package names to install before running.
        thread_id: Optional chat thread id; if provided the run_id is recorded
            in the in-memory thread registry for later reference.

    Returns:
        A multi-line string with the run_id, run URL, and next-step hint.
    """
    slug = _slugify(project_name)
    if not slug:
        return "Error: invalid project_name."

    try:
        workspace_dir, copied = _stage_volume_to_workspace(slug)
    except Exception as e:
        return f"Failed to copy {slug} from Volume to Workspace: {e}"

    if entry_file not in copied:
        return (
            f"Entry file '{entry_file}' not found in project '{slug}'. "
            f"Files copied to workspace: {copied or '(none)'}"
        )

    python_file = f"{workspace_dir}/{entry_file}"
    try:
        wait = get_workspace_client().jobs.submit(
            run_name=f"deep-agent-{slug}",
            tasks=[_build_task(python_file, libraries)],
            environments=_build_environments(),
        )
        run_id = wait.run_id
    except Exception as e:
        return f"Failed to submit workflow for {slug}: {e}"

    if thread_id:
        bucket = threads.setdefault(thread_id, {}).setdefault("workflow_runs", [])
        bucket.append({"run_id": run_id, "project": slug, "entry_file": entry_file})

    return (
        f"Submitted workflow run for '{slug}'.\n"
        f"  run_id:    {run_id}\n"
        f"  staged:    {workspace_dir} ({len(copied)} files: {', '.join(copied)})\n"
        f"  entry:     {python_file}\n"
        f"  url:       {_run_url(run_id)}\n"
        f"Call check_workflow_run({run_id}) to poll status; "
        f"call get_workflow_run_output({run_id}) once it terminates."
    )


def check_workflow_run(run_id: int) -> str:
    """Check the status of a Databricks workflow run.

    Returns a compact status summary. Poll this until life_cycle_state is one
    of: TERMINATED, INTERNAL_ERROR, SKIPPED.

    Args:
        run_id: The Databricks job run id returned by run_project_on_databricks.
    """
    try:
        run = get_workspace_client().jobs.get_run(run_id=run_id)
    except Exception as e:
        return f"Failed to fetch run {run_id}: {e}"

    state = run.state
    life = state.life_cycle_state.value if state and state.life_cycle_state else "UNKNOWN"
    result = state.result_state.value if state and state.result_state else "—"
    msg = (state.state_message or "").strip() if state else ""

    return (
        f"run_id: {run_id}\n"
        f"life_cycle_state: {life}\n"
        f"result_state:     {result}\n"
        f"state_message:    {msg or '—'}\n"
        f"start_time_ms:    {run.start_time or '—'}\n"
        f"end_time_ms:      {run.end_time or '—'}\n"
        f"url:              {_run_url(run_id)}"
    )


def get_workflow_run_output(run_id: int) -> str:
    """Fetch stdout + error output from a terminated Databricks workflow run.

    Call this only after check_workflow_run reports a terminal life_cycle_state
    (TERMINATED, INTERNAL_ERROR, or SKIPPED). Stdout is truncated to ~4000 chars.

    Args:
        run_id: The Databricks job run id returned by run_project_on_databricks.
    """
    ws = get_workspace_client()
    try:
        parent = ws.jobs.get_run(run_id=run_id)
    except Exception as e:
        return f"Failed to fetch run {run_id}: {e}"

    tasks = parent.tasks or []
    if not tasks:
        return f"Run {run_id} has no tasks (still pending?)."
    task_run_id = tasks[0].run_id
    if task_run_id is None:
        return f"Run {run_id} task has no run_id yet (still pending?)."

    try:
        out = ws.jobs.get_run_output(run_id=task_run_id)
    except Exception as e:
        return f"Failed to fetch output for run {run_id} (task {task_run_id}): {e}"

    logs = out.logs or ""
    truncated = ""
    if len(logs) > _OUTPUT_TRUNCATE_CHARS:
        logs = logs[-_OUTPUT_TRUNCATE_CHARS:]
        truncated = f"(stdout truncated to last {_OUTPUT_TRUNCATE_CHARS} chars)\n"

    parts = [f"run_id: {run_id} (task_run_id: {task_run_id})"]
    if out.error:
        parts.append(f"error: {out.error}")
    if out.error_trace:
        parts.append(f"error_trace:\n{out.error_trace}")
    parts.append(f"{truncated}stdout:\n{logs or '(empty)'}")
    return "\n".join(parts)
