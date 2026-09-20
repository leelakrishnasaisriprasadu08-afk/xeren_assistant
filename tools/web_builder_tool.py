"""Autonomous Web Builder & Local Preview Deployment Tool for Xeren Assistant."""

import asyncio
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from .base import Action, BaseTool, ToolResult


class WebBuilderTool(BaseTool):
  """Tool for autonomous website generation, scaffolding, and local preview server deployment."""

  def __init__(
      self,
      deployments_dir: Optional[Path] = None,
      agent: Optional[Any] = None,
  ):
    self.deployments_dir = (deployments_dir or Path("data/deployments")).resolve()
    self.deployments_dir.mkdir(parents=True, exist_ok=True)
    if agent is None:
      from agents.web_deployer import WebDeployerAgent
      self.agent = WebDeployerAgent()
    else:
      self.agent = agent
    self._active_servers: Dict[str, Dict[str, Any]] = {}

  @property
  def name(self) -> str:
    return "web_builder"

  @property
  def description(self) -> str:
    return (
        "Autonomous Web & App Deployment Tool: scaffold full websites and web apps"
        " tailored to user ideology, launch live local preview servers, and monitor"
        " server health."
    )

  @property
  def supported_operations(self) -> List[str]:
    return [
        "scaffold_website",
        "deploy_preview",
        "stop_preview",
        "status_preview",
        "list_deployments",
    ]

  def _find_free_port(self, start_port: int = 3000) -> int:
    for port in range(start_port, start_port + 200):
      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
          return port
    return 8080

  def _scaffold_website(
      self, prompt: str, project_name: Optional[str] = None
  ) -> Dict[str, Any]:
    name = (
        project_name
        or re.sub(r"[^a-zA-Z0-9_\-]", "_", prompt[:25].strip().lower())
        or "xeren_web_app"
    )
    name = name.strip("_").lower() or "xeren_web_app"
    target_dir = self.deployments_dir / name
    target_dir.mkdir(parents=True, exist_ok=True)

    files = self.agent.generate_scaffold_files(prompt=prompt, project_name=name)
    created_files = []
    for fname, content in files.items():
      fpath = target_dir / fname
      fpath.parent.mkdir(parents=True, exist_ok=True)
      fpath.write_text(content, encoding="utf-8")
      created_files.append({"file": fname, "size_bytes": len(content.encode("utf-8"))})

    return {
        "status": "scaffolded",
        "project_name": name,
        "directory": str(target_dir),
        "files_created": created_files,
        "total_files": len(created_files),
    }

  def _deploy_preview(self, project_name: str, port: Optional[int] = None) -> Dict[str, Any]:
    name = project_name.strip().lower()
    target_dir = self.deployments_dir / name
    if not target_dir.exists():
      raise FileNotFoundError(f"Project directory not found: {target_dir}")

    # Check if already running
    if name in self._active_servers:
      existing = self._active_servers[name]
      return {
          "status": "already_running",
          "project_name": name,
          "port": existing["port"],
          "url": existing["url"],
          "directory": str(target_dir),
      }

    target_port = port or self._find_free_port(3000)

    # Spawn background Python HTTP / API server process
    server_py = target_dir / "server.py"
    if server_py.exists():
      cmd = [
          sys.executable,
          str(server_py),
          str(target_port),
      ]
      cwd = str(target_dir)
    else:
      cmd = [
          sys.executable,
          "-m",
          "http.server",
          str(target_port),
          "--directory",
          str(target_dir),
      ]
      cwd = None

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    url = f"http://127.0.0.1:{target_port}"
    server_info = {
        "project_name": name,
        "pid": proc.pid,
        "port": target_port,
        "url": url,
        "process": proc,
        "start_time": time.time(),
        "directory": str(target_dir),
    }
    self._active_servers[name] = server_info

    return {
        "status": "deployed",
        "project_name": name,
        "port": target_port,
        "url": url,
        "pid": proc.pid,
        "directory": str(target_dir),
    }

  def _stop_preview(self, project_name: str) -> Dict[str, Any]:
    name = project_name.strip().lower()
    if name not in self._active_servers:
      return {"status": "not_running", "project_name": name}

    info = self._active_servers.pop(name)
    proc: subprocess.Popen = info["process"]
    try:
      proc.terminate()
      proc.wait(timeout=2)
    except Exception:
      try:
        proc.kill()
      except Exception:
        pass

    return {"status": "stopped", "project_name": name, "port": info["port"]}

  def _status_preview(self, project_name: str) -> Dict[str, Any]:
    name = project_name.strip().lower()
    if name in self._active_servers:
      info = self._active_servers[name]
      proc: subprocess.Popen = info["process"]
      is_alive = proc.poll() is None
      uptime = round(time.time() - info["start_time"], 1)
      return {
          "status": "RUNNING" if is_alive else "STOPPED",
          "project_name": name,
          "port": info["port"],
          "url": info["url"],
          "pid": info["pid"],
          "uptime_seconds": uptime,
      }
    return {"status": "STOPPED", "project_name": name}

  def _list_deployments(self) -> List[Dict[str, Any]]:
    deployments = []
    if self.deployments_dir.exists():
      for p in self.deployments_dir.iterdir():
        if p.is_dir():
          is_running = p.name in self._active_servers
          deployments.append({
              "project_name": p.name,
              "path": str(p),
              "is_running": is_running,
              "url": self._active_servers[p.name]["url"] if is_running else None,
          })
    return deployments

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      if op == "scaffold_website":
        prompt = params.get("prompt") or params.get("description") or "Modern Interactive Web Platform"
        project_name = params.get("project_name") or params.get("name")
        data = self._scaffold_website(prompt=prompt, project_name=project_name)

      elif op == "deploy_preview":
        project_name = params.get("project_name") or params.get("name")
        if not project_name:
          # Try using first existing project
          deps = self._list_deployments()
          if deps:
            project_name = deps[0]["project_name"]
          else:
            raise ValueError("Parameter 'project_name' is required for deploy_preview.")
        port = int(params["port"]) if params.get("port") is not None else None
        data = self._deploy_preview(project_name=project_name, port=port)

      elif op == "stop_preview":
        project_name = params.get("project_name") or params.get("name")
        if not project_name:
          raise ValueError("Parameter 'project_name' is required for stop_preview.")
        data = self._stop_preview(project_name=project_name)

      elif op == "status_preview":
        project_name = params.get("project_name") or params.get("name")
        if not project_name:
          raise ValueError("Parameter 'project_name' is required for status_preview.")
        data = self._status_preview(project_name=project_name)

      elif op == "list_deployments":
        data = {"deployments": self._list_deployments()}

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
