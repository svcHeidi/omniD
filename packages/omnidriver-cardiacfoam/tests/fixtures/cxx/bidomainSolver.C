\*---------------------------------------------------------------------------*/

#include "bidomainSolver.H"

#include "IOmanip.H"
#include "PstreamReduceOps.H"
#include "myocardiumDomain.H"
#include "insulatedFaceConductivity.H"
#include "sealedWallPolicy.H"
#include "compatibilityProjection.H"
#include "conormalStabilisation.H"
#include "exposedPhiETrace.H"
#include "fvMeshSubset.H"
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
            electroProperties.found("bathPotentialDomain")
          ? IOobject::NO_READ
          : myocardiumFieldReadOption(meshSubsetPtr),
            IOobject::AUTO_WRITE
        ),
        mesh,
        dimensionedScalar("phiE", dimVoltage, 0.0),
        "zeroGradient"
    ),
    gradPhiE_
    (
        IOobject
        (
            "grad(" + phiE_.name() + ")",
            mesh.time().timeName(),
            mesh,
            myocardiumFieldReadOption(meshSubsetPtr),
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
            myocardiumFieldReadOption(meshSubsetPtr),
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
    externalPhiECellMapPtr_(nullptr),
    meshSubsetPtr_(meshSubsetPtr),
    bathHeartPhiETrace_
    (
        electroProperties.getOrDefault<word>("bathHeartPhiETrace", "zeroGradient")
    ),
    verifierPtr_(nullptr)
{
    if
    (
        bathHeartPhiETrace_ != "zeroGradient"
     && bathHeartPhiETrace_ != "global"
    )
    {
        FatalIOErrorInFunction(electroProperties)
            << "bathHeartPhiETrace must be zeroGradient or global"
            << exit(FatalIOError);
    }
    if (bathHeartPhiETrace_ == "global" && !sealedHeartBoundary_)
    {
        FatalIOErrorInFunction(electroProperties)
            << "bathHeartPhiETrace global requires sealedHeartBoundary true"
            << exit(FatalIOError);
    }
    sealedWallPolicy::publish(phiE_, sealedHeartBoundary_);

    if (meshSubsetPtr_ && meshSubsetPtr_->hasSubMesh())
    {
        const labelUList& cellMap = meshSubsetPtr_->cellMap();

        if (!electroProperties.found("bathPotentialDomain"))
        {
            readMappedCellField(phiE_, supportMesh, cellMap);
        }
        readMappedCellField(phiI_, supportMesh, cellMap);
    }
}
