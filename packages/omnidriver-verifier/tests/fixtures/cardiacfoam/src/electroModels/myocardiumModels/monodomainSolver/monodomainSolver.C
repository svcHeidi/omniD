// cardiacFOAM d684422bc085c40bd8a08a633e5c6e517d32626b src/electroModels/myocardiumModels/monodomainSolver/monodomainSolver.C, verbatim lines 130, 176-179
void monodomainSolver::solveDiffusionImplicit
// ...
            domain.chi()*domain.Cm()*fvm::ddt(domain.VmRef())
          == fvm::laplacian(tGf(), domain.Vm())
           - domain.chi()*domain.Cm()*tIionExtrap()
           + domain.sourceField()
