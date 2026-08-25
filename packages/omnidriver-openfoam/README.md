# omnidriver-openfoam

OpenFOAM environment plugin for `omnidriver`. Translates the core
orchestrator's generic requests into OpenFOAM actions: `controlDict` parsing,
fallback `blockMeshDict` provisioning, and `foamlib`-based dictionary
mutation. Depends on `omnidriver`, knows nothing about specific physics.
