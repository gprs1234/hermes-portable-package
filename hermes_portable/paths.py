"""Runtime path helpers for portable Hermes installs."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_HOME = Path.home() / ".hermes"


def hermes_home(value: str | None = None) -> Path:
    """Resolve the Hermes runtime home.

    Precedence:
      1. explicit value
      2. HERMES_HOME environment variable
      3. ~/.hermes
    """
    raw = value or os.environ.get("HERMES_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_HOME.resolve()


def portable_home(value: str | None = None) -> Path:
    """Resolve the portable package management home."""
    raw = value or os.environ.get("HERMES_PORTABLE_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".hermes-portable").resolve()
