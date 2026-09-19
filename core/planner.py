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
      target_url = intent.entities.get("url")
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

    # Task Scheduling Plan
    if intent.intent_type == IntentType.SCHEDULE:
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
            " capture_page_screenshot)."
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
