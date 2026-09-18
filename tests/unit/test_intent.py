"""Unit tests for IntentClassifier."""

import pytest
from core.intent import IntentClassifier, IntentType


@pytest.mark.asyncio
async def test_intent_classification_rules():
  classifier = IntentClassifier()

  # Filesystem
  res = await classifier.classify("read file README.md")
  assert res.intent_type == IntentType.FILESYSTEM

  # GitHub
  res = await classifier.classify("fetch open issues from octocat/Hello-World")
  assert res.intent_type == IntentType.GITHUB
  assert res.entities.get("repo") == "octocat/Hello-World"

  # Web search
  res = await classifier.classify("search the web for Python 3.12 release date")
  assert res.intent_type == IntentType.WEB_SEARCH

  # Tasks
  res = await classifier.classify("create task review security policies")
  assert res.intent_type == IntentType.TASKS

  # Composite
  res = await classifier.classify(
      "check issues in owner/repo and create a task for reviewing them"
  )
  assert res.intent_type == IntentType.COMPOSITE

  # Chat
  res = await classifier.classify("hello who are you?")
  assert res.intent_type == IntentType.CHAT
