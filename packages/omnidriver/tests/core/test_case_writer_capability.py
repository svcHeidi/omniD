"""Who answers what, and what happens when nobody does."""

from pathlib import Path

import pytest

from omnidriver.core import case_write, plugin_capabilities, provider_stack


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
        provider_stack.compose(
            provider_stack.order_providers([_Renderer(), _SecondRenderer()])
        )


def test_a_format_nobody_declares_is_refused_by_name_not_silently_skipped():
    """An unrenderable file must stop the plan."""
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
            request=request, targets=(), expected_effects=(), semantic_owner_id=self.plugin_id,
        )


def test_the_declared_renderer_is_the_one_asked_in_a_composed_stack():
    """`_ComposedProvider.plugin_id` is the most-specific provider's id, which is not necessarily who declared the format being asked about."""
    capabilities = provider_stack.compose(
        provider_stack.order_providers([_Renderer(), _SemanticOnly()])
    )
    assert capabilities.case_writer.renderer_for("openfoam_dictionary") == "org.format"


def test_resolution_must_not_touch_the_filesystem(tmp_path, monkeypatch):
    """A dry run is non-destructive only if resolution is pure."""

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
        workflow="w", source_artifacts=(), parameters=(_assignment(),),
        requested_by="test",
    )
    with pytest.raises(ValueError, match="pure"):
        capabilities.case_writer.resolve(request, driver_context=object())


def test_an_adapter_with_no_writer_hooks_refuses_by_name():
    """Not neutral."""

    class _Bare:
        plugin_id = "org.bare"

        def get_profile(self):
            return _Profile()

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Bare())
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"), adapter_id="org.bare",
        workflow="w", source_artifacts=(), parameters=(_assignment(),),
        requested_by="test",
    )
    with pytest.raises(ValueError, match="org.bare"):
        capabilities.case_writer.resolve(request, driver_context=object())


def test_an_unsupported_mode_is_refused_by_the_adapter_not_the_type():
    """`CaseMutationRequest` refuses an unknown mode."""

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


def test_a_resolver_with_no_mutation_modes_hook_is_refused_by_name():
    class _UndeclaredModes(_Renderer):
        plugin_id = "org.undeclared_modes"

        def resolve_case_mutation(self, request, *, driver_context):
            return case_write.ResolvedMutation(
                request=request, targets=(), expected_effects=(), semantic_owner_id=self.plugin_id,
            )

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_UndeclaredModes())
    with pytest.raises(ValueError, match="org.undeclared_modes"):
        capabilities.case_writer.supported_modes()


def test_a_provider_with_neither_hook_supports_no_modes():
    """Both absent -> `frozenset()`, not a raise: nothing here resolves, so an empty set changes nothing -- `resolve()` already refuses this provider by name (no `resolve_case_mutation`) before the mode check is ever reached."""

    class _Bystander:
        plugin_id = "org.bystander"

        def get_profile(self):
            return _Profile()

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Bystander())
    assert capabilities.case_writer.supported_modes() == frozenset()


def test_an_adapter_with_no_render_hook_refuses_by_name():
    class _ResolveOnly:
        plugin_id = "org.resolve_only"

        def get_profile(self):
            return _Profile()

        def get_rendered_formats(self):
            return frozenset()

        def resolve_case_mutation(self, request, *, driver_context):
            return case_write.ResolvedMutation(
                request=request, targets=(), expected_effects=(), semantic_owner_id=self.plugin_id,
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
    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Liar())
    with pytest.raises(ValueError, match="does not declare"):
        capabilities.case_writer.render(
            object(), snapshot_root=Path("/tmp/snap"), driver_context=object(),
        )


def test_a_composed_stack_refuses_a_liar_alongside_the_real_declarer():
    """The defect as described: a provider declaring only `other_format` can return a file claiming `openfoam_dictionary` and it is concatenated alongside the real declarer's, unnoticed."""
    capabilities = provider_stack.compose(
        provider_stack.order_providers([_Renderer(), _Liar()])
    )
    with pytest.raises(ValueError, match="does not declare"):
        capabilities.case_writer.render(
            object(), snapshot_root=Path("/tmp/snap"), driver_context=object(),
        )
