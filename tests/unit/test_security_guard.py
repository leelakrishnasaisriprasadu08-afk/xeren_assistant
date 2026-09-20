"""Unit tests for Linux-Grade SecurityGuard, privilege rings, and ephemeral leases."""

import time
import pytest
from security.security_guard import (
    EphemeralCredentialLease,
    SecurityCapability,
    SecurityGuard,
    SecurityRing,
)


def test_security_rings_and_capabilities():
  guard = SecurityGuard()

  # Ring 0 & Ring 1 can invoke vault write
  assert guard.check_capability(SecurityCapability.CAP_VAULT_WRITE, SecurityRing.RING_0_KERNEL_ENCLAVE) is True
  assert guard.check_capability(SecurityCapability.CAP_VAULT_WRITE, SecurityRing.RING_1_CAPABILITY_CONTROL) is True

  # Ring 2 (Sandbox) cannot write or delete vault keys directly
  assert guard.check_capability(SecurityCapability.CAP_VAULT_DELETE, SecurityRing.RING_2_SANDBOX_EXECUTION) is False
  assert guard.check_capability(SecurityCapability.CAP_WEB_DEPLOY, SecurityRing.RING_2_SANDBOX_EXECUTION) is True

  # Ring 3 (User space) has no direct execution capabilities without policy gate
  assert guard.check_capability(SecurityCapability.CAP_VAULT_READ, SecurityRing.RING_3_USER_SPACE) is False


def test_ephemeral_credential_lease_lifecycle():
  guard = SecurityGuard()

  # Issue lease
  lease = guard.issue_credential_lease(
      platform="linkedin",
      username_or_email="pro_user@linkedin.com",
      decrypted_secret="SecretP@ssword2026!",
      ttl_seconds=2.0,
  )

  assert lease.lease_id
  assert lease.is_valid() is True

  # Redeem lease (single-use)
  secret = guard.redeem_credential_lease(lease.lease_id, action_id="act_browser_login")
  assert secret == "SecretP@ssword2026!"

  # Second redemption must fail (single use consumed)
  second_try = guard.redeem_credential_lease(lease.lease_id, action_id="act_second_attempt")
  assert second_try is None


def test_ephemeral_lease_expiration():
  guard = SecurityGuard()

  # Issue short-lived lease
  lease = guard.issue_credential_lease(
      platform="gmail",
      username_or_email="user@gmail.com",
      decrypted_secret="GmailPass123",
      ttl_seconds=0.1,
  )

  time.sleep(0.15)
  assert lease.is_valid() is False
  redeemed = guard.redeem_credential_lease(lease.lease_id, action_id="act_late")
  assert redeemed is None


def test_security_audit_tamper_evident_trail():
  guard = SecurityGuard()
  rec1 = guard.record_audit(
      ring=SecurityRing.RING_0_KERNEL_ENCLAVE,
      capability=SecurityCapability.CAP_VAULT_WRITE.value,
      resource="vault:upwork",
      status="STORED",
  )
  rec2 = guard.record_audit(
      ring=SecurityRing.RING_1_CAPABILITY_CONTROL,
      capability=SecurityCapability.CAP_VAULT_READ.value,
      resource="vault:upwork",
      status="LEASE_ISSUED",
  )

  assert rec1.record_hash
  assert rec2.record_hash
  assert rec1.record_hash != rec2.record_hash
  trail = guard.get_audit_trail(limit=10)
  assert len(trail) >= 2
