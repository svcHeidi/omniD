// cardiacFOAM 15b3e18324d597bc396c3e314f6461143d300301 src/electroModels/myocardiumModels/monodomainSolver/monodomainSolver.C, verbatim lines 130, 176-179
void monodomainSolver::solveDiffusionImplicit
// ...
            domain.chi()*domain.Cm()*fvm::ddt(domain.VmRef())
          == fvm::laplacian(tGf(), domain.Vm())
           - domain.chi()*domain.Cm()*tIionExtrap()
           + domain.sourceField()
