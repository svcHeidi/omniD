"""``system/controlDict`` and ``system/fvSchemes``: the documents every OpenFOAM-based solver shares.

OpenFOAM's own source reads them (``Foam::Time``, the finite-volume scheme tables), never a solver's, so this layer
catalogues, validates, lists and rule-checks them once for every stack.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog


@lru_cache(maxsize=1)
def layer_catalogue() -> DictionaryCatalog:
    from .control_dict import CONTROL_DICT_ENTRIES
    from .fv_schemes import FV_SCHEMES_ENTRIES

    return DictionaryCatalog({"controlDict": CONTROL_DICT_ENTRIES, "fvSchemes": FV_SCHEMES_ENTRIES})


def layer_validator_documents() -> dict[str, Any]:
    """The layer's ``CataloguedDocument`` for each of its documents, by case-relative path."""
    from .control_dict import CONTROL_DICT_DOCUMENT, control_dict_document
    from .fv_schemes import FV_SCHEMES_DOCUMENT, fv_schemes_document

    return {CONTROL_DICT_DOCUMENT: control_dict_document(), FV_SCHEMES_DOCUMENT: fv_schemes_document()}


def layer_record_key_catalog(case_root: Path, *, catalogue: DictionaryCatalog) -> tuple[dict[str, Any], ...]:
    """The layer's catalogued keys the case's documents hold, and every other ``system/`` file of the case as an open
    document, less the ``system/`` documents the stack's ``catalogue`` closes."""
    from .control_dict import control_dict_listing
    from .fv_schemes import fv_schemes_listing
    from .record_key_validation import open_system_documents

    closed = {f"system/{name}" for name in catalogue.documents if name not in layer_catalogue().documents}
    return (
        *control_dict_listing(Path(case_root)), *fv_schemes_listing(case_root),
        *open_system_documents(case_root, exclude=closed),
    )


def layer_run_semantics(case_root: Path) -> tuple[Any, ...]:
    """The catalogue's rules over the resolved case's ``controlDict``: what ``Foam::Time`` requires, its menus and bounds."""
    from .case_rules import document_rule_diagnostics
    from .control_dict import CONTROL_DICT_DOCUMENT, CONTROL_DICT_ENTRIES

    return document_rule_diagnostics(case_root, {CONTROL_DICT_DOCUMENT: CONTROL_DICT_ENTRIES})
