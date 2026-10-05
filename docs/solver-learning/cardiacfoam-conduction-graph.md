# cardiacFOAM's conduction graph: the 1D network, its coupling to the 3D myocardium, and their units

**Method:** [`method.md`](method.md). **Tree:** a `git archive` of
`origin/omnid/tutorials-are-pointers` (`e3e3fc8a`, which contains native main
`0b1bf13c`). **Date:** 2026-10-05. **Question (owner):** what the graph file's
keys mean, why each exists, and their units, derived from the C++.

The native code declares no units for the 1D network: `chi`, `cm`,
`purkinjeConductivity`, `rPvj` and every graph value are plain `scalar`s. Each
unit below is derived from an equation in the code, anchored on the quantities
the 3D myocardium does declare with OpenFOAM dimension sets.

## Units, derived

| quantity | where it is read | unit | how it follows |
|---|---|---|---|
| `Vm` of a graph node | `conductionSystemDomain` (`Vm1D_`), `vm1DRest` | V | default `-0.084`; the output column is `node<i>_Vm_V`; the 3D `Vm` is `dimVoltage` |
| `t`, `dt` | `Time` | s | |
| `chi` | `purkinjeGraphModelCoeffs` | 1/m | it multiplies `cm` exactly as the 3D `chi [0 -1 0 0 0 0 0]` does |
| `cm` | `purkinjeGraphModelCoeffs` | F/m² | the 3D `cm [-1 -4 4 0 0 2 0]` |
| `Iion` | the ionic model, per node | V/s | `monodomain1DSolver::advance`: `rhs = Vm - dt*Iion`; in 3D `chi*Cm*Iion` stands beside A/m³ terms |
| applied current, `rootStimulus.intensity` | `conductionSystemDomain::assembleAppliedCurrent` | A/m³ | `rhs += dt*Iapp/(chi*Cm)` must be a voltage: A/m³ ÷ F/m³ × s = V |
| edge `length` (3rd value of `conductionEdges`) | `conductionGraph::readFromDict` | m | `1DgraphToFoam` writes `mag(points[b] - points[a])` in mesh coordinates; `eikonalSolver1D` adds `length/purkinjeCV` (m ÷ m/s) to a time |
| edge conductivity `sigma_e` = 4th value × `purkinjeConductivity` | `readGraphFile` multiplies, `monodomain1DSolver` uses | S/m, given `chi` [1/m] and `cm` [F/m²] | see the derivation below |
| edge conductance (4th value of `conductionEdges`) | `conductionGraph::readFromDict` | dimensionless factor; 0 blocks the edge | it multiplies `purkinjeConductivity`, which carries the S/m; every native graph writes 1 |
| `purkinjeConductivity` | `readGraphFile` | S/m | the product `sigma_e` is a conductivity, the graph's factor is 1 in every native graph, and every native case gives it in S/m (0.4, and 0.111453302, the 3D tissue's `sigma_xx`); the C++ prints it as a "multiplier" (default 1.0) |
| `referenceConductance` | `restitutionEikonalSolver1D` | S/m | it divides `G.edgeConductances`, which hold `sigma_e` after the multiplication |
| `purkinjeCV` | `eikonalSolver1D` | m/s | dimensioned `[0 1 -1 0 0 0 0]` |
| `points`, `pvjLocations` | `readGraphFile` | m | `pvjMapper` compares `pvjLocations` with `mesh.C()`; native graphs are in metres (idealizedHeart edges of 0.29 mm) |
| `pvjRadius` | `pvjCoupler` | m | `pvjMapper` compares it with `cbrt(cell volume)` |
| junction current `I_pvj` (`terminalCurrent`) | `reactionDiffusionPvjCoupler::couplingCurrentAtPvjs` | A on the tissue side | `pvjMapper::volumetricSource` divides it by the kernel-weighted sphere volume and adds it to `externalStimulusCurrent`, dimensioned `dimCurrent/dimVolume` |
| `rPvj`, `pvjResistances` | the couplers; `conductionGraph` | Ω | the tissue side divides a voltage difference by `R` to get `I` in A, spread over the kernel-weighted junction volume; and the implicit scheme's coefficient `1/(R*V_sphere)` lands in `implicitSourceCoeff`, dimensioned `dimCurrent/(dimVolume*dimVoltage)`, so `R` is V/A. The network side applies `I` without a node volume (below) |
| junction source `IcouplingSource` | output only | A/m³ | the column is `pvj<i>_IcouplingSource_Am3` |
| `I_pvj` on the network side | `assembleAppliedCurrent` | used as A/m³ | `appliedCurrent[pvjNode] -= terminalCurrent[i]`, then divided by `chi*Cm` only, with no cross-section or control length; the network side of a `bidirectional` junction is therefore not a current in A ([`cardiacfoam-pvj-coupling.md`](cardiacfoam-pvj-coupling.md)) |

