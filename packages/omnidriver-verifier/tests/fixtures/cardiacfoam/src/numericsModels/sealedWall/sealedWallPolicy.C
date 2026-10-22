// cardiacFOAM 15b3e18324d597bc396c3e314f6461143d300301 src/numericsModels/sealedWall/sealedWallPolicy.C, verbatim lines 42-46
    labelList result(psi.boundaryField().size(), label(stock));
    if (!seal)
    {
        return result;
    }
