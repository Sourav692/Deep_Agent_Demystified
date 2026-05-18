"""Chat endpoint — SSE-streamed agent responses."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import BaseMessage

from deep_agent.api.schemas import ChatRequest
from deep_agent.runtime import agent_init_status, get_agent, threads

logger = logging.getLogger("deep-agent")

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(request: ChatRequest):
    """Stream agent responses as Server-Sent Events."""
    agent, _ = get_agent()
    if not agent:
        return JSONResponse(
            status_code=503,
            content={"detail": f"Agent not initialized: {agent_init_status()['init_error']}"},
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
                                    "content": (
                                        message.content
                                        if isinstance(message.content, str)
                                        else str(message.content)
                                    ),
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
