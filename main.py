"""Main application entry point for Xeren Assistant."""

import argparse
import asyncio
import sys
import uvicorn

# Force UTF-8 on Windows standard streams
if sys.platform == "win32":
  try:
    if hasattr(sys.stdout, "reconfigure"):
      sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
      sys.stderr.reconfigure(encoding="utf-8")
  except Exception:
    pass

from app.api import create_app
from app.cli import XerenCLI
from core.assistant import XerenAssistant


def main():
  parser = argparse.ArgumentParser(
      description="Xeren Assistant - Phase 1 Core"
  )
  subparsers = parser.add_subparsers(dest="command", help="Command to run")

  # CLI mode
  subparsers.add_parser("cli", help="Start interactive Rich terminal session")

  # API mode
  api_parser = subparsers.add_parser("api", help="Start FastAPI REST server")
  api_parser.add_argument(
      "--host", default="127.0.0.1", help="Host interface to bind"
  )
  api_parser.add_argument(
      "--port", type=int, default=8000, help="Port to listen on"
  )
  api_parser.add_argument(
      "--reload", action="store_true", help="Enable auto-reload"
  )

  # One-shot run mode
  run_parser = subparsers.add_parser(
      "run", help="Execute a single query and exit"
  )
  run_parser.add_argument("query", type=str, help="Instruction or query to run")

  # Daemon mode
  daemon_parser = subparsers.add_parser(
      "daemon",
      help=(
          "Start background desktop daemon, system tray, and global hotkey"
          " listener"
      ),
  )
  daemon_parser.add_argument(
      "--host", default="127.0.0.1", help="Host interface to bind"
  )
  daemon_parser.add_argument(
      "--port", type=int, default=8000, help="Port to listen on"
  )
  daemon_parser.add_argument(
      "--no-server",
      action="store_true",
      help="Do not start web server in daemon thread",
  )

  # Notify command
  notify_parser = subparsers.add_parser(
      "notify", help="Dispatch a desktop toast notification"
  )
  notify_parser.add_argument("title", type=str, help="Notification title")
  notify_parser.add_argument("message", type=str, help="Notification message")

  args = parser.parse_args()

  # Default to CLI if no subcommand provided
  if not args.command or args.command == "cli":
    assistant = XerenAssistant()
    cli = XerenCLI(assistant)
    asyncio.run(cli.run_interactive())

  elif args.command == "daemon":
    import time
    from desktop.daemon import DesktopDaemon

    daemon = DesktopDaemon(host=args.host, port=args.port)
    print(
        f"Starting Xeren Desktop Daemon (Tray, Hotkeys, Dashboard:"
        f" http://{args.host}:{args.port})"
    )
    status = daemon.start(run_server=not args.no_server)
    print(f"Daemon Status: {status}")
    try:
      while True:
        time.sleep(1)
    except KeyboardInterrupt:
      print("Stopping Desktop Daemon...")
      daemon.stop()

  elif args.command == "notify":
    from desktop.notifications import DesktopNotifier

    notifier = DesktopNotifier.get_instance()
    notifier.notify(title=args.title, message=args.message)
    print(f"Notification sent: {args.title} — {args.message}")

  elif args.command == "api":
    app = create_app()
    print(f"Starting Xeren Assistant API on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

  elif args.command == "run":
    from rich.console import Console
    from rich.markdown import Markdown

    console = Console()
    assistant = XerenAssistant()

    async def _execute():
      resp = await assistant.process_request(args.query)
      console.print(Markdown(resp.response_text))

    asyncio.run(_execute())


if __name__ == "__main__":
  main()
