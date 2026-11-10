"""Interactive input prompts with graceful fallback."""

import getpass
import sys
from typing import Callable, List, Optional, Tuple

try:
    import questionary
    _HAS_QUESTIONARY = True
except ImportError:
    _HAS_QUESTIONARY = False


def prompt_text(
    label: str,
    default: Optional[str] = None,
    validator: Optional[Callable[[str], bool]] = None,
) -> str:
    """Prompt the user for a text string."""
    default_hint = f" [{default}]" if default is not None else ""
    full_prompt = f"{label}{default_hint}: "

    while True:
        try:
            value = input(full_prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nInstallation aborted by user.")
            sys.exit(1)

        if not value and default is not None:
            return default

        if validator and not validator(value):
            print("Invalid input. Please try again.")
            continue

        return value


def prompt_password(
    label: str,
    default: Optional[str] = None,
) -> str:
    """Prompt the user for a masked secret or password."""
    default_hint = " [leave blank to keep default]" if default is not None else ""
    full_prompt = f"{label}{default_hint}: "

    try:
        value = getpass.getpass(full_prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nInstallation aborted by user.")
        sys.exit(1)

    if not value and default is not None:
        return default

    return value


def prompt_confirm(
    label: str,
    default: bool = True,
) -> bool:
    """Prompt the user for a yes/no confirmation."""
    choices_hint = " [Y/n]" if default else " [y/N]"
    full_prompt = f"{label}{choices_hint}: "

    while True:
        try:
            answer = input(full_prompt).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nInstallation aborted by user.")
            sys.exit(1)

        if not answer:
            return default

        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False

        print("Please answer 'y' or 'n'.")


def prompt_choice(
    label: str,
    choices: List[Tuple[str, str]],
    default_index: int = 0,
) -> str:
    """Prompt user to select one choice from a list of (key, display_label)."""
    if _HAS_QUESTIONARY:
        questionary_choices = [
            questionary.Choice(title=disp, value=key) for key, disp in choices
        ]
        default_val = choices[default_index][0] if choices else None
        try:
            result = questionary.select(
                label,
                choices=questionary_choices,
                default=default_val,
            ).ask()
            if result is not None:
                return result
        except Exception:
            pass  # Fall back to console select if questionary fails

    print(f"\n{label}")
    for idx, (_, disp) in enumerate(choices, start=1):
        indicator = "*" if (idx - 1) == default_index else " "
        print(f"  {idx}) {indicator} {disp}")

    prompt_str = f"Select [1-{len(choices)}] (default: {default_index + 1}): "

    while True:
        try:
            raw = input(prompt_str).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nInstallation aborted by user.")
            sys.exit(1)

        if not raw:
            return choices[default_index][0]

        if raw.isdigit():
            chosen_idx = int(raw) - 1
            if 0 <= chosen_idx < len(choices):
                return choices[chosen_idx][0]

        print(f"Please enter a number between 1 and {len(choices)}.")
