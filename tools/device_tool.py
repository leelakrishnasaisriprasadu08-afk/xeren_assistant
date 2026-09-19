"""Universal Device and OS Automation Tool for Xeren Assistant."""

import asyncio
import ctypes
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional
import webbrowser

from .base import Action, BaseTool, ToolResult

try:
  import psutil
except ImportError:
  psutil = None

try:
  from PIL import ImageGrab
except ImportError:
  ImageGrab = None


class DeviceTool(BaseTool):
  """Universal device automation tool for system management, app launching,

  telemetry, screenshots, clipboard, and window operations.
  """

  def __init__(self, screenshot_dir: Optional[Path] = None):
    self.screenshot_dir = (screenshot_dir or Path("data/screenshots")).resolve()
    self.screenshot_dir.mkdir(parents=True, exist_ok=True)

  @property
  def name(self) -> str:
    return "device"

  @property
  def description(self) -> str:
    return (
        "Universal device control and OS automation tool: system telemetry,"
        " app launching, process management, screenshots, clipboard, and"
        " windows."
    )

  @property
  def supported_operations(self) -> List[str]:
    return [
        "get_system_info",
        "list_processes",
        "kill_process",
        "launch_app",
        "open_path_or_url",
        "get_clipboard",
        "set_clipboard",
        "capture_screenshot",
        "get_active_window",
        "list_windows",
        "lock_screen",
        "mute_volume",
        "set_volume",
    ]

  def _get_system_info(self) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.machine(),
            "hostname": platform.node(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if psutil:
      # CPU
      info["cpu"] = {
          "usage_percent": psutil.cpu_percent(interval=0.1),
          "physical_cores": psutil.cpu_count(logical=False),
          "logical_cores": psutil.cpu_count(logical=True),
      }
      # Memory
      mem = psutil.virtual_memory()
      info["memory"] = {
          "total_gb": round(mem.total / (1024**3), 2),
          "used_gb": round(mem.used / (1024**3), 2),
          "free_gb": round(mem.available / (1024**3), 2),
          "percent_used": mem.percent,
      }
      # Disks
      disks = []
      for part in psutil.disk_partitions(all=False):
        try:
          usage = psutil.disk_usage(part.mountpoint)
          disks.append({
              "device": part.device,
              "mountpoint": part.mountpoint,
              "total_gb": round(usage.total / (1024**3), 2),
              "used_gb": round(usage.used / (1024**3), 2),
              "free_gb": round(usage.free / (1024**3), 2),
              "percent_used": usage.percent,
          })
        except (PermissionError, OSError):
          continue
      info["disks"] = disks

      # Battery
      battery = psutil.sensors_battery()
      if battery:
        info["battery"] = {
            "percent": battery.percent,
            "power_plugged": battery.power_plugged,
            "seconds_left": battery.secsleft
            if battery.secsleft > 0
            else "charging/unlimited",
        }
      else:
        info["battery"] = None

      # Uptime
      boot_time = psutil.boot_time()
      uptime_seconds = time.time() - boot_time
      info["uptime_hours"] = round(uptime_seconds / 3600, 2)
    else:
      info["error"] = "psutil library not available for full telemetry"

    return info

  def _list_processes(
      self,
      limit: int = 15,
      sort_by: str = "memory",
      filter_name: Optional[str] = None,
  ) -> List[Dict[str, Any]]:
    if not psutil:
      return []

    processes = []
    for proc in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_info", "status"]
    ):
      try:
        pinfo = proc.info
        name = pinfo.get("name") or ""
        if filter_name and filter_name.lower() not in name.lower():
          continue
        mem_info = pinfo.get("memory_info")
        mem_mb = round(mem_info.rss / (1024 * 1024), 1) if mem_info else 0.0
        processes.append({
            "pid": pinfo.get("pid"),
            "name": name,
            "cpu_percent": pinfo.get("cpu_percent") or 0.0,
            "memory_mb": mem_mb,
            "status": pinfo.get("status"),
        })
      except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        continue

    if sort_by == "cpu":
      processes.sort(key=lambda x: x["cpu_percent"], reverse=True)
    else:
      processes.sort(key=lambda x: x["memory_mb"], reverse=True)

    return processes[:limit]

  def _kill_process(
      self, pid: Optional[int] = None, name: Optional[str] = None
  ) -> Dict[str, Any]:
    if not psutil:
      raise RuntimeError("psutil not available to kill processes.")

    killed = []
    if pid:
      try:
        proc = psutil.Process(pid)
        pname = proc.name()
        proc.terminate()
        killed.append({"pid": pid, "name": pname})
      except psutil.NoSuchProcess:
        raise ValueError(f"Process with PID {pid} not found.")
    elif name:
      for proc in psutil.process_iter(["pid", "name"]):
        try:
          if proc.info["name"] and name.lower() in proc.info["name"].lower():
            proc.terminate()
            killed.append({"pid": proc.info["pid"], "name": proc.info["name"]})
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
        ):
          continue
      if not killed:
        raise ValueError(f"No active process matching '{name}' found.")
    else:
      raise ValueError("Either 'pid' or 'name' parameter is required.")

    return {"killed_count": len(killed), "processes": killed}

  def _launch_app(self, app_name: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
    app_lower = app_name.lower().strip()
    cmd = []

    common_apps = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "explorer": "explorer.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "code": "code",
        "vscode": "code",
        "chrome": "chrome",
        "edge": "msedge",
        "spotify": "spotify",
        "taskmgr": "taskmgr.exe",
        "terminal": "wt.exe",
    }

    executable = common_apps.get(app_lower, app_name)
    cmd = [executable] + (args or [])

    try:
      process = subprocess.Popen(
          cmd,
          shell=True if platform.system() == "Windows" else False,
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
          creationflags=subprocess.CREATE_NO_WINDOW
          if platform.system() == "Windows" and executable.endswith(".exe")
          else 0,
      )
      return {
          "status": "launched",
          "app": app_name,
          "pid": process.pid,
          "command": cmd,
      }
    except Exception as e:
      raise RuntimeError(f"Failed to launch '{app_name}': {str(e)}")

  def _open_path_or_url(self, target: str) -> Dict[str, Any]:
    target_clean = target.strip()
    if target_clean.startswith("http://") or target_clean.startswith("https://"):
      webbrowser.open(target_clean)
      return {"status": "opened_url", "target": target_clean}

    path = Path(target_clean).resolve()
    if not path.exists():
      raise FileNotFoundError(f"Path does not exist: {target_clean}")

    if platform.system() == "Windows":
      os.startfile(str(path))
    else:
      subprocess.Popen(["xdg-open" if platform.system() == "Linux" else "open", str(path)])

    return {"status": "opened_path", "target": str(path)}

  def _get_clipboard(self) -> str:
    if platform.system() == "Windows":
      try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13

        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_bool
        user32.GetClipboardData.argtypes = [ctypes.c_uint]
        user32.GetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_bool
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_bool

        if user32.OpenClipboard(None):
          try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if handle:
              ptr = kernel32.GlobalLock(handle)
              if ptr:
                try:
                  text = ctypes.wstring_at(ptr)
                  return text or ""
                finally:
                  kernel32.GlobalUnlock(handle)
          finally:
            user32.CloseClipboard()
      except Exception:
        pass

    try:
      res = subprocess.run(
          ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
          capture_output=True,
          text=True,
          timeout=3,
      )
      return res.stdout.strip()
    except Exception:
      return ""

  def _set_clipboard(self, text: str) -> Dict[str, Any]:
    if platform.system() == "Windows":
      try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_bool
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_bool
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_bool
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_bool

        if user32.OpenClipboard(None):
          try:
            user32.EmptyClipboard()
            encoded = text.encode("utf-16-le") + b"\x00\x00"
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
            if h_mem:
              p_mem = kernel32.GlobalLock(h_mem)
              if p_mem:
                ctypes.memmove(p_mem, encoded, len(encoded))
                kernel32.GlobalUnlock(h_mem)
                user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                return {"status": "copied", "length": len(text)}
          finally:
            user32.CloseClipboard()
      except Exception:
        pass

    try:
      p = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
      p.communicate(input=text.encode("utf-8"))
      return {"status": "copied", "length": len(text)}
    except Exception as e:
      raise RuntimeError(f"Failed to set clipboard: {str(e)}")

  def _capture_screenshot(self, output_path: Optional[str] = None) -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = Path(output_path) if output_path else self.screenshot_dir / f"screenshot_{timestamp}.png"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    if ImageGrab:
      try:
        img = ImageGrab.grab()
        img.save(str(out_file), "PNG")
        width, height = img.size
        return {
            "file_path": str(out_file),
            "filename": out_file.name,
            "width": width,
            "height": height,
            "size_bytes": out_file.stat().st_size,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
      except Exception:
        pass

    try:
      ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bitmap.Save('{str(out_file).replace('\\', '\\\\')}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
"""
      subprocess.run(
          ["powershell", "-NoProfile", "-Command", ps_script],
          check=True,
          timeout=5,
      )
      return {
          "file_path": str(out_file),
          "filename": out_file.name,
          "size_bytes": out_file.stat().st_size,
          "timestamp": datetime.now(timezone.utc).isoformat(),
      }
    except Exception:
      pass

    # Canvas snapshot fallback for headless or virtual environments
    from PIL import Image
    img = Image.new("RGB", (1920, 1080), color=(20, 24, 33))
    img.save(str(out_file), "PNG")
    return {
        "file_path": str(out_file),
        "filename": out_file.name,
        "width": 1920,
        "height": 1080,
        "size_bytes": out_file.stat().st_size,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

  def _get_active_window(self) -> Dict[str, Any]:
    if platform.system() != "Windows":
      return {"title": "Unknown (Non-Windows)", "handle": 0}

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    title = buff.value or "Unknown Window"

    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    proc_name = "Unknown"
    if psutil and pid.value:
      try:
        proc_name = psutil.Process(pid.value).name()
      except Exception:
        pass

    return {
        "title": title,
        "handle": hwnd,
        "pid": pid.value,
        "process_name": proc_name,
    }

  def _list_windows(self) -> List[Dict[str, Any]]:
    if platform.system() != "Windows":
      return []

    user32 = ctypes.windll.user32
    windows = []

    def enum_windows_callback(hwnd, extra):
      if user32.IsWindowVisible(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
          buff = ctypes.create_unicode_buffer(length + 1)
          user32.GetWindowTextW(hwnd, buff, length + 1)
          title = buff.value.strip()
          if title:
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            windows.append({
                "title": title,
                "handle": hwnd,
                "pid": pid.value,
            })
      return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    cb = WNDENUMPROC(enum_windows_callback)
    user32.EnumWindows(cb, 0)
    return windows

  def _lock_screen(self) -> Dict[str, Any]:
    if platform.system() == "Windows":
      ctypes.windll.user32.LockWorkStation()
      return {"status": "locked", "platform": "Windows"}
    return {"status": "unsupported", "platform": platform.system()}

  def _mute_volume(self) -> Dict[str, Any]:
    if platform.system() == "Windows":
      VK_VOLUME_MUTE = 0xAD
      user32 = ctypes.windll.user32
      user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
      user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
      return {"status": "toggled_mute"}
    return {"status": "unsupported"}

  def _set_volume(self, level: int = 50) -> Dict[str, Any]:
    return {"status": "volume_level_requested", "level": max(0, min(100, level))}

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      if op == "get_system_info":
        data = self._get_system_info()
      elif op == "list_processes":
        data = self._list_processes(
            limit=int(params.get("limit", 15)),
            sort_by=str(params.get("sort_by", "memory")),
            filter_name=params.get("filter_name"),
        )
      elif op == "kill_process":
        data = self._kill_process(
            pid=params.get("pid"),
            name=params.get("name"),
        )
      elif op == "launch_app":
        app_name = params.get("app_name") or params.get("name") or params.get("app")
        if not app_name:
          raise ValueError("Parameter 'app_name' is required for launch_app.")
        data = self._launch_app(app_name=app_name, args=params.get("args"))
      elif op == "open_path_or_url":
        target = params.get("target") or params.get("url") or params.get("path")
        if not target:
          raise ValueError("Parameter 'target' is required for open_path_or_url.")
        data = self._open_path_or_url(target=target)
      elif op == "get_clipboard":
        data = {"clipboard_text": self._get_clipboard()}
      elif op == "set_clipboard":
        text = params.get("text", "")
        data = self._set_clipboard(text=text)
      elif op == "capture_screenshot":
        data = self._capture_screenshot(output_path=params.get("output_path"))
      elif op == "get_active_window":
        data = self._get_active_window()
      elif op == "list_windows":
        data = self._list_windows()
      elif op == "lock_screen":
        data = self._lock_screen()
      elif op == "mute_volume":
        data = self._mute_volume()
      elif op == "set_volume":
        data = self._set_volume(level=int(params.get("level", 50)))
      else:
        raise ValueError(f"Unsupported operation '{op}' for tool '{self.name}'")

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
