"""Integration tests for Linux-Grade Security Vault, 2FA, and Autonomous Web Builder workflows."""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from app.api import create_app
from config.settings import Settings
from core.assistant import XerenAssistant
from core.intent import IntentClassifier, IntentType
from core.planner import TaskPlanner
from memory.credential_vault import CredentialVault
from models.provider import MockLLMProvider
from tools.registry import get_default_registry


@pytest.fixture
def test_assistant(tmp_path: Path) -> XerenAssistant:
  settings = Settings(
      workspace_root=tmp_path / "sandbox",
      db_path=tmp_path / "data" / "xeren_test.sqlite",
      traces_dir=tmp_path / "traces",
      preferences_path=tmp_path / "config" / "preferences.yaml",
  )
  settings.workspace_root.mkdir(parents=True, exist_ok=True)
  llm = MockLLMProvider()
  registry = get_default_registry(settings)
  # Pre-approve approvals for automated test runs
  registry.permission_gate.approval_callback = lambda req: True
  return XerenAssistant(settings=settings, llm_provider=llm, tool_registry=registry)


@pytest.mark.asyncio
async def test_vault_and_web_intent_classification():
  classifier = IntentClassifier()

  # 1. Credential storage intent
  intent_save = await classifier.classify("save my login for linkedin (email: user@gmail.com, password: secret123)")
  assert intent_save.intent_type == IntentType.VAULT
  assert intent_save.entities.get("sub_type") == "store_credential"

  # 2. 2FA submission intent
  intent_2fa = await classifier.classify("my 2fa code for linkedin is 849201")
  assert intent_2fa.intent_type == IntentType.VAULT
  assert intent_2fa.entities.get("code") == "849201"

  # 3. Account checking intent
  intent_login = await classifier.classify("check my linkedin account by my gmail account")
  assert intent_login.intent_type == IntentType.VAULT
  assert intent_login.entities.get("platform") == "linkedin"

  # 4. Web Builder intent
  intent_web = await classifier.classify("build a website for an AI SaaS analytics startup")
  assert intent_web.intent_type == IntentType.WEB_BUILDER


@pytest.mark.asyncio
async def test_vault_and_web_dag_planning():
  planner = TaskPlanner()
  classifier = IntentClassifier()

  # Test account login DAG planning
  intent_login = await classifier.classify("check my linkedin account by my gmail account")
  dag_login = await planner.plan_dag("check my linkedin account by my gmail account", intent_login)
  assert len(dag_login.actions) == 3
  assert dag_login.actions[0].tool_name == "vault"
  assert dag_login.actions[0].operation == "get_credential"
  assert dag_login.actions[1].tool_name == "browser"
  assert dag_login.actions[2].tool_name == "vision"

  # Test Web Builder DAG planning
  intent_web = await classifier.classify("build a website for creative design agency")
  dag_web = await planner.plan_dag("build a website for creative design agency", intent_web)
  assert len(dag_web.actions) == 2
  assert dag_web.actions[0].tool_name == "web_builder"
  assert dag_web.actions[0].operation == "scaffold_website"
  assert dag_web.actions[1].tool_name == "web_builder"
  assert dag_web.actions[1].operation == "deploy_preview"


@pytest.mark.asyncio
async def test_assistant_vault_and_web_execution(test_assistant: XerenAssistant):
  # 1. Execute save login query
  resp_save = await test_assistant.process_request("save my login for linkedin password MySecretPass123!")
  assert resp_save.success is True
  assert "Credential Secured" in resp_save.response_text or "Enclave" in resp_save.response_text

  # 2. Execute 2FA submit query
  resp_2fa = await test_assistant.process_request("submit 2fa code 123456 for linkedin")
  assert resp_2fa.success is True
  assert "2FA" in resp_2fa.response_text or "Authentication Response" in resp_2fa.response_text

  # 3. Execute Web Builder query
  resp_web = await test_assistant.process_request("build a website for a cybersecurity consulting firm")
  assert resp_web.success is True
  assert "Scaffolding Complete" in resp_web.response_text or "Deployed" in resp_web.response_text


def test_api_vault_and_web_endpoints(test_assistant: XerenAssistant):
  app = create_app(assistant=test_assistant)
  client = TestClient(app)

  # 1. Vault Save
  res_save = client.post("/vault/credentials", json={
      "platform": "upwork",
      "username_or_email": "freelancer@example.com",
      "password": "UpworkSecretPassword123#",
      "two_factor_type": "prompt",
  })
  assert res_save.status_code == 200
  data_save = res_save.json()
  assert data_save["platform"] == "upwork"
  assert data_save["password_masked"] == "********"

  # 2. Vault List
  res_list = client.get("/vault/credentials")
  assert res_list.status_code == 200
  assert res_list.json()["total"] >= 1

  # 3. Vault 2FA Submit
  res_2fa = client.post("/vault/2fa", json={"platform": "upwork", "code": "654321"})
  assert res_2fa.status_code == 200
  assert res_2fa.json()["status"] == "2fa_registered"

  # 4. Web Scaffold
  res_scaffold = client.post("/web/scaffold", json={"prompt": "Interactive AI Portfolio", "project_name": "ai_portfolio"})
  assert res_scaffold.status_code == 200
  assert res_scaffold.json()["project_name"] == "ai_portfolio"

  # 5. Web Deploy
  res_deploy = client.post("/web/deploy", json={"project_name": "ai_portfolio"})
  assert res_deploy.status_code == 200
  assert "url" in res_deploy.json()

  # 6. Web List Deployments
  res_deps = client.get("/web/deployments")
  assert res_deps.status_code == 200
  assert len(res_deps.json()["deployments"]) >= 1

  # 7. Web Stop
  res_stop = client.post("/web/stop", json={"project_name": "ai_portfolio"})
  assert res_stop.status_code == 200
