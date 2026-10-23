// cardiacFOAM d684422bc085c40bd8a08a633e5c6e517d32626b src/verificationModels/monodomainVerification/manufacturedAnisotropicMonodomainVerifier.C, verbatim lines 109-110, 122-131, 258-259, 349-350, 368-372
        model.verificationFamily() != "monodomainFDAManufactured"
     || model.geometricDimension() != 3
// ...
    const boundBox bounds(mesh.points(), true);
    const vector unitMin(vector::zero);
    const vector unitMax(vector::one);
    const scalar cubeTolerance = 1e-10;

    if
    (
        mag(bounds.min() - unitMin) > cubeTolerance
     || mag(bounds.max() - unitMax) > cubeTolerance
    )
// ...
    const vectorField& centres = Vm.mesh().C().primitiveField();
    const scalar t = Vm.mesh().time().value();
// ...
    const vectorField& centres = mesh.C().primitiveField();
    const scalar t = mesh.time().value();
// ...
    const auto VmNorms = computeNorms(mesh, Vm.primitiveField(), VmExact);
    const auto u1Norms =
        computeNorms(mesh, fields[u1Idx].primitiveField(), u1Exact);
    const auto u2Norms =
        computeNorms(mesh, fields[u2Idx].primitiveField(), u2Exact);
