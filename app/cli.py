"""Interactive Rich CLI for Xeren Assistant (Phase 2 with HITL Approvals)."""

import asyncio
import json
import sys

if sys.platform == "win32":
  try:
    if hasattr(sys.stdout, "reconfigure"):
      sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
      sys.stderr.reconfigure(encoding="utf-8")
  except Exception:
    pass

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from core.assistant import XerenAssistant
from security.permission_gate import ApprovalRequest


class XerenCLI:
  """Terminal interface using Rich for formatting, real-time interaction, and interactive approvals."""

  def __init__(self, assistant: XerenAssistant):
    self.assistant = assistant
    self.console = Console()
    # Bind interactive approval callback
    self.assistant.tool_registry.permission_gate.approval_callback = (
        self.request_approval
    )

  def print_banner(self) -> None:
    banner_text = (
        "[bold cyan]Xeren Assistant[/bold cyan] - [dim]Phase 2: Secure"
        " Execution[/dim]\n[italic]Your Personal AI Automation Assistant •"
        " Build Today, Power Xeren Tomorrow[/italic]\n\nType [bold"
        " green]'exit'[/bold green] to close, [bold yellow]'tools'[/bold"
        " yellow] to list capabilities, [bold yellow]'status'[/bold yellow] for"
        " telemetry."
    )
    self.console.print(
        Panel(banner_text, title="🤖 Xeren Assistant", border_style="cyan")
    )

  def request_approval(self, req: ApprovalRequest) -> bool:
    """Renders a visual approval modal in terminal and prompts user for confirmation."""
    self.console.print("\n")
    approval_content = [
        f"[bold yellow]⚠️  Action Requires Approval (ASK Level)[/bold yellow]",
        f"[bold cyan]Tool:[/bold cyan] {req.tool_name} | [bold cyan]Operation:[/bold cyan] {req.operation}",
        f"[bold yellow]Risk Level:[/bold yellow] [bold red]{req.risk_level.value}[/bold red]",
        f"[bold white]Description:[/bold white] {req.description}",
        f"[dim]Parameters:[/dim] {json.dumps(req.parameters, indent=2)}",
    ]

    if req.diff_preview and req.diff_preview != "(No changes detected)":
      self.console.print(
          Panel(
              "\n".join(approval_content),
              title="🔒 Security Gatekeeper",
              border_style="yellow",
          )
      )
      self.console.print("[bold green]Proposed Diff Preview:[/bold green]")
      self.console.print(
          Syntax(
              req.diff_preview,
              "diff",
              theme="monokai",
              line_numbers=True,
          )
      )
    else:
      self.console.print(
          Panel(
              "\n".join(approval_content),
              title="🔒 Security Gatekeeper",
              border_style="yellow",
          )
      )

    while True:
      choice = (
          self.console.input(
              "\n[bold yellow]Approve this action? [Y]es / [N]o / [C]ancel >[/bold yellow] "
          )
          .strip()
          .lower()
      )
      if choice in ["y", "yes"]:
        self.console.print("[bold green]✔ Action Approved.[/bold green]\n")
        return True
      elif choice in ["n", "no", "c", "cancel"]:
        self.console.print("[bold red]✖ Action Rejected by user.[/bold red]\n")
        return False
      else:
        self.console.print("Please enter 'y' to approve or 'n' to reject.")

  def show_tools(self) -> None:
    table = Table(title="Registered Tools & Operations", border_style="cyan")
    table.add_column("Tool", style="bold green")
    table.add_column("Operation", style="cyan")
    table.add_column("Permission", style="magenta")
    table.add_column("Risk", style="yellow")
    table.add_column("Description", style="white")

    for tool in self.assistant.tool_registry.list_tools():
      for op in tool["operations"]:
        table.add_row(
            tool["name"],
            op["operation"],
            op["permission_level"],
            op["risk_level"],
            op["description"],
        )
    self.console.print(table)

  def show_status(self) -> None:
    summary = self.assistant.analytics_tracker.get_summary()
    table = Table(title="Xeren Telemetry & Analytics", border_style="blue")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold white")

    table.add_row("Total Requests", str(summary["total_requests"]))
    table.add_row("Successful Requests", str(summary["successful_requests"]))
    table.add_row("Failed Requests", str(summary["failed_requests"]))
    table.add_row(
        "Success Rate", f"{summary['success_rate_percent']}%"
    )
    self.console.print(table)

  async def run_interactive(self) -> None:
    self.print_banner()

    while True:
      try:
        user_input = self.console.input("\n[bold cyan]xeren >[/bold cyan] ").strip()
        if not user_input:
          continue

        if user_input.lower() in ["exit", "quit"]:
          self.console.print("[dim]Goodbye![/dim]")
          break

        if user_input.lower() == "tools":
          self.show_tools()
          continue

        if user_input.lower() == "status":
          self.show_status()
          continue

        with self.console.status("[bold green]Thinking and planning...[/bold green]"):
          resp = await self.assistant.process_request(user_input)

        if resp.success:
          self.console.print("\n" + "=" * 50)
          self.console.print(Markdown(resp.response_text))
          self.console.print("=" * 50)
          self.console.print(
              f"[dim]Trace ID: {resp.trace_id[:8]}... | Duration: {resp.duration_ms:.1f}ms[/dim]"
          )
        else:
          self.console.print(f"[bold red]Execution Notice:[/bold red] {resp.error or resp.response_text}")

      except (KeyboardInterrupt, EOFError):
        self.console.print("\n[dim]Session interrupted. Exiting...[/dim]")
        break
      except Exception as e:
        self.console.print(f"[bold red]Unexpected Error:[/bold red] {str(e)}")


def run_cli():
  assistant = XerenAssistant()
  cli = XerenCLI(assistant)
  asyncio.run(cli.run_interactive())
