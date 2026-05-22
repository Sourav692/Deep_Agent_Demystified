"""Centralized configuration — all environment variables and derived paths."""

import os


# ============ Paths ============
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(PACKAGE_DIR))  # .../app/backend
APP_DIR = os.path.dirname(BACKEND_DIR)                        # .../app
REPO_ROOT = os.path.dirname(APP_DIR)                          # repo root

PROJECTS_DIR = os.path.join(BACKEND_DIR, "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

# Skills dir: deployed location first (alongside backend/), else repo-root /skills
_skills_deployed = os.path.join(APP_DIR, "skills")
_skills_repo = os.path.join(REPO_ROOT, "skills")
SKILLS_DIR = _skills_deployed if os.path.isdir(_skills_deployed) else _skills_repo

# Frontend build (served by the FastAPI app in prod)
FRONTEND_BUILD_DIR = os.path.join(APP_DIR, "frontend", "build")


# ============ Databricks ============
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
VOLUME_BASE = os.environ.get(
    "VOLUME_BASE", "/Volumes/aia_multi_agent_catalog/default/agent_projects"
)


# ============ Workflows (Databricks Jobs execution) ============
WORKFLOW_USE_SERVERLESS = os.environ.get("WORKFLOW_USE_SERVERLESS", "true").lower() == "true"
WORKFLOW_CLUSTER_ID = os.environ.get("WORKFLOW_CLUSTER_ID", "")
WORKFLOW_ENVIRONMENT_SPEC_VERSION = os.environ.get("WORKFLOW_ENVIRONMENT_SPEC_VERSION", "2")
WORKFLOW_DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("WORKFLOW_DEFAULT_TIMEOUT_SECONDS", "1800"))
# Workspace dir where Volume files are staged before submission. Empty = derive from current user.
WORKFLOW_WORKSPACE_BASE = os.environ.get("WORKFLOW_WORKSPACE_BASE", "")


# ============ Lakebase (Postgres long-term memory) ============
LAKEBASE_INSTANCE_NAME = os.environ.get("LAKEBASE_INSTANCE_NAME", "deep-agent-memory")
LAKEBASE_DATABASE = os.environ.get("LAKEBASE_DATABASE", "databricks_postgres")
LAKEBASE_SCHEMA = "public"
LAKEBASE_TABLE = "agent_memories"


# ============ Model ============
MODEL_ENDPOINT = os.environ.get("MODEL_ENDPOINT", "databricks-claude-sonnet-4-6")
MODEL_TEMPERATURE = float(os.environ.get("MODEL_TEMPERATURE", "0.1"))


# ============ Tools ============
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
USE_SANDBOX = os.environ.get("USE_SANDBOX", "false").lower() == "true"

GENIE_SPACES = {
    "customer_analytics": "01f1272d4de1188cac8feeb7e71bdb69",
    "distribution_channels": "01f1272d4d271203ad122e9280470248",
    "policy_underwriting": "01f1272d4c6b1fb49223785ab841befd",
    "claims_analytics": "01f1272d4ba6144ba75d868762f1925d",
}
