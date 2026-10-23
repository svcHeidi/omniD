// cardiacFOAM d684422bc085c40bd8a08a633e5c6e517d32626b src/verificationModels/monodomainVerification/manufacturedFDAMonodomainVerifier.C, verbatim lines 105, 109, 118-119, 157, 162, 171-178
    const vectorField& centres = Vm.mesh().C().primitiveField();
// ...
    const scalar t = Vm.mesh().time().value();
// ...
    computeManufacturedV(VmI, X, Y, Z, t, dimension);
    computeManufacturedU(u1I, u2I, u3I, X, Y, Z, t, dimension);
// ...
    const vectorField& centres = mesh.C().primitiveField();
// ...
    const scalar t = mesh.time().value();
// ...
    computeManufacturedV(VmExact, X, Y, Z, t, dimension);
    computeManufacturedU(u1Exact, u2Exact, u3Exact, X, Y, Z, t, dimension);

    const auto VmNorms = computeNorms(mesh, Vm.primitiveField(), VmExact);
    const auto u1Norms =
        computeNorms(mesh, fields[u1Idx].primitiveField(), u1Exact);
    const auto u2Norms =
        computeNorms(mesh, fields[u2Idx].primitiveField(), u2Exact);
