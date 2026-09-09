import pytest

from omnidriver.openfoam import foam_backend


HEADER = "FoamFile { version 2.0; class dictionary; object d; }\n"


def _dict(tmp_path, body):
    path = tmp_path / "d"
    path.write_text(HEADER + body)
    return path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1e-6", 1e-6),
        ("0.0", 0.0),
        ("250", 250),
        ("yes", True),
        ("no", False),
        ("PCG", "PCG"),
        ("constant/purkinjeGraph", "constant/purkinjeGraph"),
    ],
)
def test_coerce_value_maps_strings_to_foamlib_types(raw, expected):
    assert foam_backend.coerce_value(raw) == expected


def test_coerce_value_passes_non_strings_through():
    assert foam_backend.coerce_value(1e-6) == 1e-6
    assert foam_backend.coerce_value(True) is True


def test_coerce_value_parses_dimensioned_tensor():
    from foamlib import Dimensioned

    raw = "[-1 -3 3 0 0 2 0] (0.106875 -0.0084931 -0.022561 0.116682 -0.0130256 0.0398782)"
    result = foam_backend.coerce_value(raw)
    assert isinstance(result, Dimensioned)
    assert list(result.value) == pytest.approx(
        [0.106875, -0.0084931, -0.022561, 0.116682, -0.0130256, 0.0398782]
    )


def test_coerce_value_parses_dimensioned_scalar():
    from foamlib import Dimensioned

    result = foam_backend.coerce_value("[0 -1 0 0 0 0 0] 3")
    assert isinstance(result, Dimensioned)
    assert result.value == pytest.approx(3.0)


def test_coerce_value_parses_bare_vector():
    import numpy as np

    result = foam_backend.coerce_value("(0.001 0.002 0.006)")
    assert isinstance(result, np.ndarray)
    assert list(result) == pytest.approx([0.001, 0.002, 0.006])


def test_coerce_value_parses_bare_multiword_scheme_spec():
    result = foam_backend.coerce_value("Gauss linear")
    assert result == ("Gauss", "linear")


def test_coerce_value_parses_uniform_field_shorthand():
    # foamlib recognises "uniform <value>" as OpenFOAM's field-uniform-value
    # shorthand and collapses it straight to the scalar -- a deliberate,
    # accepted behaviour change once coerce_value stopped scoping to a
    # leading '['/'(' check (see module docstring).
    assert foam_backend.coerce_value("uniform 0") == 0.0


def test_coerce_value_falls_back_to_string_on_unparseable_bracket_token():
    # Looks like a dimensioned literal (leading '[') but isn't one -- must
    # fall back to the plain-string behaviour, not raise.
    assert foam_backend.coerce_value("[not a real dimension set") == (
        "[not a real dimension set"
    )


def test_update_entry_splices_multicomponent_dimensioned_tensor_verbatim(tmp_path):
    # Regression test for a real cardiacFoam FATAL IO ERROR: writing a
    # multi-component Dimensioned through foamlib's normal path produces
    # "conductivity [...] 6(...)" (a generic sized-list), but the actual
    # solver reads conductivity as a fixed-arity symmTensor VectorSpace,
    # which rejects the leading count outright. Confirmed directly against
    # the real solver before this fix existed.
    raw = "[-1 -3 3 0 0 2 0] (0.106875 -0.0084931 -0.022561 0.116682 -0.0130256 0.0398782)"
    path = _dict(
        tmp_path,
        "monodomainSolverCoeffs\n{\n"
        "    conductivity [-1 -3 3 0 0 2 0] (0.1 0 0 0.1 0 0.1);\n"
        "}\n",
    )
    foam_backend.update_entry(
        path, "conductivity", raw, scope=["monodomainSolverCoeffs"]
    )
    text = path.read_text()
    assert f"conductivity    {raw};" in text
    assert "6(" not in text


def test_update_entry_still_uses_foamlib_for_dimensioned_scalar(tmp_path):
    # The unaffected case: a dimensioned scalar has nothing to size-prefix,
    # so it keeps going through foamlib's normal (verified-safe) path.
    path = _dict(
        tmp_path,
        "monodomainSolverCoeffs\n{\n    chi [0 -1 0 0 0 0 0] 3;\n}\n",
    )
    foam_backend.update_entry(
        path, "chi", "[0 -1 0 0 0 0 0] 5", scope=["monodomainSolverCoeffs"]
    )
    assert "chi    [0 -1 0 0 0 0 0] 5.0;" in path.read_text()


