"""Deep agent with long-term memory, wired for the FastAPI backend.

Exposes a pre-built agent and memory tools that the API layer calls.
Memory tools use DatabricksSQLMemoryStore instead of JSON files.
"""

import os
import re
from typing import Literal

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend, LocalShellBackend
from langgraph.checkpoint.memory import MemorySaver
from databricks_langchain import ChatDatabricks
from tavily import TavilyClient
from databricks.sdk import WorkspaceClient

try:
    from backend.memory_store import DatabricksSQLMemoryStore, DEFAULT_USER_ID
except ImportError:
    from memory_store import DatabricksSQLMemoryStore, DEFAULT_USER_ID


# ============ Directories ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
VOLUME_BASE = "/Volumes/aia_multi_agent_catalog/default/agent_projects"
# Skills dir: check deployed location (one level up) first, then local dev (two levels up)
_app_root = os.path.dirname(BASE_DIR)
_skills_deployed = os.path.join(_app_root, "skills")
_skills_local = os.path.join(os.path.dirname(_app_root), "skills")
SKILLS_DIR = _skills_deployed if os.path.isdir(_skills_deployed) else _skills_local
USE_SANDBOX = os.environ.get("USE_SANDBOX", "false").lower() == "true"

os.makedirs(PROJECTS_DIR, exist_ok=True)


# ============ Memory store ============
memory_db = DatabricksSQLMemoryStore()


# ============ Memory tools (called by the LLM) ============

def save_memory(content: str, category: str = "general") -> str:
    """Save a piece of information to long-term memory for future recall.

    Use this tool when the user shares preferences, facts about themselves,
    important decisions, project context, or anything that should be
    remembered across conversations.

    Args:
        content: The information to remember. Be specific and concise.
        category: A short label to organize the memory (e.g., "preference",
                  "fact", "decision", "project", "feedback"). Defaults to "general".
    """
    result = memory_db.save(content, category)
    return f"Memory saved (category: {category}): {content}"


def recall_memories(query: str = "", category: str = "") -> str:
    """Search long-term memory for previously saved information.

    Use this tool at the start of conversations or when the user references
    something they told you before. Also use it proactively when context
    about the user's preferences, past decisions, or project details
    would improve your response.

    Args:
        query: A search term to find relevant memories. Leave empty to
               retrieve all memories.
        category: Optional category filter (e.g., "preference", "fact",
                  "decision"). Leave empty to search all categories.
    """
    rows = memory_db.recall(query, category)
    if not rows:
        filter_desc = f"category='{category}'" if category else f"'{query}'" if query else "any"
        return f"No memories matching {filter_desc} found."

    lines = []
    for r in rows:
        lines.append(f"- [{r['category']}] {r['content']} (saved: {r['saved_at']})")
    return f"Found {len(lines)} memories:\n" + "\n".join(lines)


def forget_memory(content_substring: str) -> str:
    """Remove a specific memory from long-term storage.

    Use this when the user explicitly asks you to forget something,
    or when stored information is no longer accurate.

    Args:
        content_substring: A substring that uniquely identifies the memory
                           to delete. The first matching memory will be removed.
    """
    result = memory_db.forget(content_substring)
    if result:
        return f"Memory deleted: {result['content']}"
    return f"No memory matching '{content_substring}' found."


# ============ Project tools (write to UC Volume via SDK) ============

import io

def name_project(project_name: str) -> str:
    """Create a project folder with the given name.

    Call this FIRST before writing any files. The name should be a short,
    descriptive, lowercase slug using hyphens (e.g., 'email-validator',
    'todo-api', 'csv-parser').

    Args:
        project_name: A short, lowercase, hyphenated name for the project.
    """
    slug = project_name.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = slug.strip("-")

    if not slug:
        return "Error: Could not create a valid project name."

    # Create locally for the backend
    local_path = os.path.join(PROJECTS_DIR, slug)
    os.makedirs(local_path, exist_ok=True)

    # Create a placeholder in the Volume to ensure the directory exists
    try:
        volume_path = f"{VOLUME_BASE}/{slug}/.project"
        databricks_client.files.upload(
            volume_path,
            io.BytesIO(f"project: {slug}\n".encode()),
            overwrite=True,
        )
    except Exception as e:
        return f"Project '{slug}' created locally but Volume write failed: {e}"

    return (
        f"Project folder created: {slug}/\n"
        f"Volume path: {VOLUME_BASE}/{slug}/\n"
        f"Use write_project_file('{slug}', 'main.py', '...code...') to write files."
    )


