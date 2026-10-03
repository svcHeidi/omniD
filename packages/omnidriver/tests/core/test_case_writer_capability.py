"""Who answers what, and what happens when nobody does."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from omnidriver.core import case_write, provider_stack


def _context(*providers):
    return SimpleNamespace(stack=provider_stack.ProviderStack(provider_stack.order_providers(providers)))


def _assignment(**overrides):
    fields = dict(
        qualified_id="$E.ionicModel", owner="org.a",
        document="constant/electroProperties", key_path=("ionicModel",),
        value="TT06", value_kind="word", source="case",
    )
    fields.update(overrides)
    return case_write.ParameterAssignment(**fields)


class _Profile:
    def __init__(self, requires=()):
        self.requires = tuple(requires)
        self.case_files = ()


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


def test_two_providers_claiming_one_format_are_refused():
    with pytest.raises(ValueError, match="openfoam_dictionary"):
        _context(_Renderer(), _SecondRenderer())


def test_resolution_must_not_touch_the_filesystem(tmp_path, monkeypatch):
    """A dry run is non-destructive only if resolution is pure."""

    class _ImpureAdapter:
        plugin_id = "org.impure"

        def get_profile(self):
            return _Profile()

        def get_supported_mutation_modes(self):
            return frozenset({"clone_and_patch"})

        def resolve_case_mutation(self, request, *, driver_context):
            (Path(request.case_root) / "probe").open("w").close()
            return None

    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=tmp_path, adapter_id="org.impure",
        workflow="w", source_artifacts=(), parameters=(_assignment(),),
        requested_by="test",
    )
    with pytest.raises(ValueError, match="pure"):
        case_write.resolve_mutation(_context(_ImpureAdapter()), request)


def test_an_adapter_with_no_writer_hooks_refuses_by_name():
    """Not neutral."""

    class _Bare:
        plugin_id = "org.bare"

        def get_profile(self):
            return _Profile()

    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"), adapter_id="org.bare",
        workflow="w", source_artifacts=(), parameters=(_assignment(),),
        requested_by="test",
    )
    with pytest.raises(provider_stack.MemberAbsent, match="org.bare.*writing a case"):
        case_write.resolve_mutation(_context(_Bare()), request)


def test_an_unsupported_mode_is_refused_by_the_adapter_not_the_type():
    """`CaseMutationRequest` refuses an unknown mode."""

    class _PatchOnly(_Renderer):
        plugin_id = "org.patch_only"

        def get_supported_mutation_modes(self):
            return frozenset({"clone_and_patch"})

        def resolve_case_mutation(self, request, *, driver_context):
            raise AssertionError("must be refused before reaching the adapter")

    request = case_write.CaseMutationRequest(
        mode="synthesize", case_root=Path("/tmp/case"), adapter_id="org.patch_only",
        workflow="w", source_artifacts=("mesh.vtu",), parameters=(),
        requested_by="test",
    )
    with pytest.raises(ValueError, match="clone_and_patch"):
        case_write.resolve_mutation(_context(_PatchOnly()), request)


def test_an_adapter_with_no_render_hook_refuses_by_name():
    class _ResolveOnly:
        plugin_id = "org.resolve_only"

        def get_profile(self):
            return _Profile()

    with pytest.raises(provider_stack.MemberAbsent, match="render_case_files"):
        case_write.render_mutation(_context(_ResolveOnly()), object(), snapshot_root=Path("/tmp/snap"))


def test_a_renderer_renders_its_declared_format():
    rendered = case_write.render_mutation(_context(_Renderer()), object(), snapshot_root=Path("/tmp/snap"))
    assert rendered[0].path == "constant/electroProperties"
    assert rendered[0].format == "openfoam_dictionary"


class _Liar:
    """Declares one format, renders a file claiming a different one."""

    plugin_id = "org.liar"

    def get_profile(self):
        return _Profile()

    def get_rendered_formats(self):
        return frozenset({"other_format"})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env):
        return (
            case_write.RenderedFile(
                path="constant/lie", content=b"x", mode=None,
                exists_before=False, before_digest=None,
                renderer_id=self.plugin_id, format="openfoam_dictionary",
            ),
        )


def test_a_renderer_cannot_claim_a_format_it_does_not_declare():
    """`render_case_files` is `sequence`-composed: a returned `RenderedFile.format` must be one the returning provider itself declares."""
    with pytest.raises(ValueError, match="does not declare"):
        case_write.render_mutation(_context(_Liar()), object(), snapshot_root=Path("/tmp/snap"))


def test_a_composed_stack_refuses_a_liar_alongside_the_real_declarer():
    """The defect as described: a provider declaring only `other_format` can return a file claiming `openfoam_dictionary` and it is concatenated alongside the real declarer's, unnoticed."""
    with pytest.raises(ValueError, match="does not declare"):
        case_write.render_mutation(_context(_Renderer(), _Liar()), object(), snapshot_root=Path("/tmp/snap"))
