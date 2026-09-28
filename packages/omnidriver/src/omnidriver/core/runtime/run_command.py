"""The one place an ``omnidriver run`` child command is built.

Every spawned/advertised child must rebuild the parent's provider stack via
``--plugin <DriverContext.plugin_selector>``; a context with no selector
gets no flag rather than guessing one.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext


def omnidriver_run_command(driver_context: "DriverContext", *arguments: str) -> list[str]:
    """``python -m omnidriver run [--plugin <selector>] <arguments...>``."""
    command = [sys.executable, "-m", "omnidriver", "run"]
    if driver_context.plugin_selector is not None:
        command.extend(["--plugin", driver_context.plugin_selector])
    command.extend(arguments)
    return command
