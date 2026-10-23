// cardiacFOAM d684422bc085c40bd8a08a633e5c6e517d32626b src/electroModels/electroDomains/myocardiumDomain/myocardiumDomain.C, verbatim lines 225-226, 278, 285, 364-365
        dimensionedScalar("Vm", dimVoltage, -0.084),
        "zeroGradient"
// ...
            "ionicCurrent",
// ...
        dimensionedScalar("zero", dimVoltage/dimTime, 0.0),
// ...
    chi_("chi", dimArea/dimVolume, electroProperties_),
    Cm_("cm", dimCurrent*dimTime/(dimVoltage*dimArea), electroProperties_),
