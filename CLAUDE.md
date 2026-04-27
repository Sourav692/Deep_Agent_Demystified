# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Educational repository teaching agentic AI design patterns using LangGraph. Contains Jupyter notebooks organized by difficulty, Streamlit apps, and a full-stack capstone project. Package name: `agentic-ai-design-pattern-demystified`.

## Environment Setup

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"       # includes pytest, jupyter
# or install everything: uv pip install -e ".[all]"
# extras: [dev], [apps] (streamlit), [fullstack] (fastapi+postgres), [all]
```

Always use `uv` for dependency management. Dependencies are defined in `pyproject.toml` (single source of truth). `requirements.txt` is a pinned mirror — update both when adding deps.

## Running Things

```bash
# Notebooks
jupyter lab

# Streamlit apps
cd 06_Production/streamlit_apps/doc-entity-extractor
streamlit run app.py

# Full-stack capstone (FastAPI + Angular + Postgres)
cd 06_Production/fullstackapp
docker compose up
# Backend: localhost:8000, Frontend: localhost:5555

# Tests
cd 06_Production/unit_tests
pytest

# Deep Agents
cd 07_Deep_Agents
python simple_coding_agent.py
```

## Required Environment Variables (.env at project root)

- `OPENAI_API_KEY` — OpenAI models
- `GROQ_API_KEY` — Groq models (used on Windows)
- `GOOGLE_API_KEY` — LangExtract Streamlit apps
- `TAVILY_API_KEY` — web search notebooks
- Databricks credentials — used on macOS (default provider)

## Architecture

### `helpers/` — Shared LLM/Embedding Factory Package

Installed as an editable package (`hatchling` build). Imported in all notebooks via:
```python
from helpers import get_llm, get_embeddings
```

**Platform-aware defaults** (auto-selected when no provider specified):
- **macOS**: Databricks (`databricks-claude-opus-4-6` for LLM, `databricks-gte-large-en` for embeddings)
- **Windows**: Groq for LLM (`openai/gpt-oss-120b`), OpenAI for embeddings (`text-embedding-3-small`)

Provider can be overridden: `get_llm(provider="openai", model="gpt-4o")`.

### Tutorial Structure (7 Chapters)

| Directory | Content |
|---|---|
| `01_Foundations/` | Core LangGraph: state, graphs, routing, tools, ReAct, Pydantic |
| `02_Core_Capabilities/` | Platform features: memory, routing, HITL, advanced state, subgraphs, async |
| `03_RAG/` | Retrieval-augmented generation: basic → Databricks → advanced → RAG-as-tool |
| `04_Agents/` | Real-world agents: research assistant, competitive intelligence |
| `05_Agentic_Design_Patterns/` | Design patterns: tool use, planning, reflection, agent patterns, long-term memory |
| `06_Production/` | Deployment: full-stack app, unit tests, Streamlit apps |
| `07_Deep_Agents/` | Multi-agent orchestration with deepagents library |
| `archive/` | Retired notebooks from old Reference Course + RAG Bootcamp |

### Agentic Patterns Covered

ReAct, Tool Use (direct + ReAct), RAG (standalone + as-tool), Planning (parallel execution, `Send` API / map-reduce), Reflection, Agent Patterns, Long-Term Memory, Multi-Agent (supervisor, subagents with skills).

## Notebook Conventions

Notebooks follow a specific formatting standard (see `.claude/skills/format-notebook/SKILL.md`):
- Title cell: `# Title` in first markdown cell
- Section headers use `##` / `###` / `####` hierarchy
- Code cells start with banner comments: `# ============ SECTION NAME ============`
- Imports grouped: stdlib → third-party → local (`from helpers import get_llm`)
- LLM initialization uses the helpers factory, never direct provider instantiation
- Final cell: summary markdown with key takeaways

## Conventions

- Python >= 3.11 required (target 3.12 for venv)
- All LLM/embedding initialization goes through `helpers/utils.py` factories — never instantiate `ChatOpenAI`/`ChatGroq`/`ChatDatabricks` directly in notebooks
- Directory names use numeric prefixes without spaces (e.g., `01_Foundations/`, `03_Advanced_Agents/01_Tool_Use/`) — no need to quote these paths
