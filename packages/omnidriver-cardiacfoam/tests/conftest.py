import re
import pytest
from pathlib import Path

@pytest.fixture(autouse=True)
def _environment_preflight_is_stubbed(monkeypatch):
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    monkeypatch.setattr(OpenFOAMEnvironmentPlugin, "get_environment_diagnostics", lambda *args, **kwargs: ())


def _cardiacfoam_monorepo_root() -> Path | None:
    """First ancestor holding ``tutorials/`` and ``applications/`` (checkout inside the native repo)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "tutorials").exists() and (parent / "applications").exists():
            return parent
    return None


monorepo_root: Path | None = _cardiacfoam_monorepo_root()

#: Skips a test that reads real tutorial cases from the monorepo ``tutorials/`` tree.
skip_without_monorepo = pytest.mark.skipif(
    monorepo_root is None,
    reason=(
        "Requires the full cardiacFoam monorepo tree (tutorials/ + applications/). "
        "Clone the full repository or run with --cases-root to enable this test."
    ),
)


def _foam_tokens(value: str) -> list[str]:
    """Split an OpenFOAM value into tokens, with brackets as their own."""
    return re.findall(r"[()\[\]]|[^\s()\[\]]+", value)


def foam_values_equal(actual: str, expected: str) -> bool:
    """Compare OpenFOAM values ignoring bracket padding and numeric spelling (``foamDictionary`` vs pure-Python writer)."""
    actual_tokens, expected_tokens = _foam_tokens(actual), _foam_tokens(expected)
    if len(actual_tokens) != len(expected_tokens):
        return False
    for got, want in zip(actual_tokens, expected_tokens):
        if got == want:
            continue
        try:
            if float(got) == float(want):
                continue
        except ValueError:
            pass
        return False
    return True


def assert_foam_entry(path, key, expected, *, scope=None) -> None:
    """Assert that ``key`` resolves to ``expected``, whatever its spelling."""
    from omnidriver.openfoam.mutators import read_foam_entry

    actual = read_foam_entry(Path(path), key, scope=scope)
    assert actual is not None, f"{key!r} not found (scope={scope!r}) in {path}"
    assert foam_values_equal(actual, expected), (
        f"{key!r} (scope={scope!r}) is {actual!r}, expected {expected!r}"
    )
