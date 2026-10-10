// cardiacFOAM 277dfeb1933990da366d4b30dd9ef40b3e94c87c src/electroModels/electroDomains/myocardiumDomain/sealedWall/conormalZeroFluxFvPatchScalarField.C, verbatim lines 192-197, 201-202
    const word physicalType
    (
        trace == "conormal"
      ? conormalZeroFluxFvPatchScalarField::typeName
      : word("zeroGradient")
    );
// ...
        const word& t = mesh.boundary()[patchI].type();
        types[patchI] = polyPatch::constraintType(t) ? t : physicalType;
