"""Linux-Grade Multi-Level Security Guard with Privilege Rings and Ephemeral Leases."""

from datetime import datetime, timezone
from enum import Enum, IntEnum
import hashlib
import hmac
import os
import secrets
import time
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class SecurityRing(IntEnum):
  """Linux/POSIX-inspired 4-tier privilege ring architecture."""

  RING_0_KERNEL_ENCLAVE = 0  # Master encryption keys, raw credentials, zero-trust enclave
  RING_1_CAPABILITY_CONTROL = 1  # Policy engine, capability enforcement, permission gates
  RING_2_SANDBOX_EXECUTION = 2  # Sandboxed tool calls, payload scrubbers, audited execution
  RING_3_USER_SPACE = 3  # External REST APIs, WebSockets, CLI, chat presentation (masked)


class SecurityCapability(str, Enum):
  """Granular capability bitmask flags for system operations."""

  CAP_VAULT_READ = "CAP_VAULT_READ"  # Read decrypted platform credentials
  CAP_VAULT_WRITE = "CAP_VAULT_WRITE"  # Store or update encrypted credentials
  CAP_VAULT_DELETE = "CAP_VAULT_DELETE"  # Remove stored platform credentials
  CAP_WEB_DEPLOY = "CAP_WEB_DEPLOY"  # Scaffold and deploy web apps on local ports
  CAP_SERVER_ADMIN = "CAP_SERVER_ADMIN"  # Inspect network sockets and server processes
  CAP_BROWSER_AUTH = "CAP_BROWSER_AUTH"  # Inject credentials into browser session


class EphemeralCredentialLease(BaseModel):
  """Single-use, time-bounded credential lease that auto-expires."""

  lease_id: str = Field(default_factory=lambda: secrets.token_hex(16))
  platform: str
  username_or_email: str
  decrypted_secret: str
  ring_level: SecurityRing = SecurityRing.RING_0_KERNEL_ENCLAVE
  created_at: float = Field(default_factory=time.time)
  ttl_seconds: float = 60.0  # 60s single-use ephemeral lease
  is_consumed: bool = False
  consumer_action_id: Optional[str] = None

  def is_valid(self) -> bool:
    """Checks if lease has not expired and has not been consumed."""
    if self.is_consumed:
      return False
    return (time.time() - self.created_at) <= self.ttl_seconds

  def consume(self, action_id: str) -> str:
    """Consumes the lease, marking it spent and returning the decrypted secret."""
    if not self.is_valid():
      raise PermissionError(
          f"Credential lease '{self.lease_id}' for '{self.platform}' has expired or was already consumed."
      )
    self.is_consumed = True
    self.consumer_action_id = action_id
    return self.decrypted_secret


class SecurityAuditRecord(BaseModel):
  """Tamper-evident security audit log entry with cryptographic signature."""

  timestamp: str = Field(
      default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )
  ring_level: int
  capability_invoked: str
  target_resource: str
  status: str
  action_id: Optional[str] = None
  record_hash: str = ""


