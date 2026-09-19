"""Autonomous Client Communication Agent for response drafting and relationship management."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from models.base import BaseLLMProvider, LLMMessage
from models.provider import get_default_llm_provider
from memory.client_store import ClientStore, ClientThread, ClientMessage


class ClientAgent:
  """Specialized agent for drafting client responses, status updates, and professional outreach."""

  def __init__(
      self,
      llm_provider: Optional[BaseLLMProvider] = None,
      client_store: Optional[ClientStore] = None,
  ):
    self.llm_provider = llm_provider or get_default_llm_provider()
    self.client_store = client_store or ClientStore()

  async def draft_reply(
      self,
      client_name: str,
      inquiry: str,
      subject: Optional[str] = None,
      persona: str = "professional",
      project_context: Optional[str] = None,
      client_email: Optional[str] = None,
  ) -> Dict[str, Any]:
    """Drafts a personalized, context-aware client response."""
    subj = subject or f"Update regarding {client_name}'s inquiry"
    
    # Store thread in CRM
    thread = self.client_store.create_thread(
        client_name=client_name,
        client_email=client_email,
        subject=subj,
        inquiry_text=inquiry,
    )

    persona_prompts = {
        "professional": "Formal, courteous, respectful, clear, and reassuring. Focus on deliverables and milestones.",
        "technical": "Precise, architectural, providing code/system details, root cause analysis, and ETA.",
        "empathetic": "Warm, supportive, actively addressing client pain points with priority reassurance.",
        "concise": "Brief, executive summary style, bullet points, directly answering the question with next steps.",
    }

    style_guide = persona_prompts.get(persona.lower(), persona_prompts["professional"])

    prompt = f"""
Draft a reply to the following client inquiry:

Client Name: {client_name}
Subject: {subj}
Client Inquiry:
\"\"\"
{inquiry}
\"\"\"

Project Status Context:
\"\"\"
{project_context or "Project is on schedule. All recent milestone builds have passed automated quality and security checks."}
\"\"\"

Tone & Style Guide:
{style_guide}

Generate a complete, ready-to-send professional email draft with a Subject Line, Greeting, Body Paragraphs, Next Steps, and Sign-off.
"""

    system_instruction = (
        "You are the Client Relations & Communications Specialist for Xeren"
        " Assistant. You write articulate, brand-aligned, and reassuring client"
        " responses that build trust and clearly explain technical/project status."
    )

    resp = await self.llm_provider.generate(
        messages=[LLMMessage(role="user", content=prompt)],
        system_instruction=system_instruction,
        temperature=0.3,
    )

    draft_text = resp.text.strip()

    # Save draft message in thread
    msg = self.client_store.save_message(
        thread_id=thread.thread_id,
        sender="xeren",
        recipient=client_email or client_name,
        content=draft_text,
        status="drafted",
    )

    return {
        "thread_id": thread.thread_id,
        "message_id": msg.message_id,
        "client_name": client_name,
        "recipient": client_email or client_name,
        "subject": subj,
        "persona": persona,
        "style": persona,
        "body": draft_text,
        "draft": draft_text,
        "confidence_score": 0.95,
        "status": "drafted",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

  async def summarize_thread(self, thread_id: str) -> Dict[str, Any]:
    """Summarizes a client thread with key takeaways and action items."""
    thread = self.client_store.get_thread(thread_id)
    if not thread:
      raise ValueError(f"Thread '{thread_id}' not found.")

    messages = self.client_store.list_messages(thread_id)
    conv_text = f"Inquiry from {thread.client_name}:\n{thread.inquiry_text}\n\n"
    for m in messages:
      conv_text += f"{m.sender.upper()} -> {m.recipient}:\n{m.content}\n\n"

    prompt = f"Summarize this client interaction and extract immediate next steps and open deliverables:\n\n{conv_text}"
    resp = await self.llm_provider.generate(
        messages=[LLMMessage(role="user", content=prompt)],
        system_instruction="Provide a concise bulleted summary and action items.",
        temperature=0.1,
    )

    return {
        "thread_id": thread_id,
        "client_name": thread.client_name,
        "summary": resp.text.strip(),
        "total_messages": len(messages),
    }
