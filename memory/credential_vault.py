"""Encrypted Credential Vault & 2FA Authentication Storage."""

import base64
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field
from security.security_guard import (
    EphemeralCredentialLease,
    SecurityCapability,
    SecurityGuard,
    SecurityRing,
)


class AccountCredential(BaseModel):
  """Representation of an encrypted user account credential."""

  platform: str  # e.g., "linkedin", "gmail", "upwork", "github", "custom"
  username_or_email: str
  password_masked: str = "********"
  two_factor_type: str = "none"  # "none", "totp", "sms", "email_otp", "prompt"
  has_2fa: bool = False
  last_2fa_code: Optional[str] = None
  last_2fa_timestamp: Optional[float] = None
  is_active: bool = True
  metadata: Dict[str, Any] = Field(default_factory=dict)
  updated_at: str = Field(
      default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )


class CredentialVault:
  """Secure, encrypted credential storage engine backed by SQLite and Fernet."""

  def __init__(
      self,
      db_path: Optional[Path] = None,
      master_key: Optional[str] = None,
      security_guard: Optional[SecurityGuard] = None,
  ):
    self.db_path = (db_path or Path("data/xeren_vault.sqlite")).resolve()
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self.security_guard = security_guard or SecurityGuard.get_instance()
    self._fernet = self._init_crypto(master_key)
    self._init_db()

  def _init_crypto(self, master_key: Optional[str]) -> Fernet:
    """Derives a deterministic 32-byte Fernet key from environment or master key."""
    raw_key = (
        master_key
        or os.environ.get("XEREN_VAULT_KEY")
        or "xeren_default_master_salt_enclave_2026"
    )
    derived = hashlib.sha256(raw_key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)

  def _encrypt(self, plain_text: str) -> str:
    if not plain_text:
      return ""
    return self._fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")

  def _decrypt(self, cipher_text: str) -> str:
    if not cipher_text:
      return ""
    try:
      return self._fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
      return ""

  def _get_connection(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self.db_path))
    conn.row_factory = sqlite3.Row
    return conn

  def _init_db(self) -> None:
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute("""
              CREATE TABLE IF NOT EXISTS user_credentials (
                  platform TEXT PRIMARY KEY,
                  username_or_email TEXT NOT NULL,
                  password_encrypted TEXT NOT NULL,
                  two_factor_type TEXT NOT NULL DEFAULT 'none',
                  two_factor_secret_encrypted TEXT,
                  last_2fa_code TEXT,
                  last_2fa_timestamp REAL,
                  session_cookies_encrypted TEXT,
                  is_active INTEGER NOT NULL DEFAULT 1,
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  updated_at TEXT NOT NULL
              )
              """)

  def store_credential(
      self,
      platform: str,
      username_or_email: str,
      password: str,
      two_factor_type: str = "none",
      two_factor_secret: Optional[str] = None,
      metadata: Optional[Dict[str, Any]] = None,
  ) -> AccountCredential:
    """Stores or updates encrypted credentials for a target platform."""
    plat = platform.lower().strip()
    enc_pass = self._encrypt(password)
    enc_2fa_secret = self._encrypt(two_factor_secret) if two_factor_secret else None
    now_iso = datetime.now(timezone.utc).isoformat()

    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute(
            """
                  INSERT OR REPLACE INTO user_credentials
                  (platform, username_or_email, password_encrypted, two_factor_type,
                   two_factor_secret_encrypted, is_active, metadata_json, updated_at)
                  VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                  """,
            (
                plat,
                username_or_email.strip(),
                enc_pass,
                two_factor_type,
                enc_2fa_secret,
                json.dumps(metadata or {}),
                now_iso,
            ),
        )

    self.security_guard.record_audit(
        ring=SecurityRing.RING_0_KERNEL_ENCLAVE,
        capability=SecurityCapability.CAP_VAULT_WRITE.value,
        resource=f"vault:{plat}",
        status="CREDENTIAL_STORED",
    )

    return AccountCredential(
        platform=plat,
        username_or_email=username_or_email,
        two_factor_type=two_factor_type,
        has_2fa=(two_factor_type != "none"),
        metadata=metadata or {},
        updated_at=now_iso,
    )

  def get_credential(
      self, platform: str, action_id: str = "internal_dispatch"
  ) -> Optional[Dict[str, Any]]:
    """Retrieves credential details and generates an ephemeral Ring 0 lease for the password."""
    plat = platform.lower().strip()
    with closing(self._get_connection()) as conn:
      row = conn.execute(
          "SELECT * FROM user_credentials WHERE platform = ?", (plat,)
      ).fetchone()
      if not row:
        return None

      dec_pass = self._decrypt(row["password_encrypted"])
      lease = self.security_guard.issue_credential_lease(
          platform=plat,
          username_or_email=row["username_or_email"],
          decrypted_secret=dec_pass,
          ttl_seconds=60.0,
      )

      return {
          "platform": row["platform"],
          "username_or_email": row["username_or_email"],
          "two_factor_type": row["two_factor_type"],
          "last_2fa_code": row["last_2fa_code"],
          "has_active_2fa": bool(
              row["last_2fa_code"]
              and (time.time() - (row["last_2fa_timestamp"] or 0)) < 300
          ),
          "lease_id": lease.lease_id,
          "ttl_seconds": lease.ttl_seconds,
          "is_active": bool(row["is_active"]),
          "updated_at": row["updated_at"],
      }

  def list_credentials(self) -> List[AccountCredential]:
    """Returns all registered credentials with permanently masked passwords."""
    with closing(self._get_connection()) as conn:
      rows = conn.execute(
          "SELECT * FROM user_credentials ORDER BY platform ASC"
      ).fetchall()
      results = []
      for r in rows:
        meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
        results.append(
            AccountCredential(
                platform=r["platform"],
                username_or_email=r["username_or_email"],
                two_factor_type=r["two_factor_type"],
                has_2fa=(r["two_factor_type"] != "none"),
                last_2fa_code=r["last_2fa_code"],
                last_2fa_timestamp=r["last_2fa_timestamp"],
                is_active=bool(r["is_active"]),
                metadata=meta,
                updated_at=r["updated_at"],
            )
        )
      return results

  def delete_credential(self, platform: str) -> bool:
    """Removes a platform credential from the vault."""
    plat = platform.lower().strip()
    with closing(self._get_connection()) as conn:
      with conn:
        cur = conn.execute(
            "DELETE FROM user_credentials WHERE platform = ?", (plat,)
        )
        success = cur.rowcount > 0
    if success:
      self.security_guard.record_audit(
          ring=SecurityRing.RING_0_KERNEL_ENCLAVE,
          capability=SecurityCapability.CAP_VAULT_DELETE.value,
          resource=f"vault:{plat}",
          status="CREDENTIAL_DELETED",
      )
    return success

  def submit_2fa_code(self, platform: str, code: str) -> bool:
    """Stores the latest 2FA / OTP authentication response from the user."""
    plat = platform.lower().strip()
    now_ts = time.time()
    with closing(self._get_connection()) as conn:
      with conn:
        cur = conn.execute(
            """
                  UPDATE user_credentials
                  SET last_2fa_code = ?, last_2fa_timestamp = ?
                  WHERE platform = ?
                  """,
            (code.strip(), now_ts, plat),
        )
        if cur.rowcount == 0:
          # If not yet registered, create stub entry
          now_iso = datetime.now(timezone.utc).isoformat()
          conn.execute(
              """
                    INSERT INTO user_credentials 
                    (platform, username_or_email, password_encrypted, two_factor_type, last_2fa_code, last_2fa_timestamp, is_active, updated_at)
                    VALUES (?, 'user@example.com', '', 'prompt', ?, ?, 1, ?)
                    """,
              (plat, code.strip(), now_ts, now_iso),
          )
    return True