def test_update_entry_writes_bare_multiword_scheme_spec(tmp_path):
    # Regression test for a real materialization failure across every
    # gauss_linear sweep case: "cannot write value 'Gauss linear' to
    # 'default': invalid string: 'Gauss linear'". Confirmed directly against
    # the real solver before this fix: writes clean, foamDictionary reads it
    # back as the same two tokens.
    path = _dict(
        tmp_path,
        "gradSchemes\n{\n    default leastSquares;\n}\n",
    )
    foam_backend.update_entry(
        path, "default", "Gauss linear", scope=["gradSchemes"]
    )
    assert "default    Gauss linear;" in path.read_text()


def test_update_entry_raises_when_multicomponent_dimensioned_key_missing(tmp_path):
    path = _dict(tmp_path, "monodomainSolverCoeffs\n{\n}\n")
    raw = "[-1 -3 3 0 0 2 0] (0.1 0 0 0.1 0 0.1)"
    with pytest.raises(ValueError, match="not found"):
        foam_backend.update_entry(
            path, "conductivity", raw, scope=["monodomainSolverCoeffs"]
        )


def test_update_entry_writes_four_space_separator(tmp_path):
    path = _dict(tmp_path, "solvers\n{\n    Vm { tolerance 1e-11; }\n}\n")
    foam_backend.update_entry(path, "tolerance", "1e-12", scope=["solvers", "Vm"])
    assert "tolerance    1e-12;" in path.read_text()


def test_update_entry_does_not_insert_blank_line(tmp_path):
    path = _dict(tmp_path, "// documented\nendTime 0.3;\n")
    before = path.read_text().count("\n\n")
    foam_backend.update_entry(path, "endTime", "0.4")
    assert path.read_text().count("\n\n") == before


def test_update_entry_fails_closed_on_unknown_key(tmp_path):
    path = _dict(tmp_path, "endTime 0.3;\n")
    with pytest.raises(KeyError):
        foam_backend.update_entry(path, "endTimee", "999")
    assert "endTimee" not in path.read_text()


def test_update_entry_creates_key_when_add_if_missing(tmp_path):
    path = _dict(tmp_path, "solvers\n{\n    Vm { tolerance 1e-11; }\n}\n")
    foam_backend.update_entry(
        path, "purgeWrite", "0", scope=["solvers", "Vm"], add_if_missing=True
    )
    assert "purgeWrite    0;" in path.read_text()


def test_update_entry_add_if_missing_requires_scope(tmp_path):
    """Mirrors tier 1's mutators.py:434 guard so the two tiers agree.

    Tier 1's ``update_foam_entry`` raises this *before* ever falling
    through to this adapter, so a mismatched contract here would be
    untestable through the real call path and misleading in isolation.
    """
    path = _dict(tmp_path, "endTime 0.3;\n")
    with pytest.raises(ValueError, match="add_if_missing requires a scope"):
        foam_backend.update_entry(path, "purgeWrite", "0", add_if_missing=True)


def test_update_entry_handles_brace_inside_quoted_string(tmp_path):
    """The case tier 1 cannot parse: a brace inside a quoted value."""
    path = _dict(
        tmp_path,
        'note  "a value with { an unbalanced brace";\n'
        "solvers\n{\n    Vm { tolerance 1e-11; }\n}\n",
    )
    foam_backend.update_entry(path, "tolerance", "1e-12", scope=["solvers", "Vm"])
    text = path.read_text()
    assert "1e-12" in text
    assert 'note  "a value with { an unbalanced brace";' in text


def test_update_entry_rejects_injected_second_entry(tmp_path):
    path = _dict(tmp_path, "deltaT 1e-06;\n")
    with pytest.raises(ValueError):
        foam_backend.update_entry(path, "deltaT", "1e-6;  rogue  1")
    assert "rogue" not in path.read_text()


def test_update_entry_rejects_directive_value(tmp_path):
    path = _dict(tmp_path, "deltaT 1e-06;\n")
    with pytest.raises(ValueError):
        foam_backend.update_entry(path, "deltaT", '#calc "2*3"')


