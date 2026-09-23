"""Who answers what, and what happens when nobody does.

Resolution is the semantic owner's: what a parameter means, whether it applies,
where it lives. Rendering is the format owner's: how that address and value are
spelled in that file format. Committing is core's.

One declarer per format, for the same reason there is one declarer per case
file: two providers claiming to render `openfoam_dictionary` makes the bytes
that reach disk depend on composition order.
"""

from pathlib import Path

import pytest

from omnidriver.core import case_write, plugin_capabilities, provider_stack


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
        provider_stack.compose(
            provider_stack.order_providers([_Renderer(), _SecondRenderer()])
        )


def test_a_format_nobody_declares_is_refused_by_name_not_silently_skipped():
    """An unrenderable file must stop the plan. Dropping it would commit a
    partial case that looks complete."""
    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Renderer())
    with pytest.raises(ValueError, match="vtk_unstructured"):
        capabilities.case_writer.renderer_for("vtk_unstructured")


def test_the_declared_renderer_is_the_one_asked():
    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Renderer())
    assert capabilities.case_writer.renderer_for("openfoam_dictionary") == "org.format"


class _SemanticOnly:
    """A more-specific provider that renders nothing -- only resolves."""

    plugin_id = "org.semantic"

    def get_profile(self):
        return _Profile()

    def resolve_case_mutation(self, request, *, driver_context):
        return case_write.ResolvedMutation(
            request=request, targets=(), preconditions=(),
            expected_effects=(), semantic_owner_id=self.plugin_id,
        )


def test_the_declared_renderer_is_the_one_asked_in_a_composed_stack():
    """`_ComposedProvider.plugin_id` is the most-specific provider's id, which
    is not necessarily who declared the format being asked about.

    Reproduces the bug verbatim: a two-provider stack ``['org.format',
    'org.semantic']`` where `org.format` declares `openfoam_dictionary` and
    `org.semantic` is the more specific provider (last in stack order) but
    renders nothing. Before the fix, `renderer_for` returned
    `self.plugin.plugin_id`, which is the composed provider's -- i.e.
    `org.semantic` -- regardless of who actually declared the format.
    """
    capabilities = provider_stack.compose(
        provider_stack.order_providers([_Renderer(), _SemanticOnly()])
    )
    assert capabilities.case_writer.renderer_for("openfoam_dictionary") == "org.format"


def test_resolution_must_not_touch_the_filesystem(tmp_path, monkeypatch):
    """A dry run is non-destructive only if resolution is pure. The adapter
    that resolves is the one with a case in front of it, so this is enforced,
    not trusted."""

    class _ImpureAdapter:
        plugin_id = "org.impure"

        def get_profile(self):
            return _Profile()

        def resolve_case_mutation(self, request, *, driver_context):
            (Path(request.case_root) / "probe").open("w").close()
            return None

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_ImpureAdapter())
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=tmp_path, adapter_id="org.impure",
        workflow="w", source_artifacts=(), parameters=(), requested_by="test",
    )
    with pytest.raises(ValueError, match="pure"):
        capabilities.case_writer.resolve(request, driver_context=object())


def test_an_adapter_with_no_writer_hooks_refuses_by_name():
    """Not neutral. An empty resolution silently produces a case that is not
    the one that was asked for -- the same reason
    `SweepMaterializerCapability` refuses rather than defaulting."""

    class _Bare:
        plugin_id = "org.bare"

        def get_profile(self):
            return _Profile()

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Bare())
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"), adapter_id="org.bare",
        workflow="w", source_artifacts=(), parameters=(), requested_by="test",
    )
    with pytest.raises(ValueError, match="org.bare"):
        capabilities.case_writer.resolve(request, driver_context=object())


def test_an_unsupported_mode_is_refused_by_the_adapter_not_the_type():
    """`CaseMutationRequest` refuses an unknown mode. An adapter refusing a
    known mode it does not support is a different, equally explicit answer --
    and it names the modes it does support."""

    class _PatchOnly(_Renderer):
        plugin_id = "org.patch_only"

        def get_supported_mutation_modes(self):
            return frozenset({"clone_and_patch"})

        def resolve_case_mutation(self, request, *, driver_context):
            raise AssertionError("must be refused before reaching the adapter")

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_PatchOnly())
    request = case_write.CaseMutationRequest(
        mode="synthesize", case_root=Path("/tmp/case"), adapter_id="org.patch_only",
        workflow="w", source_artifacts=("mesh.vtu",), parameters=(),
        requested_by="test",
    )
    with pytest.raises(ValueError, match="clone_and_patch"):
        capabilities.case_writer.resolve(request, driver_context=object())


def test_an_adapter_with_no_mutation_modes_hook_supports_every_mode():
    """Absent get_supported_mutation_modes -> every MUTATION_MODES member, per
    the seam's documented default."""

    class _AllModes(_Renderer):
        plugin_id = "org.all_modes"

        def resolve_case_mutation(self, request, *, driver_context):
            return case_write.ResolvedMutation(
                request=request, targets=(), preconditions=(),
                expected_effects=(), semantic_owner_id=self.plugin_id,
            )

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_AllModes())
    assert capabilities.case_writer.supported_modes() == case_write.MUTATION_MODES


def test_an_adapter_with_no_render_hook_refuses_by_name():
    class _ResolveOnly:
        plugin_id = "org.resolve_only"

        def get_profile(self):
            return _Profile()

        def get_rendered_formats(self):
            return frozenset()

        def resolve_case_mutation(self, request, *, driver_context):
            return case_write.ResolvedMutation(
                request=request, targets=(), preconditions=(),
                expected_effects=(), semantic_owner_id=self.plugin_id,
            )

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_ResolveOnly())
    with pytest.raises(ValueError, match="render_case_files"):
        capabilities.case_writer.render(
            object(), snapshot_root=Path("/tmp/snap"), driver_context=object(),
        )


def test_a_renderer_renders_its_declared_format():
    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Renderer())
    rendered = capabilities.case_writer.render(
        object(), snapshot_root=Path("/tmp/snap"), driver_context=object(),
    )
    assert rendered[0].path == "constant/electroProperties"
    assert rendered[0].format == "openfoam_dictionary"
