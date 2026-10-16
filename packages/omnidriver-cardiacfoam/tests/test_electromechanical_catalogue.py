"""Keys native main reads that the catalogue declares: the electromechanical dictionary, the active-tension
ODESolver sub-dictionary, the conormal patch's offsetField and the eikonal-ECG verifier's wave vector."""

from __future__ import annotations

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

_CATALOGUE = CardiacFoamPlugin.get_dictionary_catalog()
_ELECTRO = {entry.driver_path: entry for entry in _CATALOGUE.entries_for("electroProperties")}
_EM = {entry.driver_path: entry for entry in _CATALOGUE.entries_for("electroMechanicalProperties")}
_COEFFS = "$ELECTRO_MECHANICAL_COEFFS."


def test_the_electromechanical_model_is_a_required_word():
    entry = _EM["electroMechanicalModel"]
    assert entry.required and entry.enum_values == ("sequentialElectroMechanical",)


def test_the_electromechanical_defaults_are_the_ones_the_cxx_gives():
    typical = {
        path.removeprefix(_COEFFS): entry.typical_value for path, entry in _EM.items() if path.startswith(_COEFFS)
    }
    assert typical["TaScale"] == "1e3"
    assert typical["verificationModel.amplitude"] == "(0.02 0.02 0.02)"
    assert typical["verificationModel.initializeFields"] == "true"
    assert {typical[f"verificationModel.{key}"] for key in ("Tmax", "V0", "gamma")} == {"1.0"}
    assert typical["verificationModel.TaScale"] == "1e3"


def test_the_spherical_shell_verifiers_are_selectable():
    menu = _ELECTRO["$ELECTRO_MODEL_COEFFS.verificationModel.type"].enum_values
    assert {
        "manufacturedShellMonodomainVerifier", "manufacturedShellBidomainVerifier", "manufacturedShellEikonalVerifier",
    } <= set(menu)


def test_the_active_tension_odesolver_sub_dictionary_is_optional_and_for_the_land_models():
    kids = {path: entry for path, entry in _ELECTRO.items() if path.startswith("$ELECTRO_MODEL_COEFFS.ODESolver.")}
    assert {path.rsplit(".", 1)[1] for path in kids} == {"solver", "maxSteps", "absTol", "relTol"}
    for entry in kids.values():
        assert not entry.required and not entry.required_when
        assert entry.applicable_when["activeTensionModel"] == ("LandNiederer", "LandNiedererTWorld")


def test_the_eikonal_ecg_wave_vector_sits_under_the_ecg_domain():
    entry = _ELECTRO["$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.verificationModel.k"]
    assert entry.value_kind == "vector3"
    assert entry.applicable_when == {
        "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.verificationModel.type": ("manufacturedEikonalECGVerifier",)
    }


def test_the_purkinje_fibre_radius_is_catalogued_in_metres_for_the_cardiacfoam_59_head_that_reads_it():
    """#59's head (with #53's PVJ fixes) reads it in conductionSystemDomain and sets it in monodomain1D3D."""
    (entry,) = [entry for entry in CardiacFoamPlugin().get_dict_entries() if entry.driver_path.endswith("purkinjeFibreRadius")]
    assert (entry.unit, entry.exclusive_minimum) == ("m", 0)
    assert entry.required_when == {"$ELECTRO_MODEL_COEFFS.domainCouplings.<name>.couplingMode": "bidirectional"}
