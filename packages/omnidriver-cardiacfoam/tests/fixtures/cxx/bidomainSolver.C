\*---------------------------------------------------------------------------*/

#include "bidomainSolver.H"

#include "IOmanip.H"
#include "PstreamReduceOps.H"
#include "myocardiumDomain.H"
#include "insulatedFaceConductivity.H"
#include "conormalZeroFluxFvPatchScalarField.H"
#include "addToRunTimeSelectionTable.H"
#include "polyMesh.H"

namespace Foam
{

defineTypeNameAndDebug(bidomainSolver, 0);
addToRunTimeSelectionTable(myocardiumSolver, bidomainSolver, dictionary);


bidomainSolver::bidomainSolver
(
    const fvMesh& mesh,
    const fvMesh& supportMesh,
    const fvMeshSubset* meshSubsetPtr,
    const dictionary& electroProperties
)
:
    phiE_
    (
        IOobject
        (
            "phiE",
            mesh.time().timeName(),
            mesh,
            IOobject::READ_IF_PRESENT,
            IOobject::AUTO_WRITE
        ),
        mesh,
        dimensionedScalar("phiE", dimVoltage, 0.0),
        conormalWallPatchTypes
        (
            mesh,
            electroProperties.get<word>("sealedWallTrace")
        )
    ),
    gradPhiE_
    (
        IOobject
        (
            "grad(" + phiE_.name() + ")",
            mesh.time().timeName(),
            mesh,
            IOobject::READ_IF_PRESENT,
            IOobject::NO_WRITE
        ),
        mesh,
        dimensionedVector("0", dimVoltage/dimLength, vector::zero)
    ),
    phiI_
    (
        IOobject
        (
            "phiI",
            mesh.time().timeName(),
            mesh,
            IOobject::READ_IF_PRESENT,
            IOobject::AUTO_WRITE
        ),
        mesh,
        dimensionedScalar("phiI", dimVoltage, 0.0),
        "zeroGradient"
    ),
    Gi_(initialiseConductivityTensor
    (
        mesh,
        supportMesh,
        meshSubsetPtr,
        conductivityFieldSpec
        {
            "ConductivityIntracellular",
            "conductivityIntracellular",
            "conductivityIntracellular"
        },
        electroProperties
    )),
    Ge_(initialiseConductivityTensor
    (
        mesh,
        supportMesh,
        meshSubsetPtr,
        conductivityFieldSpec
        {
            "ConductivityExtracellular",
            "conductivityExtracellular",
            "conductivityExtracellular"
        },
        electroProperties
    )),
    GiPlusGe_
    (
        IOobject
        (
            "GiPlusGe",
            mesh.time().timeName(),
            mesh,
            IOobject::NO_READ,
            IOobject::NO_WRITE
        ),
        Gi_ + Ge_
    ),
    sealedHeartBoundary_
    (
        electroProperties.get<Switch>("sealedHeartBoundary")
    ),
    phiEReferenceValue_
    (
        electroProperties.lookupOrDefault<scalar>("phiEReferenceValue", 0.0)
    ),
    phiEReferencePoint_
    (
        electroProperties.found("phiERefPoint")
      ? electroProperties.get<point>("phiERefPoint")
      : point::zero
    ),
    hasPhiEReferencePoint_(electroProperties.found("phiERefPoint")),
    externalPhiEBasePtr_(nullptr),
    externalPhiECellMapPtr_(nullptr)
{
    setConormalWallConductivity(phiE_, Ge_.name(), word::null);
}
