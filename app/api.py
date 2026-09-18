"""FastAPI REST, WebSockets, and Web Dashboard for Xeren Assistant (Phase 3)."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from core.assistant import AssistantResponse, XerenAssistant
from security.permission_gate import ApprovalRequest


class QueryRequest(BaseModel):
  query: str = Field(description="User prompt or instruction")
  session_id: str = Field(
      default="default_session", description="Conversation session ID"
  )


class DecisionRequest(BaseModel):
  decision: str = Field(
      description="Approval decision: 'approve', 'accept', 'deny', or 'reject'"
  )


class HealthResponse(BaseModel):
  status: str = "ok"
  app_name: str
  version: str
  analytics: Dict[str, Any]


def create_app(assistant: Optional[XerenAssistant] = None) -> FastAPI:
  """Factory creating FastAPI application with injected XerenAssistant instance and approval hooks."""
  app = FastAPI(
      title="Xeren Assistant API & Dashboard",
      description="REST API, WebSockets, and Visual Dashboard for Xeren Assistant Phase 3",
      version="0.3.0",
  )

  _assistant = assistant or XerenAssistant()

  @app.get("/")
  async def serve_dashboard():
    """Serves the interactive Xeren Web Dashboard."""
    index_file = Path(__file__).parent / "static" / "index.html"
    if index_file.exists():
      return FileResponse(str(index_file))
    return {"message": "Xeren Assistant API running. Dashboard file not found."}

  # In-memory approval state for asynchronous remote approvals
  pending_approvals: Dict[str, ApprovalRequest] = {}
  approval_futures: Dict[str, asyncio.Future] = {}
  active_websockets: List[WebSocket] = []

  async def broadcast_ws_event(event_type: str, data: Any):
    disconnected = []
    for ws in active_websockets:
      try:
        await ws.send_json({"event": event_type, "data": data})
      except Exception:
        disconnected.append(ws)
    for ws in disconnected:
      if ws in active_websockets:
        active_websockets.remove(ws)

  async def api_approval_callback(req: ApprovalRequest) -> bool:
    """Hooks into PermissionGate to route ASK permissions to the API approval queue."""
    pending_approvals[req.approval_id] = req
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    approval_futures[req.approval_id] = future

    # Broadcast approval request to active WebSockets
    await broadcast_ws_event("approval_required", req.model_dump())

    try:
      # Await decision with 30s timeout
      result = await asyncio.wait_for(future, timeout=30.0)
      return bool(result)
    except asyncio.TimeoutError:
      return False
    finally:
      pending_approvals.pop(req.approval_id, None)
      approval_futures.pop(req.approval_id, None)

  # Attach approval callback to permission gate
  _assistant.tool_registry.permission_gate.approval_callback = (
      api_approval_callback
  )

  @app.get("/health", response_model=HealthResponse)
  async def health():
    return HealthResponse(
        status="ok",
        app_name=_assistant.settings.app_name,
        version=_assistant.settings.version,
        analytics=_assistant.analytics_tracker.get_summary(),
    )

  @app.post("/query", response_model=AssistantResponse)
  async def query_assistant(req: QueryRequest):
    if not req.query.strip():
      raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
      response = await _assistant.process_request(
          query=req.query, session_id=req.session_id
      )
      return response
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))

  @app.get("/approvals")
  async def list_pending_approvals():
    """Lists all actions currently awaiting human-in-the-loop approval."""
    return {"pending_approvals": [req.model_dump() for req in pending_approvals.values()]}

  @app.post("/approvals/{approval_id}/decision")
  async def submit_approval_decision(approval_id: str, body: DecisionRequest):
    """Submits approve or reject decision for a pending approval."""
    if approval_id not in approval_futures:
      raise HTTPException(
          status_code=404, detail=f"No pending approval found for ID {approval_id}"
      )

    approved = body.decision.lower() in ["approve", "accept", "yes", "true"]
    future = approval_futures[approval_id]
    if not future.done():
      future.set_result(approved)

    return {"approval_id": approval_id, "approved": approved, "status": "resolved"}

  @app.get("/tools")
  async def list_tools():
    return {"tools": _assistant.tool_registry.list_tools()}

  @app.get("/tasks")
  async def list_tasks(status: Optional[str] = None, limit: int = 50):
    task_tool = _assistant.tool_registry.get_tool("tasks")
    if not task_tool:
      raise HTTPException(status_code=500, detail="Task tool not registered.")

    from tools.base import Action

    act = Action(
        action_id="api_list_tasks",
        tool_name="tasks",
        operation="list_tasks",
        parameters={"status": status, "limit": limit},
    )
    result = await task_tool.execute(act)
    if not result.success:
      raise HTTPException(status_code=500, detail=result.error)
    return {"tasks": result.data}

  @app.get("/memory/semantic")
  async def query_semantic_memory(
      q: Optional[str] = None, category: Optional[str] = None, limit: int = 10
  ):
    """Searches or lists long-term semantic memories."""
    if q:
      results = await _assistant.semantic_memory.search(
          query=q, limit=limit, category=category
      )
      return {"results": [r.model_dump() for r in results]}
    memories = _assistant.semantic_memory.list_memories(
        limit=limit, category=category
    )
    return {"memories": [m.model_dump() for m in memories]}

  @app.post("/memory/semantic")
  async def add_semantic_memory(item: Dict[str, Any]):
    """Adds a custom document or experience to long-term memory."""
    content = item.get("content", "").strip()
    if not content:
      raise HTTPException(status_code=400, detail="Content cannot be empty.")
    category = item.get("category", "custom")
    metadata = item.get("metadata", {})
    record = await _assistant.semantic_memory.add_memory(
        content=content, category=category, metadata=metadata
    )
    return {"status": "saved", "memory": record.model_dump()}

  # Phase 5: Task Scheduler Engine
  from core.scheduler import TaskScheduler
  from agents.swarm import SwarmCoordinator
  from telemetry.flamegraph import TraceSpanTree

  scheduler = TaskScheduler(db_path=_assistant.settings.db_path)
  swarm_coordinator = SwarmCoordinator(
      llm_provider=_assistant.llm_provider,
      tool_registry=_assistant.tool_registry,
  )

  @app.get("/jobs")
  async def list_jobs():
    """Lists all background scheduled jobs."""
    jobs = scheduler.list_jobs()
    return {"jobs": [j.model_dump() for j in jobs]}

  @app.post("/jobs")
  async def create_job(data: Dict[str, Any]):
    """Creates a new recurring background job."""
    name = data.get("name", "Custom Scheduled Job")
    interval = float(data.get("interval_seconds", 300))
    action_type = data.get("action_type", "custom")
    payload = data.get("payload", {})
    job = scheduler.add_job(
        name=name,
        interval_seconds=interval,
        action_type=action_type,
        payload=payload,
    )
    return {"status": "scheduled", "job": job.model_dump()}

  @app.delete("/jobs/{job_id}")
  async def delete_job(job_id: str):
    """Cancels/deletes a scheduled job."""
    success = scheduler.delete_job(job_id)
    if not success:
      raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}

  @app.post("/swarm/run")
  async def run_swarm(data: Dict[str, Any]):
    """Runs a multi-agent collaborative swarm workflow."""
    prompt = data.get("prompt", "").strip()
    if not prompt:
      raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    result = await swarm_coordinator.collaborate(prompt=prompt)
    return result.model_dump()

  @app.get("/traces")
  async def list_traces(limit: int = 20):
    """Lists recent execution traces."""
    traces = _assistant.trace_logger.list_traces(limit=limit)
    return {"traces": [t.model_dump() for t in traces]}

  @app.get("/traces/{trace_id}/flamegraph")
  async def get_flamegraph(trace_id: str):
    """Generates hierarchical flamegraph timing breakdown for a trace."""
    trace = _assistant.trace_logger.get_trace(trace_id)
    if not trace:
      raise HTTPException(
          status_code=404, detail=f"Trace {trace_id} not found."
      )
    flamegraph = TraceSpanTree.from_trace_dict(trace.model_dump())
    return flamegraph.model_dump()

  @app.websocket("/ws/stream")
  async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
      while True:
        data = await websocket.receive_text()
        # Ping/pong or client event
        await websocket.send_json({"event": "ack", "received": data})
    except WebSocketDisconnect:
      if websocket in active_websockets:
        active_websockets.remove(websocket)

  return app
