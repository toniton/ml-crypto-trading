"""UI elements for installer."""

from installer.ui.console import console
from installer.ui.prompts import (
    prompt_choice,
    prompt_confirm,
    prompt_password,
    prompt_text,
)
from installer.ui.spinners import task_status

__all__ = [
    "console",
    "prompt_choice",
    "prompt_confirm",
    "prompt_password",
    "prompt_text",
    "task_status",
]