**The edge conductivity.** `monodomain1DSolver::advance` states its own
discretisation:

```
dV_i/dt = (1/(chi*Cm*controlLength_i)) * sum_e sigma_e/L_e * (V_j - V_i) - Iion_i + Iapp_i/(chi*Cm)
```

with `controlLength_i` half the length of every edge at node `i`, and assembles
exactly that: `edgeCoeff = edgeConductance/edgeLength`, `coeff =
dt*edgeCoeff/(chiCm*controlLength)`. The equation itself fixes only
`sigma/(chi*Cm)`, a diffusivity in m²/s. Given `chi` in 1/m and `cm` in F/m², as
the 3D myocardium declares them, and `dV/dt` in V/s:

[sigma] = (V/s) × (F/m³) × m × m / V = F/(m·s) = S/m.

So `sigma_e` is a conductivity, not a conductance: the cable's cross-section
cancels between the axial flux and the membrane capacitance, which assumes one
cross-section for the whole tree. The native README `idealizedHeart/electroHeart`
measures the conduction velocity grow with it (3.16 m/s at 0.35, 5.8 m/s at 1.5,
about 8.7 m/s at 10.0, with `chi 14000`, `cm 0.01`), and `sigma/(chi*Cm)` at 0.4
is 2.9e-3 m²/s, a diffusivity of the order a ~3 m/s cable needs. An
observation: that case gives the network `chi 14000` and the myocardium
`chi [0 -1 0 0 0 0 0] 140000`, a tenth of the tissue's surface-to-volume ratio.

## The 1D network

`conductionSystemDomain` (`conductionSystemDomain purkinjeGraphModel;`, the
only type `conductionSystemDomain::New` accepts) is built per
`conductionNetworkDomains.<name>` and reads its `purkinjeGraphModelCoeffs`.
`readGraphFile` opens `constant/<graphFile>` as an `IOdictionary` (`graphFile`
is the object name, so any file under `constant/` can be named; the README of
`1DgraphToFoam` and its `-name` default call it `purkinjeGraph`).

Every key read from the graph dictionary, and nothing else:

| key | read by | required | meaning |
|---|---|---|---|
| `conductionEdges` | `conductionGraph::readFromDict`, `get<List<scalarList>>` | yes | one `(nodeA nodeB length conductance)` per edge; a fatal names an entry with other than 4 values |
| `pvjResistances` | `readFromDict`, under `found` | no | one resistance per junction (below) |
| `rootNode` | `readGraphFile`, `get<label>` | yes | the node `rootStimulus` drives; fatal outside `[0, N-1]` |
| `pvjNodes` | `readGraphFile`, `lookup` | yes | the junction nodes; fatal outside `[0, N-1]` |
| `points` | `readGraphFile`, `lookup` | yes | one position per node; fatal unless `points.size() == N` |
| `pvjLocations` | `readGraphFile`, `lookup` | yes | one position per junction; fatal unless the same size as `pvjNodes` |

`1DgraphToFoam` also writes `edges`, `edgeVtkCellMap`, `edgeLength`,
`endpointNodes`, `pointFields` and `edgeFields`, its provenance from the VTK
source; no solver reads them.

**Node numbering and topology.** `readFromDict` takes the node indices with
`static_cast<label>` and sets `N = max(index) + 1`; `buildTreeTopology` then
refuses anything but a tree: exactly `N - 1` edges, and a breadth-first search
**from node 0** that reaches all `N` nodes. So indices count from 0, every index
up to the largest is used (an unused one is a disconnected node), and the graph
is acyclic. The order of that search, from node 0 and not from `rootNode`, is
the order `monodomain1DSolver`'s Hines elimination sweeps (leaves to node 0,
then back). In a parallel run the whole graph is on every rank; only the ionic
ODEs are split, into contiguous blocks of node indices
(`conductionSystemDomain::initialiseState`).

**How length and conductance enter each solver.**

- `monodomain1DSolver` (default): the cable equation above; `length` sets both
  the edge's `sigma/length` coupling and the nodes' control lengths (which must
  be positive: every node needs an edge). A zero conductance removes the
  coupling, which is how `idealizedHeart/pathos/conductionBlock` severs a
  bundle branch (`Allrun`'s `severBundleBranch` zeroes `conductionEdges[0]` or
  `[22]`).
