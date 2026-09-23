"""The write channel's conformance suite.

The 2026-09-22 roadmap enumerates what must be covered before any route
migrates onto this channel (Tasks 8-14). ``CHANNEL_CONFORMANCE_CASES`` names
every one of those eighteen cases; ``test_every_conformance_case_has_a_test``
is the suite's own completeness check, so a missing case is a visible name
rather than an absence nobody notices.

Several cases are already exercised, in more depth, by
``test_case_transaction.py`` (Task 5) and ``test_case_transaction_recovery.py``
(Task 6) and by ``test_case_writer_capability.py`` (Task 3). Rather than
literally importing those test functions -- this repository's test tree has
no ``__init__.py`` and runs under ``--import-mode=importlib``, so sibling test
modules are not reliably importable from one another -- the cases below call
the same production entry points those files already prove, at the depth this
suite needs to have its own name for each case. A gap in one of those other
files would still be a gap here too; this suite is the inventory, not a
substitute for reading them.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from omnidriver.core import case_transaction, case_write, plugin_capabilities, provider_stack
from omnidriver.core import provider_identity
from omnidriver.core.planning_types import SimulationAuditItem
from omnidriver.core.runtime.attempt_lease import acquire_case_lease
from omnidriver.core.runtime.launch_readiness import is_launchable

#: Every case the write channel must handle before any route migrates onto
#: it. A name here with no test is a visible gap; a case not listed is one
#: nobody decided to leave out. Derived from the 2026-09-22 roadmap §4.
CHANNEL_CONFORMANCE_CASES = (
    "complete_plan_serialization_and_identity",
    "no_hidden_mutable_payloads",
    "format_specific_patching",
    "repeated_edits_to_one_file",
    "missing_files",
    "new_files",
    "file_modes",
    "rollback_after_injected_failure",
    "interrupted_recovery",
    "rollback_failure",
    "stale_input",
    "stale_build",
    "changed_indirect_dependency",
    "replay_after_an_uncertain_result",
    "competing_attempts",
    "path_escape_and_symlinks",
    "duplicate_ownership",
    "post_write_evidence_unavailable",
)

_root_makes_chmod_tests_meaningless = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores the write-permission bit this test injects a failure with",
)


def test_every_conformance_case_has_a_test():
    """The suite's own completeness check."""
    import inspect
    import sys

    module = sys.modules[__name__]
    names = {name for name, _ in inspect.getmembers(module, inspect.isfunction)}
    missing = [
        case for case in CHANNEL_CONFORMANCE_CASES
        if f"test_{case}" not in names
    ]
    assert not missing, f"conformance cases with no test: {missing}"


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def _parameter(**overrides):
    fields = dict(
        qualified_id="$TEST.value", owner="org.a", document="constant/a",
        key_path=("value",), binding={}, value=1.0, value_kind="scalar",
        source="case",
    )
    fields.update(overrides)
    return case_write.ParameterAssignment(**fields)


def _plan(case_root: Path, files, preconditions=(), **overrides):
    fields = dict(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.a",
        workflow="w", source_artifacts=(), parameters=(_parameter(),),
        requested_by="test",
    )
    fields.update(overrides)
    request = case_write.CaseMutationRequest(**fields)
    return case_write.CaseWritePlan(
        request=request, files=tuple(files), preconditions=tuple(preconditions),
        semantic_owner_id="org.a", stack_identity="0" * 64,
        created_at="2026-09-22T00:00:00Z",
    )


def _rendered(path, content, **kwargs):
    return case_write.RenderedFile(
        path=path, content=content, mode=kwargs.get("mode"),
        exists_before=kwargs.get("exists_before", False),
        before_digest=kwargs.get("before_digest"),
        renderer_id=kwargs.get("renderer_id", "org.r"),
        format=kwargs.get("format", "f"),
    )


class _Profile:
    def __init__(self, requires=()):
        self.requires = tuple(requires)
        self.case_files = ()


# --------------------------------------------------------------------------
# 1: complete plan serialization and identity
# --------------------------------------------------------------------------


