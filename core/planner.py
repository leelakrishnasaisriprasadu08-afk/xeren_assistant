"""Task Planner generating DAG and Action plans."""

import json
import re
from typing import Any, Dict, List, Optional
from models.base import BaseLLMProvider, LLMMessage
from security.policies import get_operation_policy
from tools.base import Action
from .dag import DAGAction, TaskGraph
from .intent import Intent, IntentType


class TaskPlanner:
  """Generates DAG task graphs and sequential action plans conforming to the strict Action schema."""

  def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
    self.llm_provider = llm_provider

  def create_action(
      self,
      action_id: str,
      tool_name: str,
      operation: str,
      parameters: Dict[str, Any],
      reason: str,
      timeout: float = 10.0,
      depends_on: Optional[List[str]] = None,
  ) -> DAGAction:
    """Helper creating a validated DAGAction with auto-populated policy metadata."""
    policy = get_operation_policy(tool_name, operation)
    return DAGAction(
        action_id=action_id,
        tool_name=tool_name,
        operation=operation,
        parameters=parameters,
        required_permission=policy.permission_level,
        risk_level=policy.risk_level,
        reason=reason,
        timeout=timeout,
        depends_on=depends_on or [],
    )

  def _plan_deterministic_dag(
      self, query: str, intent: Intent
  ) -> Optional[TaskGraph]:
    """Deterministic DAG plan generator with dependency graphs."""
    q = query.strip()
    entities = intent.entities
    graph = TaskGraph()

    # Filesystem Plan
    if intent.intent_type == IntentType.FILESYSTEM:
      file_match = re.search(
          r'(?:read|show|cat|view|open)\s+(?:file\s+)?[\'"]?([^\s\'"]+\.[a-zA-Z0-9]+)[\'"]?',
          q,
          re.IGNORECASE,
      )
      if file_match:
        target_file = file_match.group(1)
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="filesystem",
                operation="read_file",
                parameters={"path": target_file},
                reason=f"Read requested file '{target_file}' from workspace",
            )
        )
        return graph

      if any(kw in q.lower() for kw in ["list files", "ls", "show files"]):
        dir_match = re.search(
            r'(?:in|dir|directory)\s+[\'"]?([^\s\'"]+)[\'"]?', q, re.IGNORECASE
        )
        target_dir = dir_match.group(1) if dir_match else "."
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="filesystem",
                operation="list_dir",
                parameters={"path": target_dir},
                reason=f"List directory contents of '{target_dir}'",
            )
        )
        return graph

      search_match = re.search(
          r'(?:search|find)\s+(?:files?\s+)?(?:for\s+)?[\'"]?([^\'"]+)[\'"]?',
          q,
          re.IGNORECASE,
      )
      if search_match:
        search_query = search_match.group(1).replace("files", "").strip()
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="filesystem",
                operation="search_files",
                parameters={"query": search_query},
                reason=f"Search workspace files for '{search_query}'",
            )
        )
        return graph

    # GitHub Plan
    if intent.intent_type == IntentType.GITHUB:
      repo = entities.get("repo")
      if not repo:
        repo_match = re.search(r"([\w\-]+/[\w\-]+)", q)
        if repo_match:
          repo = repo_match.group(1)

      if repo:
        if "issue" in q.lower():
          graph.add_action(
              self.create_action(
                  action_id="act_01",
                  tool_name="github",
                  operation="read_issues",
                  parameters={"repo": repo, "limit": 10},
                  reason=f"Fetch open issues from GitHub repository '{repo}'",
              )
          )
          return graph
        elif "commit" in q.lower():
          graph.add_action(
              self.create_action(
                  action_id="act_01",
                  tool_name="github",
                  operation="get_commits",
                  parameters={"repo": repo, "limit": 10},
                  reason=f"Fetch commit history from GitHub repository '{repo}'",
              )
          )
          return graph
        elif any(kw in q.lower() for kw in ["pull request", "pr", "prs", "pulls"]):
          graph.add_action(
              self.create_action(
                  action_id="act_01",
                  tool_name="github",
                  operation="read_prs",
                  parameters={"repo": repo, "limit": 10},
                  reason=f"Fetch pull requests from GitHub repository '{repo}'",
              )
          )
          return graph
        else:
          graph.add_action(
              self.create_action(
                  action_id="act_01",
                  tool_name="github",
                  operation="get_repo",
                  parameters={"repo": repo},
                  reason=f"Fetch repository metadata for '{repo}'",
              )
          )
          return graph
      else:
        # User did not specify a repo (e.g. "check my github", "check repos with pull request")
        if any(kw in q.lower() for kw in ["pull request", "pr", "prs", "pulls"]):
          graph.add_action(
              self.create_action(
                  action_id="act_01",
                  tool_name="github",
                  operation="search_prs",
                  parameters={},
                  reason="Search pull requests across user's GitHub repositories",
              )
          )
          return graph
        else:
          graph.add_action(
              self.create_action(
                  action_id="act_01",
                  tool_name="github",
                  operation="list_repos",
                  parameters={"limit": 10},
                  reason="List repositories from authenticated GitHub user account",
              )
          )
          return graph

    # Web Search Plan
    if intent.intent_type == IntentType.WEB_SEARCH:
      clean_query = re.sub(
          r"^(?:search the web for|search web for|search for|google|look up)\s+",
          "",
          q,
          flags=re.IGNORECASE,
      ).strip()
      graph.add_action(
          self.create_action(
              action_id="act_01",
              tool_name="web_search",
              operation="search",
              parameters={"query": clean_query or q, "max_results": 5},
              reason=f"Search the web for '{clean_query or q}'",
          )
      )
      return graph

    # Task Management Plan
    if intent.intent_type == IntentType.TASKS:
      if any(
          kw in q.lower()
          for kw in ["list tasks", "show tasks", "my tasks", "get tasks"]
      ):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="tasks",
                operation="list_tasks",
                parameters={},
                reason="List current tasks from local database",
            )
        )
        return graph
      elif any(kw in q.lower() for kw in ["create task", "add task", "new task"]):
        task_title = re.sub(
            r"^(?:create task|add task|new task)\s+(?:to\s+)?",
            "",
            q,
            flags=re.IGNORECASE,
        ).strip()
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="tasks",
                operation="create_task",
                parameters={
                    "title": task_title or "New Task",
                    "description": f"Created from prompt: '{q}'",
                },
                reason=f"Create new local task '{task_title or 'New Task'}'",
            )
        )
        return graph

    # Device and OS Automation Plan
    if intent.intent_type == IntentType.DEVICE:
      # 0. Server Health Check & Infrastructure Audit
      if any(
          kw in q.lower()
          for kw in [
              "server check",
              "check server",
              "server health",
              "infrastructure check",
              "system health check",
              "system health",
              "server status",
              "server audit",
              "system diagnostics",
              "diagnostics",
              "server performance",
          ]
      ):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="server_health_check",
                parameters={},
                reason="Execute comprehensive production-grade server health and infrastructure audit",
            )
        )
        return graph

      # 0b. Network Port & Socket Inspection
      if any(
          kw in q.lower()
          for kw in [
              "check ports",
              "network ports",
              "open ports",
              "listening ports",
              "port check",
              "network sockets",
              "active connections",
          ]
      ):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="check_network_ports",
                parameters={},
                reason="Inspect active listening network ports, socket connection counts, and throughput",
            )
        )
        return graph

      # 1. System Info / Telemetry
      if any(
          kw in q.lower()
          for kw in [
              "system stats",
              "system info",
              "cpu",
              "ram",
              "memory",
              "disk space",
              "battery",
              "device info",
              "hardware",
          ]
      ):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="get_system_info",
                parameters={},
                reason="Gather real-time CPU, RAM, Disk, Battery, and OS telemetry",
            )
        )
        return graph

      # 2. Screenshot
      if any(
          kw in q.lower()
          for kw in ["screenshot", "capture screen", "capture desktop"]
      ):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="capture_screenshot",
                parameters={},
                reason="Capture full screen desktop screenshot",
            )
        )
        return graph

      # 3. Process Management
      if any(
          kw in q.lower()
          for kw in ["kill process", "terminate process", "stop process"]
      ):
        proc_match = re.search(
            r'(?:kill|terminate|stop)\s+process\s+[\'"]?([^\s\'"]+)[\'"]?',
            q,
            re.IGNORECASE,
        )
        target = proc_match.group(1) if proc_match else None
        params: Dict[str, Any] = {}
        if target:
          if target.isdigit():
            params["pid"] = int(target)
          else:
            params["name"] = target
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="kill_process",
                parameters=params,
                reason=f"Terminate process '{target or 'specified'}'",
            )
        )
        return graph

      if any(
          kw in q.lower()
          for kw in ["list processes", "running processes", "show processes", "task manager"]
      ):
        sort = "cpu" if "cpu" in q.lower() else "memory"
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="list_processes",
                parameters={"limit": 15, "sort_by": sort},
                reason=f"List active processes sorted by {sort}",
            )
        )
        return graph

      # 4. Clipboard
      if any(
          kw in q.lower()
          for kw in ["get clipboard", "read clipboard", "paste clipboard"]
      ):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="get_clipboard",
                parameters={},
                reason="Read current text from system clipboard",
            )
        )
        return graph

      if any(
          kw in q.lower()
          for kw in ["set clipboard", "copy to clipboard"]
      ):
        text_match = re.search(
            r'(?:copy to clipboard|set clipboard)\s+[\'"]?(.+)[\'"]?',
            q,
            re.IGNORECASE,
        )
        text_to_copy = text_match.group(1).strip("'\"") if text_match else ""
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="set_clipboard",
                parameters={"text": text_to_copy},
                reason="Copy text to system clipboard",
            )
        )
        return graph

      # 5. Windows & Lock
      if any(kw in q.lower() for kw in ["lock screen", "lock pc", "lock computer"]):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="lock_screen",
                parameters={},
                reason="Lock the Windows workstation screen",
            )
        )
        return graph

      if any(kw in q.lower() for kw in ["active window", "focused window"]):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="get_active_window",
                parameters={},
                reason="Inspect active foreground desktop window",
            )
        )
        return graph

      if any(kw in q.lower() for kw in ["list windows", "open windows"]):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="list_windows",
                parameters={},
                reason="List visible top-level application windows",
            )
        )
        return graph

      # 6. Audio / Volume
      if any(kw in q.lower() for kw in ["mute volume", "unmute", "mute audio"]):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="mute_volume",
                parameters={},
                reason="Toggle mute on system audio",
            )
        )
        return graph

      # 7. App Launching
      app_match = re.search(
          r'(?:open|launch|run|start)\s+(?:app\s+|application\s+)?[\'"]?([a-zA-Z0-9_\-\.\s]+)[\'"]?',
          q,
          re.IGNORECASE,
      )
      if app_match:
        app_name = app_match.group(1).strip()
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="launch_app",
                parameters={"app_name": app_name},
                reason=f"Launch desktop application '{app_name}'",
            )
        )
        return graph

    # Vision & Screen Analysis Plan
    if intent.intent_type == IntentType.VISION:
      if any(kw in q.lower() for kw in ["extract text", "read text", "read error", "diagnose error", "ocr"]):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="vision",
                operation="extract_screen_text",
                parameters={},
                reason="Extract all visible text, logs, and error dialogs from active screen",
            )
        )
        return graph
      else:
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="vision",
                operation="analyze_screen",
                parameters={"prompt": q},
                reason=f"Analyze active screen with visual multimodal model for query: '{q}'",
            )
        )
        return graph

    # Browser & Autonomous Web Crawling Plan
    if intent.intent_type == IntentType.BROWSER:
      platform = intent.entities.get("platform")
      target_url = intent.entities.get("url")

      if platform:
        # Step 1: Check active desktop window for the platform/browser
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="device",
                operation="get_active_window",
                parameters={},
                reason=f"Inspect active desktop foreground window for {platform.capitalize()}",
            )
        )
        # Step 2: Use multimodal vision to capture and analyze open profile, dashboard, or browser tab
        graph.add_action(
            self.create_action(
                action_id="act_02",
                tool_name="vision",
                operation="analyze_screen",
                parameters={"prompt": f"Inspect the active {platform.capitalize()} window, account dashboard, gigs, statistics, or open web tabs and provide detailed diagnostic advice for: '{q}'"},
                depends_on=["act_01"],
                reason=f"Visually analyze active {platform.capitalize()} workspace and account dashboard",
            )
        )
        # Step 3: Headless navigation/summarization
        if target_url:
          graph.add_action(
              self.create_action(
                  action_id="act_03",
                  tool_name="browser",
                  operation="navigate_url",
                  parameters={"url": target_url},
                  depends_on=["act_01"],
                  reason=f"Navigate to {platform.capitalize()} gateway ({target_url}) to extract live metadata",
              )
          )
        return graph

      if not target_url:
        url_match = re.search(r'(https?://[^\s\'"]+)', q)
        if url_match:
          target_url = url_match.group(1)

      if target_url:
        if any(kw in q.lower() for kw in ["extract", "scrape", "article", "full text"]):
          graph.add_action(
              self.create_action(
                  action_id="act_01",
                  tool_name="browser",
                  operation="extract_page_content",
                  parameters={"url": target_url},
                  reason=f"Extract structured article text and headings from '{target_url}'",
              )
          )
          return graph
        else:
          graph.add_action(
              self.create_action(
                  action_id="act_01",
                  tool_name="browser",
                  operation="navigate_url",
                  parameters={"url": target_url},
                  reason=f"Navigate to '{target_url}' and inspect page structure",
              )
          )
          return graph
      else:
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="browser",
                operation="search_and_summarize",
                parameters={"query": q},
                reason=f"Perform autonomous web research and extraction for '{q}'",
            )
        )
        return graph

    # Client Communications & Outreach Plan
    if intent.intent_type == IntentType.CLIENT:
      if any(kw in q.lower() for kw in ["list client threads", "show client threads", "client threads"]):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="communication",
                operation="list_client_threads",
                parameters={},
                reason="Retrieve active client inquiry threads and drafts",
            )
        )
        return graph

      elif any(kw in q.lower() for kw in ["client profile", "get client", "lookup client"]):
        client_name = intent.entities.get("client_name") or "Client"
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="communication",
                operation="get_client_profile",
                parameters={"name": client_name},
                reason=f"Look up client profile for '{client_name}'",
            )
        )
        return graph

      elif any(kw in q.lower() for kw in ["create client", "add client", "new client"]):
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="communication",
                operation="create_client",
                parameters={"name": intent.entities.get("client_name", "New Client"), "email": "client@example.com"},
                reason="Register new client profile",
            )
        )
        return graph

      else:
        client_name = intent.entities.get("client_name") or "Client"
        persona = "technical" if "technical" in q.lower() else ("concise" if "concise" in q.lower() else "professional")
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="communication",
                operation="draft_client_reply",
                parameters={
                    "client_name": client_name,
                    "inquiry": q,
                    "persona": persona,
                },
                reason=f"Draft tailored client response for '{client_name}' ({persona} tone)",
            )
        )
        return graph

    # Linux-Grade Credential Vault & Automated Account Login Plan
    if intent.intent_type == IntentType.VAULT:
      sub_type = intent.entities.get("sub_type", "account_login")
      platform = intent.entities.get("platform") or "linkedin"

      if sub_type == "store_credential":
        # Extract password if present
        pass_match = re.search(r'(?:password|pass)\s*(?:is|:)?\s*[\'"]?([^\s\'"]+)[\'"]?', q)
        pwd = pass_match.group(1) if pass_match else "SecurePass123!"
        username = intent.entities.get("username_or_email") or "user@example.com"
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="vault",
                operation="store_credential",
                parameters={
                    "platform": platform,
                    "username": username,
                    "password": pwd,
                    "two_factor_type": "prompt" if "2fa" in q else "none",
                },
                reason=f"Store encrypted credentials for platform '{platform}'",
            )
        )
        return graph

      elif sub_type == "list_credentials":
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="vault",
                operation="list_credentials",
                parameters={},
                reason="List registered vault credentials with masked secrets",
            )
        )
        return graph

      elif sub_type == "delete_credential":
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="vault",
                operation="delete_credential",
                parameters={"platform": platform},
                reason=f"Delete stored credentials for '{platform}'",
            )
        )
        return graph

      elif sub_type == "submit_2fa_code":
        code = intent.entities.get("code") or "123456"
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="vault",
                operation="submit_2fa_code",
                parameters={"platform": platform, "code": code},
                reason=f"Register active 2FA/OTP code for '{platform}'",
            )
        )
        return graph

      else:
        # Automated multi-step login workflow:
        # 1. Fetch credentials from vault (Ring 0 single-use lease)
        # 2. Navigate browser to platform portal
        # 3. Multimodal vision screen audit to verify session and 2FA prompt
        plat_urls = {
            "linkedin": "https://www.linkedin.com/login",
            "gmail": "https://mail.google.com",
            "upwork": "https://www.upwork.com/ab/account-security/login",
            "fiverr": "https://www.fiverr.com/login",
            "github": "https://github.com/login",
        }
        target_url = plat_urls.get(platform, f"https://www.{platform}.com")

        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="vault",
                operation="get_credential",
                parameters={"platform": platform},
                reason=f"Retrieve encrypted login credentials and lease for '{platform}'",
            )
        )
        graph.add_action(
            self.create_action(
                action_id="act_02",
                tool_name="browser",
                operation="navigate_url",
                parameters={"url": target_url},
                reason=f"Navigate to {platform.capitalize()} authentication gateway",
                depends_on=["act_01"],
            )
        )
        graph.add_action(
            self.create_action(
                action_id="act_03",
                tool_name="vision",
                operation="analyze_screen",
                parameters={"prompt": f"Verify active login session or 2FA verification prompt for {platform.capitalize()}"},
                reason="Inspect active visual state to confirm authentication and 2FA challenge",
                depends_on=["act_02"],
            )
        )
        return graph

    # Autonomous Web Builder & App Deployment Plan
    if intent.intent_type == IntentType.WEB_BUILDER:
      sub_type = intent.entities.get("sub_type", "scaffold_website")
      if sub_type in ["deploy_preview", "start_preview"]:
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="web_builder",
                operation="deploy_preview",
                parameters={"project_name": "xeren_web_app"},
                reason="Deploy web application to local background preview server",
            )
        )
        return graph

      elif sub_type in ["stop_preview", "stop_web"]:
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="web_builder",
                operation="stop_preview",
                parameters={"project_name": "xeren_web_app"},
                reason="Stop running local preview server",
            )
        )
        return graph

      elif sub_type == "list_deployments":
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="web_builder",
                operation="list_deployments",
                parameters={},
                reason="List active web deployments and live URLs",
            )
        )
        return graph

      else:
        # Full end-to-end scaffolding + live preview deployment DAG
        clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", q[:25].strip().lower()).strip("_") or "xeren_web_app"
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="web_builder",
                operation="scaffold_website",
                parameters={"prompt": q, "project_name": clean_name},
                reason=f"Generate complete web application source files for '{clean_name}'",
            )
        )
        graph.add_action(
            self.create_action(
                action_id="act_02",
                tool_name="web_builder",
                operation="deploy_preview",
                parameters={"project_name": clean_name},
                reason=f"Launch live local background preview server for '{clean_name}'",
                depends_on=["act_01"],
            )
        )
        return graph

    # Voice Assistant & Speech Synthesis Plan
    if intent.intent_type == IntentType.VOICE:
      sub_type = intent.entities.get("sub_type", "speak")
      if sub_type == "list_voices":
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="voice",
                operation="list_voices",
                parameters={},
                reason="List available Text-to-Speech system voices",
            )
        )
        return graph

      elif sub_type == "get_voice_status":
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="voice",
                operation="get_voice_status",
                parameters={},
                reason="Check voice synthesis engine status and voice profiles",
            )
        )
        return graph

      elif sub_type == "synthesize_speech":
        clean_text = q
        for prefix in ["synthesize speech for", "synthesize voice for", "synthesize speech", "synthesize"]:
          if q.lower().startswith(prefix):
            clean_text = q[len(prefix):].strip()
            break
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="voice",
                operation="synthesize_speech",
                parameters={"text": clean_text or "Speech synthesis test"},
                reason="Synthesize speech audio metadata and phonetic parameters",
            )
        )
        return graph

      else:
        clean_text = q
        for prefix in ["speak response", "speak aloud", "read aloud", "read out loud", "say out loud", "speak this", "speak", "say"]:
          if q.lower().startswith(prefix):
            clean_text = q[len(prefix):].strip()
            break
        graph.add_action(
            self.create_action(
                action_id="act_01",
                tool_name="voice",
                operation="speak",
                parameters={"text": clean_text or "Hello! Xeren voice assistant active."},
                reason="Speak response aloud using system audio synthesis",
            )
        )
        return graph
      graph.add_action(
          self.create_action(
              action_id="act_01",
              tool_name="tasks",
              operation="create_task",
              parameters={
                  "title": f"Scheduled Job: {q}",
                  "description": f"Scheduled task created from prompt: '{q}'",
                  "priority": "high",
              },
              reason=f"Register scheduled workflow for '{q}'",
          )
      )
      return graph

    # Composite DAG Workflow (GitHub check + task creation with dependency)
    if intent.intent_type == IntentType.COMPOSITE:
      repo_match = re.search(r"([\w\-]+/[\w\-]+)", q)
      repo = repo_match.group(1) if repo_match else "owner/repo"
      graph.add_action(
          self.create_action(
              action_id="act_01",
              tool_name="github",
              operation="read_issues",
              parameters={"repo": repo, "limit": 5},
              reason=f"Retrieve issues from {repo}",
          )
      )
      graph.add_action(
          self.create_action(
              action_id="act_02",
              tool_name="tasks",
              operation="create_task",
              parameters={
                  "title": f"Review {repo} issues",
                  "description": f"Follow-up task created for {repo}",
                  "priority": "high",
              },
              reason="Save follow-up task to local task storage",
              depends_on=["act_01"],
          )
      )
      return graph

    return None

  async def plan_dag(self, query: str, intent: Intent) -> TaskGraph:
    """Generates a TaskGraph DAG for the controller."""
    if intent.intent_type == IntentType.CHAT:
      return TaskGraph()

    det_graph = self._plan_deterministic_dag(query, intent)
    if det_graph:
      return det_graph

    # LLM fallback
    graph = TaskGraph()
    if self.llm_provider:
      try:
        system_prompt = (
            "You are the Task Planner for Xeren Assistant. Available tools:"
            " filesystem (read_file, list_dir, search_files, write_file,"
            " create_file), github (get_repo, read_issues, read_prs,"
            " get_commits, create_issue, create_pr, list_repos, search_prs),"
            " web_search (search, fetch_page), tasks (create_task, list_tasks,"
            " update_task, get_task), codebase (index_workspace, find_symbol,"
            " get_file_outline, get_call_graph), patch (generate_patch,"
            " apply_patch), device (get_system_info, list_processes,"
            " kill_process, launch_app, open_path_or_url, get_clipboard,"
            " set_clipboard, capture_screenshot, get_active_window,"
            " list_windows, lock_screen, mute_volume, set_volume),"
            " vision (analyze_screen, extract_screen_text, inspect_image_file),"
            " browser (navigate_url, extract_page_content, search_and_summarize,"
            " capture_page_screenshot),"
            " communication (draft_client_reply, send_email, send_webhook,"
            " list_client_threads, get_client_profile, create_client)."
            " Return a JSON array of Action objects with keys: action_id,"
            " tool_name, operation, parameters, reason, timeout, depends_on."
        )
        resp = await self.llm_provider.generate(
            messages=[LLMMessage(role="user", content=query)],
            system_instruction=system_prompt,
            temperature=0.0,
        )
        clean_text = resp.text.strip()
        if "```json" in clean_text:
          clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text:
          clean_text = clean_text.split("```")[1].split("```")[0].strip()

        raw_actions = json.loads(clean_text)
        for i, item in enumerate(raw_actions):
          action_id = item.get("action_id", f"act_{i+1:02d}")
          graph.add_action(
              self.create_action(
                  action_id=action_id,
                  tool_name=item.get("tool_name", ""),
                  operation=item.get("operation", ""),
                  parameters=item.get("parameters", {}),
                  reason=item.get("reason", ""),
                  timeout=float(item.get("timeout", 10.0)),
                  depends_on=item.get("depends_on", []),
              )
          )
        return graph
      except Exception:
        pass

    return graph

  async def plan(self, query: str, intent: Intent) -> List[Action]:
    """Sequential plan generator for backward compatibility."""
    graph = await self.plan_dag(query, intent)
    return list(graph.actions)
