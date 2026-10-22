// cardiacFOAM 15b3e18324d597bc396c3e314f6461143d300301 src/electroModels/electroDomains/myocardiumDomain/myocardiumDomain.C, verbatim lines 225-226, 278, 285, 364-365
        dimensionedScalar("Vm", dimVoltage, -0.084),
        "zeroGradient"
// ...
            "ionicCurrent",
// ...
        dimensionedScalar("zero", dimVoltage/dimTime, 0.0),
// ...
    chi_("chi", dimArea/dimVolume, electroProperties_),
    Cm_("cm", dimCurrent*dimTime/(dimVoltage*dimArea), electroProperties_),
