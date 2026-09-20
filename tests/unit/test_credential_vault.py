"""Unit tests for CredentialVault and 2FA response management."""

from pathlib import Path
import pytest
from memory.credential_vault import CredentialVault


@pytest.fixture
def vault(tmp_path: Path) -> CredentialVault:
  return CredentialVault(
      db_path=tmp_path / "vault_test.sqlite",
      master_key="test_master_encryption_key_2026",
  )


def test_vault_store_and_get_credential(vault: CredentialVault):
  # Store LinkedIn credential
  cred = vault.store_credential(
      platform="LinkedIn",
      username_or_email="leela.krishna@example.com",
      password="SuperSecretPassword2026#",
      two_factor_type="prompt",
  )

  assert cred.platform == "linkedin"
  assert cred.username_or_email == "leela.krishna@example.com"
  assert cred.password_masked == "********"

  # Retrieve credential details + lease
  info = vault.get_credential("linkedin")
  assert info is not None
  assert info["platform"] == "linkedin"
  assert info["lease_id"] is not None

  # Redeem secret via SecurityGuard
  secret = vault.security_guard.redeem_credential_lease(info["lease_id"], action_id="test_act")
  assert secret == "SuperSecretPassword2026#"


def test_vault_list_and_delete(vault: CredentialVault):
  vault.store_credential(
      platform="gmail",
      username_or_email="user@gmail.com",
      password="GmailPassword123",
  )
  vault.store_credential(
      platform="upwork",
      username_or_email="freelancer@upwork.com",
      password="UpworkPassword456",
  )

  creds = vault.list_credentials()
  assert len(creds) >= 2
  platforms = [c.platform for c in creds]
  assert "gmail" in platforms
  assert "upwork" in platforms

  # Delete upwork
  del_res = vault.delete_credential("upwork")
  assert del_res is True

  creds_after = vault.list_credentials()
  assert "upwork" not in [c.platform for c in creds_after]


def test_vault_2fa_code_submission(vault: CredentialVault):
  vault.store_credential(
      platform="linkedin",
      username_or_email="user@linkedin.com",
      password="Pass",
      two_factor_type="prompt",
  )

  # Submit 2FA code
  vault.submit_2fa_code(platform="linkedin", code="482910")

  info = vault.get_credential("linkedin")
  assert info["last_2fa_code"] == "482910"
  assert info["has_active_2fa"] is True
