<!-- cardiacFOAM a7b8e845c76579aec8fa0ff7b5e13a21547c1242: tutorials/manufacturedSolutions/bathBidomain/README.md, lines 8-15 -->

### Stack

- myocardium solver: `bidomainSolver`
- ionic model: `bathBidomainFDAManufactured`
- myocardium verifier: `manufacturedFDABathBidomainVerifier`
- bath potential domain: `bidomainSolverCoeffs.bathPotentialDomain`
- complete time coupling: explicit first-order `godunov` (Lie splitting)
