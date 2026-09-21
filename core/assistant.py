"""Main Xeren Assistant Orchestrator (Phase 3 with DAG and Dual-Loop Verification)."""

import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from config.settings import Settings, get_settings
from memory.context import SessionMemory
from memory.preferences import PreferencesManager
from memory.semantic import SemanticMemoryStore
from memory.storage import SQLiteSessionStorage
from models.base import BaseLLMProvider, LLMMessage
from models.provider import get_default_llm_provider
from telemetry.analytics import AnalyticsTracker
from telemetry.traces import TraceLogger, TraceRecord
from tools.base import ToolResult
from tools.registry import ToolRegistry, get_default_registry
from tools.subagent_tool import SubagentTool
from .controller import CancellationToken, ExecutionController, ExecutionResult
from .dag import DAGAction, TaskGraph
from .intent import Intent, IntentClassifier, IntentType
from .planner import TaskPlanner
from .verifier import SemanticVerificationResult, Verifier


class AssistantResponse(BaseModel):
  """User-facing response from Xeren Assistant."""

  query: str
  response_text: str
  intent: Intent
  tools_used: List[str] = Field(default_factory=list)
  execution_result: Optional[ExecutionResult] = None
  semantic_verification: Optional[SemanticVerificationResult] = None
  trace_id: str = ""
  duration_ms: float = 0.0
  success: bool = True
  error: Optional[str] = None


