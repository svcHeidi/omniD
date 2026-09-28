"""cardiacCore's ``run_document_configuration``/``configuration_validator``
answers.

Every spec this plugin plans is a generic case, whose configuration lives
in the case files themselves (``RunDocument.configurationSource ==
"case"``), never in this document's own ``config``; both hooks are
therefore always this trivial answer, kept as named functions (matching
cardiacFOAM's own ``run_document_config.py`` shape) so a future real
config source has one place to grow into.
"""

from __future__ import annotations


def build_config(spec):
    del spec
    return {}, ()


def validate_configuration(spec, plugin):
    del spec, plugin
    return ()