class SecurityGuard:
  """Central Linux-Grade Security Guard managing privilege rings, capabilities, and leases."""

  _instance: Optional["SecurityGuard"] = None

  def __init__(self, master_salt: Optional[bytes] = None):
    self._salt = master_salt or os.urandom(16)
    self._active_leases: Dict[str, EphemeralCredentialLease] = {}
    self._audit_log: List[SecurityAuditRecord] = []
    self._allowed_capabilities: Set[SecurityCapability] = {
        SecurityCapability.CAP_VAULT_READ,
        SecurityCapability.CAP_VAULT_WRITE,
        SecurityCapability.CAP_VAULT_DELETE,
        SecurityCapability.CAP_WEB_DEPLOY,
        SecurityCapability.CAP_SERVER_ADMIN,
        SecurityCapability.CAP_BROWSER_AUTH,
    }

  @classmethod
  def get_instance(cls) -> "SecurityGuard":
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def issue_credential_lease(
      self,
      platform: str,
      username_or_email: str,
      decrypted_secret: str,
      ttl_seconds: float = 60.0,
      ring_level: SecurityRing = SecurityRing.RING_0_KERNEL_ENCLAVE,
  ) -> EphemeralCredentialLease:
    """Issues an ephemeral, time-bounded credential lease in Ring 0."""
    lease = EphemeralCredentialLease(
        platform=platform,
        username_or_email=username_or_email,
        decrypted_secret=decrypted_secret,
        ttl_seconds=ttl_seconds,
        ring_level=ring_level,
    )
    self._active_leases[lease.lease_id] = lease
    self.record_audit(
        ring=ring_level,
        capability=SecurityCapability.CAP_VAULT_READ.value,
        resource=f"vault:{platform}",
        status="LEASE_ISSUED",
        action_id=lease.lease_id,
    )
    return lease

  def redeem_credential_lease(
      self, lease_id: str, action_id: str
  ) -> Optional[str]:
    """Redeems an ephemeral lease, returning raw secret and immediately zeroing availability."""
    self.prune_expired_leases()
    lease = self._active_leases.get(lease_id)
    if not lease:
      self.record_audit(
          ring=SecurityRing.RING_1_CAPABILITY_CONTROL,
          capability=SecurityCapability.CAP_VAULT_READ.value,
          resource=f"lease:{lease_id}",
          status="LEASE_NOT_FOUND",
          action_id=action_id,
      )
      return None

    try:
      secret = lease.consume(action_id)
      self.record_audit(
          ring=SecurityRing.RING_2_SANDBOX_EXECUTION,
          capability=SecurityCapability.CAP_VAULT_READ.value,
          resource=f"vault:{lease.platform}",
          status="LEASE_CONSUMED",
          action_id=action_id,
      )
      return secret
    except PermissionError:
      self.record_audit(
          ring=SecurityRing.RING_1_CAPABILITY_CONTROL,
          capability=SecurityCapability.CAP_VAULT_READ.value,
          resource=f"vault:{lease.platform}",
          status="LEASE_EXPIRED_OR_CONSUMED",
          action_id=action_id,
      )
      return None

  def prune_expired_leases(self) -> int:
    """Purges expired leases from memory."""
    now = time.time()
    expired_ids = [
        lid
        for lid, l in self._active_leases.items()
        if (now - l.created_at) > l.ttl_seconds or l.is_consumed
    ]
    for lid in expired_ids:
      self._active_leases.pop(lid, None)
    return len(expired_ids)

  def check_capability(
      self, capability: SecurityCapability, ring: SecurityRing
  ) -> bool:
    """Verifies that the requested capability is authorized for the caller's ring."""
    if ring in [SecurityRing.RING_0_KERNEL_ENCLAVE, SecurityRing.RING_1_CAPABILITY_CONTROL]:
      return capability in self._allowed_capabilities

    if ring == SecurityRing.RING_2_SANDBOX_EXECUTION:
      return capability in [
          SecurityCapability.CAP_VAULT_READ,
          SecurityCapability.CAP_WEB_DEPLOY,
          SecurityCapability.CAP_SERVER_ADMIN,
          SecurityCapability.CAP_BROWSER_AUTH,
      ]

    return False

  def record_audit(
      self,
      ring: int,
      capability: str,
      resource: str,
      status: str,
      action_id: Optional[str] = None,
  ) -> SecurityAuditRecord:
    """Appends a cryptographically chained audit record."""
    prev_hash = self._audit_log[-1].record_hash if self._audit_log else "GENESIS"
    raw_str = f"{prev_hash}:{ring}:{capability}:{resource}:{status}:{action_id}"
    rec_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    record = SecurityAuditRecord(
        ring_level=int(ring),
        capability_invoked=capability,
        target_resource=resource,
        status=status,
        action_id=action_id,
        record_hash=rec_hash,
    )
    self._audit_log.append(record)
    return record

  def get_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
    """Returns recent audit records."""
    return [r.model_dump() for r in self._audit_log[-limit:]]
