"""Ending the processes a run starts, by process group.

A step is its own session, so ending the omnidriver that started it does not
end the step. Every process this module runs or is told about is ended through
its group, and a group is judged alive while any member is, whether or not its
leader still is."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .workflow_state import WorkflowStepState, workflow_state_from_json

#: Processes being waited on in this one, each with the state file of the run
#: it is (for a child omnidriver), whose recorded steps are ended with it.
_LIVE: dict[subprocess.Popen[Any], Path | None] = {}
_SPAWNING = 0
_STOP = threading.Event()
_STOP_SIGNAL = 0

#: How long a child omnidriver gets to end its own step after a SIGTERM.
CHILD_GRACE_S = 3.0


def group_alive(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_group(group: int, *, grace: float = 1.0, reap: Any = None) -> None:
    """SIGTERM a process group, then SIGKILL it once ``grace`` seconds pass with a member left.

    ``reap`` is called while waiting, for a leader this process must reap before the group reads as gone.
    """
    try:
        os.killpg(group, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if reap is not None:
            reap()
        if not group_alive(group):
            return
        time.sleep(0.02)
    try:
        os.killpg(group, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def terminate_process(process: subprocess.Popen[Any], *, grace: float = 1.0) -> None:
    """End ``process`` and every descendant in its group, and reap it."""
    if os.name != "posix":
        process.kill()
        process.wait()
        return
    terminate_group(process.pid, grace=grace, reap=process.poll)
    process.wait()


def _recorded_groups(state_path: Path) -> list[int]:
    """The process groups of the steps ``state_path`` records as running on this host."""
    try:
        state = workflow_state_from_json(json.loads(Path(state_path).read_text()))
    except (OSError, ValueError, KeyError):
        return []
    return [step.pid for step in state.steps if recorded_here(step) and step.pid is not None]


def recorded_here(step: WorkflowStepState) -> bool:
    """Whether ``step`` is recorded running, with a pid, by this host."""
    return (
        os.name == "posix" and step.status == "running" and step.pid is not None
        and (step.host or {}).get("hostname") == socket.gethostname()
    )


def terminate_recorded_steps(state_path: Path, *, grace: float = 1.0) -> None:
    """End the process group of every step ``state_path`` records as running."""
    for group in _recorded_groups(state_path):
        terminate_group(group, grace=grace)


def has_live_steps() -> bool:
    return bool(_LIVE)


@contextmanager
def spawning() -> Iterator[None]:
    """Mark a process as being started and not yet registered, so a signal in that window still stops it."""
    global _SPAWNING
    _SPAWNING += 1
    try:
        yield
    finally:
        _SPAWNING -= 1


def register(process: subprocess.Popen[Any], state_path: Path | None = None) -> None:
    _LIVE[process] = state_path


def unregister(process: subprocess.Popen[Any]) -> None:
    _LIVE.pop(process, None)


def request_stop(number: int) -> None:
    """Ask every process being waited on to be ended; ``number`` is the signal that asked."""
    global _STOP_SIGNAL
    _STOP_SIGNAL = number
    _STOP.set()


def stop_requested() -> bool:
    return _STOP.is_set()


def stop_signal() -> int:
    return _STOP_SIGNAL


def clear_stop_request() -> None:
    _STOP.clear()


def _kill_live_groups() -> None:
    for process, state_path in list(_LIVE.items()):
        groups = [process.pid, *(_recorded_groups(state_path) if state_path is not None else ())]
        for group in groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def on_signal(number: int) -> None:
    """What SIGTERM or SIGINT does to a CLI that runs processes.

    Nothing running: it stops the CLI. The first signal while something runs
    asks the waits to end it gracefully; a repeat kills every group at once
    and stops.
    """
    if not (_LIVE or _SPAWNING):
        raise SystemExit(128 + number)
    if _STOP.is_set():
        _kill_live_groups()
        raise SystemExit(128 + number)
    request_stop(number)


def install_signal_handlers() -> dict[int, Any]:
    """Route SIGTERM and SIGINT to :func:`on_signal`, except one the parent ignored; returns the handlers to restore."""
    previous: dict[int, Any] = {}
    for number in (signal.SIGTERM, signal.SIGINT):
        try:
            if signal.getsignal(number) is signal.SIG_IGN:
                continue
            previous[number] = signal.signal(number, lambda received, _frame: on_signal(received))
        except ValueError:
            return previous
    return previous


def run_child(
    command: Sequence[str], *, env: Mapping[str, str] | None = None, timeout: float | None = None,
    state_path: Path | None = None, cwd: Path | None = None, grace: float = CHILD_GRACE_S,
) -> subprocess.CompletedProcess[str]:
    """Run a command in its own process group and capture its output.

    On timeout, and when this process is told to stop, the step ``state_path``
    records as running is ended before the child, which gets ``grace``
    seconds to end its own. A timeout raises
    ``subprocess.TimeoutExpired``; a stop raises ``SystemExit`` with the
    signal's code.
    """
    with spawning():
        process = subprocess.Popen(
            list(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd,
            env=None if env is None else dict(env), start_new_session=(os.name == "posix"),
        )
        register(process, state_path)
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        while True:
            if _STOP.is_set():
                _end(process, state_path, grace)
                raise SystemExit(128 + _STOP_SIGNAL)
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                _end(process, state_path, grace)
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(list(command), timeout, output=stdout, stderr=stderr)
            try:
                stdout, stderr = process.communicate(timeout=0.1 if remaining is None else min(0.1, remaining))
            except subprocess.TimeoutExpired:
                continue
            return subprocess.CompletedProcess(list(command), process.returncode, stdout, stderr)
    finally:
        unregister(process)


def _end(process: subprocess.Popen[Any], state_path: Path | None, grace: float) -> None:
    if state_path is not None:
        terminate_recorded_steps(state_path)
    terminate_process(process, grace=grace)
