// cardiacFOAM 277dfeb1933990da366d4b30dd9ef40b3e94c87c src/electroModels/electroDomains/myocardiumDomain/myocardiumDomain.C, verbatim lines 272, 279, 358-359
            "ionicCurrent",
// ...
        dimensionedScalar("zero", dimVoltage/dimTime, 0.0),
// ...
    chi_("chi", dimArea/dimVolume, electroProperties_),
    Cm_("cm", dimCurrent*dimTime/(dimVoltage*dimArea), electroProperties_),
