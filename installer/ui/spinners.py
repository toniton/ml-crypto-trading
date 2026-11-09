"""Progress indicators and task spinners."""

import contextlib
import sys
from typing import Generator

try:
    from rich.console import Console
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


@contextlib.contextmanager
def task_status(status_text: str) -> Generator[None, None, None]:
    """Displays a spinner or status indicator during a blocking action."""
    if _HAS_RICH:
        console = Console()
        with console.status(f"[cyan]{status_text}[/cyan]"):
            yield
    else:
        print(f"[*] {status_text}...", end="", flush=True)
        try:
            yield
            print(" [OK]")
        except Exception:
            print(" [FAILED]")
            raise
