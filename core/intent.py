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
