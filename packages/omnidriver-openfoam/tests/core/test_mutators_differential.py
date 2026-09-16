"""Security invariant for dictionary mutation: directives remain inert."""

from omnidriver.openfoam import mutators


def test_no_directive_is_evaluated(tmp_path):
    """A #codeStream entry must survive as text, never execute."""
    sentinel = tmp_path / "PWNED_DIFF"
    path = tmp_path / "d"
    path.write_text(
        "FoamFile { version 2.0; class dictionary; object d; }\n"
        f'pwned  #codeStream {{ code #{{ os << system("touch {sentinel}"); #}}; }};\n'
        "sigma  0.2;\n"
    )
    mutators.update_foam_entry(path, "sigma", 0.35)
    assert "#codeStream" in path.read_text()
    assert not sentinel.exists()