def test_complete_plan_serialization_and_identity(tmp_path):
    """W1: the serialized plan must contain every value that will be
    written, and its digest must be stable and order-insensitive (files and
    parameters are sorted canonically before hashing, per `plan_digest`'s
    `_digest_payload`)."""
    two_params = (
        _parameter(qualified_id="$TEST.a", document="constant/a", key_path=("a",)),
        _parameter(qualified_id="$TEST.b", document="constant/b", key_path=("b",)),
    )
    files_forward = [_rendered("constant/a", b"one\n"), _rendered("constant/b", b"two\n")]

    def _request(parameters):
        return case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=tmp_path, adapter_id="org.a",
            workflow="w", source_artifacts=(), parameters=parameters,
            requested_by="test",
        )

    forward = case_write.CaseWritePlan(
        request=_request(two_params), files=tuple(files_forward),
        preconditions=(), semantic_owner_id="org.a", stack_identity="0" * 64,
        created_at="2026-09-22T00:00:00Z",
    )
    payload = forward.to_json()
    values = {p["expanded_key_path"][0]: p["value"] for p in payload["request"]["parameters"]}
    assert values == {"a": 1.0, "b": 1.0}
    assert all(f["content_base64"] for f in payload["files"])

    reordered = case_write.CaseWritePlan(
        request=_request(tuple(reversed(two_params))),
        files=tuple(reversed(files_forward)),
        preconditions=(), semantic_owner_id="org.a", stack_identity="0" * 64,
        created_at="2026-09-22T00:00:00Z",
    )
    assert forward.to_json() != reordered.to_json()  # to_json preserves review order
    assert forward.plan_digest == reordered.plan_digest  # the digest does not

    restored = case_write.CaseWritePlan.from_json(forward.to_json())
    assert restored.plan_digest == forward.plan_digest


# --------------------------------------------------------------------------
# 2: no hidden mutable payloads
# --------------------------------------------------------------------------


def test_no_hidden_mutable_payloads(tmp_path):
    """W1: `frozen=True` stops rebinding a field, not mutating what it points
    at. The closed `VALUE_KINDS` vocabulary has no generic "dictionary" kind
    (a plan-snippet claim that does not match `contracts/dictionary.py` --
    reported, not followed); `dimensioned_scalar` is the mapping-shaped kind
    it actually declares, and a mapping-valued parameter must be frozen too."""
    assignment = _parameter(
        value={"value": 50000.0, "dimensions": (0, -3, 0, 0, 0, 1, 0)},
        value_kind="dimensioned_scalar",
    )
    with pytest.raises(TypeError):
        assignment.value["value"] = 1.0
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    with pytest.raises(Exception):
        plan.files = ()


# --------------------------------------------------------------------------
# 3: format-specific patching
# --------------------------------------------------------------------------


class _FormatARenderer:
    plugin_id = "org.format_a"

    def get_profile(self):
        return _Profile()

    def get_rendered_formats(self):
        return frozenset({"format_a"})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env):
        return (
            case_write.RenderedFile(
                path="constant/a", content=b"alpha\n", mode=None,
                exists_before=False, before_digest=None,
                renderer_id=self.plugin_id, format="format_a",
            ),
        )


class _FormatBRenderer:
    plugin_id = "org.format_b"

    def get_profile(self):
        return _Profile()

    def get_rendered_formats(self):
        return frozenset({"format_b"})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env):
        return (
            case_write.RenderedFile(
                path="system/b", content=b"beta\n", mode=None,
                exists_before=False, before_digest=None,
                renderer_id=self.plugin_id, format="format_b",
            ),
        )


def test_format_specific_patching(tmp_path):
    """A plan spanning two formats, each rendered by its own declarer,
    committed in one transaction."""
    capabilities = provider_stack.compose(
        provider_stack.order_providers([_FormatARenderer(), _FormatBRenderer()])
    )
    rendered = capabilities.case_writer.render(
        object(), snapshot_root=tmp_path, driver_context=object(),
    )
    assert {r.renderer_id for r in rendered} == {"org.format_a", "org.format_b"}

    plan = _plan(tmp_path, rendered)
    record = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None,
    )
    assert (tmp_path / "constant" / "a").read_bytes() == b"alpha\n"
    assert (tmp_path / "system" / "b").read_bytes() == b"beta\n"
    assert record.status == "committed"


# --------------------------------------------------------------------------
# 4: repeated edits to one file
# --------------------------------------------------------------------------


class _TwoFileRenderer:
    plugin_id = "org.two"

    def get_profile(self):
        return _Profile()

    def get_rendered_formats(self):
        return frozenset({"fmt"})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env):
        return (
            case_write.RenderedFile(
                path="constant/a", content=b"one\n", mode=None,
                exists_before=False, before_digest=None,
                renderer_id=self.plugin_id, format="fmt",
            ),
            case_write.RenderedFile(
                path="constant/a", content=b"two\n", mode=None,
                exists_before=False, before_digest=None,
                renderer_id=self.plugin_id, format="fmt",
            ),
        )


