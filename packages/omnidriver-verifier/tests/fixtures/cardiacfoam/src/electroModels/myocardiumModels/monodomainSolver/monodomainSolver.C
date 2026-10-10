// cardiacFOAM 277dfeb1933990da366d4b30dd9ef40b3e94c87c src/electroModels/myocardiumModels/monodomainSolver/monodomainSolver.C, verbatim lines 128, 174-177
void monodomainSolver::solveDiffusionImplicit
// ...
            domain.chi()*domain.Cm()*fvm::ddt(domain.VmRef())
          == fvm::laplacian(tGf(), domain.Vm())
           - domain.chi()*domain.Cm()*tIionExtrap()
           + domain.sourceField()
