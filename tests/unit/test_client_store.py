"""Unit tests for ClientStore (Phase 10)."""

import pytest
import tempfile
import os
from memory.client_store import ClientStore, ClientProfile, ClientThread, ClientMessage


@pytest.fixture
def temp_db():
  with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    db_path = f.name
  yield db_path
  if os.path.exists(db_path):
    os.remove(db_path)


@pytest.fixture
def store(temp_db):
  return ClientStore(db_path=temp_db)


def test_create_and_get_client(store):
  client = store.create_client(
      name="Acme Corp Lead",
      email="contact@acme.org",
      company="Acme Corp",
      communication_tone="technical",
      notes="Key enterprise client",
  )
  assert client.client_id is not None
  assert client.name == "Acme Corp Lead"
  assert client.email == "contact@acme.org"
  assert client.communication_tone == "technical"

  fetched = store.get_client(client.client_id)
  assert fetched is not None
  assert fetched.client_id == client.client_id
  assert fetched.name == "Acme Corp Lead"

  by_email = store.get_client_by_email("contact@acme.org")
  assert by_email is not None
  assert by_email.client_id == client.client_id


def test_list_and_update_clients(store):
  store.create_client("Alice", "alice@example.com")
  store.create_client("Bob", "bob@example.com")

  clients = store.list_clients()
  assert len(clients) == 2

  alice = store.get_client_by_email("alice@example.com")
  updated = store.update_client(alice.client_id, communication_tone="empathetic", company="Tech Inc")
  assert updated is True

  fetched = store.get_client(alice.client_id)
  assert fetched.communication_tone == "empathetic"
  assert fetched.company == "Tech Inc"


def test_thread_lifecycle(store):
  client = store.create_client("John Doe", "john@doe.com")
  thread = store.create_thread(
      client_id=client.client_id,
      subject="API Integration Status",
      channel="email",
  )
  assert thread.thread_id is not None
  assert thread.client_id == client.client_id
  assert thread.status == "open"

  fetched = store.get_thread(thread.thread_id)
  assert fetched is not None
  assert fetched.subject == "API Integration Status"

  threads = store.list_threads(client_id=client.client_id)
  assert len(threads) == 1

  status_updated = store.update_thread_status(thread.thread_id, "resolved", summary="Integration verified")
  assert status_updated is True

  updated_thread = store.get_thread(thread.thread_id)
  assert updated_thread.status == "resolved"
  assert updated_thread.summary == "Integration verified"


def test_message_management(store):
  client = store.create_client("Jane Smith", "jane@smith.com")
  thread = store.create_thread(client.client_id, "Issue with Webhook")

  msg1 = store.add_message(
      thread_id=thread.thread_id,
      sender="client",
      body="The webhook returns a 500 error when triggered.",
      channel="email",
      metadata={"ip": "1.2.3.4"}
  )
  assert msg1.message_id is not None
  assert msg1.sender == "client"

  msg2 = store.add_message(
      thread_id=thread.thread_id,
      sender="assistant",
      body="We have identified the issue in the signature validator and patched it.",
      channel="email",
  )

  messages = store.get_thread_messages(thread.thread_id)
  assert len(messages) == 2
  assert messages[0].sender == "client"
  assert messages[1].sender == "assistant"
  assert messages[0].metadata == {"ip": "1.2.3.4"}

  recent = store.list_recent_messages(limit=5)
  assert len(recent) == 2
