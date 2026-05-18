"""FastAPI backend for Deep Agent with Long-Term Memory.

Endpoints:
  POST /api/chat           — Send a message, get streamed response (SSE)
  POST /api/threads        — Create a new thread
  GET  /api/threads        — List all threads
  GET  /api/memories       — List all stored memories
  POST /api/memories       — Manually save a memory
  DELETE /api/memories/{id} — Delete a specific memory
"""

import json
import logging
import os
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger("deep-agent")
logging.basicConfig(level=logging.INFO)


# ============ Lazy-loaded agent ============
_agent = None
_init_error = None
_init_attempted = False


def _get_agent():
    """Lazy-load the agent on first use to avoid crashing on startup."""
    global _agent, _init_error, _init_attempted
    if _init_attempted:
        if _agent is None and _init_error:
            logger.warning(f"Agent previously failed to init: {_init_error[:200]}")
        return _agent
    _init_attempted = True
    try:
        logger.info("Attempting agent initialization...")
        try:
            from backend.agent import agent, checkpointer
        except ImportError:
            from agent import agent, checkpointer
        _agent = agent
        logger.info("Agent initialized successfully")
    except Exception as e:
        _init_error = f"{e}\n{traceback.format_exc()}"
        logger.error(f"Agent init failed: {_init_error}")
    return _agent


# ============ Lazy-loaded memory store ============
_memory_db = None


def _get_memory_db():
    global _memory_db
    if _memory_db is not None:
        return _memory_db
    try:
        try:
            from backend.memory_store import LakebaseMemoryStore
        except ImportError:
            from memory_store import LakebaseMemoryStore
        _memory_db = LakebaseMemoryStore()
        _memory_db.ensure_table()
    except Exception as e:
        logger.error(f"Memory store init failed: {e}")
        _memory_db = None
    return _memory_db


# ============ FastAPI app ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — eagerly initializing agent...")
    _get_agent()
    if _agent:
        logger.info("Agent ready")
    else:
        logger.error(f"Agent failed to initialize: {_init_error}")
    yield

