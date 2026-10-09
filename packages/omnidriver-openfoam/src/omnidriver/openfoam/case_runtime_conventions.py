"""OpenFOAM's generated-case path declarations: a runtime convention, not
core policy or cardiacFOAM science, shared by the OpenFOAM plugin and
cardiacFOAM alike."""

from __future__ import annotations

from omnidriver.core.plugin_interface import CaseRuntimeConventions


def openfoam_case_runtime_conventions() -> CaseRuntimeConventions:
    """Return the paths an OpenFOAM execution derives rather than authors.

    A mesh is not among them: a case folder may hold the ``polyMesh`` or
    ``.msh`` its solver reads, so staging drops one only where a record's
    step declares it produced.
    """

    return CaseRuntimeConventions(
        generated_directory_names=(
            "postProcessing",
            "logs",
            "results",
        ),
        generated_file_prefixes=("log.",),
        generated_file_suffixes=(".foam",),
        case_entrypoints=("Allrun",),
        case_script_commands=("Allrun", "Allclean", "Allrun.pre", "Allrun.post"),
        replica_directory_globs=("processor*",),
        instance_directory_pattern=r"^-?\d+(\.\d+)?(e[+\-]?\d+)?$",
        preserved_instance_names=("0",),
    )
