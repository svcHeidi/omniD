"""A utility manifest compared with the command line its C++ declares, on verbatim native snippets."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.utility_catalog import PositionalArg, UtilityFlag, UtilityManifest
from omnidriver.openfoam.utility_scanner import utility_manifest_report, utility_sources

# cardiacCore chore/repo-layout, applications/utilities/refine1Dgraph: Make/files, and refine1Dgraph.C's main from
# argList::noParallel to the reads of its two options.
REFINE_MAKE_FILES = r'''../newVtkUnstructuredToFoam/vtkUnstructuredReader.C
refine1Dgraph.C

EXE = $(FOAM_USER_APPBIN)/refine1Dgraph
'''
REFINE_MAIN = r'''    argList::noParallel();
    argList::noFunctionObjects();
    argList::addArgument("input", "Input legacy ASCII VTK line graph");
    argList::addArgument("output", "Output legacy ASCII VTK POLYDATA file");
    argList::addOption
    (
        "maxEdgeLength",
        "scalar",
        "Maximum segment length after refinement (m). "
        "Default 3e-4 m (0.3 mm)."
    );
    argList::addOption
    (
        "internalRole",
        "label",
        "Role value written on inserted nodes for the node-role field "
        "(default: 1 for NodeType, 0 for nodeRole/node_role/role)"
    );

    #include "setRootCase.H"

    // Dummy Time: the VTK reader only needs an objectRegistry, no case files
    autoPtr<Time> runTimePtr(Time::New());
    const Time& runTime = runTimePtr();

    const fileName inputFile(args.get<fileName>(1).expand());
    const fileName outputFile(args.get<fileName>(2).expand());

    const scalar maxEdgeLength(args.getOrDefault<scalar>("maxEdgeLength", 3e-4));
    const label internalRole(args.getOrDefault<label>("internalRole", -1));
'''

# cardiacFOAM #59, applications/utilities/setIonicRestartState: Make/files, and setIonicRestartState.C's main from
# its -dict option to createNamedMesh.H, then the read of -dict.
RESTART_MAKE_FILES = r'''setIonicRestartState.C

EXE = $(FOAM_USER_APPBIN)/setIonicRestartState
'''
RESTART_MAIN = r'''    argList::addNote
    (
        "Write the per-cell ionic restart state (<Model>State) of the"
        " myocardium from one single-cell state file per ionicHeterogeneity"
        " namedRegions region."
    );
    argList::addOption
    (
        "dict",
        "file",
        "State map dictionary (default: system/setIonicRestartStateDict)"
    );

    #include "addRegionOption.H"
    #include "setRootCase.H"
    #include "createTime.H"
    #include "createNamedMesh.H"
    const fileName dictPath
    (
        casePath
        (
            args.getOrDefault<fileName>
            (
                "dict",
                fileName("system/setIonicRestartStateDict")
            ),
            runTime
        )
    );
'''


def _utility(root: Path, name: str, make_files: str, main: str) -> Path:
    folder = root / "applications" / "utilities" / name
    (folder / "Make").mkdir(parents=True)
    (folder / "Make" / "files").write_text(make_files)
    (folder / f"{name}.C").write_text(main)
    return root


def _manifest(name: str, *flags: UtilityFlag, arguments: int = 0) -> UtilityManifest:
    return UtilityManifest(
        name=name, description="d", purpose="", inputs=(), requires_mesh=False, flags=flags, example="",
        category="io-conversion", source_path=Path(name),
        positional_args=tuple(PositionalArg(name=f"a{i}", argument_kind="path", description="") for i in range(arguments)),
    )


def _findings(root: Path, manifest: UtilityManifest) -> list[tuple]:
    report = utility_manifest_report(root, {manifest.name: manifest})
    return [(item["kind"], item["flag"]) for item in report["findings"]]


def test_a_utility_is_found_by_the_make_files_that_builds_it(tmp_path):
    _utility(tmp_path, "refine1Dgraph", REFINE_MAKE_FILES, REFINE_MAIN)
    (sources,) = utility_sources(tmp_path).values()
    assert [path.name for path in sources] == ["refine1Dgraph.C"]


def test_a_manifest_that_states_the_cxx_command_line_agrees(tmp_path):
    root = _utility(tmp_path, "refine1Dgraph", REFINE_MAKE_FILES, REFINE_MAIN)
    manifest = _manifest(
        "refine1Dgraph",
        UtilityFlag(name="-maxEdgeLength", description="", takes_value=True, default="3e-4"),
        UtilityFlag(name="-internalRole", description="", takes_value=True, default="-1"),
        arguments=2,
    )
    assert _findings(root, manifest) == []


def test_a_default_the_manifest_does_not_state_as_the_cxx_does_is_a_disagreement(tmp_path):
    root = _utility(tmp_path, "refine1Dgraph", REFINE_MAKE_FILES, REFINE_MAIN)
    manifest = _manifest(
        "refine1Dgraph",
        UtilityFlag(name="-maxEdgeLength", description="", takes_value=True, default="3e-4"),
        UtilityFlag(name="-internalRole", description="", takes_value=True),
        arguments=2,
    )
    report = utility_manifest_report(root, {"refine1Dgraph": manifest})
    (item,) = report["findings"]
    assert (item["kind"], item["flag"], item["source"]) == (
        "disagreement", "-internalRole", "applications/utilities/refine1Dgraph/refine1Dgraph.C:30",
    )


def test_an_option_the_manifest_lacks_a_flag_the_cxx_lacks_and_a_wrong_positional_count_are_named(tmp_path):
    root = _utility(tmp_path, "refine1Dgraph", REFINE_MAKE_FILES, REFINE_MAIN)
    manifest = _manifest(
        "refine1Dgraph",
        UtilityFlag(name="-maxEdgeLength", description="", takes_value=True, default="3e-4"),
        UtilityFlag(name="-noScale", description=""),
        arguments=1,
    )
    assert _findings(root, manifest) == [
        ("uncatalogued", "-internalRole"), ("unread", "-noScale"), ("disagreement", None),
    ]


def test_an_option_an_openfoam_header_adds_satisfies_a_flag_and_a_cast_default_is_read(tmp_path):
    root = _utility(tmp_path, "setIonicRestartState", RESTART_MAKE_FILES, RESTART_MAIN)
    manifest = _manifest(
        "setIonicRestartState",
        UtilityFlag(name="-dict", description="", takes_value=True, default="system/setIonicRestartStateDict"),
        UtilityFlag(name="-region", description="", takes_value=True),
    )
    assert _findings(root, manifest) == []


def test_a_utility_the_repository_does_not_build_is_not_compared(tmp_path):
    report = utility_manifest_report(tmp_path, {"absent": _manifest("absent")})
    assert report == {"findings": [], "not_built": ["absent"]}


def test_a_plan_notes_the_drift_of_a_utility_it_runs_and_of_no_other(tmp_path):
    from types import SimpleNamespace

    from omnidriver.core.provider_stack import ProviderStack
    from omnidriver.openfoam.plan_diagnostics import _utility_manifest_diagnostics

    root = _utility(tmp_path, "refine1Dgraph", REFINE_MAKE_FILES, REFINE_MAIN)
    manifest = _manifest(
        "refine1Dgraph",
        UtilityFlag(name="-maxEdgeLength", description="", takes_value=True, default="3e-4"),
        UtilityFlag(name="-internalRole", description="", takes_value=True),
        arguments=2,
    )
    provider = SimpleNamespace(plugin_id="toy", plugin_api_version="3", get_utility_manifests=lambda: {"refine1Dgraph": manifest})
    context = SimpleNamespace(stack=ProviderStack((provider,)), repository=SimpleNamespace(root=root))
    runs = {"steps": [{"id": "refine", "command": "refine1Dgraph in.vtk out.vtk"}]}
    (note,) = _utility_manifest_diagnostics(context, runs)
    assert (note.level, note.code, note.field) == ("warning", "utility_manifest_disagreement", "-internalRole")
    assert _utility_manifest_diagnostics(context, {"steps": [{"id": "mesh", "command": "blockMesh"}]}) == ()
