"""cardiacCore's ``run_document_configuration``/``configuration_validator``
answers.

**S5 (2026-09-28):** every spec this plugin ever plans now is a generic
case (a tutorial record's committed case, or a plain case-folder entry) --
the factory catalog that used to build a non-generic spec
(``workflows/preprocessing.py``) is deleted. A generic case's configuration
lives in the case files themselves (``RunDocument.configurationSource ==
"case"``), never in this document's own ``config``, and
``run_document_adapter._run_document_from_case`` already skips
``validate_run`` entirely for one. Both hooks below are therefore always
the same trivial answer; kept as named functions (not inlined into
``plugin.py``) only so a future real config source has one place to grow
into, matching cardiacFOAM's own ``run_document_config.py`` shape.
"""

from __future__ import annotations


def build_config(spec):
    del spec
    return {}, ()


def validate_configuration(spec, plugin):
    del spec, plugin
    return ()
