// cardiacFOAM 15b3e18324d597bc396c3e314f6461143d300301 src/verificationModels/monodomainVerification/manufacturedFDAMonodomainVerifier.C, verbatim lines 105, 109, 118-119, 157, 162, 171-178
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