- `eikonalSolver1D`: Dijkstra over `length/purkinjeCV`; the conductance is never
  read.
- `restitutionEikonalSolver1D`: `length/cv`, with `cv` from the restitution
  curve times `sqrt(sigma_e/referenceConductance)` when `useEdgeConductance`
  (default true); a relative conductance at or below `SMALL` blocks the edge.

**The root.** `rootNode_` is the graph's `rootNode`, replaced by
`rootStimulus.node` when the coefficients give one
(`conductionSystemDomain::readRootStimulus`). `rootStimulus.intensity` (A/m³)
is added to the root's applied current from each start time for `duration`;
the eikonal solvers seed the root at the earliest start time.

**What `points` is for.** The positions go to the network's VTK output
(`purkinjeModelIO::writeVTK`) and to the graph verifier
(`graphVerificationModel::preProcess`/`postProcess`, which evaluates the
manufactured solution at them). The solvers never compute a length from them.

## The coupling to the 3D myocardium

A coupling is `domainCouplings.<name>` with `electroDomainCoupler` and
`conductionNetworkDomain` (the network's name). All three couplers derive from
`pvjCoupler`, which builds a `pvjMapper` from the network's `pvjLocations`:

- for each junction, the cells whose centres lie within `pvjRadius` (default
  `0.5e-3` m; fatal if smaller than the cube root of the nearest cell's volume),
  weighted by `pvjKernel` (`uniform` 1, `gaussian` `exp(-4.5 r²/R²)`, `linear`
  `1 - r/R`); `V_sphere` is the weighted sum of their volumes;
- the tissue `Vm` at a junction is the weighted volume average over that set
  (`gatherVm3DPvjs`), and a junction current is spread over it as
  `I * w / V_sphere` (`depositCoupling`).

`couplingMode` (required) is `unidirectional` or `bidirectional`.

- `reactionDiffusionPvjCoupler` (monodomain network to monodomain or bidomain
  tissue): `I_pvj = (Vm_network - Vm_tissue)/R_pvj` at each junction. The
  tissue receives it explicitly, or with `pvjCouplingScheme implicit` as a
  source `w*Vm_network/(R*V_sphere)` plus an implicit coefficient
  `w/(R*V_sphere)` on the cell's own `Vm`. In `bidirectional` mode the network
  node loses the same number (`appliedCurrent[pvjNode] -= I_pvj`), used as A/m³
  without a node volume; in `unidirectional` mode the buffers are cleared
  before the network advances.
  This is the coupler the 1D-3D manufactured solution exercises.
- `eikonalMonodomainPvjCoupler` (eikonal network to monodomain tissue): the
  network's activation time drives a voltage template at each junction, offset
  to the tissue's resting potential, and the same `(V - Vm_tissue)/R` current
  enters the tissue; in `bidirectional` mode the tissue's activation times are
  returned to the junction nodes.
- `eikonalPvjCoupler` (eikonal to eikonal): copies junction activation times
  into the tissue's activation-time field; `bidirectional` returns the tissue's.
  It reads no resistance.

**The per-junction resistances against the block's coefficient.**
`conductionSystemDomain::terminalResistances` returns the graph's
`pvjResistances` when the list is non-empty, else nothing. Then:

- `reactionDiffusionPvjCoupler` uses it in place of `rPvj` for every junction,
  and reads `rPvj` (`dict.get`, required) only when the graph has none;
- `eikonalMonodomainPvjCoupler` requires `rPvj` at construction and replaces it
  with the graph's list at every step;
- `coupled1D3DMonodomainVerifier` takes the same precedence.

The graph's per-edge conductances are always multiplied by
`purkinjeConductivity` (default 1.0); nothing replaces them. `referenceConductance`
only normalises them inside `restitutionEikonalSolver1D`.

## Why each exists

- **The 1D network** is the Purkinje fibre tree: the fast conduction system that
  activates the ventricles from the inside (`electroDomains/README.md`: "the
  Purkinje network as a graph"). `idealizedHeart/electroHeart` runs it at
  ~3.3 m/s under all three solvers, against the myocardium's much slower
  conduction.
- **`conductionEdges`** carries the tree and its per-edge conductance, so a
  branch can conduct differently or not at all; `conductionBlock` models a
  bundle branch block by zeroing one edge.
- **`points`** places the tree for output and verification; **`pvjNodes`** and
  **`pvjLocations`** are the Purkinje-ventricular junctions, where the network
  meets the myocardium. The location is separate from the node position, and
  `electroHeart`'s pig tree marches its junctions into the wall
  (`terminalModel transmural`).
- **`pvjResistances`** lets each junction couple with its own resistance.
  `electroHeart`'s README measures what the resistance controls: at `rPvj 1000`
  intramural junctions capture after ~11 ms against ~5 ms at the surface, and
  faster below `rPvj` 300.
- **The coupled 1D-3D manufactured solution**
  (`manufacturedSolutions/monodomain1D3D`, its README "Convergence
  verification") exists to show the coupled implementation converges at O(h²);
  `setup/generate_purkinje_graphs.py` writes the refined Y-shaped graphs it
  sweeps (one root at x = 0.5, two junctions at x = 0 and x = 1, every
  conductance 1.0).

## Probes

| # | command | observed | conclusion |
|---|---|---|---|
| G1 | `omnidriver catalog --repo <tree> --uncatalogued`, before the graph document | `conductionEdges` and `pvjResistances` uncatalogued (root `param:readFromDict:dict`, no document); `rootNode`, `pvjNodes`, `points`, `pvjLocations` unresolved (the receiver is an `IOdictionary` named by a variable); `torsoSurface` uncatalogued | the scan sees all six graph reads |
| G2 | the same, after (`purkinjeGraph` document, `common_dict_entries.PURKINJE_GRAPH_ENTRIES`) | `conductionEdges` and `pvjResistances` gone; `--unread` empty; no disagreement | the scan places `readFromDict`'s dictionary in the graph document by the entries' `source_refs` |
| G3 | foamlib's `FoamFile(...).as_dict()` on the first 100 and 1000 edges of `idealizedHeart/mesh/constant/purkinjeGraph` | 0.45 s and 43 s; the full file (44499 edges) does not finish in 5 minutes | foamlib cannot read a real graph; omniD reads one lexically (`mutators.read_foam_entries`, `literals.list_elements`) |
| G4 | `validation.case_diagnostics` on `electroHeart/constant/electroProperties.monodomain` with the human graph, then the pig graph | no diagnostic; one pass of `mutators.read_foam_entries` reads the human graph's keys in 0.12 s | both native trees are trees with consistent sizes |
| G5 | `plan --strict --case` on a copy of `monodomain1D3D` with `pvjNodes (20 41)` | refused: "pvjNodes [41] are outside the graph's nodes 0 to 40" | the C++'s `readGraphFile` fatal, named before the run |
| G6 | `plan --strict --repo <tree> --entry <record>`, every record, before and after | all `ok`, no diagnostic added or removed | |
| G7 | `run --strict --entry manufacturedMonodomain1D3D` (20³ cells, 41-node graph, `rPvj 1`) | `ok` in 13 s; log: `Purkinje edge conductance multiplier: 0.111453`; `PVJ coupling debug`: `networkVm` ±1.0, `tissueVm` ±0.45, `terminalCurrent` ±1.45, `terminalSource` ±2081; graph error summary `Vm1D` L2 7.1e-6 | `terminalCurrent = ΔV/R` with R = 1 (1.0 - (-0.45) = 1.45), and `terminalSource = I/V_sphere` |
| G8 | the native utilities `checkMeshGeometry` and `runPurkinjeGraph`, read for what they check (`.C`, README, manifest) | `checkMeshGeometry` reads `constant/<region>/polyMesh` points and compares the largest bounding-box dimension with fixed thresholds (below 20 is metres, 20 to 1000 mm, 1000 to 1e6 µm); it never reads a graph. `runPurkinjeGraph` builds the `conductionSystemDomain` and advances it for the case's whole `controlDict`; the checks it runs are `conductionGraph::readFromDict`'s and `readGraphFile`'s, which omniD already mirrors; it builds no coupler and so reads no `pvjLocations` against the mesh and no `pvjResistances`, and `readRootStimulus` is unchecked | neither compares a graph with a mesh, and neither judges a sign: omniD's checks duplicate neither |
| G9 | min, median and max of \|`pvjLocations[i]` − `points[pvjNodes[i]]`\|, and of edge lengths and conductances, over the human and pig `idealizedHeart` graphs, `purkinjeRestitution2D`, and every `monodomain1D3D` graph | the offset is 0 for every junction of every graph; lengths 7.8e-6 to 3.4e-4 m (idealizedHeart), 0.00625 to 0.5 (monodomain1D3D, a unit cube); every conductance 1; no edge of length 0; no node index with a fraction | a check that a location sits at its node's position, a length above 0, and a conductance of 0 or more refuses no native data |
| G10 | `plan --strict --case` of each native graph case materialized as its `Allrun` does (human and pig × monodomain, eikonal and hybrid; `conductionBlock` lbbb and rbbb; `ionicPathology` brugada and ischemia; `purkinjeRestitution2D` three variants; `monodomain1D3D` and its six graphs), on `main` and with the checks | all 20 `ok` on both, the same diagnostics; human `idealizedHeart` 3.6 s on both | no native case is newly refused, and the check is not felt in a plan |
| G11 | the same, `rootStimulus.node 50000` | refused: "rootStimulus.node is 50000, outside the nodes 0 to 44499 of constant/purkinjeGraph" | the C++ gives no message |
| G12 | `monodomain1D3D` with `pvjLocations` in millimetres against its metre mesh: `plan --strict --entry`, then `step --step mesh`, then `step --step solve`; then `run` | `plan` is `ok` with the `pvj_location_off_node` warning; `step --step solve` refuses with the bounding-box error before `cardiacFoam` starts; `run` completes `ok` | a plan cannot see a mesh the case has yet to make (`polyMesh` is a generated directory and is not staged), and `run` validates once, before its first step; the bounding-box check fires wherever the mesh exists when the case is judged |


## Units, settled

The owner settled the two unit questions the C++ leaves open, from the evidence
below.

- **`purkinjeConductivity` is S/m**, and the per-edge conductance in
  `conductionEdges` is a dimensionless factor (0 blocks the edge). The product
  enters the cable update as a conductivity, given the catalogue's 1D `chi` in
  1/m and `cm` in F/m² (the derivation above); every native graph writes
  conductance 1, and the native cases give `purkinjeConductivity` in S/m (0.4,
  and 0.111453302, the 3D tissue's `sigma_xx`). `readGraphFile` prints it as a
  "multiplier" and `1DgraphToFoam` fills the conductance from a VTK field named
  `conductance`, `conductivity`, `D` or `sigma`; a `D` there would be a
  diffusivity (m²/s), not a factor.
- **`rPvj` and `pvjResistances` are Ω.** The tissue side divides a voltage
  difference by `R` to get the junction current in A, distributed over the
  kernel-weighted junction volume. The network side of
  `reactionDiffusionPvjCoupler` applies the same number without a node volume
  (`appliedCurrent[terminalNodes_[i]] -= terminalCurrent_[i];`, then
  `dt*appliedCurrentBuffer_[i]/chiCm`), so in the current C++ a `bidirectional`
  junction barely moves the network. The native
  `electroModels/ARCHITECTURE.md` labels the current `[A/m²]`, which neither
  side uses. [`cardiacfoam-pvj-coupling.md`](cardiacfoam-pvj-coupling.md) holds
  the measurements.

## Needs owner confirmation

1. **`pvjResistances` length.** `couplingCurrentAtPvjs` indexes
   `R_pvj_[i]` for each junction, and only the implicit scheme
   (`pvjMapper::depositImplicitCoupling`) checks the size. With the explicit
   scheme, a short list reads past its end. omniD refuses a list whose length
   is not the number of `pvjNodes`, and a value that is not above 0 (the
   current is divided by it); likewise an `rPvj` that is not above 0.
2. **`rootStimulus.node` is not range-checked.** The graph's `rootNode` is, but
   the override from `readRootStimulus` goes straight into
   `appliedCurrent[rootNode_]`. omniD refuses a node past the graph's last.
3. **`pvjLocations` against `points[pvjNodes]`.** They are never compared, so a
   junction can couple away from its node's position. Is that intended, for
   example a junction placed inside the wall? Every native graph, the pig
   tree's transmural junctions included, writes the two equal (G9), so omniD
   warns of a location more than the coupling's `pvjRadius` from its node's
   position. It refuses a location more than `pvjRadius` outside the mesh's
   bounding box, which `pvjMapper` would couple to its nearest cell, however far.
4. **`eikonalMonodomainPvjCoupler` requires `rPvj`** even when the graph lists
   `pvjResistances`, and then never uses it.
5. **`torsoSurface`.** Its only reader is `ecgModelIO::loadSurface`
   (`dict.get<fileName>("torsoSurface")`, opened as `runTime.path()/stlPath`, so
   the path is relative to the case directory). The function takes a
   `const dictionary&`, as `ecgDomain::readElectrodes` and `ecgSolver::New`
   do, and those receive the `ecgDomains.<name>` block, so the catalogue places
   the key there; the owner wires the call with the bath-heart case, on a
   branch, and confirms the placement. Its face centres are the ECG evaluation
   points, in the frame of the electrodes, so the STL is in mesh units
   (metres); `ecgModelIO::writeSurfaceVtk` writes the potential on its faces
   under `postProcessing/ECG`.
