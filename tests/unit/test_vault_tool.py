"""Unit tests for VaultTool operations."""

from pathlib import Path
import pytest
from memory.credential_vault import CredentialVault
from security.secrets import SecretStore
from tools.base import Action
from tools.vault_tool import VaultTool


@pytest.fixture
def vault_tool(tmp_path: Path) -> VaultTool:
  vault = CredentialVault(
      db_path=tmp_path / "vault_tool_test.sqlite",
      master_key="tool_test_master_key",
  )
  return VaultTool(vault=vault)


@pytest.mark.asyncio
async def test_vault_tool_store_and_redact(vault_tool: VaultTool):
  action = Action(
      action_id="act_store",
      tool_name="vault",
      operation="store_credential",
      parameters={
          "platform": "github",
          "username": "octocat",
          "password": "SpecialGithubSecretToken12345",
          "two_factor_type": "totp",
      },
  )
  res = await vault_tool.execute(action)
  assert res.success is True
  assert res.data["platform"] == "github"
  assert res.data["password_masked"] == "********"

  # Verify secret is automatically registered in SecretStore
  registered = SecretStore.get_instance().get_registered_secrets()
  assert "SpecialGithubSecretToken12345" in registered


@pytest.mark.asyncio
async def test_vault_tool_get_and_list(vault_tool: VaultTool):
  # Store
  await vault_tool.execute(Action(
      action_id="act_store",
      tool_name="vault",
      operation="store_credential",
      parameters={"platform": "fiverr", "username": "seller@fiverr.com", "password": "FiverrPass!"},
  ))

  # List
  res_list = await vault_tool.execute(Action(
      action_id="act_list",
      tool_name="vault",
      operation="list_credentials",
      parameters={},
  ))
  assert res_list.success is True
  assert res_list.data["total"] >= 1

  # Get
  res_get = await vault_tool.execute(Action(
      action_id="act_get",
      tool_name="vault",
      operation="get_credential",
      parameters={"platform": "fiverr"},
  ))
  assert res_get.success is True
  assert res_get.data["platform"] == "fiverr"
  assert "lease_id" in res_get.data


@pytest.mark.asyncio
async def test_vault_tool_2fa_submission(vault_tool: VaultTool):
  res_2fa = await vault_tool.execute(Action(
      action_id="act_2fa",
      tool_name="vault",
      operation="submit_2fa_code",
      parameters={"platform": "linkedin", "code": "987654"},
  ))
  assert res_2fa.success is True
  assert res_2fa.data["status"] == "2fa_registered"