def write_project_file(project_name: str, file_name: str, content: str) -> str:
    """Write a file to a project folder in the Databricks Volume.

    This persists the file in Unity Catalog Volume storage so it survives
    app redeployments. Always call name_project() first to create the project.

    Args:
        project_name: The project slug (e.g., 'csv-parser-cli').
        file_name: The file name including extension (e.g., 'main.py', 'README.md').
        content: The full file content to write.
    """
    slug = project_name.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = slug.strip("-")

    volume_path = f"{VOLUME_BASE}/{slug}/{file_name}"
    try:
        databricks_client.files.upload(
            volume_path,
            io.BytesIO(content.encode("utf-8")),
            overwrite=True,
        )
        return f"Written: {volume_path} ({len(content)} bytes)"
    except Exception as e:
        return f"Failed to write {volume_path}: {e}"


def list_project_files(project_name: str) -> str:
    """List all files in a project folder in the Databricks Volume.

    Args:
        project_name: The project slug (e.g., 'csv-parser-cli').
    """
    slug = project_name.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = slug.strip("-")

    volume_dir = f"{VOLUME_BASE}/{slug}/"
    try:
        files = list(databricks_client.files.list_directory_contents(volume_dir))
        if not files:
            return f"No files in {volume_dir}"
        lines = [f"- {f.name} ({f.file_size} bytes)" for f in files if f.name != ".project"]
        return f"Files in {volume_dir}:\n" + "\n".join(lines)
    except Exception as e:
        return f"Failed to list {volume_dir}: {e}"


# ============ Tavily search tool ============
_tavily_client = None


def _get_tavily():
    global _tavily_client
    if _tavily_client is None:
        key = os.environ.get("TAVILY_API_KEY", "")
        if not key:
            raise RuntimeError("TAVILY_API_KEY not set — web search unavailable")
        _tavily_client = TavilyClient(api_key=key)
    return _tavily_client


def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
) -> dict:
    """Run a web search using Tavily.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.
        topic: Search topic category — "general", "news", or "finance".
        include_raw_content: Whether to include full page content in results.
    """
    try:
        return _get_tavily().search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic,
        )
    except RuntimeError as e:
        return {"error": str(e), "results": []}


# ============ Databricks Genie tools ============
databricks_client = WorkspaceClient()

GENIE_SPACES = {
    "customer_analytics": "01f1272d4de1188cac8feeb7e71bdb69",
    "distribution_channels": "01f1272d4d271203ad122e9280470248",
    "policy_underwriting": "01f1272d4c6b1fb49223785ab841befd",
    "claims_analytics": "01f1272d4ba6144ba75d868762f1925d",
}


def _query_genie(space_id: str, question: str) -> dict:
    resp = databricks_client.genie.start_conversation_and_wait(
        space_id=space_id, content=question,
    )
    result = {"status": str(resp.status), "conversation_id": resp.conversation_id}
    for att in resp.attachments or []:
        if att.query:
            result["sql"] = att.query.query
            result["description"] = att.query.description
            if att.query.query_result_metadata:
                result["row_count"] = att.query.query_result_metadata.row_count
        if att.text:
            result["answer"] = att.text.content
        if att.suggested_questions:
            result["suggested_questions"] = att.suggested_questions.questions
    return result


def ask_customer_analytics(question: str) -> dict:
    """Ask a natural language question about AIA customer data.
    Covers customer segmentation, retention, demographics, and claim frequency.
    Args:
        question: Natural language question about customers.
    """
    return _query_genie(GENIE_SPACES["customer_analytics"], question)


def ask_distribution_channels(question: str) -> dict:
    """Ask a natural language question about AIA agent performance and distribution channels.
    Covers agent sales, premium volumes, channel comparisons, and top performers.
    Args:
        question: Natural language question about agents or distribution channels.
    """
    return _query_genie(GENIE_SPACES["distribution_channels"], question)


def ask_policy_underwriting(question: str) -> dict:
    """Ask a natural language question about AIA policies and underwriting.
    Covers premium volumes, policy counts, renewal rates, product mix, and underwriting metrics.
    Args:
        question: Natural language question about policies or underwriting.
    """
    return _query_genie(GENIE_SPACES["policy_underwriting"], question)


def ask_claims_analytics(question: str) -> dict:
    """Ask a natural language question about AIA insurance claims.
    Covers claim counts, amounts, processing times, fraud scores, and regional breakdowns.
    Args:
        question: Natural language question about claims or fraud.
    """
    return _query_genie(GENIE_SPACES["claims_analytics"], question)


# ============ Subagents ============

memory_manager = {
    "name": "memory-manager",
    "description": (
        "Manages long-term memory — saving, recalling, and organizing information "
        "the user wants remembered across conversations."
    ),
    "system_prompt": "Follow the memory-manager skill instructions.",
    "skills": ["/skills/"],
    "tools": [save_memory, recall_memories, forget_memory],
}