class _FoldedRenderer(_TwoFileRenderer):
    plugin_id = "org.folded"

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env):
        return (
            case_write.RenderedFile(
                path="constant/a", content=b"one\ntwo\n", mode=None,
                exists_before=False, before_digest=None,
                renderer_id=self.plugin_id, format="fmt",
            ),
        )


def test_repeated_edits_to_one_file(tmp_path):
    """`CaseWritePlan` refuses two `RenderedFile`s at one path, so a renderer
    handling two parameters landing in one document must fold them into one
    rendering."""
    two_files = plugin_capabilities.adapt_plugin_capabilities(_TwoFileRenderer())
    rendered = two_files.case_writer.render(
        object(), snapshot_root=tmp_path, driver_context=object(),
    )
    with pytest.raises(ValueError, match="written twice"):
        _plan(tmp_path, rendered)

    folded = plugin_capabilities.adapt_plugin_capabilities(_FoldedRenderer())
    one_file = folded.case_writer.render(
        object(), snapshot_root=tmp_path, driver_context=object(),
    )
    plan = _plan(tmp_path, one_file)
    case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    content = (tmp_path / "constant" / "a").read_bytes()
    assert b"one" in content and b"two" in content


# --------------------------------------------------------------------------
# 5: missing files
# --------------------------------------------------------------------------


def test_missing_files(tmp_path):
    """A precondition expects an existing file with a digest; it was deleted
    since planning. Refused by name, distinct from `stale_input`'s changed
    (but still present) content."""
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"original\n")
    digest = case_write._digest_bytes(b"original\n")
    (tmp_path / "constant" / "a").unlink()

    plan = _plan(
        tmp_path,
        [_rendered("constant/a", b"new\n", exists_before=True, before_digest=digest)],
        preconditions=[case_write.Precondition(
            kind="file", target="constant/a", digest=digest, must_be_absent=False,
        )],
    )
    with pytest.raises(case_transaction.CaseTransactionError, match="missing"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


# --------------------------------------------------------------------------
# 6: new files
# --------------------------------------------------------------------------


def test_new_files(tmp_path):
    plan = _plan(tmp_path, [_rendered("constant/brand_new", b"hello\n")])
    record = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None,
    )
    assert (tmp_path / "constant" / "brand_new").read_bytes() == b"hello\n"
    assert record.status == "committed"


# --------------------------------------------------------------------------
# 7: file modes
# --------------------------------------------------------------------------


def test_file_modes(tmp_path):
    (tmp_path / "constant").mkdir()
    script = tmp_path / "constant" / "Allrun"
    script.write_bytes(b"#!/bin/sh\n")
    script.chmod(0o755)
    before = case_write._digest_bytes(b"#!/bin/sh\n")
    plan = _plan(tmp_path, [
        _rendered("constant/Allrun", b"#!/bin/sh\necho hi\n",
                  exists_before=True, before_digest=before, mode=0o755),
    ])
    case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert script.stat().st_mode & 0o777 == 0o755


@_root_makes_chmod_tests_meaningless
def test_file_modes_an_unreadable_existing_file_is_a_transaction_error_not_a_leak(tmp_path):
    """R3 blocker 1 (2026-09-23): closest existing case to file modes,
    since it is one of those modes -- 0o000 -- that made the pre-existing
    file unreadable. `_before_image`'s `target.read_bytes()` used to raise a
    bare `PermissionError` that escaped `commit_case_write` unwrapped."""
    first = _plan(tmp_path, [_rendered("constant/a", b"one\n", mode=0o000)])
    case_transaction.commit_case_write(first, driver_context=object(), execution_env=None)
    before = case_write._digest_bytes(b"one\n")
    second = _plan(tmp_path, [
        _rendered("constant/a", b"two\n", exists_before=True, before_digest=before),
    ])
    try:
        with pytest.raises(case_transaction.CaseTransactionError, match="constant/a"):
            case_transaction.commit_case_write(
                second, driver_context=object(), execution_env=None,
            )
    finally:
        (tmp_path / "constant" / "a").chmod(0o644)


# --------------------------------------------------------------------------
# 8: rollback after injected failure
# --------------------------------------------------------------------------


