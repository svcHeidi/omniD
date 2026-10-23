// cardiacFOAM d684422bc085c40bd8a08a633e5c6e517d32626b src/numericsModels/sealedWall/sealedWallPolicy.C, verbatim lines 42-46
    labelList result(psi.boundaryField().size(), label(stock));
    if (!seal)
    {
        return result;
    }
