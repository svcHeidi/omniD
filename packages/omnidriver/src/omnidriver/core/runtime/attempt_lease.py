"""A small, local ownership lease for workflow output directories.

The lease is deliberately host-local.  A lock from another host or a malformed
record is not reclaimed: without shared ownership semantics, treating it as
stale could corrupt a live remote attempt.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

if os.name == "posix":
    import fcntl
elif os.name == "nt":
    import msvcrt


_LOCAL_LEASES: dict[Path, tuple[str, int]] = {}


class AttemptLeaseError(RuntimeError):
    """The output directory is already or ambiguously owned."""


@dataclass(frozen=True)
class AttemptLease:
    path: Path
    token: str


def attempt_lease_is_held(output_dir: Path) -> bool:
    """Whether this thread already owns the local lease for ``output_dir``."""
    path = Path(output_dir).resolve() / ".omnidriver-attempt.lock"
    owner = _LOCAL_LEASES.get(path)
    return owner is not None and owner[1] == threading.get_ident()


def _case_lease_path(case_root: Path) -> Path:
    """Stable ownership record for one mutable case directory.

    A case can be transactionally replaced by staging.  Its lock therefore
    cannot live *in* that directory: a rename would otherwise replace the
    lock inode while a workflow still holds it.  Keep the record as a named
    sibling, which is stable across replacement and also lets staging acquire
    ownership before the case exists for the first time.
    """
    root = Path(case_root).resolve()
    return root.parent / f".{root.name}.omnidriver-case.lock"


def case_lease_is_held(case_root: Path) -> bool:
    """Whether this thread already owns the local lease for ``case_root``."""
    path = _case_lease_path(case_root)
    owner = _LOCAL_LEASES.get(path)
    return owner is not None and owner[1] == threading.get_ident()


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_record(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _reclaimable_local_record(record: dict[str, object], hostname: str) -> bool:
    pid = record.get("pid")
    return (
        record.get("hostname") == hostname
        and isinstance(pid, int)
        and not isinstance(pid, bool)
        and not _pid_is_alive(pid)
    )


@contextmanager
def _lease_record_guard(path: Path) -> Iterator[None]:
    """Serialize inspection and replacement of the host-local lease record.

    The guard file is intentionally stable rather than deleted after use.
    Removing a lock file allows different contenders to lock different inodes,
    recreating the same read/unlink race this guard closes.
    """
    if os.name not in {"posix", "nt"}:
        raise AttemptLeaseError(
            "attempt leases require host-local advisory locking for safe recovery"
        )
    guard_path = path.with_name(f"{path.name}.guard")
    descriptor = os.open(guard_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "posix":
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        else:
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            while True:
                try:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        yield
    finally:
        if os.name == "posix":
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        else:
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        os.close(descriptor)


@contextmanager
def _acquire_local_lease(
    directory: Path,
    *,
    filename: str,
    resource_label: str,
    create_directory: bool,
) -> Iterator[AttemptLease]:
    # One physical directory must have one in-process ownership identity,
    # independent of relative spelling or a symlink alias.
    directory = Path(directory).resolve()
    if create_directory:
        directory.mkdir(parents=True, exist_ok=True)
    elif not directory.is_dir():
        raise AttemptLeaseError(f"{resource_label} does not exist: {directory}")
    path = directory / filename
    hostname = socket.gethostname()
    token = str(uuid.uuid4())
    record = {
        "schema_version": 1,
        "hostname": hostname,
        "pid": os.getpid(),
        "token": token,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lease_record_guard(path):
        while True:
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                existing = _read_record(path)
                if existing is not None and _reclaimable_local_record(existing, hostname):
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                owner = "an unreadable or remote owner" if existing is None else (
                    f"pid {existing.get('pid')!r} on host {existing.get('hostname')!r}"
                )
                raise AttemptLeaseError(
                    f"{resource_label} is already owned by {owner}: {path}"
                )
            else:
                with os.fdopen(descriptor, "w") as handle:
                    json.dump(record, handle, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                break
    lease = AttemptLease(path=path, token=token)
    _LOCAL_LEASES[path] = (token, threading.get_ident())
    try:
        yield lease
    finally:
        try:
            current = _read_record(path)
            if current is not None and current.get("token") == token:
                path.unlink(missing_ok=True)
        finally:
            if _LOCAL_LEASES.get(path) == (token, threading.get_ident()):
                _LOCAL_LEASES.pop(path, None)


@contextmanager
def acquire_attempt_lease(output_dir: Path) -> Iterator[AttemptLease]:
    """Exclusively own ``output_dir`` until the context exits.

    A dead same-host owner is reclaimed atomically by removing its record and
    retrying exclusive creation. Remote or malformed records fail closed.
    """
    with _acquire_local_lease(
        output_dir,
        filename=".omnidriver-attempt.lock",
        resource_label="output directory",
        create_directory=True,
    ) as lease:
        yield lease


@contextmanager
def acquire_case_lease(case_root: Path) -> Iterator[AttemptLease]:
    """Exclusively own an existing mutable case independently of its output path.

    The lease record is a stable sibling of the case, not content that may be
    copied or renamed with it.
    """
    root = Path(case_root).resolve()
    if not root.is_dir():
        raise AttemptLeaseError(f"case root does not exist: {root}")
    with _acquire_local_lease(
        root.parent,
        filename=_case_lease_path(root).name,
        resource_label="case root",
        create_directory=False,
    ) as lease:
        yield lease


@contextmanager
def acquire_case_staging_lease(case_root: Path) -> Iterator[AttemptLease]:
    """Own a case's stable lease while creating or replacing it.

    This deliberately uses the same sibling record as :func:`acquire_case_lease`.
    It is the only lease appropriate before a new staged case directory has
    been promoted into place.
    """
    root = Path(case_root).resolve()
    with _acquire_local_lease(
        root.parent,
        filename=_case_lease_path(root).name,
        resource_label="case root",
        create_directory=True,
    ) as lease:
        yield lease
