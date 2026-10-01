"""OpenFOAM's generated-case path declarations: a runtime convention, not
core policy or cardiacFOAM science, shared by the OpenFOAM plugin and
cardiacFOAM alike."""

from __future__ import annotations

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions


def openfoam_case_runtime_conventions() -> CaseRuntimeConventions:
    """Return the paths an OpenFOAM execution derives rather than authors."""

    return CaseRuntimeConventions(
        output_collection_relpath="postProcessing",
        generated_directory_names=(
            "postProcessing",
            "logs",
            "polyMesh",
            "results",
        ),
        generated_file_prefixes=("log.",),
        generated_file_suffixes=(".foam", ".msh", ".geo"),
        preserved_file_suffixes=(".geo.template",),
        case_entrypoints=("Allrun",),
        case_script_commands=("Allrun", "Allclean", "Allrun.pre", "Allrun.post"),
        case_discovery_ignored_directory_names=("postProcessing", "logs"),
        replica_directory_globs=("processor*",),
        instance_directory_pattern=r"^-?\d+(\.\d+)?(e[+\-]?\d+)?$",
        preserved_instance_names=("0",),
    )