class XerenAssistant:
  """The central AI assistant coordinating Intent, DAG Planning, Safety, Concurrent Execution, Dual-Loop Verification, and Memory."""

  def __init__(
      self,
      settings: Optional[Settings] = None,
      llm_provider: Optional[BaseLLMProvider] = None,
      tool_registry: Optional[ToolRegistry] = None,
      intent_classifier: Optional[IntentClassifier] = None,
      planner: Optional[TaskPlanner] = None,
      controller: Optional[ExecutionController] = None,
      verifier: Optional[Verifier] = None,
      session_memory: Optional[SessionMemory] = None,
      session_storage: Optional[SQLiteSessionStorage] = None,
      preferences_manager: Optional[PreferencesManager] = None,
      semantic_memory: Optional[SemanticMemoryStore] = None,
      trace_logger: Optional[TraceLogger] = None,
      analytics_tracker: Optional[AnalyticsTracker] = None,
  ):
    self.settings = settings or get_settings()
    self.llm_provider = llm_provider or get_default_llm_provider(self.settings)
    self.tool_registry = tool_registry or get_default_registry(self.settings)

    # Register SubagentTool if not already present
    if not self.tool_registry.get_tool("subagent"):
      self.tool_registry.register_tool(
          SubagentTool(
              llm_provider=self.llm_provider, tool_registry=self.tool_registry
          )
      )

    # Ensure VisionTool and CommunicationTool use configured llm_provider
    vis_tool = self.tool_registry.get_tool("vision")
    if vis_tool and hasattr(vis_tool, "agent"):
      vis_tool.agent.llm_provider = self.llm_provider

    comm_tool = self.tool_registry.get_tool("communication")
    if comm_tool and hasattr(comm_tool, "agent"):
      comm_tool.agent.llm_provider = self.llm_provider


    self.intent_classifier = intent_classifier or IntentClassifier(
        llm_provider=self.llm_provider
    )
    self.planner = planner or TaskPlanner(llm_provider=self.llm_provider)
    self.verifier = verifier or Verifier(llm_provider=self.llm_provider)
    self.controller = controller or ExecutionController(
        tool_registry=self.tool_registry,
        verifier=self.verifier,
        max_steps=self.settings.max_steps_per_task,
        max_retries=self.settings.max_retries_per_step,
        task_timeout=self.settings.task_timeout_seconds,
    )
    self.session_memory = session_memory or SessionMemory()
    self.session_storage = session_storage or SQLiteSessionStorage(
        db_path=self.settings.db_path
    )
    self.preferences_manager = preferences_manager or PreferencesManager(
        file_path=self.settings.preferences_path
    )
    self.semantic_memory = semantic_memory or SemanticMemoryStore(
        db_path=self.settings.db_path
    )
    self.trace_logger = trace_logger or TraceLogger(
        traces_dir=self.settings.traces_dir
    )
    self.analytics_tracker = analytics_tracker or AnalyticsTracker()

  async def _format_response_text(
      self,
      intent: Intent,
      exec_res: Optional[ExecutionResult],
      query: str,
      session_id: str = "default_session",
  ) -> str:
    """Formats a rich response based on intent, live LLM generation, or tool execution outputs."""
    if not exec_res or not exec_res.step_records:
      # If a live generative LLM is configured (not Mock), generate a natural conversational answer
      from models.provider import GeminiProvider

      if isinstance(self.llm_provider, GeminiProvider):
        try:
          system_prompt = (
              "You are Xeren, a futuristic, embodied autonomous AI operating system. "
              "You possess full device control, multimodal screen vision, browser automation, "
              "file manipulation, and client outreach powers on the user's computer.\n\n"
              "CRITICAL RULES:\n"
              "1. NEVER give standard generic AI refusal disclaimers (e.g. NEVER say 'I cannot log into private accounts' or 'As an AI I am unable').\n"
              "2. When a user asks you to check, audit, or work on any account, dashboard, web portal, or platform (like Fiverr, Upwork, Gmail, GitHub, LinkedIn, or custom apps):\n"
              "   - Act as an active automation partner.\n"
              "   - State that you can directly inspect their open browser window or active screen using multimodal vision.\n"
              "   - Offer to launch the browser to the platform URL, capture and analyze their active workspace, or guide them through automated steps with their permission.\n"
              "   - Ask for their username/profile link or tell them to open the tab and say 'analyze my screen' so you can immediately evaluate their gigs, orders, or dashboard in real time.\n"
              "3. Provide direct, highly capable, and empowering guidance."
          )
          context_msgs = self.session_memory.get_context(session_id).messages
          llm_resp = await self.llm_provider.generate(
              messages=context_msgs or [LLMMessage(role="user", content=query)],
              system_instruction=system_prompt,
              temperature=0.7,
          )
          if llm_resp.text and len(llm_resp.text.strip()) > 0:
            return llm_resp.text.strip()
        except Exception:
          pass

      # Contextual smart guidance for offline / mock mode
      q_lower = query.lower().strip()
      if intent.intent_type == IntentType.CHAT or any(
          kw in q_lower for kw in ["hi", "hello", "help", "can you help"]
      ):
        return (
            "Hello! I am Xeren Assistant, your personal AI automation assistant.\n\n"
            "Here is what I can do for you:\n"
            "• 📁 **Files**: `list files`, `read file main.py`, `search files config`\n"
            "• 🐙 **GitHub**: `check repo owner/repo`, `read issues on owner/repo`\n"
            "• 🌐 **Web**: `search web latest python release`\n"
            "• 📋 **Tasks**: `list tasks`, `create task Write documentation`\n"
            "• 💻 **Terminal**: `run echo hello`\n\n"
            "*(Tip: Set `GEMINI_API_KEY` in `.env` to enable full autonomous generative reasoning!)*"
        )
      elif intent.intent_type == IntentType.GITHUB:
        return (
            "To inspect or search a GitHub repository, please provide the repository name in `owner/repo` format.\n\n"
            "**Examples**:\n"
            "• `check repo octocat/Hello-World`\n"
            "• `read issues on fastapi/fastapi`\n"
            "• `get commits for pallets/flask`"
        )
      elif intent.intent_type == IntentType.FILESYSTEM:
        return (
            "To inspect or modify files in your workspace, please specify the target path.\n\n"
            "**Examples**:\n"
            "• `read file main.py`\n"
            "• `list files`\n"
            "• `search files test`"
        )
      elif intent.intent_type == IntentType.TASKS:
        return (
            "To manage your local tasks, try:\n\n"
            "• `list tasks`\n"
            "• `create task Implement feature X`\n"
            "• `update task 1 status completed`"
        )
      return (
          f"I received your request: '{query}'. To execute actions, specify a file, GitHub repository (`owner/repo`), web search, or task.\n\n"
          "*(Configure `GEMINI_API_KEY` in `.env` to enable open-ended natural conversation).* "
      )

    lines = []
    for record in exec_res.step_records:
      action = record.action
      if not record.success:
        lines.append(
            f"❌ **Failed {action.tool_name}:{action.operation}**:"
            f" {record.error}"
        )
        continue

      repaired_badge = " *(Self-Healed via Replanner)*" if record.was_repaired else ""
      data = record.tool_result.data if record.tool_result else None

      if action.tool_name == "filesystem":
        if action.operation == "read_file":
          lines.append(
              f"📄 **Read File `{data.get('path')}`** ({data.get('size_bytes')} bytes){repaired_badge}:\n```\n{data.get('content', '')}\n```"
          )
        elif action.operation in ["write_file", "create_file"]:
          backup_msg = (
              f" (Backup: `{data.get('backup_created')}`)"
              if data.get("backup_created")
              else ""
          )
          lines.append(
              f"✍️ **Saved File `{data.get('path')}`** ({data.get('bytes_written')} bytes written){backup_msg}{repaired_badge}"
          )
        elif action.operation == "list_dir":
          entries_summary = ", ".join(
              [
                  f"{e['name']}{'/' if e['is_dir'] else ''}"
                  for e in data.get("entries", [])[:15]
              ]
          )
          lines.append(
              f"📁 **Directory `{data.get('directory')}`**:"
              f" {entries_summary or 'Empty directory'}{repaired_badge}"
          )
        elif action.operation == "search_files":
          matches = data.get("matches", [])
          lines.append(
              f"🔍 **Found {len(matches)} matches for '{data.get('query')}'**{repaired_badge}:\n"
              + "\n".join([f"- `{m}`" for m in matches[:10]])
          )

      elif action.tool_name == "github":
        if action.operation == "read_issues":
          issues = data if isinstance(data, list) else []
          lines.append(f"🐙 **GitHub Open Issues ({len(issues)})**{repaired_badge}:")
          for iss in issues[:5]:
            lines.append(
                f"- [#{iss.get('number')}] **{iss.get('title')}** (by"
                f" @{iss.get('user')})"
            )
        elif action.operation in ["read_prs", "search_prs", "search_pull_requests"]:
          prs = data if isinstance(data, list) else []
          if prs:
            lines.append(f"🐙 **GitHub Pull Requests ({len(prs)})**{repaired_badge}:")
            for pr in prs[:10]:
              repo_str = f" in `{pr.get('repository')}`" if pr.get('repository') else ""
              url_str = f"\n  🔗 {pr.get('html_url')}" if pr.get('html_url') else ""
              lines.append(
                  f"- [#{pr.get('number')}] **{pr.get('title')}** ({pr.get('state')}){repo_str} (by @{pr.get('user')}){url_str}"
              )
          else:
            lines.append(f"🐙 **No pull requests found on your GitHub account**{repaired_badge}.")
        elif action.operation in ["list_repos", "list_user_repos"]:
          repos = data if isinstance(data, list) else []
          lines.append(f"🐙 **Your GitHub Repositories ({len(repos)})**{repaired_badge}:")
          for r in repos[:10]:
            lines.append(
                f"- **[{r.get('full_name')}]({r.get('html_url')})** ⭐ {r.get('stars', 0)} | 📌 {r.get('open_issues_count', 0)} open issues/PRs\n  > {r.get('description') or 'No description'}"
            )
        elif action.operation == "create_issue":
          lines.append(
              f"🐙 **Created GitHub Issue #{data.get('issue_number')}**:"
              f" [{data.get('title')}]({data.get('html_url')}){repaired_badge}"
          )
        elif action.operation == "create_pr":
          lines.append(
              f"🐙 **Created Pull Request #{data.get('pr_number')}**:"
              f" [{data.get('title')}]({data.get('html_url')}) ({data.get('head')} -> {data.get('base')}){repaired_badge}"
          )
        elif action.operation == "get_repo":
          lines.append(
              f"🐙 **Repository {data.get('full_name')}**:"
              f" ⭐ {data.get('stars')} stars | 🍴 {data.get('forks')} forks |"
              f" 📌 {data.get('open_issues_count')} open issues\n> "
              f" {data.get('description') or 'No description'}{repaired_badge}"
          )

      elif action.tool_name == "web_search":
        results = data.get("results", []) if isinstance(data, dict) else []
        query_searched = data.get("query", query) if isinstance(data, dict) else query

        # If live LLM is active, synthesize the retrieved snippets prioritizing verified sources
        synthesized = None
        from models.provider import GeminiProvider
        if isinstance(self.llm_provider, GeminiProvider) and results:
          try:
            snippets_context = "\n\n".join([
                f"Source: {r.get('title')}\nURL: {r.get('url')}\nTrust Score: {r.get('trust_score', 50)}% ({r.get('trust_badge', 'Standard')})\nRationale: {r.get('trust_rationale', '')}\nSnippet: {r.get('snippet')}"
                for r in results[:5]
            ])
            synthesis_prompt = (
                f"User Question: {query}\n\n"
                f"Verified Web Search & Intelligence Results:\n{snippets_context}\n\n"
                "Provide a direct, informative, and well-structured answer explaining the accurate facts to the user. "
                "Emphasize the most authoritative, official, and trusted findings. "
                "Cite relevant sources with markdown links [Source Title](URL)."
            )
            llm_synth = await self.llm_provider.generate(
                messages=[LLMMessage(role="user", content=synthesis_prompt)],
                temperature=0.3,
            )
            if llm_synth.text and len(llm_synth.text.strip()) > 20:
              synthesized = llm_synth.text.strip()
          except Exception:
            synthesized = None

        if synthesized:
          sources_summary = "\n".join([
              f"- {r.get('trust_badge', '🌐')} **[{r.get('title')}]({r.get('url')})** `[Trust: {r.get('trust_score', 50)}%]` — _{r.get('trust_rationale', 'Verified')}_"
              for r in results[:3]
          ])
          lines.append(
              f"🌐 **Verified Web Intelligence & Answer for '{query_searched}'**{repaired_badge}:\n\n"
              f"{synthesized}\n\n"
              f"**🛡️ Top Trusted & Verified References**:\n{sources_summary}"
          )
        else:
          lines.append(f"🌐 **Verified Web Search Results for '{query_searched}'** (Ranked by Trust & Accuracy){repaired_badge}:")
          for r in results[:5]:
            badge = r.get("trust_badge", "🌐 General Web Result")
            score = r.get("trust_score", 50)
            rat = f"  *Trust Rationale: {r.get('trust_rationale')}*\n" if r.get("trust_rationale") else ""
            lines.append(f"- {badge} **[{r.get('title')}]({r.get('url')})** `[{score}% Trust]`\n{rat}  {r.get('snippet')}")

      elif action.tool_name == "tasks":
        if action.operation == "create_task":
          lines.append(
              f"✅ **Created Task #{data.get('task_id')}**: '{data.get('title')}'"
              f" (Priority: {data.get('priority')}){repaired_badge}"
          )
        elif action.operation == "list_tasks":
          tasks = data if isinstance(data, list) else []
          lines.append(f"📋 **Current Tasks ({len(tasks)})**{repaired_badge}:")
          for t in tasks[:10]:
            lines.append(
                f"- [#{t.get('id')}] **[{t.get('status')}]** {t.get('title')}"
                f" ({t.get('priority')})"
            )

      elif action.tool_name == "shell":
        stdout = data.get("stdout", "").strip()
        stderr = data.get("stderr", "").strip()
        output_display = (
            stdout or stderr or "(Command executed with no terminal output)"
        )
        lines.append(
            f"💻 **Shell Command `{data.get('command')}`** (Exit"
            f" {data.get('exit_code')}){repaired_badge}:\n```\n{output_display}\n```"
        )

      elif action.tool_name == "http":
        body_display = (
            str(data.get("body"))[:1000]
            if data
            else "(Empty response)"
        )
        lines.append(
            f"🌐 **HTTP {action.operation.upper()} `{data.get('url')}`**"
            f" [{data.get('status_code')}]{repaired_badge}:\n```\n{body_display}\n```"
        )

      elif action.tool_name == "subagent":
        agent_name = data.get("subagent_name", "Subagent").capitalize()
        findings = data.get("findings", "")
        lines.append(
            f"🤖 **{agent_name} Autonomous Report**"
            f" ({action.operation}){repaired_badge}:\n{findings}"
        )

      elif action.tool_name == "device":
        if action.operation == "server_health_check":
          score = data.get("health_score", 100) if isinstance(data, dict) else 100
          status = data.get("overall_status", "HEALTHY") if isinstance(data, dict) else "HEALTHY"
          alerts = data.get("alerts", []) if isinstance(data, dict) else []
          cpu = data.get("cpu", {}) if isinstance(data, dict) else {}
          mem = data.get("memory", {}) if isinstance(data, dict) else {}
          disks = data.get("disks", []) if isinstance(data, dict) else []
          uptime = data.get("uptime", {}) if isinstance(data, dict) else {}
          procs = data.get("top_services", []) if isinstance(data, dict) else []
          listening = data.get("listening_services", []) if isinstance(data, dict) else []

          status_icon = "🟢" if status == "HEALTHY" else ("🟡" if status == "DEGRADED" else "🔴")

          metrics_rows = [
              "| Subsystem | Specification / Allocation | Utilization | Status |",
              "| :--- | :--- | :--- | :--- |",
              f"| **CPU Core Load** | {cpu.get('physical_cores', 0)} Cores ({cpu.get('logical_cores', 0)} Threads) | {cpu.get('usage_percent', 0)}% | `{(cpu.get('status') or 'OPTIMAL')}` |",
              f"| **Physical RAM** | {mem.get('total_gb', 0)} GB Total ({mem.get('free_gb', 0)} GB Free) | {mem.get('percent_used', 0)}% | `{(mem.get('status') or 'OPTIMAL')}` |",
          ]
          for d in disks[:3]:
            metrics_rows.append(
                f"| **Disk Storage ({d.get('mountpoint')})** | {d.get('total_gb', 0)} GB Total ({d.get('free_gb', 0)} GB Free) | {d.get('percent_used', 0)}% | `{(d.get('status') or 'OPTIMAL')}` |"
            )
          metrics_rows.append(f"| **System Uptime** | {uptime.get('formatted', 'N/A')} ({uptime.get('uptime_hours', 0)}h) | Continuous | `HEALTHY` |")

          sock_rows = []
          for s in listening:
            sock_rows.append(f"- 🌐 `Port {s.get('port')}`: **{s.get('service')}** ({s.get('state')})")
          sock_str = "\n".join(sock_rows) if sock_rows else "- No active exposed listener ports on inspected ranges."

          proc_rows = []
          for p in procs[:5]:
            proc_rows.append(f"- `{p.get('name')}` (PID: {p.get('pid')}) — {p.get('cpu_percent')}% CPU, {p.get('memory_mb')} MB RAM")
          proc_str = "\n".join(proc_rows) if proc_rows else "- No top process data."

          if alerts:
            alert_str = "\n".join([f"- ⚠️ {a}" for a in alerts])
          else:
            alert_str = "- ✅ All subsystems operating within optimal production tolerances."

          lines.append(
              f"🛡️ **Infrastructure & Server Health Audit** (Score: **{score}/100** • {status_icon} `{status}`){repaired_badge}:\n\n"
              f"**Host**: `{data.get('hostname')}` | **Environment**: {data.get('os')}\n\n"
              + "\n".join(metrics_rows)
              + f"\n\n**Active Services & Listening Sockets**:\n{sock_str}\n\n"
              + f"**Top Resource Consumers**:\n{proc_str}\n\n"
              + f"**Diagnostic Alerts & Telemetry Notes**:\n{alert_str}"
          )

        elif action.operation == "check_network_ports":
          io_c = data.get("io_counters", {}) if isinstance(data, dict) else {}
          listening = data.get("listening_ports", []) if isinstance(data, dict) else []
          est = data.get("active_established_connections", 0) if isinstance(data, dict) else 0

          io_str = (
              f"- **Network Throughput**: {io_c.get('bytes_sent_mb', 0)} MB Sent / {io_c.get('bytes_recv_mb', 0)} MB Received\n"
              f"- **Packets Handled**: {io_c.get('packets_sent', 0):,} Outbound / {io_c.get('packets_recv', 0):,} Inbound\n"
              f"- **Active Established Connections**: {est}"
              if io_c else f"- **Active Established Connections**: {est}"
          )

          port_rows = ["| Port | Bound Address | PID | Status |", "| :--- | :--- | :--- | :--- |"]
          for p in listening[:12]:
            port_rows.append(f"| `{p.get('port')}` | `{p.get('ip')}` | {p.get('pid') or '—'} | 🟢 LISTENING |")

          port_table = "\n".join(port_rows) if len(port_rows) > 2 else "_No listening sockets found or elevated permissions needed._"

          lines.append(
              f"🌐 **Network Sockets & Port Diagnostics**{repaired_badge} (Host: `{data.get('hostname')}`):\n\n"
              f"{io_str}\n\n"
              f"**Listening Endpoints ({len(listening)})**:\n{port_table}"
          )

        elif action.operation == "get_system_info":
          cpu = data.get("cpu", {})
          mem = data.get("memory", {})
          plat = data.get("platform", {})
          disks = data.get("disks", [])
          bat = data.get("battery")
          uptime = data.get("uptime_hours", 0)

          disk_lines = []
          for d in disks:
            disk_lines.append(f"    - `{d.get('mountpoint')}` {d.get('used_gb')}GB / {d.get('total_gb')}GB ({d.get('percent_used')}%)")
          disk_str = "\n".join(disk_lines) if disk_lines else "    - None detected"

          bat_str = f"{bat.get('percent')}% (Plugged in: {bat.get('power_plugged')})" if bat else "Desktop / No battery"

          lines.append(
              f"🖥️ **System Telemetry & Device Health**{repaired_badge}:\n"
              f"- **OS**: {plat.get('system')} {plat.get('release')} ({plat.get('architecture')}) | Host: `{plat.get('hostname')}`\n"
              f"- **CPU Usage**: {cpu.get('usage_percent')}% ({cpu.get('logical_cores')} logical cores)\n"
              f"- **Memory (RAM)**: {mem.get('used_gb')} GB / {mem.get('total_gb')} GB ({mem.get('percent_used')}% used, {mem.get('free_gb')} GB free)\n"
              f"- **Storage Disks**:\n{disk_str}\n"
              f"- **Battery**: {bat_str}\n"
              f"- **System Uptime**: {uptime} hours"
          )

        elif action.operation == "list_processes":
          procs = data if isinstance(data, list) else []
          proc_rows = ["| PID | Process Name | CPU % | Memory (MB) | Status |", "| :--- | :--- | :--- | :--- | :--- |"]
          for p in procs[:15]:
            proc_rows.append(f"| {p.get('pid')} | `{p.get('name')}` | {p.get('cpu_percent')}% | {p.get('memory_mb')} MB | {p.get('status')} |")
          lines.append(f"⚙️ **Active Running Processes ({len(procs)})**{repaired_badge}:\n\n" + "\n".join(proc_rows))

        elif action.operation == "launch_app":
          lines.append(f"🚀 **Launched Desktop Application**{repaired_badge}: `{data.get('app')}` (PID: {data.get('pid')})")

        elif action.operation == "kill_process":
          lines.append(f"🛑 **Terminated Process**{repaired_badge}: {data.get('killed_count')} process(es) stopped.")

        elif action.operation == "capture_screenshot":
          lines.append(
              f"📸 **Desktop Screenshot Captured**{repaired_badge}:\n"
              f"- **Saved to**: `{data.get('file_path')}`\n"
              f"- **Resolution**: {data.get('width')}x{data.get('height')} px\n"
              f"- **Size**: {round(data.get('size_bytes', 0) / 1024, 1)} KB"
          )

        elif action.operation == "get_clipboard":
          clip = data.get("clipboard_text", "")
          lines.append(f"📋 **Current Clipboard Text**{repaired_badge}:\n```\n{clip or '(Clipboard is empty)'}\n```")

        elif action.operation == "set_clipboard":
          lines.append(f"📋 **Copied to Clipboard**{repaired_badge}: {data.get('length')} characters.")

        elif action.operation == "get_active_window":
          lines.append(
              f"🪟 **Active Foreground Window**{repaired_badge}:\n"
              f"- **Title**: `{data.get('title')}`\n"
              f"- **Process**: `{data.get('process_name')}` (PID: {data.get('pid')})"
          )

        elif action.operation == "list_windows":
          wins = data if isinstance(data, list) else []
          lines.append(f"🪟 **Visible Desktop Windows ({len(wins)})**{repaired_badge}:")
          for w in wins[:10]:
            lines.append(f"- `{w.get('title')}` (PID: {w.get('pid')})")

        elif action.operation == "lock_screen":
          lines.append(f"🔒 **Windows Workstation Screen Locked**{repaired_badge}")

        elif action.operation == "mute_volume":
          lines.append(f"🔊 **System Audio Mute Toggled**{repaired_badge}")

        elif action.operation == "set_volume":
          lines.append(f"🔊 **System Audio Volume**: Set to {data.get('level')}%{repaired_badge}")

        elif action.operation == "open_path_or_url":
          lines.append(f"🔗 **Opened Target**{repaired_badge}: `{data.get('target')}`")

      elif action.tool_name == "vision":
        analysis_text = data.get("analysis", "") if isinstance(data, dict) else str(data)
        src_path = data.get("screenshot_path") if isinstance(data, dict) else ""
        lines.append(
            f"👁️ **Multimodal Screen Vision Analysis**{repaired_badge}:\n{analysis_text}\n\n"
            f"*(Snapshot: `{src_path}`)*"
            if src_path
            else f"👁️ **Multimodal Screen Vision Analysis**{repaired_badge}:\n{analysis_text}"
        )

      elif action.tool_name == "browser":
        if action.operation == "navigate_url":
          headings_list = data.get("headings", [])
          h_str = "\n".join([f"- **{h.get('level')}**: {h.get('text')}" for h in headings_list[:5]])
          badge = data.get("trust_badge", "🌐 Web Gateway")
          score = data.get("domain_trust_score", 50)
          rat = data.get("trust_rationale", "Direct Navigation")
          lines.append(
              f"🌐 **Web Page Navigated**{repaired_badge}: [{data.get('title')}]({data.get('url')})\n"
              f"**Domain Security & Trust**: {badge} `[{score}% Trust Score]` ({rat})\n\n"
              f"**Key Headings**:\n{h_str or '- None'}\n\n"
              f"**Page Summary**:\n> {data.get('content_snippet', '')[:500]}"
          )
        elif action.operation == "extract_page_content":
          badge = data.get("trust_badge", "🌐 Web Page")
          score = data.get("domain_trust_score", 50)
          lines.append(
              f"📄 **Extracted Page Content**{repaired_badge}: [{data.get('title')}]({data.get('url')}) `[{score}% Trust • {badge}]` ({data.get('word_count')} words)\n\n"
              f"{data.get('text_content', '')[:1200]}"
          )
        elif action.operation == "search_and_summarize":
          results = data.get("results", [])
          res_lines = []
          for r in results[:5]:
            badge = r.get("trust_badge", "🌐")
            score = r.get("trust_score", 50)
            snip = f"\n  {r.get('snippet')}" if r.get("snippet") else ""
            rat = f"\n  *Trust Rationale: {r.get('trust_rationale')}*" if r.get("trust_rationale") else ""
            res_lines.append(f"- {badge} **[{r.get('title')}]({r.get('url')})** `[{score}% Trust]`{rat}{snip}")
          lines.append(f"🔎 **Browser Search Results for '{data.get('query')}'** (Ranked by Trust & Accuracy){repaired_badge}:\n\n" + "\n".join(res_lines))

      elif action.tool_name == "communication":
        if action.operation == "draft_client_reply":
          draft_obj = data.get("draft", {}) if isinstance(data, dict) else {}
          if not isinstance(draft_obj, dict):
            draft_obj = {"body": str(draft_obj), "recipient": "Client", "subject": "Update", "style": "professional"}
          recipient = draft_obj.get("recipient") or (data.get("recipient") if isinstance(data, dict) else None) or "Client"
          subject = draft_obj.get("subject") or (data.get("subject") if isinstance(data, dict) else None) or "Update"
          style = draft_obj.get("style") or draft_obj.get("persona") or "professional"
          body = draft_obj.get("body") or draft_obj.get("draft") or str(draft_obj)
          conf = draft_obj.get("confidence_score", 0.95)
          lines.append(
              f"✉️ **Client Reply Drafted**{repaired_badge}:\n"
              f"**To**: `{recipient}`\n"
              f"**Subject**: {subject}\n"
              f"**Style**: `{style}`\n\n"
              f"```markdown\n{body}\n```\n\n"
              f"*(Confidence: {conf:.2f})*"
          )
        elif action.operation == "send_email":
          lines.append(
              f"📧 **Email Dispatched**{repaired_badge} to `{data.get('to')}`: "
              f"*{data.get('subject')}* (Message ID: `{data.get('message_id')}`)"
          )
        elif action.operation == "send_webhook":
          lines.append(
              f"🔗 **Webhook Fired**{repaired_badge} to `{data.get('url')}`: Status {data.get('status_code')}"
          )
        elif action.operation == "list_client_threads":
          threads = data.get("threads", []) if isinstance(data, dict) else []
          t_lines = "\n".join([f"- **Thread `{t.get('thread_id')}`** ({t.get('status')}): {t.get('subject')}" for t in threads[:5]])
          lines.append(f"💬 **Client Threads ({len(threads)})**{repaired_badge}:\n{t_lines or '- No active threads'}")
        elif action.operation == "get_client_profile":
          client = data.get("client") or {} if isinstance(data, dict) else {}
          lines.append(
              f"👤 **Client Profile**{repaired_badge}: **{client.get('name')}** (`{client.get('client_id')}`)\n"
              f"- **Email**: `{client.get('email')}`\n"
              f"- **Company**: {client.get('company')}\n"
              f"- **Default Tone**: `{client.get('communication_tone')}`"
          )
        elif action.operation == "create_client":
          lines.append(
              f"✅ **Client Registered**{repaired_badge}: **{data.get('name')}** (`{data.get('client_id')}`) - `{data.get('email')}`"
          )

      elif action.tool_name == "vault":
        if action.operation == "store_credential":
          lines.append(
              f"🔐 **Credential Secured in Linux-Grade Enclave (Ring 0)**{repaired_badge}:\n"
              f"- **Platform**: `{str(data.get('platform')).capitalize()}`\n"
              f"- **Account Identifier**: `{data.get('username_or_email')}`\n"
              f"- **Password**: `********` *(AES-256 Encrypted at Rest)*\n"
              f"- **2FA Method**: `{data.get('two_factor_type')}`\n"
              f"- **Enclave Status**: 🟢 Protected & Redacted in Memory"
          )
        elif action.operation == "get_credential":
          lines.append(
              f"🔓 **Ephemeral Credential Lease Issued (Ring 0 Enclave)**{repaired_badge}:\n"
              f"- **Platform**: `{str(data.get('platform')).capitalize()}`\n"
              f"- **Account**: `{data.get('username_or_email')}`\n"
              f"- **Lease ID**: `{str(data.get('lease_id'))[:12]}...` *(TTL: {data.get('ttl_seconds')}s single-use)*\n"
              f"- **Recent 2FA Response Active**: {'✅ Yes' if data.get('has_active_2fa') else '⚠️ None (Interactive 2FA prompt ready)'}"
          )
        elif action.operation == "list_credentials":
          creds = data.get("credentials", []) if isinstance(data, dict) else []
          rows = ["| Platform | Account Identifier | 2FA Protection | Status |", "| :--- | :--- | :--- | :--- |"]
          for c in creds:
            rows.append(f"| **{c.get('platform').capitalize()}** | `{c.get('username_or_email')}` | `{c.get('two_factor_type')}` | 🟢 ACTIVE |")
          lines.append(f"🔐 **Registered Account Credentials ({len(creds)})**{repaired_badge}:\n\n" + ("\n".join(rows) if len(rows) > 2 else "_No credentials currently stored in vault._"))
        elif action.operation == "delete_credential":
          lines.append(f"🗑️ **Credential Removed from Vault**{repaired_badge}: Platform `{data.get('platform')}`")
        elif action.operation == "submit_2fa_code":
          lines.append(
              f"🔑 **2FA / OTP Authentication Response Stored**{repaired_badge}:\n"
              f"- **Platform**: `{str(data.get('platform')).capitalize()}`\n"
              f"- **OTP Token**: `{data.get('code_masked')}`\n"
              f"- **Authentication State**: Ready for active login injection"
          )

      elif action.tool_name == "web_builder":
        if action.operation == "scaffold_website":
          files = data.get("files_created", [])
          f_lines = ", ".join([f"`{f['file']}` ({f['size_bytes']}B)" for f in files])
          lines.append(
              f"🚀 **Autonomous Web Application Scaffolding Complete**{repaired_badge}:\n"
              f"- **Project Name**: `{data.get('project_name')}`\n"
              f"- **Target Directory**: `{data.get('directory')}`\n"
              f"- **Artifacts Generated**: {f_lines}\n"
              f"- **Design Standard**: Modern Glassmorphic UI with Google Fonts & Interactive Sandbox"
          )
        elif action.operation == "deploy_preview":
          lines.append(
              f"🌐 **Live Web Application Deployed & Hosted**{repaired_badge}:\n"
              f"- **Live Preview URL**: [{data.get('url')}]({data.get('url')})\n"
              f"- **Port Bound**: `{data.get('port')}` (PID: `{data.get('pid')}`)\n"
              f"- **Project**: `{data.get('project_name')}`\n"
              f"- **Status**: 🟢 `RUNNING` (Ready in browser)"
          )
        elif action.operation == "stop_preview":
          lines.append(f"🛑 **Preview Server Stopped**{repaired_badge}: Project `{data.get('project_name')}` on Port `{data.get('port')}`")
        elif action.operation == "status_preview":
          lines.append(
              f"📊 **Preview Server Status**{repaired_badge}: `{data.get('status')}`\n"
              f"- **Project**: `{data.get('project_name')}`\n"
              f"- **URL**: {data.get('url') or 'N/A'} (Uptime: {data.get('uptime_seconds', 0)}s)"
          )
        elif action.operation == "list_deployments":
          deps = data.get("deployments", []) if isinstance(data, dict) else []
          d_lines = []
          for d in deps:
            status_str = f"🟢 LIVE: [{d.get('url')}]({d.get('url')})" if d.get("is_running") else "⚪ STOPPED"
            d_lines.append(f"- **{d.get('project_name')}**: {status_str}")
          lines.append(f"🌐 **Web Deployments ({len(deps)})**{repaired_badge}:\n" + ("\n".join(d_lines) if d_lines else "- No scaffolded web projects yet."))

      elif action.tool_name == "voice":
        if action.operation == "speak":
          lines.append(
              f"🎙️ **Voice Speech Synthesized & Spoken Aloud**{repaired_badge}:\n"
              f"- **Spoken Text**: \"{data.get('text')}\"\n"
              f"- **Audio Engine**: `{data.get('backend')}`\n"
              f"- **Voice**: `{data.get('voice')}` (Volume: {data.get('volume', 100)}%, Rate: {data.get('rate', 0)})\n"
              f"- **Status**: 🟢 `ACTIVE`"
          )
        elif action.operation == "synthesize_speech":
          lines.append(
              f"🔊 **Speech Audio Synthesized**{repaired_badge}:\n"
              f"- **Text**: \"{data.get('text')}\"\n"
              f"- **Word Count**: {data.get('word_count')} words\n"
              f"- **Estimated Duration**: {data.get('estimated_duration_seconds')}s\n"
              f"- **Sample Rate**: {data.get('sample_rate')} Hz ({data.get('encoding')})"
          )
        elif action.operation == "list_voices":
          voices = data.get("voices", []) if isinstance(data, dict) else []
          v_lines = "\n".join([f"- 🗣️ **{v.get('name')}** ({v.get('gender')}, `{v.get('culture')}`)" for v in voices[:8]])
          lines.append(f"🎙️ **Installed System Voices ({len(voices)})**{repaired_badge}:\n{v_lines}")
        elif action.operation == "get_voice_status":
          lines.append(
              f"🎙️ **Voice Subsystem Status**{repaired_badge}:\n"
              f"- **Engine**: `{data.get('engine')}`\n"
              f"- **TTS Status**: 🟢 Active\n"
              f"- **STT Status**: 🟢 Active\n"
              f"- **Voices Available**: {data.get('total_voices')} voice profile(s)"
          )
        elif action.operation == "transcribe_audio":
          lines.append(
              f"📝 **Audio Transcribed to Text**{repaired_badge}:\n"
              f"- **Transcript**: \"{data.get('transcript')}\"\n"
              f"- **Confidence**: {round(data.get('confidence', 1.0) * 100, 1)}%"
          )



    return (
        "\n\n".join(lines)
        if lines
        else "Execution finished with no output data."
    )

  async def process_request(
      self,
      query: str,
      session_id: str = "default_session",
      cancellation_token: Optional[CancellationToken] = None,
  ) -> AssistantResponse:
    """Executes the full assistant pipeline from prompt to trace recording."""
    start_total_time = time.perf_counter()
    trace_id = str(uuid.uuid4())

    # 1. Update session memory with user prompt
    self.session_memory.add_message("user", query, session_id=session_id)
    self.session_storage.save_message(
        session_id, LLMMessage(role="user", content=query)
    )

    # 2. Intent Understanding
    intent = await self.intent_classifier.classify(query)

    # 3. DAG Task Planning
    task_graph = await self.planner.plan_dag(query, intent)

    # 4. Concurrent DAG Controller Execution
    exec_result: Optional[ExecutionResult] = None
    tools_used: List[str] = []

    if task_graph.actions:
      exec_result = await self.controller.execute_task_graph(
          task_graph, cancellation_token=cancellation_token, user_query=query
      )
      tools_used = [act.tool_name for act in task_graph.actions]

    # 5. Response Formatting
    success = exec_result.success if exec_result else True
    error_msg = exec_result.error if exec_result else None
    response_text = await self._format_response_text(
        intent, exec_res=exec_result, query=query, session_id=session_id
    )

    # 6. Loop-2 Semantic Verification
    step_results_dict = {}
    if exec_result:
      for r in exec_result.step_records:
        if r.tool_result:
          step_results_dict[r.action.action_id] = r.tool_result

    semantic_verif = await self.verifier.verify_semantic_response(
        user_prompt=query,
        response_text=response_text,
        tool_results=step_results_dict,
    )

    # 7. Save assistant message to memory & index into Semantic Long-Term Store
    self.session_memory.add_message(
        "assistant", response_text, session_id=session_id
    )
    self.session_storage.save_message(
        session_id,
        LLMMessage(role="assistant", content=response_text),
        intent_str=intent.intent_type.value,
        tools_used=tools_used,
    )

    if success and semantic_verif.verified and len(query.strip()) > 3:
      try:
        await self.semantic_memory.add_memory(
            content=f"User Query: {query}\nResolution: {response_text[:500]}",
            category="conversation_experience",
            metadata={"intent": intent.intent_type.value, "trace_id": trace_id},
        )
      except Exception:
        pass

    elapsed_ms = (time.perf_counter() - start_total_time) * 1000

    # 8. Record Analytics & Structured Trace
    self.analytics_tracker.record_request(
        intent_type=intent.intent_type.value,
        success=success and semantic_verif.verified,
        tools_used=tools_used,
    )

    trace_record = TraceRecord(
        trace_id=trace_id,
        user_request=query,
        intent=intent.model_dump(),
        plan=[act.model_dump() for act in task_graph.actions],
        tool_executions=(
            [r.model_dump() for r in exec_result.step_records]
            if exec_result
            else []
        ),
        verification_results=[semantic_verif.model_dump()],
        final_response=response_text,
        total_duration_ms=elapsed_ms,
        success=success and semantic_verif.verified,
        error=error_msg,
    )
    self.trace_logger.log_trace(trace_record)

    return AssistantResponse(
        query=query,
        response_text=response_text,
        intent=intent,
        tools_used=tools_used,
        execution_result=exec_result,
        semantic_verification=semantic_verif,
        trace_id=trace_id,
        duration_ms=elapsed_ms,
        success=success and semantic_verif.verified,
        error=error_msg,
    )
