"""Terminal presentation and styling helpers."""

import sys
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


class InstallerConsole:
    """Handles terminal formatting and styled output."""

    def __init__(self) -> None:
        if _HAS_RICH:
            self._rich_console = Console()
            self._rich_error_console = Console(stderr=True)
        else:
            self._rich_console = None
            self._rich_error_console = None

    def print_banner(self, title: str, subtitle: str) -> None:
        if self._rich_console:
            banner_text = Text()
            banner_text.append(f"{title}\n", style="bold cyan")
            banner_text.append(subtitle, style="dim white")
            self._rich_console.print(Panel(banner_text, border_style="cyan"))
        else:
            print("\n" + "=" * 50)
            print(f" {title}")
            print(f" {subtitle}")
            print("=" * 50 + "\n")

    def print_section(self, title: str) -> None:
        if self._rich_console:
            self._rich_console.rule(f"[bold yellow]{title}[/bold yellow]")
        else:
            print(f"\n--- {title} ---")

    def info(self, message: str) -> None:
        if self._rich_console:
            self._rich_console.print(f"[blue]ℹ[/blue] {message}")
        else:
            print(f"[*] {message}")

    def success(self, message: str) -> None:
        if self._rich_console:
            self._rich_console.print(f"[bold green]✔[/bold green] {message}")
        else:
            print(f"[✓] {message}")

    def warning(self, message: str) -> None:
        if self._rich_console:
            self._rich_console.print(f"[bold yellow]⚠[/bold yellow] {message}")
        else:
            print(f"[!] {message}")

    def error(self, message: str) -> None:
        if self._rich_error_console:
            self._rich_error_console.print(f"[bold red]✖[/bold red] {message}")
        else:
            print(f"[✗] {message}", file=sys.stderr)


console = InstallerConsole()
