"""Unit tests for individual tools in isolation."""

import pytest
from tools.base import Action
from tools.filesystem_tool import FilesystemTool
from tools.task_tool import TaskTool


@pytest.mark.asyncio
async def test_filesystem_tool_read_and_list(temp_workspace, permission_gate):
  fs_tool = FilesystemTool(
      workspace_root=temp_workspace, permission_gate=permission_gate
  )

  # Test read_file
  read_action = Action(
      action_id="act_01",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "README.md"},
  )
  result = await fs_tool.execute(read_action)
  assert result.success is True
  assert "Xeren Workspace" in result.data["content"]

  # Test list_dir
  list_action = Action(
      action_id="act_02",
      tool_name="filesystem",
      operation="list_dir",
      parameters={"path": "."},
  )
  list_result = await fs_tool.execute(list_action)
  assert list_result.success is True
  entry_names = [e["name"] for e in list_result.data["entries"]]
  assert "README.md" in entry_names
  assert "src" in entry_names

  # Test search_files
  search_action = Action(
      action_id="act_03",
      tool_name="filesystem",
      operation="search_files",
      parameters={"query": "main"},
  )
  search_result = await fs_tool.execute(search_action)
  assert search_result.success is True
  assert any("main.py" in m for m in search_result.data["matches"])


@pytest.mark.asyncio
async def test_task_tool_crud(temp_workspace):
  db_path = temp_workspace / "tasks.sqlite"
  task_tool = TaskTool(db_path=db_path)

  # 1. Create task
  create_action = Action(
      action_id="act_t1",
      tool_name="tasks",
      operation="create_task",
      parameters={
          "title": "Build Phase 1 Core",
          "description": "Implement strictly validated architecture",
          "priority": "high",
      },
  )
  c_res = await task_tool.execute(create_action)
  assert c_res.success is True
  task_id = c_res.data["task_id"]
  assert task_id == 1

  # 2. Get task
  get_action = Action(
      action_id="act_t2",
      tool_name="tasks",
      operation="get_task",
      parameters={"task_id": task_id},
  )
  g_res = await task_tool.execute(get_action)
  assert g_res.success is True
  assert g_res.data["title"] == "Build Phase 1 Core"

  # 3. Update task
  update_action = Action(
      action_id="act_t3",
      tool_name="tasks",
      operation="update_task",
      parameters={"task_id": task_id, "status": "completed"},
  )
  u_res = await task_tool.execute(update_action)
  assert u_res.success is True

  # 4. List tasks
  list_action = Action(
      action_id="act_t4",
      tool_name="tasks",
      operation="list_tasks",
      parameters={"status": "completed"},
  )
  l_res = await task_tool.execute(list_action)
  assert l_res.success is True
  assert len(l_res.data) == 1
  assert l_res.data[0]["id"] == task_id