app = FastAPI(title="Deep Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Models ============

class ChatRequest(BaseModel):
    message: str
    thread_id: str


class ThreadCreate(BaseModel):
    title: str = "New Chat"


class ThreadRename(BaseModel):
    title: str


class MemorySave(BaseModel):
    content: str
    category: str = "general"


# ============ In-memory thread registry ============
threads: dict[str, dict] = {}


# ============ Health check ============

@app.get("/api/health")
async def health():
    """Health check with diagnostic info."""
    return {
        "status": "ok",
        "agent_loaded": _agent is not None,
        "init_attempted": _init_attempted,
        "init_error": _init_error,
        "cwd": os.getcwd(),
        "files_in_cwd": os.listdir("."),
        "python_path_sample": os.environ.get("PYTHONPATH", "not set"),
        "env_keys": [k for k in os.environ if "DATABRICKS" in k or "TAVILY" in k],
    }


# ============ Chat endpoint (SSE streaming) ============

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Stream agent responses as Server-Sent Events."""
    from langchain_core.messages import BaseMessage

    agent = _get_agent()
    if not agent:
        return JSONResponse(
            status_code=503,
            content={"detail": f"Agent not initialized: {_init_error}"},
        )

    thread_id = request.thread_id

    if thread_id not in threads:
        threads[thread_id] = {
            "id": thread_id,
            "title": request.message[:50],
            "created_at": datetime.now().isoformat(),
        }

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}

    def event_stream():
        try:
            for event in agent.stream(
                {"messages": [{"role": "user", "content": request.message}]},
                config,
                stream_mode=["updates", "messages"],
            ):
                mode, payload = event

                if mode == "messages":
                    message, metadata = payload
                    if not isinstance(message, BaseMessage):
                        continue
                    langgraph_node = metadata.get("langgraph_node", "")
                    if message.type == "AIMessageChunk":
                        content = message.content if isinstance(message.content, str) else ""
                        tool_calls = None
                        if hasattr(message, "tool_call_chunks") and message.tool_call_chunks:
                            tool_calls = [
                                {"name": tc.get("name", ""), "args": tc.get("args", {})}
                                for tc in message.tool_call_chunks
                                if tc.get("name")
                            ]
                        if content or tool_calls:
                            event_data = {
                                "node": langgraph_node,
                                "type": "ai",
                                "content": content,
                            }
                            if tool_calls:
                                event_data["tool_calls"] = tool_calls
                            yield f"data: {json.dumps(event_data)}\n\n"

                elif mode == "updates":
                    for node_name, update in payload.items():
                        if not update:
                            continue
                        messages = update.get("messages", [])
                        if not isinstance(messages, list):
                            messages = [messages]
                        for message in messages:
                            if not isinstance(message, BaseMessage):
                                continue
                            if message.type == "tool":
                                event_data = {
                                    "node": node_name,
                                    "type": "tool",
                                    "content": message.content if isinstance(message.content, str) else str(message.content),
                                }
                                yield f"data: {json.dumps(event_data)}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============ Thread endpoints ============

@app.post("/api/threads")
async def create_thread(request: ThreadCreate):
    thread_id = str(uuid.uuid4())
    threads[thread_id] = {
        "id": thread_id,
        "title": request.title,
        "created_at": datetime.now().isoformat(),
    }
    return threads[thread_id]


@app.get("/api/threads")
async def list_threads():
    return list(threads.values())


@app.get("/api/threads/{thread_id}/messages")
async def get_thread_messages(thread_id: str):
    """Retrieve the message history for a thread from the checkpointer."""
    from langchain_core.messages import AIMessage, HumanMessage

    if thread_id not in threads:
        raise HTTPException(status_code=404, detail="Thread not found")

    agent = _get_agent()
    if not agent:
        return []

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
    try:
        state = agent.get_state(config)
        if not state or not state.values:
            return []

        messages = state.values.get("messages", [])
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({
                    "role": "user",
                    "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                })
            elif isinstance(msg, AIMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if content:
                    entry = {"role": "assistant", "content": content}
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        entry["tool_calls"] = [
                            {"name": tc["name"], "args": tc.get("args", {})}
                            for tc in msg.tool_calls
                        ]
                    if hasattr(msg, "name") and msg.name:
                        entry["node"] = msg.name
                    result.append(entry)
            elif hasattr(msg, "type") and msg.type == "tool":
                result.append({
                    "role": "tool",
                    "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                })
        return result
    except Exception:
        return []


@app.delete("/api/threads/{thread_id}")
async def delete_thread(thread_id: str):
    if thread_id not in threads:
        raise HTTPException(status_code=404, detail="Thread not found")
    deleted = threads.pop(thread_id)
    return {"deleted": deleted}


@app.patch("/api/threads/{thread_id}")
async def rename_thread(thread_id: str, request: ThreadRename):
    if thread_id not in threads:
        raise HTTPException(status_code=404, detail="Thread not found")
    threads[thread_id]["title"] = request.title
    return threads[thread_id]


# ============ Memory endpoints (direct CRUD) ============

@app.get("/api/memories")
async def list_memories():
    db = _get_memory_db()
    if not db:
        return []
    return db.list_all()


@app.post("/api/memories")
async def save_memory(request: MemorySave):
    db = _get_memory_db()
    if not db:
        raise HTTPException(status_code=503, detail="Memory store not available")
    return db.save(request.content, request.category)


@app.delete("/api/memories/{content_substring}")
async def delete_memory(content_substring: str):
    db = _get_memory_db()
    if not db:
        raise HTTPException(status_code=503, detail="Memory store not available")
    result = db.forget(content_substring)
    if not result:
        raise HTTPException(status_code=404, detail="Memory not found")
    return result


# ============ Serve React frontend ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend", "build")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