@_root_makes_chmod_tests_meaningless
def test_rollback_after_injected_failure(tmp_path):
    (tmp_path / "constant").mkdir()
    existing = tmp_path / "constant" / "a"
    existing.write_bytes(b"original\n")
    before = case_write._digest_bytes(b"original\n")
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"replaced\n", exists_before=True, before_digest=before),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )
        assert existing.read_bytes() == b"original\n"
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


# --------------------------------------------------------------------------
# 9: interrupted recovery
# --------------------------------------------------------------------------


def test_interrupted_recovery(tmp_path, monkeypatch):
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"original\n")
    before = case_write._digest_bytes(b"original\n")
    calls = {"n": 0}
    real = case_transaction._write_one

    def _die_after_first(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt("simulated interruption")
        return real(*args, **kwargs)

    monkeypatch.setattr(case_transaction, "_write_one", _die_after_first)
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"new\n", exists_before=True, before_digest=before),
        _rendered("constant/b", b"two\n"),
    ])
    with pytest.raises(KeyboardInterrupt):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert case_transaction.pending_transaction(tmp_path)

    record = case_transaction.recover_case_transaction(tmp_path)
    assert record.status == "rolled_back"
    assert (tmp_path / "constant" / "a").read_bytes() == b"original\n"
    assert not case_transaction.pending_transaction(tmp_path)


# --------------------------------------------------------------------------
# 10: rollback failure
# --------------------------------------------------------------------------


@_root_makes_chmod_tests_meaningless
def test_rollback_failure(tmp_path, monkeypatch):
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"original\n")
    before = case_write._digest_bytes(b"original\n")
    monkeypatch.setattr(
        case_transaction, "_restore_one",
        lambda *a, **k: (_ for _ in ()).throw(OSError("restore failed")),
    )
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"new\n", exists_before=True, before_digest=before),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError, match="rollback"):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )
        assert case_transaction.pending_transaction(tmp_path)
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


# --------------------------------------------------------------------------
# 11: stale input
# --------------------------------------------------------------------------


def test_stale_input(tmp_path):
    """The precondition target still exists, but its content changed since
    the plan was made -- distinct from `missing_files`, where it vanished."""
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"changed since planning\n")
    plan = _plan(
        tmp_path,
        [_rendered("constant/a", b"new\n", exists_before=True, before_digest="a" * 64)],
        preconditions=[case_write.Precondition(
            kind="file", target="constant/a", digest="a" * 64, must_be_absent=False,
        )],
    )
    with pytest.raises(case_transaction.CaseTransactionError, match="constant/a"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert (tmp_path / "constant" / "a").read_bytes() == b"changed since planning\n"


# --------------------------------------------------------------------------
# 12: stale build
# --------------------------------------------------------------------------


class _StackProfile:
    def __init__(self, requires=()):
        self.requires = tuple(requires)
        self.case_files = ()


class _StackProvider:
    """Implements `case_writer` (not digested) and `get_profile` (digested
    via `cxx_mapping`), so `resolutions()` gives one capability a real winner
    with a placeholder digest -- the shape audit finding C4 describes."""

    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id

    def get_profile(self):
        return _StackProfile()

    def get_rendered_formats(self):
        return frozenset({"openfoam_dictionary"})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env):
        return ()


def _installed_providers():
    return (_StackProvider("org.format"),)


def _stack_identity_for(providers) -> provider_identity.StackIdentity:
    ordered = provider_stack.order_providers(providers)
    resolved = provider_stack.resolutions(ordered)
    identities = tuple(
        provider_identity.ProviderIdentity(
            id=provider.plugin_id, version="1.0", api_version="2",
            source="test", provider_digest="d",
        )
        for provider in ordered
    )
    return provider_identity.build_stack_identity(providers=identities, resolutions=resolved)


def test_stale_build(tmp_path):
    """A plan bound to one stack is refused against another.

    Known limit (audit finding C4, recorded not discovered): most
    capabilities contribute a placeholder digest, so an edited implementation
    in an editable install is invisible here. Binding a plan to the
    implementations actually used needs real content digests, which is G4
    work. Do not document this as catching an edited renderer.
    """
    current = _stack_identity_for(_installed_providers())
    other = _stack_identity_for((*_installed_providers(), _StackProvider("org.extra")))
    assert current.capability_digest != other.capability_digest

    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")],
                 **{})
    plan = case_write.CaseWritePlan(
        request=plan.request, files=plan.files, preconditions=plan.preconditions,
        semantic_owner_id="org.a", stack_identity=current.capability_digest,
        created_at=plan.created_at,
    )

    class _Context:
        identity = other

    with pytest.raises(case_transaction.CaseTransactionError) as excinfo:
        case_transaction.commit_case_write(
            plan, driver_context=_Context(), execution_env=None,
        )
    assert current.capability_digest in str(excinfo.value)
    assert other.capability_digest in str(excinfo.value)

    class _MatchingContext:
        identity = current

    case_transaction.commit_case_write(
        plan, driver_context=_MatchingContext(), execution_env=None,
    )
    assert (tmp_path / "constant" / "a").exists()


