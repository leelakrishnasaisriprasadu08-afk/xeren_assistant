"""Universal Security Vault & Authentication Tool for Xeren Assistant."""

import time
from typing import Any, Dict, List, Optional
from memory.credential_vault import CredentialVault
from security.secrets import SecretStore
from .base import Action, BaseTool, ToolResult


class VaultTool(BaseTool):
  """Tool for managing encrypted user credentials, account logins, and 2FA authentication."""

  def __init__(self, vault: Optional[CredentialVault] = None):
    self.vault = vault or CredentialVault()
    self.secret_store = SecretStore.get_instance()

  @property
  def name(self) -> str:
    return "vault"

  @property
  def description(self) -> str:
    return (
        "Universal Linux-Grade Security Vault: stores encrypted account logins"
        " (LinkedIn, Gmail, Upwork, Fiverr), issues single-use credential leases,"
        " and manages 2FA/OTP authentication."
    )

  @property
  def supported_operations(self) -> List[str]:
    return [
        "store_credential",
        "get_credential",
        "list_credentials",
        "delete_credential",
        "submit_2fa_code",
    ]

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      if op == "store_credential":
        platform = params.get("platform") or params.get("name") or params.get("service")
        username = params.get("username") or params.get("email") or params.get("username_or_email")
        password = params.get("password") or params.get("pass") or ""
        two_fa_type = params.get("two_factor_type") or params.get("two_fa") or "none"
        two_fa_secret = params.get("two_factor_secret") or params.get("totp_seed")

        if not platform or not username:
          raise ValueError("Parameters 'platform' and 'username' (or 'email') are required.")

        cred = self.vault.store_credential(
            platform=platform,
            username_or_email=username,
            password=password,
            two_factor_type=two_fa_type,
            two_factor_secret=two_fa_secret,
            metadata=params.get("metadata", {}),
        )

        # Register secret in SecretStore so it is automatically redacted everywhere
        if password:
          self.secret_store.set_secret(f"vault_{platform.lower()}", password)

        data = cred.model_dump()

      elif op == "get_credential":
        platform = params.get("platform") or params.get("name") or params.get("service")
        if not platform:
          raise ValueError("Parameter 'platform' is required for get_credential.")
        cred_info = self.vault.get_credential(platform=platform, action_id=action.action_id)
        if not cred_info:
          raise ValueError(f"No stored credentials found in vault for platform '{platform}'.")
        data = cred_info

      elif op == "list_credentials":
        creds = self.vault.list_credentials()
        data = {"credentials": [c.model_dump() for c in creds], "total": len(creds)}

      elif op == "delete_credential":
        platform = params.get("platform") or params.get("name")
        if not platform:
          raise ValueError("Parameter 'platform' is required for delete_credential.")
        success = self.vault.delete_credential(platform=platform)
        if not success:
          raise ValueError(f"No credential found to delete for platform '{platform}'.")
        data = {"status": "deleted", "platform": platform}

      elif op == "submit_2fa_code":
        platform = params.get("platform") or params.get("service")
        code = params.get("code") or params.get("otp") or params.get("token")
        if not platform or not code:
          raise ValueError("Parameters 'platform' and 'code' (2FA OTP) are required.")
        self.vault.submit_2fa_code(platform=platform, code=str(code))
        data = {"status": "2fa_registered", "platform": platform, "code_masked": f"{str(code)[:2]}****"}

      else:
        raise ValueError(f"Unsupported operation '{op}' on tool '{self.name}'")

      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=True,
          data=data,
          execution_time_ms=elapsed,
      )

    except Exception as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=str(e),
          execution_time_ms=elapsed,
      )
