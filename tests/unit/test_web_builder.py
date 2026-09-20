"""Unit tests for WebBuilderTool and WebDeployerAgent."""

from pathlib import Path
import pytest
from tools.base import Action
from tools.web_builder_tool import WebBuilderTool


@pytest.fixture
def builder_tool(tmp_path: Path) -> WebBuilderTool:
  return WebBuilderTool(deployments_dir=tmp_path / "deployments")


@pytest.mark.asyncio
async def test_web_builder_scaffolding(builder_tool: WebBuilderTool):
  action = Action(
      action_id="act_scaffold",
      tool_name="web_builder",
      operation="scaffold_website",
      parameters={
          "prompt": "Build a modern decentralized AI analytics dashboard with glassmorphism and real-time metrics",
          "project_name": "ai_analytics",
      },
  )
  res = await builder_tool.execute(action)
  assert res.success is True
  assert res.data["project_name"] == "ai_analytics"
  assert res.data["total_files"] >= 4

  proj_dir = Path(res.data["directory"])
  assert (proj_dir / "index.html").exists()
  assert (proj_dir / "styles.css").exists()
  assert (proj_dir / "app.js").exists()
  assert (proj_dir / "README.md").exists()


@pytest.mark.asyncio
async def test_web_builder_preview_lifecycle(builder_tool: WebBuilderTool):
  # 1. Scaffold first
  await builder_tool.execute(Action(
      action_id="act_scaffold",
      tool_name="web_builder",
      operation="scaffold_website",
      parameters={"prompt": "Portfolio site", "project_name": "portfolio"},
  ))

  # 2. Deploy preview
  res_deploy = await builder_tool.execute(Action(
      action_id="act_deploy",
      tool_name="web_builder",
      operation="deploy_preview",
      parameters={"project_name": "portfolio"},
  ))
  assert res_deploy.success is True
  assert "url" in res_deploy.data
  assert res_deploy.data["port"] >= 3000

  # 3. Status
  res_stat = await builder_tool.execute(Action(
      action_id="act_stat",
      tool_name="web_builder",
      operation="status_preview",
      parameters={"project_name": "portfolio"},
  ))
  assert res_stat.success is True
  assert res_stat.data["status"] == "RUNNING"

  # 4. Stop preview
  res_stop = await builder_tool.execute(Action(
      action_id="act_stop",
      tool_name="web_builder",
      operation="stop_preview",
      parameters={"project_name": "portfolio"},
  ))
  assert res_stop.success is True
  assert res_stop.data["status"] == "stopped"