def test_the_stack_digest_does_not_yet_bind_renderer_content(tmp_path):
    """Fails when C4 is fixed. That failure is the signal to delete the
    limit note on `test_stale_build` above -- not to relax this assertion."""
    recorded = provider_stack.resolutions(
        provider_stack.order_providers(_installed_providers())
    )
    placeheld = [
        capability for capability, (_winner, digest) in recorded.items()
        if digest == provider_stack.RESOLUTION_PLACEHOLDER
    ]
    assert placeheld, (
        "every capability now carries a real content digest; C4 is closed, "
        "so delete this test and the limit note on test_stale_build"
    )
    # The stronger form of the claim: `case_writer` has a real IMPLEMENTER
    # (not `UNCLAIMED`) and still only a placeholder digest -- an editable
    # install's renderer content is genuinely unbound, not merely unclaimed.
    winner, digest = recorded["case_writer"]
    assert winner == "org.format"
    assert digest == provider_stack.RESOLUTION_PLACEHOLDER


# --------------------------------------------------------------------------
# 13: changed indirect dependency
# --------------------------------------------------------------------------


def test_changed_indirect_dependency(tmp_path):
    """An `include` precondition's digest changed even though every case
    file the plan itself writes is untouched."""
    (tmp_path / "constant").mkdir()
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "included").write_bytes(b"original include\n")
    plan = _plan(
        tmp_path, [_rendered("constant/a", b"new\n")],
        preconditions=[case_write.Precondition(
            kind="include", target="site/included",
            digest=case_write._digest_bytes(b"original include\n"),
            must_be_absent=False,
        )],
    )
    (tmp_path / "site" / "included").write_bytes(b"changed include\n")
    with pytest.raises(case_transaction.CaseTransactionError, match="site/included"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


def test_changed_indirect_dependency_an_environment_value_too(tmp_path, monkeypatch):
    """R3 finding 3 (2026-09-23): an indirect dependency is not only an
    included file -- `openfoam.case_rendering.patch_preconditions` used to
    call `_inspect_source_closure`, bind its `environment_keys` to `_keys`,
    and discard them, though `"environment"` is a first-class
    `PRECONDITION_KINDS` member. A changed `WM_PROJECT_DIR` between planning
    and commit was invisible. Covered here at the `case_transaction` level
    (the environment-precondition *check*); the openfoam-level *emission* of
    these preconditions is covered in
    `omnidriver-cardiaccore/tests/test_patch_through_the_channel.py`."""
    monkeypatch.setenv("OMNIDRIVER_CONFORMANCE_ENV_KEY", "planned-value")
    plan = _plan(
        tmp_path, [_rendered("constant/a", b"new\n")],
        preconditions=[case_write.Precondition(
            kind="environment", target="OMNIDRIVER_CONFORMANCE_ENV_KEY",
            digest=case_write._digest_bytes(b"planned-value"), must_be_absent=False,
        )],
    )
    monkeypatch.setenv("OMNIDRIVER_CONFORMANCE_ENV_KEY", "changed-since-planning")
    with pytest.raises(case_transaction.CaseTransactionError, match="OMNIDRIVER_CONFORMANCE_ENV_KEY"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


# --------------------------------------------------------------------------
# 14: replay after an uncertain result
# --------------------------------------------------------------------------


def test_replay_after_an_uncertain_result(tmp_path):
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    first = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None, transaction_id="t-1",
    )
    (tmp_path / "constant" / "a").write_bytes(b"someone else edited this\n")
    second = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None, transaction_id="t-1",
    )
    assert second.transaction_id == first.transaction_id
    assert second.status == "committed"
    assert (tmp_path / "constant" / "a").read_bytes() == b"someone else edited this\n"


# --------------------------------------------------------------------------
# 15: competing attempts
# --------------------------------------------------------------------------