@pytest.mark.parametrize(
    "payload",
    ["#includeEtcFuncs", "#", "PCG#calc"],
)
def test_update_entry_rejects_directive_value_foamlib_would_have_allowed(tmp_path, payload):
    """foamlib's own type-strictness is not a substitute for an explicit check.

    Measured directly against 1.7.5: none of these three payloads look
    type-inconsistent to foamlib (none reads back as another type), so
    foamlib accepts and writes them completely unconverted -- e.g.
    ``'#includeEtcFuncs'``, a bare ``'#'``, and ``'PCG#calc'`` all pass
    through with no error. Only an explicit rejection (mirroring tier 1's
    rule, not delegating to foamlib's incidental behaviour) closes this.
    """
    path = _dict(tmp_path, "solvers\n{\n    Vm { solver PCG; }\n}\n")
    with pytest.raises(ValueError):
        foam_backend.update_entry(path, "solver", payload, scope=["solvers", "Vm"])


def test_update_entry_rejects_directive_shaped_container_value(tmp_path):
    """A non-str value must not bypass the guard by skipping the string check.

    Reproduced directly: an earlier version of _reject_directive_shaped
    returned immediately for any non-str value, so a dict/list containing a
    directive-shaped string inside it reached foamlib completely unscreened
    -- e.g. {"codeInclude": '#{ system("id"); #}'} was accepted and written
    as a live coded block. Tier 1's _format_value has no equivalent hole
    because it stringifies unconditionally, for every type, before
    screening; this guard must do the same.
    """
    path = _dict(tmp_path, "solvers\n{\n    Vm { solver PCG; }\n}\n")
    payload = {"codeInclude": '#{ system("id"); #}'}
    with pytest.raises(ValueError):
        foam_backend.update_entry(path, "solver", payload, scope=["solvers", "Vm"])


def test_remove_dict_deletes_block(tmp_path):
    path = _dict(tmp_path, "solvers\n{\n    Vm { tolerance 1e-11; }\n}\n")
    foam_backend.remove_dict(path, "Vm", scope=["solvers"])
    assert "Vm" not in path.read_text()


def test_remove_dict_missing_ok_false_raises(tmp_path):
    path = _dict(tmp_path, "solvers\n{\n}\n")
    with pytest.raises(KeyError):
        foam_backend.remove_dict(path, "Vm", scope=["solvers"], missing_ok=False)


def test_remove_dict_missing_ok_true_is_silent(tmp_path):
    path = _dict(tmp_path, "solvers\n{\n}\n")
    foam_backend.remove_dict(path, "Vm", scope=["solvers"], missing_ok=True)


def test_remove_dict_leaves_no_whitespace_only_line(tmp_path):
    """foamlib's ``del`` leaves the emptied block's line as spaces, not gone.

    Measured directly: deleting ``solvers/Vm`` from
    ``solvers\\n{\\n    Vm {...}\\n}\\n`` leaves ``solvers\\n{\\n    \\n}\\n`` --
    the brace lines survive but the interior line is whitespace, not absent.
    ``"Vm" not in text`` alone does not catch this.
    """
    path = _dict(tmp_path, "solvers\n{\n    Vm { tolerance 1e-11; }\n}\n")
    foam_backend.remove_dict(path, "Vm", scope=["solvers"])
    text = path.read_text()
    assert "Vm" not in text
    assert not any(line.strip() == "" and line != "\n" for line in text.splitlines(keepends=True))


def test_remove_dict_maps_decode_error_to_value_error(tmp_path):
    """``del`` re-parses the whole file, so unrelated garbage elsewhere can

    surface as a ``FoamFileDecodeError`` even when the delete target itself
    is well-formed. Measured directly: deleting a perfectly valid
    ``solvers/Vm`` from a file that *also* contains unrelated malformed text
    raises ``foamlib.FoamFileDecodeError`` (a ``ValueError`` subclass) from
    the ``del`` call, not a ``KeyError`` -- the bare ``except KeyError:`` an
    earlier draft of this function had would let it escape unmapped.
    """
    path = _dict(
        tmp_path,
        "solvers\n{\n    Vm { tolerance 1e-11; }\n}\n"
        "garbage {{{ not valid @@@ ;;; \n",
    )
    before = path.read_text()
    with pytest.raises(ValueError) as excinfo:
        foam_backend.remove_dict(path, "Vm", scope=["solvers"])
    # exact-type, not isinstance: FoamFileDecodeError IS a ValueError subclass,
    # so `pytest.raises(ValueError)` alone passes whether or not this is
    # actually mapped -- it would also pass against the unmapped bug this
    # test exists to catch. The exact-type check is what discriminates.
    assert type(excinfo.value) is ValueError
    assert path.read_text() == before


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        foam_backend.update_entry(tmp_path / "nope", "k", "1")
