"""Intent understanding and parameter extraction."""

from enum import Enum
import json
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from models.base import BaseLLMProvider, LLMMessage


class IntentType(str, Enum):
  CHAT = "chat"
  FILESYSTEM = "filesystem"
  GITHUB = "github"
  WEB_SEARCH = "web_search"
  TASKS = "tasks"
  DEVICE = "device"
  SCHEDULE = "schedule"
  VISION = "vision"
  BROWSER = "browser"
  CLIENT = "client"
  VAULT = "vault"
  WEB_BUILDER = "web_builder"
  COMPOSITE = "composite"


class Intent(BaseModel):
  """Structured intent representation of user request."""

  intent_type: IntentType
  confidence: float = 1.0
  entities: Dict[str, Any] = Field(default_factory=dict)
  primary_tool: Optional[str] = None
  summary: str = ""


class IntentClassifier:
  """Understands user intent using fast deterministic pattern matching with LLM fallback."""

  def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
    self.llm_provider = llm_provider

  def _classify_rules(self, query: str) -> Optional[Intent]:
    """Fast deterministic rule-based classifier."""
    q = query.lower().strip()

    # Linux-Grade Security Vault & Account Login Automation
    if any(
        kw in q
        for kw in [
            "save my login",
            "store credential",
            "store login",
            "save login",
            "save password",
            "remember my login",
            "remember login",
            "list credentials",
            "list saved logins",
            "show saved accounts",
            "show credentials",
            "delete credential",
            "delete saved login",
            "remove credential",
            "2fa code",
            "two factor code",
            "otp is",
            "my 2fa",
            "submit 2fa",
        ]
    ) or (
        any(p in q for p in ["linkedin", "gmail", "upwork", "fiverr", "github", "portal"])
        and any(action in q for action in ["login with", "login by", "by my gmail", "with password", "using my credentials", "stored login", "account by my"])
    ):
      entities = {}
      # Detect platform
      for p in ["linkedin", "gmail", "upwork", "fiverr", "github", "discord", "slack", "trello", "notion"]:
        if p in q:
          entities["platform"] = p
          break

      # Detect 2FA code
      if any(kw in q for kw in ["2fa", "two factor", "otp", "code", "pin", "token", "verification"]):
        code_match = re.search(r'\b([0-9]{4,8})\b', q)
        if code_match:
          entities["code"] = code_match.group(1)
          entities["sub_type"] = "submit_2fa_code"
        elif any(kw in q for kw in ["save", "store", "remember"]):
          entities["sub_type"] = "store_credential"
        elif any(kw in q for kw in ["list", "show"]):
          entities["sub_type"] = "list_credentials"
        elif any(kw in q for kw in ["delete", "remove"]):
          entities["sub_type"] = "delete_credential"
        else:
          entities["sub_type"] = "submit_2fa_code"
      elif any(kw in q for kw in ["save", "store", "remember"]):
        entities["sub_type"] = "store_credential"
      elif any(kw in q for kw in ["list", "show"]):
        entities["sub_type"] = "list_credentials"
      elif any(kw in q for kw in ["delete", "remove"]):
        entities["sub_type"] = "delete_credential"
      else:
        entities["sub_type"] = "account_login"

      # Extract email if present
      email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', query)
      if email_match:
        entities["username_or_email"] = email_match.group(0)

      return Intent(
          intent_type=IntentType.VAULT,
          confidence=0.98,
          primary_tool="vault",
          entities=entities,
          summary="Linux-grade security vault operation or account login automation",
      )

    # Autonomous Web Builder & App Deployment
    if any(
        kw in q
        for kw in [
            "build a website",
            "build website",
            "create a website",
            "create website",
            "build web app",
            "create web app",
            "scaffold website",
            "scaffold web",
            "deploy preview",
            "deploy website",
            "deploy web app",
            "start preview server",
            "stop preview server",
            "stop web preview",
            "list web deployments",
            "show web deployments",
        ]
    ):
      sub = "deploy_preview" if "deploy" in q else ("stop_preview" if "stop" in q else ("list_deployments" if "list" in q else "scaffold_website"))
      return Intent(
          intent_type=IntentType.WEB_BUILDER,
          confidence=0.98,
          primary_tool="web_builder",
          entities={"sub_type": sub, "prompt": query},
          summary="Autonomous website generation, scaffolding, and preview deployment",
      )

    # Client Outreach & Communications
    if any(
        kw in q
        for kw in [
            "draft reply to client",
            "reply to client",
            "client reply",
            "draft client email",
            "send client email",
            "send email to client",
            "client inquiry",
            "client thread",
            "list client threads",
            "show client messages",
            "client profile",
            "create client",
            "client message",
            "draft to client",
        ]
    ):
      client_name_match = re.search(
          r'(?:to client|for client|client)\s+([a-zA-Z0-9_\-]+)',
          query,
          re.IGNORECASE,
      )
      entities = {}
      if client_name_match and client_name_match.group(1).lower() not in ["email", "thread", "message", "reply", "profile"]:
        entities["client_name"] = client_name_match.group(1)
      return Intent(
          intent_type=IntentType.CLIENT,
          confidence=0.95,
          primary_tool="communication",
          entities=entities,
          summary="Client communication, outreach drafting, or CRM operation",
      )

    # Vision & Screen Understanding
    if any(
        kw in q
        for kw in [
            "look at my screen",
            "see my screen",
            "analyze my screen",
            "analyze screen",
            "what is on my screen",
            "what's on my screen",
            "what is open on my screen",
            "explain my screen",
            "explain what is on screen",
            "read screen text",
            "extract screen text",
            "diagnose screen error",
            "inspect image",
            "analyze image",
            "what is in this image",
        ]
    ):
      return Intent(
          intent_type=IntentType.VISION,
          confidence=0.95,
          primary_tool="vision",
          summary="Multi-modal screen vision or visual image understanding",
      )

    # Autonomous Web Account / Portal / Platform Inspection
    known_platforms = {
        "fiverr": "https://www.fiverr.com",
        "upwork": "https://www.upwork.com",
        "freelancer": "https://www.freelancer.com",
        "linkedin": "https://www.linkedin.com",
        "gmail": "https://mail.google.com",
        "google mail": "https://mail.google.com",
        "nptel": "https://nptel.ac.in",
        "trello": "https://trello.com",
        "notion": "https://notion.so",
        "slack": "https://slack.com",
        "discord": "https://discord.com",
    }
    for plat_name, plat_url in known_platforms.items():
      if plat_name in q and any(action in q for action in ["check", "inspect", "review", "open", "view", "audit", "account", "profile", "dashboard", "portal", "freelancing", "gigs"]):
        return Intent(
            intent_type=IntentType.BROWSER,
            confidence=0.95,
            primary_tool="browser",
            entities={"platform": plat_name, "url": plat_url},
            summary=f"Autonomous web inspection and account review for {plat_name.capitalize()}",
        )

    # Browser & Web Scraping
    if (
        any(kw in q for kw in ["browse to", "navigate to", "extract article from", "scrape webpage", "read webpage", "open url"])
        or (any(proto in q for proto in ["http://", "https://"]) and any(action in q for action in ["extract", "read", "summarize", "scrape", "headings"]))
    ):
      url_match = re.search(r'(https?://[^\s\'"]+)', query)
      entities = {}
      if url_match:
        entities["url"] = url_match.group(1)
      return Intent(
          intent_type=IntentType.BROWSER,
          confidence=0.95,
          primary_tool="browser",
          entities=entities,
          summary="Autonomous browser web navigation and content extraction",
      )

    # Schedule detection (e.g. "schedule health check every 5 minutes", "list schedules")
    if any(
        kw in q
        for kw in [
            "schedule",
            "every 10 seconds",
            "every 30 seconds",
            "every 1 minute",
            "every 5 minutes",
            "every 10 minutes",
            "every 30 minutes",
            "every hour",
            "every 2 hours",
            "every day",
            "recurring",
            "cron job",
            "list schedules",
            "show schedules",
            "cancel schedule",
        ]
    ):
      return Intent(
          intent_type=IntentType.SCHEDULE,
          confidence=0.95,
          primary_tool="scheduler",
          summary="Task scheduling and recurring background execution",
      )

    # Device & OS automation detection
    if any(
        kw in q
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
            "server performance",
            "check ports",
            "network ports",
            "open ports",
            "listening ports",
            "port check",
            "network sockets",
            "system stats",
            "system info",
            "cpu usage",
            "ram usage",
            "memory usage",
            "disk space",
            "battery status",
            "device info",
            "take screenshot",
            "take a screenshot",
            "capture screen",
            "screenshot",
            "clipboard",
            "running process",
            "list processes",
            "kill process",
            "terminate process",
            "active window",
            "list windows",
            "lock screen",
            "lock pc",
            "mute volume",
            "set volume",
            "open notepad",
            "launch notepad",
            "open calc",
            "launch calc",
            "open calculator",
            "launch calculator",
            "open chrome",
            "launch chrome",
            "open edge",
            "launch edge",
            "open spotify",
            "launch spotify",
            "open vscode",
            "launch vscode",
            "open code",
            "launch app",
            "open app",
        ]
    ):
      sub_type = "server_check" if any(k in q for k in ["server", "infrastructure", "health", "diagnostic"]) else ("network_ports" if any(k in q for k in ["port", "socket"]) else "device")
      return Intent(
          intent_type=IntentType.DEVICE,
          confidence=0.98,
          primary_tool="device",
          entities={"sub_type": sub_type},
          summary="Device, OS, server health, or network automation request",
      )

    # Composite detection (e.g. search github / web and save to tasks)
    if ("github" in q or "issue" in q or "search" in q) and (
        "task" in q or "todo" in q
    ):
      return Intent(
          intent_type=IntentType.COMPOSITE,
          confidence=0.95,
          primary_tool="composite",
          summary="Multi-step workflow involving data retrieval and task management",
      )

    # GitHub intent
    if any(
        kw in q
        for kw in [
            "github",
            "repo",
            "repository",
            "issues",
            "pull request",
            " pr ",
            "commits",
            "pulls",
        ]
    ):
      repo_match = re.search(r"([\w\-]+/[\w\-]+)", query)
      entities = {}
      if repo_match:
        entities["repo"] = repo_match.group(1)
      return Intent(
          intent_type=IntentType.GITHUB,
          confidence=0.9,
          primary_tool="github",
          entities=entities,
          summary="GitHub exploration or inspection request",
      )

    # Filesystem intent
    if any(
        kw in q
        for kw in [
            "read file",
            "show file",
            "list files",
            "search files",
            "find file",
            "view file",
            "cat ",
            "open file",
        ]
    ):
      return Intent(
          intent_type=IntentType.FILESYSTEM,
          confidence=0.9,
          primary_tool="filesystem",
          summary="Local workspace filesystem inspection",
      )

    # Task intent
    if any(
        kw in q
        for kw in [
            "create task",
            "add task",
            "list tasks",
            "show tasks",
            "my tasks",
            "update task",
            "todo",
        ]
    ):
      return Intent(
          intent_type=IntentType.TASKS,
          confidence=0.9,
          primary_tool="tasks",
          summary="Local task/todo management",
      )

    # Web search intent
    if any(
        kw in q
        for kw in [
            "search web",
            "search the web",
            "google",
            "look up online",
            "browse",
            "fetch url",
            "http://",
            "https://",
        ]
    ):
      return Intent(
          intent_type=IntentType.WEB_SEARCH,
          confidence=0.9,
          primary_tool="web_search",
          summary="Online search or web page extraction",
      )

    # General chat
    if any(
        kw in q
        for kw in [
            "hello",
            "hi",
            "who are you",
            "what can you do",
            "help",
            "explain",
        ]
    ):
      return Intent(
          intent_type=IntentType.CHAT,
          confidence=0.95,
          summary="General conversation / assistant inquiry",
      )

    return None

  async def classify(self, query: str) -> Intent:
    """Classifies user request into a structured Intent object."""
    rule_intent = self._classify_rules(query)
    if rule_intent:
      return rule_intent

    # If LLM is available, use structured prompt classification
    if self.llm_provider:
      try:
        system_prompt = (
            "You are the intent classifier for Xeren Assistant. Classify the"
            " user prompt into one of these intents: chat, filesystem, github,"
            " web_search, tasks, composite. Return valid JSON only with keys:"
            " intent_type, confidence, summary, primary_tool, entities."
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

        data = json.loads(clean_text)
        return Intent(
            intent_type=IntentType(data.get("intent_type", "chat")),
            confidence=float(data.get("confidence", 0.8)),
            entities=data.get("entities", {}),
            primary_tool=data.get("primary_tool"),
            summary=data.get("summary", ""),
        )
      except Exception:
        pass

    # Default fallback
    return Intent(
        intent_type=IntentType.CHAT,
        confidence=0.5,
        summary="Conversational query",
    )