def test_competing_attempts(tmp_path):
    """Two commits against one case; the second blocks on the lease rather
    than interleaving with the first."""
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    outcome: dict = {}

    def _attempt():
        try:
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )
        except case_transaction.CaseTransactionError as exc:
            outcome["error"] = exc

    with acquire_case_lease(tmp_path):
        thread = threading.Thread(target=_attempt)
        thread.start()
        thread.join(timeout=5)

    assert "lease" in str(outcome.get("error", ""))
    assert not (tmp_path / "constant" / "a").exists()

    # Once the lease is released, the same plan commits cleanly.
    case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert (tmp_path / "constant" / "a").read_bytes() == b"one\n"


# --------------------------------------------------------------------------
# 16: path escape and symlinks
# --------------------------------------------------------------------------


def test_path_escape_and_symlinks(tmp_path):
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "escape").symlink_to(outside / "target")
    plan = _plan(tmp_path, [_rendered("constant/escape", b"x\n")])
    with pytest.raises(case_transaction.CaseTransactionError, match="symlink"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


def test_path_escape_a_relative_case_root_is_refused_at_construction(tmp_path):
    """R3 blocker 2 (2026-09-23): the other way a plan could escape to the
    wrong place -- not a symlinked write target, but a `case_root` that never
    named an absolute location at all, so it resolved against whatever
    directory the committing process happened to be in. Reproduced against
    the real public constructor: no defensive check existed in
    `commit_case_write` itself, so this had to be refused at
    `CaseMutationRequest.__post_init__`, before a plan naming an unauditable
    root could exist."""
    with pytest.raises(ValueError, match="absolute"):
        case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=Path("somecase"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(_parameter(),), requested_by="test",
        )


def test_path_escape_and_symlinks_a_precondition_target_too(tmp_path):
    """R3 finding 4 (2026-09-23): the symlink refusal `test_path_escape_and_
    symlinks` proves for a *write* target has a mirror-image hole on the
    *read* side -- a precondition's `is_file()`/`read_bytes()` dereferenced a
    symlink instead of refusing it."""
    outside = tmp_path.parent / "outside_precondition_dep"
    outside.mkdir(exist_ok=True)
    swapped = outside / "swapped.txt"
    swapped.write_bytes(b"attacker-controlled content\n")
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "dep").symlink_to(swapped)
    plan = _plan(
        tmp_path, [_rendered("constant/a", b"new\n")],
        preconditions=[case_write.Precondition(
            kind="file", target="constant/dep",
            digest=case_write._digest_bytes(b"original trusted content\n"),
            must_be_absent=False,
        )],
    )
    with pytest.raises(case_transaction.CaseTransactionError, match="symlink"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


# --------------------------------------------------------------------------
# 17: duplicate ownership
# --------------------------------------------------------------------------


class _Renderer:
    plugin_id = "org.format"

    def get_profile(self):
        return _Profile()

    def get_rendered_formats(self):
        return frozenset({"openfoam_dictionary"})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env):
        return (
            case_write.RenderedFile(
                path="constant/electroProperties", content=b"ionicModel TT06;\n",
                mode=None, exists_before=False, before_digest=None,
                renderer_id=self.plugin_id, format="openfoam_dictionary",
            ),
        )


class _SecondRenderer(_Renderer):
    plugin_id = "org.other_format"


def test_duplicate_ownership():
    """Two providers declaring one format; composition refuses. Reuses
    `test_case_writer_capability.py`'s scenario rather than a new one."""
    with pytest.raises(ValueError, match="openfoam_dictionary"):
        provider_stack.compose(
            provider_stack.order_providers([_Renderer(), _SecondRenderer()])
        )


# --------------------------------------------------------------------------
# 18: post-write evidence unavailable
# --------------------------------------------------------------------------


def test_post_write_evidence_unavailable(tmp_path):
    """An unverifiable write is committed and does not dispatch.

    Not the same as refusing the write: offline editing is supported, and a
    case whose values could not be read back is a case nobody has verified.
    The write happens; the run does not.
    """
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    record = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None,
    )
    assert record.status == "committed"
    assert (tmp_path / "constant" / "a").exists()

    readiness = is_launchable(
        plan_status="ok",
        simulation_audit=(SimulationAuditItem(
            stage="effective_configuration", status="unavailable",
            points=0, max_points=20,
            summary="the selected runtime is absent, so post-write readback could not run",
        ),),
    )
    assert not readiness.launchable
    assert not readiness.coverage_ok
