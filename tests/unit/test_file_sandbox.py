"""Unit tests for FileSandbox atomic write and backup rollback."""

from tools.sandbox import FileSandbox


def test_file_sandbox_atomic_write_and_backup(temp_workspace):
  sandbox = FileSandbox(workspace_root=temp_workspace)
  target_file = temp_workspace / "sandbox_test.txt"

  # Initial write
  sandbox.atomic_write(target_file, "version 1 content")
  assert target_file.exists()
  assert target_file.read_text(encoding="utf-8") == "version 1 content"

  # Backup creation
  backup_path = sandbox.create_backup(target_file)
  assert backup_path is not None
  assert backup_path.exists()
  assert backup_path.read_text(encoding="utf-8") == "version 1 content"

  # Overwrite with version 2
  sandbox.atomic_write(target_file, "version 2 content")
  assert target_file.read_text(encoding="utf-8") == "version 2 content"

  # Rollback from backup
  success = sandbox.rollback(target_file, backup_path)
  assert success is True
  assert target_file.read_text(encoding="utf-8") == "version 1 content"