senior_developer = {
    "name": "senior-developer",
    "description": "Senior Python developer that plans, writes, and delivers complete projects.",
    "system_prompt": "Follow the senior-developer skill instructions.",
    "skills": ["/skills/"],
    "tools": [name_project, write_project_file, list_project_files],
}

code_reviewer = {
    "name": "code-reviewer",
    "description": "Reviews Python code for bugs, style issues, and best practices.",
    "system_prompt": "Follow the code-reviewer skill instructions.",
    "skills": ["/skills/"],
    "tools": [],
}

research_agent = {
    "name": "research-agent",
    "description": "Conducts in-depth web research on any topic.",
    "system_prompt": "Follow the research-agent skill instructions.",
    "skills": ["/skills/"],
    "tools": [internet_search],
}

aia_customer_agent = {
    "name": "aia-customer-analytics",
    "description": "Queries AIA customer data — segmentation, retention, demographics, claim frequency.",
    "system_prompt": "Follow the aia-customer-analytics skill instructions.",
    "skills": ["/skills/"],
    "tools": [ask_customer_analytics],
}

aia_distribution_agent = {
    "name": "aia-distribution-channels",
    "description": "Queries AIA agent performance and distribution channel data.",
    "system_prompt": "Follow the aia-distribution-channels skill instructions.",
    "skills": ["/skills/"],
    "tools": [ask_distribution_channels],
}

aia_policy_agent = {
    "name": "aia-policy-underwriting",
    "description": "Queries AIA policy and underwriting data — premiums, policy counts, renewals.",
    "system_prompt": "Follow the aia-policy-underwriting skill instructions.",
    "skills": ["/skills/"],
    "tools": [ask_policy_underwriting],
}

aia_claims_agent = {
    "name": "aia-claims-analytics",
    "description": "Queries AIA claims data — claim counts, amounts, fraud scores.",
    "system_prompt": "Follow the aia-claims-analytics skill instructions.",
    "skills": ["/skills/"],
    "tools": [ask_claims_analytics],
}

subagents = [
    memory_manager,
    senior_developer,
    code_reviewer,
    research_agent,
    aia_customer_agent,
    aia_distribution_agent,
    aia_policy_agent,
    aia_claims_agent,
]


# ============ System prompt ============

SYSTEM_PROMPT = """You are a multi-agent orchestrator with long-term memory.

## Memory — MANDATORY Behavior

You have long-term memory tools that persist information across conversations.
These are NOT optional — you MUST use them proactively on EVERY turn.

### CRITICAL: Tool call order on EVERY user message

You MUST follow this exact sequence:

1. **First**, call `recall_memories()` (no arguments) to load stored context.
2. **Second**, call `save_memory(...)` for anything worth remembering from the user's message (see below).
3. **Only then** proceed to handle the user's request (call `task`, `name_project`, etc.).

NEVER skip step 2. NEVER delegate to a subagent before saving memory.

### What to save — be generous, save MORE not less:

- **project**: ANY task or request the user gives you. Examples:
  - "Build a Python CLI tool for CSV parsing" → save "User requested a Python CLI tool for CSV parsing" as project
  - "Research competitor analysis" → save "User requested competitor analysis research" as project
  - "Help me with my RAG pipeline" → save "User is working on a RAG pipeline" as project
- **preference**: likes, dislikes, style choices ("I prefer Python", "keep answers short")
- **fact**: name, role, team, expertise ("I'm a data scientist", "I work at AIA")
- **decision**: architectural choices, tech stack picks ("We'll use FastAPI", "We chose Postgres")
- **feedback**: corrections or praise about your behavior ("Don't summarize", "That format was great")

**Rule: If the user asks you to DO something, that is a project — always save it.**

### When to forget:
- Only when the user explicitly asks, or when correcting outdated information.

### Categories: preference, fact, decision, project, feedback

Briefly mention when you save or recall a memory so the user knows the system is working.
"""


# ============ Build agent ============

def _create_backend():
    if USE_SANDBOX:
        return LocalShellBackend(root_dir=PROJECTS_DIR)
    return FilesystemBackend(root_dir=PROJECTS_DIR, virtual_mode=True)


checkpointer = MemorySaver()

model = ChatDatabricks(
    endpoint="databricks-claude-opus-4-7",
    temperature=0.1,
)

agent = create_deep_agent(
    model=model,
    tools=[
        name_project,
        write_project_file,
        list_project_files,
        internet_search,
        save_memory,
        recall_memories,
        forget_memory,
        ask_customer_analytics,
        ask_distribution_channels,
        ask_policy_underwriting,
        ask_claims_analytics,
    ],
    system_prompt=SYSTEM_PROMPT,
    skills=["/skills/"],
    subagents=subagents,
    backend=_create_backend(),
    checkpointer=checkpointer,
)
