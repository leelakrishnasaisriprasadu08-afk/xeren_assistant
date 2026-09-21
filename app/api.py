"""FastAPI REST, WebSockets, and Web Dashboard for Xeren Assistant (Phase 3)."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from agents.swarm import SwarmCoordinator
from codebase.indexer import CodebaseIndexer
from core.assistant import AssistantResponse, XerenAssistant
from core.scheduler import TaskScheduler
from patching.diff_applier import DiffApplier
from patching.patch_engine import PatchEngine
from security.permission_gate import ApprovalRequest
from telemetry.flamegraph import TraceSpanTree


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


class ClientDraftRequest(BaseModel):
  client_id: Optional[str] = None
  thread_id: Optional[str] = None
  incoming_message: str = Field(description="Client question or inquiry")
  sender: Optional[str] = Field(default="Client", description="Sender name or email")
  task_context: Optional[str] = None
  style: Optional[str] = Field(default="professional", description="Tone style: professional, technical, empathetic, concise")
  include_git_status: Optional[bool] = False


class ClientSendRequest(BaseModel):
  channel: str = Field(default="email", description="Channel: 'email' or 'webhook'")
  to: Optional[str] = None
  subject: Optional[str] = None
  body: Optional[str] = None
  thread_id: Optional[str] = None
  client_id: Optional[str] = None
  url: Optional[str] = None
  payload: Optional[Dict[str, Any]] = None


class ClientCreateRequest(BaseModel):
  name: str
  email: str
  company: Optional[str] = None
  communication_tone: Optional[str] = "professional"
  notes: Optional[str] = None


class CredentialSaveRequest(BaseModel):
  platform: str
  username_or_email: str
  password: str
  two_factor_type: Optional[str] = "none"
  two_factor_secret: Optional[str] = None
  metadata: Optional[Dict[str, Any]] = None


class TwoFactorSubmitRequest(BaseModel):
  platform: str
  code: str


class WebScaffoldRequest(BaseModel):
  prompt: str
  project_name: Optional[str] = None


class WebDeployRequest(BaseModel):
  project_name: Optional[str] = None
  port: Optional[int] = None


class VoiceSpeakRequest(BaseModel):
  text: str = Field(description="Text to synthesize and speak aloud")
  voice: Optional[str] = Field(default=None, description="Voice identifier or name")
  rate: Optional[int] = Field(default=None, description="Speech rate offset (-10 to 10)")
  volume: Optional[int] = Field(default=None, description="Speech volume (0 to 100)")
  async_mode: bool = Field(default=True, description="Run speech asynchronously in background")


class VoiceSynthesizeRequest(BaseModel):
  text: str = Field(description="Text to convert to speech")


class VoiceTranscribeRequest(BaseModel):
  audio_text: Optional[str] = Field(default=None, description="Transcribed voice text payload")


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

  # Phase 5 & 6 engines
  scheduler = TaskScheduler(db_path=_assistant.settings.db_path)
  swarm_coordinator = SwarmCoordinator(
      llm_provider=_assistant.llm_provider,
      tool_registry=_assistant.tool_registry,
  )
  codebase_indexer = CodebaseIndexer(
      workspace_root=_assistant.settings.workspace_root,
      db_path=_assistant.settings.db_path,
  )
  patch_engine = PatchEngine(
      workspace_root=_assistant.settings.workspace_root,
      llm_provider=_assistant.llm_provider,
      indexer=codebase_indexer,
      settings=_assistant.settings,
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

  # Phase 6: AST Codebase Indexing & Patching Endpoints
  @app.post("/codebase/index")
  async def index_codebase_endpoint(data: Optional[Dict[str, Any]] = None):
    """Triggers complete or incremental codebase AST indexing."""
    force = bool(data.get("force", False)) if data else False
    result = codebase_indexer.index_workspace(force=force)
    return result

  @app.get("/codebase/symbols")
  async def search_codebase_symbols_endpoint(
      query: str = "",
      type: Optional[str] = None,
      file: Optional[str] = None,
      limit: int = 50,
  ):
    """Searches indexed codebase symbols by name, type, or file."""
    symbols = codebase_indexer.search_symbols(
        query=query, symbol_type=type, file_pattern=file, limit=limit
    )
    return {"symbols": symbols, "total": len(symbols)}

  @app.get("/codebase/outline")
  async def get_file_outline_endpoint(file_path: str):
    """Returns the structural AST outline for a specific source file."""
    if not file_path:
      raise HTTPException(status_code=400, detail="file_path parameter is required.")
    outline = codebase_indexer.get_file_outline(file_path=file_path)
    return {"file_path": file_path, "outline": outline}

  @app.get("/codebase/call-graph")
  async def get_call_graph_endpoint(symbol_name: str):
    """Returns caller and callee hierarchies for a target symbol."""
    if not symbol_name:
      raise HTTPException(status_code=400, detail="symbol_name parameter is required.")
    hierarchy = codebase_indexer.get_call_hierarchy(symbol_name=symbol_name)
    return hierarchy

  @app.post("/patch/generate")
  async def generate_patch_endpoint(data: Dict[str, Any]):
    """Autonomous TDD patch generation and test verification."""
    target_file = data.get("target_file", "").strip()
    instruction = data.get("instruction", "").strip()
    test_target = data.get("test_target")
    max_retries = int(data.get("max_retries", 2))
    dry_run = bool(data.get("dry_run", False))

    if not target_file or not instruction:
      raise HTTPException(
          status_code=400,
          detail="target_file and instruction are required parameters.",
      )

    res = await patch_engine.generate_and_verify_patch(
        target_file=target_file,
        instruction=instruction,
        test_target=test_target,
        max_retries=max_retries,
        dry_run=dry_run,
    )
    return res.model_dump()

  @app.post("/patch/apply")
  async def apply_patch_endpoint(data: Dict[str, Any]):
    """Applies a unified diff patch to a workspace file."""
    target_file = data.get("target_file", "").strip()
    patch_diff = data.get("patch_diff", "").strip()

    if not target_file or not patch_diff:
      raise HTTPException(
          status_code=400,
          detail="target_file and patch_diff are required parameters.",
      )

    full_path = patch_engine.workspace_root / target_file
    success, error = DiffApplier.apply_patch_to_file(full_path, patch_diff)
    if not success:
      raise HTTPException(status_code=400, detail=error or "Failed to apply patch.")
    return {"status": "applied", "target_file": target_file}

  @app.get("/system/server-check")
  @app.get("/device/server-check")
  async def get_server_health_check():
    """Performs an extensive, production-grade server and infrastructure audit."""
    dev_tool = _assistant.tool_registry.get_tool("device")
    if not dev_tool:
      raise HTTPException(status_code=500, detail="DeviceTool not registered.")
    from tools.base import Action
    res = await dev_tool.execute(Action(action_id="srv_check", tool_name="device", operation="server_health_check", parameters={}))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to execute server health check.")
    return res.data

  @app.get("/device/network-ports")
  async def get_network_ports():
    """Inspects active listening network ports, socket connection counts, and throughput."""
    dev_tool = _assistant.tool_registry.get_tool("device")
    if not dev_tool:
      raise HTTPException(status_code=500, detail="DeviceTool not registered.")
    from tools.base import Action
    res = await dev_tool.execute(Action(action_id="net_ports", tool_name="device", operation="check_network_ports", parameters={}))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to inspect network ports.")
    return res.data

  @app.get("/device/stats")
  async def get_device_stats():
    """Retrieves real-time CPU, RAM, Disk, Battery, and OS telemetry."""
    dev_tool = _assistant.tool_registry.get_tool("device")
    if not dev_tool:
      raise HTTPException(status_code=500, detail="DeviceTool not registered.")
    from tools.base import Action
    res = await dev_tool.execute(Action(action_id="dev_stats", tool_name="device", operation="get_system_info", parameters={}))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to retrieve stats.")
    return res.data

  @app.get("/device/processes")
  async def get_device_processes(limit: int = 20, sort_by: str = "memory", filter: Optional[str] = None):
    """Lists running processes."""
    dev_tool = _assistant.tool_registry.get_tool("device")
    if not dev_tool:
      raise HTTPException(status_code=500, detail="DeviceTool not registered.")
    from tools.base import Action
    res = await dev_tool.execute(Action(action_id="dev_proc", tool_name="device", operation="list_processes", parameters={"limit": limit, "sort_by": sort_by, "filter_name": filter}))
    return {"processes": res.data or []}

  @app.post("/device/launch")
  async def launch_device_app(data: Dict[str, Any]):
    """Launches a desktop application."""
    app_name = data.get("app_name") or data.get("name")
    if not app_name:
      raise HTTPException(status_code=400, detail="app_name parameter is required.")
    dev_tool = _assistant.tool_registry.get_tool("device")
    from tools.base import Action
    res = await dev_tool.execute(Action(action_id="dev_launch", tool_name="device", operation="launch_app", parameters={"app_name": app_name, "args": data.get("args")}))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to launch app.")
    return res.data

  @app.post("/device/screenshot")
  async def capture_device_screenshot():
    """Captures desktop screenshot."""
    dev_tool = _assistant.tool_registry.get_tool("device")
    from tools.base import Action
    res = await dev_tool.execute(Action(action_id="dev_screen", tool_name="device", operation="capture_screenshot", parameters={}))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to take screenshot.")
    return res.data

  @app.get("/scheduler/jobs")
  async def list_scheduled_jobs(active_only: bool = False):
    """Lists scheduled background jobs."""
    scheduler = TaskScheduler(db_path=_assistant.settings.db_path)
    jobs = scheduler.list_jobs(only_active=active_only)
    return {"jobs": [j.model_dump() for j in jobs]}

  @app.post("/scheduler/jobs")
  async def create_scheduled_job(data: Dict[str, Any]):
    """Registers a new scheduled background job."""
    name = data.get("name") or "Scheduled Task"
    interval = float(data.get("interval_seconds", 60.0))
    action_type = data.get("action_type", "query")
    payload = data.get("payload", {})
    scheduler = TaskScheduler(db_path=_assistant.settings.db_path)
    job = scheduler.add_job(name=name, interval_seconds=interval, action_type=action_type, payload=payload)
    return job.model_dump()

  @app.delete("/scheduler/jobs/{job_id}")
  async def cancel_scheduled_job(job_id: str):
    """Cancels a scheduled background job."""
    scheduler = TaskScheduler(db_path=_assistant.settings.db_path)
    success = scheduler.cancel_job(job_id)
    if not success:
      raise HTTPException(status_code=404, detail=f"Job {job_id} not found or already inactive.")
    return {"status": "cancelled", "job_id": job_id}

  @app.post("/vision/analyze-screen")
  async def analyze_screen_endpoint(data: Optional[Dict[str, Any]] = None):
    """Analyzes desktop screen or image using multimodal vision."""
    payload = data or {}
    vis_tool = _assistant.tool_registry.get_tool("vision")
    if not vis_tool:
      raise HTTPException(status_code=500, detail="VisionTool not registered.")
    from tools.base import Action
    res = await vis_tool.execute(Action(action_id="vis_screen", tool_name="vision", operation="analyze_screen", parameters=payload))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Screen vision analysis failed.")
    return res.data

  @app.post("/vision/extract-text")
  async def extract_screen_text_endpoint(data: Optional[Dict[str, Any]] = None):
    """Extracts text and error diagnostics from active screen."""
    payload = data or {}
    vis_tool = _assistant.tool_registry.get_tool("vision")
    if not vis_tool:
      raise HTTPException(status_code=500, detail="VisionTool not registered.")
    from tools.base import Action
    res = await vis_tool.execute(Action(action_id="vis_text", tool_name="vision", operation="extract_screen_text", parameters=payload))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "OCR text extraction failed.")
    return res.data

  @app.post("/browser/navigate")
  async def browser_navigate_endpoint(data: Dict[str, Any]):
    """Navigates to URL and extracts page headings and links."""
    url = data.get("url")
    if not url:
      raise HTTPException(status_code=400, detail="url parameter is required.")
    browser_tool = _assistant.tool_registry.get_tool("browser")
    if not browser_tool:
      raise HTTPException(status_code=500, detail="BrowserTool not registered.")
    from tools.base import Action
    res = await browser_tool.execute(Action(action_id="browse_nav", tool_name="browser", operation="navigate_url", parameters={"url": url}))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Browser navigation failed.")
    return res.data

  @app.post("/browser/extract")
  async def browser_extract_endpoint(data: Dict[str, Any]):
    """Extracts article content and structured text from URL."""
    url = data.get("url")
    if not url:
      raise HTTPException(status_code=400, detail="url parameter is required.")
    browser_tool = _assistant.tool_registry.get_tool("browser")
    if not browser_tool:
      raise HTTPException(status_code=500, detail="BrowserTool not registered.")
    from tools.base import Action
    res = await browser_tool.execute(Action(action_id="browse_ext", tool_name="browser", operation="extract_page_content", parameters={"url": url}))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Content extraction failed.")
    return res.data

  @app.post("/client/draft")
  async def client_draft_endpoint(req: ClientDraftRequest):
    """Generates an intelligent, context-grounded response for client outreach."""
    comm_tool = _assistant.tool_registry.get_tool("communication")
    if not comm_tool:
      raise HTTPException(status_code=500, detail="CommunicationTool not registered.")
    from tools.base import Action
    res = await comm_tool.execute(Action(
        action_id="client_draft",
        tool_name="communication",
        operation="draft_client_reply",
        parameters=req.model_dump()
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to draft client reply.")
    return res.data

  @app.post("/client/send")
  async def client_send_endpoint(req: ClientSendRequest):
    """Dispatches client communication via email or webhook (requires permission approval)."""
    comm_tool = _assistant.tool_registry.get_tool("communication")
    if not comm_tool:
      raise HTTPException(status_code=500, detail="CommunicationTool not registered.")
    from tools.base import Action
    if req.channel == "webhook":
      op = "send_webhook"
      params = {"url": req.url, "payload": req.payload or {"subject": req.subject, "body": req.body}}
    else:
      op = "send_email"
      params = {"to": req.to, "subject": req.subject, "body": req.body, "thread_id": req.thread_id, "client_id": req.client_id}
    res = await comm_tool.execute(Action(
        action_id="client_send",
        tool_name="communication",
        operation=op,
        parameters=params
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to send client message.")
    return res.data

  @app.get("/client/threads")
  async def list_client_threads_endpoint(client_id: Optional[str] = None):
    """Lists client interaction threads."""
    comm_tool = _assistant.tool_registry.get_tool("communication")
    if not comm_tool:
      raise HTTPException(status_code=500, detail="CommunicationTool not registered.")
    from tools.base import Action
    res = await comm_tool.execute(Action(
        action_id="client_threads",
        tool_name="communication",
        operation="list_client_threads",
        parameters={"client_id": client_id} if client_id else {}
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to list threads.")
    return res.data

  @app.get("/client/profiles")
  async def get_client_profile_endpoint(client_id: Optional[str] = None, email: Optional[str] = None):
    """Retrieves client profile and communication preferences."""
    comm_tool = _assistant.tool_registry.get_tool("communication")
    if not comm_tool:
      raise HTTPException(status_code=500, detail="CommunicationTool not registered.")
    from tools.base import Action
    params = {}
    if client_id:
      params["client_id"] = client_id
    if email:
      params["email"] = email
    res = await comm_tool.execute(Action(
        action_id="client_profile",
        tool_name="communication",
        operation="get_client_profile",
        parameters=params
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to get client profile.")
    return res.data

  @app.post("/client/create")
  async def create_client_endpoint(req: ClientCreateRequest):
    """Registers a new client profile with tone and company preferences."""
    comm_tool = _assistant.tool_registry.get_tool("communication")
    if not comm_tool:
      raise HTTPException(status_code=500, detail="CommunicationTool not registered.")
    from tools.base import Action
    res = await comm_tool.execute(Action(
        action_id="client_create",
        tool_name="communication",
        operation="create_client",
        parameters=req.model_dump()
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to create client.")
    return res.data

  # Linux-Grade Security Vault Endpoints
  @app.get("/vault/credentials")
  async def list_vault_credentials_endpoint():
    """Lists saved account logins with masked passwords."""
    vault_tool = _assistant.tool_registry.get_tool("vault")
    if not vault_tool:
      raise HTTPException(status_code=500, detail="VaultTool not registered.")
    from tools.base import Action
    res = await vault_tool.execute(Action(action_id="vault_list", tool_name="vault", operation="list_credentials", parameters={}))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to list credentials.")
    return res.data

  @app.post("/vault/credentials")
  async def save_vault_credential_endpoint(req: CredentialSaveRequest):
    """Saves or updates encrypted platform login credentials."""
    vault_tool = _assistant.tool_registry.get_tool("vault")
    if not vault_tool:
      raise HTTPException(status_code=500, detail="VaultTool not registered.")
    from tools.base import Action
    res = await vault_tool.execute(Action(
        action_id="vault_store",
        tool_name="vault",
        operation="store_credential",
        parameters=req.model_dump()
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to store credential.")
    return res.data

  @app.delete("/vault/credentials/{platform}")
  async def delete_vault_credential_endpoint(platform: str):
    """Removes a platform credential from the vault."""
    vault_tool = _assistant.tool_registry.get_tool("vault")
    if not vault_tool:
      raise HTTPException(status_code=500, detail="VaultTool not registered.")
    from tools.base import Action
    res = await vault_tool.execute(Action(action_id="vault_del", tool_name="vault", operation="delete_credential", parameters={"platform": platform}))
    if not res.success:
      raise HTTPException(status_code=404, detail=res.error or "Credential not found.")
    return res.data

  @app.post("/vault/2fa")
  async def submit_2fa_code_endpoint(req: TwoFactorSubmitRequest):
    """Registers the latest 2FA/OTP response code."""
    vault_tool = _assistant.tool_registry.get_tool("vault")
    if not vault_tool:
      raise HTTPException(status_code=500, detail="VaultTool not registered.")
    from tools.base import Action
    res = await vault_tool.execute(Action(action_id="vault_2fa", tool_name="vault", operation="submit_2fa_code", parameters=req.model_dump()))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to register 2FA code.")
    return res.data

  # Autonomous Web Builder & Deployment Endpoints
  @app.post("/web/scaffold")
  async def scaffold_website_endpoint(req: WebScaffoldRequest):
    """Scaffolds a complete responsive web application."""
    builder_tool = _assistant.tool_registry.get_tool("web_builder")
    if not builder_tool:
      raise HTTPException(status_code=500, detail="WebBuilderTool not registered.")
    from tools.base import Action
    res = await builder_tool.execute(Action(action_id="web_scaffold", tool_name="web_builder", operation="scaffold_website", parameters=req.model_dump()))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to scaffold website.")
    return res.data

  @app.post("/web/deploy")
  async def deploy_web_preview_endpoint(req: WebDeployRequest):
    """Deploys a local background preview HTTP server."""
    builder_tool = _assistant.tool_registry.get_tool("web_builder")
    if not builder_tool:
      raise HTTPException(status_code=500, detail="WebBuilderTool not registered.")
    from tools.base import Action
    res = await builder_tool.execute(Action(action_id="web_deploy", tool_name="web_builder", operation="deploy_preview", parameters=req.model_dump()))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to deploy preview server.")
    return res.data

  @app.post("/web/stop")
  async def stop_web_preview_endpoint(data: Dict[str, Any]):
    """Stops a running preview server."""
    builder_tool = _assistant.tool_registry.get_tool("web_builder")
    if not builder_tool:
      raise HTTPException(status_code=500, detail="WebBuilderTool not registered.")
    from tools.base import Action
    res = await builder_tool.execute(Action(action_id="web_stop", tool_name="web_builder", operation="stop_preview", parameters=data))
    return res.data

  @app.get("/web/deployments")
  async def list_web_deployments_endpoint():
    """Lists all scaffolded web projects and active live preview servers."""
    builder_tool = _assistant.tool_registry.get_tool("web_builder")
    if not builder_tool:
      raise HTTPException(status_code=500, detail="WebBuilderTool not registered.")
    from tools.base import Action
    res = await builder_tool.execute(Action(action_id="web_list", tool_name="web_builder", operation="list_deployments", parameters={}))
    return res.data

  # Autonomous Voice Assistant Endpoints
  @app.post("/voice/speak")
  async def voice_speak_endpoint(req: VoiceSpeakRequest):
    """Speaks text aloud using native speech synthesis."""
    voice_tool = _assistant.tool_registry.get_tool("voice")
    if not voice_tool:
      raise HTTPException(status_code=500, detail="VoiceTool not registered.")
    from tools.base import Action
    res = await voice_tool.execute(Action(
        action_id="voice_speak",
        tool_name="voice",
        operation="speak",
        parameters=req.model_dump()
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to speak text.")
    return res.data

  @app.post("/voice/synthesize")
  async def voice_synthesize_endpoint(req: VoiceSynthesizeRequest):
    """Synthesizes text into speech response data."""
    voice_tool = _assistant.tool_registry.get_tool("voice")
    if not voice_tool:
      raise HTTPException(status_code=500, detail="VoiceTool not registered.")
    from tools.base import Action
    res = await voice_tool.execute(Action(
        action_id="voice_synth",
        tool_name="voice",
        operation="synthesize_speech",
        parameters=req.model_dump()
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to synthesize speech.")
    return res.data

  @app.post("/voice/transcribe")
  async def voice_transcribe_endpoint(req: VoiceTranscribeRequest):
    """Transcribes voice query and processes intent."""
    voice_tool = _assistant.tool_registry.get_tool("voice")
    if not voice_tool:
      raise HTTPException(status_code=500, detail="VoiceTool not registered.")
    from tools.base import Action
    res = await voice_tool.execute(Action(
        action_id="voice_transcribe",
        tool_name="voice",
        operation="transcribe_audio",
        parameters=req.model_dump()
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to transcribe audio.")
    return res.data

  @app.get("/voice/voices")
  async def list_voices_endpoint():
    """Lists available system voices for speech synthesis."""
    voice_tool = _assistant.tool_registry.get_tool("voice")
    if not voice_tool:
      raise HTTPException(status_code=500, detail="VoiceTool not registered.")
    from tools.base import Action
    res = await voice_tool.execute(Action(
        action_id="voice_list",
        tool_name="voice",
        operation="list_voices",
        parameters={}
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to list voices.")
    return res.data

  @app.get("/voice/status")
  async def get_voice_status_endpoint():
    """Returns the operational status of the Voice Assistant engine."""
    voice_tool = _assistant.tool_registry.get_tool("voice")
    if not voice_tool:
      raise HTTPException(status_code=500, detail="VoiceTool not registered.")
    from tools.base import Action
    res = await voice_tool.execute(Action(
        action_id="voice_stat",
        tool_name="voice",
        operation="get_voice_status",
        parameters={}
    ))
    if not res.success:
      raise HTTPException(status_code=500, detail=res.error or "Failed to get voice status.")
    return res.data

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
