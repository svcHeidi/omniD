# omniD: Architecture, Research Positioning, Collaboration Targets, and Code-Verification Handoff

**Date:** 2026-09-23  
**Purpose:** Research and architecture handoff for a code-aware agent that has direct access to the `omniD` repository.  
**Repository provided by author:** `https://github.com/svcHeidi/omniD`

> **Important verification note**
>
> The source repository itself was **not directly inspected in the conversation that produced this document**.  
> Statements marked **[AUTHOR-DESCRIBED — VERIFY IN CODE]** come from the project author's explanations and should be checked against the actual implementation, package structure, APIs, tutorials, and README files.
>
> External projects and research references were checked against public sources current to September 2026.

---

## 1. Executive summary

The emerging idea behind **omniD** is not to build a monolithic model that contains the full logic of every scientific solver, nor to create a separate intelligent agent for every solver/HPC combination.

The stronger architecture is:

1. **omniD owns reasoning/orchestration.**
2. **Application packages expose the structure, tooling, defaults, and manipulable objects of deterministic scientific software.**
3. **Execution/HPC packages describe how to run a prepared application workload on a particular infrastructure.**
4. **The numerical solver remains deterministic scientific software.**
5. **Models should be replaceable**, including commercial frontier models, local/open-weight models, and domain-fine-tuned specialist models.
6. **Verified tutorial/example cases can be the unit of trusted simulation knowledge**, instead of requiring unrestricted generation of a valid case from an empty directory.
7. **Evaluation should use deterministic numerical correctness wherever possible**, rather than relying primarily on LLM-as-a-judge evaluation.

A concise conceptual model is:

```text
                        omniD
              reasoning / orchestration
                        |
          +-------------+-------------+
          |                           |
   application interface        execution interface
          |                           |
  OpenFOAM / cardiac / FSI     local / SLURM / PBS / ...
          |                           |
          +-------------+-------------+
                        |
                deterministic solver
                        |
               numerical validation
```

This separation is likely one of the most important aspects to preserve and formalize.

---

# 2. What omniD appears to be today

## 2.1 Core responsibility

**[AUTHOR-DESCRIBED — VERIFY IN CODE]**

The author explicitly clarified that **decision-making does not belong inside the OpenFOAM package**.

The intended split is approximately:

```text
omniD
  |
  +-- reasoning / agent / orchestration
  |
  +-- application-specific packages
       |
       +-- OpenFOAM package
       +-- cardiac application package(s)
       +-- future FSI package
       +-- other numerical applications
```

The application-specific package should provide the **interface between omniD and the deterministic application**, rather than act as an independent scientific decision-maker.

---

## 2.2 Current OpenFOAM package

**[AUTHOR-DESCRIBED — VERIFY IN CODE]**

The OpenFOAM integration reportedly uses primarily:

- `foamlib`;
- custom parsing/manipulation functions;
- knowledge of the OpenFOAM case structure;
- knowledge of where important pieces live;
- defaults associated with supported cases/tutorials;
- mechanisms for reading/modifying/writing relevant case files.

The author specifically corrected the assumption that the package itself decides:

- which physics should be used;
- what simulation the user intends;
- which model is scientifically appropriate;
- whether a simulation should be rerun;
- what solver strategy should be selected at a high level.

Those decisions should remain at the omniD reasoning/orchestration layer.

### Code-aware agent: verify

Check:

- exact package/module name;
- how `foamlib` is wrapped;
- parser classes/functions;
- whether dictionary creation is supported as well as editing;
- whether OpenFOAM fields under `0/` are handled;
- whether `system/` and `constant/` are exposed through common abstractions;
- whether case cloning is provided by omniD or directly through `foamlib`;
- whether execution is currently triggered from the OpenFOAM package;
- whether post-processing/log/residual access exists;
- whether OpenFOAM-version-specific assumptions exist.

---

# 3. Tutorial-grounded case adaptation is already a central design pattern

**[AUTHOR-DESCRIBED — VERIFY IN CODE]**

The project already reportedly follows an important pattern:

1. Start from a specific, curated simulation/tutorial.
2. Each supported case contains a `README.md`.
3. Clone/use an existing valid case.
4. Let the agent inspect the documentation and case.
5. Modify the case through the application tooling.
6. Run the deterministic simulator.

Conceptually:

```text
User request
    |
    v
Select supported tutorial / reference case
    |
    +--> README.md / instructions
    |
    +--> trusted valid numerical case
    |
    v
omniD reasoning
    |
    v
application package tools
    |
    v
modify cloned case
    |
    v
run solver
    |
    v
inspect / validate / iterate
```

This is not a weakness relative to "generate every file from scratch."

It may be a deliberate safety and reliability feature.

---

# 4. Do not assume omniD needs unrestricted OpenFOAM generation from scratch

A previous concern was whether omniD must be capable of receiving:

> "Simulate arbitrary problem X"

and generating a complete OpenFOAM case from an empty directory.

That capability may eventually be useful, but it is **not necessary to establish the core research contribution**.

For a first serious paper, a trusted-example adaptation approach may be more defensible:

```text
verified reference case
       |
       v
structured adaptation
       |
       v
solver execution
       |
       v
numerical verification
```

rather than:

```text
LLM
 |
 v
unrestricted raw OpenFOAM text generation
 |
 v
hope generated case is correct
```

### Why this matters

A tutorial/reference case provides:

- valid directory structure;
- valid starting dictionaries;
- known compatible settings;
- explicit pedagogical context;
- a baseline result;
- a natural source of expected behavior;
- a constrained modification space.

The agent can therefore focus on **scientific adaptation**, not merely reproducing OpenFOAM syntax.

---

# 5. Tutorials can become first-class machine-actionable knowledge

The existing `README.md` files are potentially more important than ordinary documentation.

They can serve simultaneously as:

- human teaching material;
- agent grounding;
- capability documentation;
- modification constraints;
- validation instructions.

A useful long-term structure might be:

```text
tutorial/
    README.md
    manifest.yaml       # optional future addition
    case/
```

For example:

```yaml
physics:
  domain: incompressible_flow
  regime: laminar

modifiable:
  - inlet_velocity
  - viscosity
  - mesh_resolution

relevant_files:
  - 0/U
  - 0/p
  - constant/transportProperties
  - system/controlDict

validation:
  - convergence
  - mass_conservation
  - pressure_drop_range

unsupported:
  - compressibility
  - multiphase_flow
```

This is only a proposed architecture. Do **not** introduce such a manifest unless it improves the existing codebase.

### Code-aware agent: inspect

Determine whether README content is currently:

- explicitly given to the agent;
- indexed/retrieved;
- passed verbatim;
- manually selected;
- associated programmatically with a case;
- used only as human documentation.

This is an important distinction for the research paper.

---

# 6. Suggested hierarchy of task difficulty

The tutorial-based approach naturally defines levels of agent generalization.

## Level 1 — parameter interpolation

Example:

```text
reference:
pipe flow, Re = 100

requested:
pipe flow, Re = 150
```

Main challenge:
- identify parameter;
- modify correct location;
- execute;
- validate.

## Level 2 — adaptation

Same physical family, but significant changes:

- different geometry;
- modified inlet;
- changed material parameter;
- altered mesh;
- different duration/output;
- changed boundary condition.

This evaluates whether the model understands **which parts of a valid case must change together**.

## Level 3 — composition

The requested problem requires combining knowledge present across more than one example/tutorial.

Example:

```text
tutorial A -> relevant solver setup
tutorial B -> boundary-condition pattern
tutorial C -> post-processing workflow
```

This begins to test genuine compositional reasoning.

## Level 4 — unsupported / out-of-distribution recognition

The agent should be able to determine:

> "The available tools/examples do not provide enough support to safely construct this simulation."

This is especially valuable for scientific software.

A benchmark should reward appropriate abstention instead of forcing the model to hallucinate a configuration.

---

# 7. Application diversity: what should be added next?

The goal should not be "as many applications as possible."

The better research strategy is to add applications that test **different forms of generalization**.

The author's current/anticipated set is approximately:

- two cardiac applications;
- one FSI application;
- OpenFOAM;
- possibly an additional cardiac software environment.

**[AUTHOR-DESCRIBED — VERIFY DETAILS]**

A useful experimental matrix would be:

| Comparison | What it tests |
|---|---|
| Cardiac software A vs cardiac software B | same scientific domain, different software |
| Cardiac vs OpenFOAM | different physics/application family |
| single-physics vs FSI | multiphysics complexity |
| known tutorial vs changed case | adaptation |
| same task with different LLMs | model dependence |
| local vs commercial model | privacy/cost/latency tradeoffs |
| same solver on different HPC systems | infrastructure portability |

A second cardiac simulator could be especially valuable because it creates a strong experiment:

> Can omniD preserve scientific intent while changing the application interface underneath it?

That isolates application portability better than simply adding another unrelated CFD case.

---

# 8. Recommended architectural distinction: application adapters vs execution adapters

This was one of the clearest conclusions of the discussion.

## 8.1 Application package

An application package should describe:

- where relevant application state lives;
- how to inspect it;
- how to change it;
- what commands/executables correspond to operations;
- defaults or conventions associated with supported workflows;
- result/log locations;
- perhaps validation hooks.

It should **not necessarily contain scientific reasoning**.

For OpenFOAM:

```text
OpenFOAM package
    |
    +-- file/dictionary locations
    +-- parser/writer tooling
    +-- case defaults
    +-- application commands
    +-- foamlib integration
    +-- custom helper functions
```

---

## 8.2 Execution/HPC package

HPC execution should be a separate abstraction.

The same prepared OpenFOAM case may be launched differently on:

- local workstation;
- SLURM;
- PBS;
- LSF;
- another scheduler;
- SSH remote environment;
- containerized HPC environment.

Conceptually:

```text
application says:
    executable = simpleFoam
    working_dir = case/
    parallel = true
    ranks = 64

executor decides:
    how that becomes an actual job
```

Potential common interface:

```python
submit(...)
status(...)
logs(...)
cancel(...)
```

Possible implementations:

```text
LocalExecutor
SlurmExecutor
PBSExecutor
LSFExecutor
...
```

This prevents an undesirable Cartesian product:

```text
OpenFOAM × SLURM
OpenFOAM × PBS
Cardiac × SLURM
Cardiac × PBS
FSI × SLURM
FSI × PBS
```

Instead:

```text
Applications:
    OpenFOAM
    Cardiac A
    Cardiac B
    FSI

Executors:
    Local
    SLURM
    PBS
    LSF
```

and compose:

```text
Application + Executor
```

### Important caveat

Different HPC systems may still require machine-specific configuration:

- software modules;
- MPI implementation;
- containers;
- scratch paths;
- partitions;
- accounts;
- licenses;
- GPU requirements;
- wall-time/resource conventions.

These should preferably be infrastructure configuration, not new scientific-agent logic.

---

# 9. A useful portability experiment

Once an executor abstraction exists, a clean experiment is:

```text
same user request
same LLM
same application adapter
same numerical case

local
SLURM cluster A
PBS cluster B
```

Evaluate whether the scientific result is equivalent.

This demonstrates:

> The scientific agent/application logic is portable independently of execution infrastructure.

That is stronger than simply claiming "SLURM support."

---

# 10. Model strategy: omniD should allow replaceable specialist models

The architecture should not require a single giant model that understands every numerical solver.

A useful long-term design is:

```text
                       omniD
                         |
                  routing / reasoning
                         |
          +--------------+--------------+
          |              |              |
       FEniCS         OpenFOAM        cardiac
       model            model          model
          |              |              |
      deterministic  deterministic  deterministic
        solver          solver          solver
```

Different application specialists may be:

- frontier commercial models;
- small open-weight models;
- fine-tuned solver-specific models;
- code-specialized models;
- models using retrieval;
- models that only provide high-level decisions.

omniD should ideally depend on a **stable capability/tool contract**, not on the internal architecture of a particular model.

---

# 11. Local/private models and patient data

The author anticipates possible use with sensitive patient data.

Therefore a future research track should explicitly evaluate:

- fully local inference;
- on-premise inference;
- whether prompts/results leave the HPC environment;
- logging and auditability;
- artifact provenance;
- model/data isolation;
- role of retrieval stores;
- whether different applications require different specialist models.

Do not assume that replacing a cloud model with any open-weight model automatically solves the privacy problem.

The complete data path must be considered:

```text
input data
 -> prompt/context construction
 -> model inference
 -> tool arguments
 -> logs/traces
 -> vector stores / retrieval
 -> solver
 -> outputs
 -> monitoring
```

A private deployment claim requires the full pipeline to remain controlled.

---

# 12. Training strategy: do not start from scratch unless evidence demands it

For this project, training a foundation model from scratch is unlikely to be the first useful step.

A reasonable progression is:

1. prompting + deterministic tools;
2. tutorial/document retrieval;
3. structured tool interfaces;
4. open-weight general model;
5. supervised fine-tuning;
6. LoRA/QLoRA;
7. distillation from stronger models;
8. domain-specific continued pretraining only if justified;
9. from-scratch training only if there is a very strong reason.

The key empirical question should be:

> What is the smallest/safest model that successfully performs a given class of simulation task when supported by good tools and trusted examples?

This is more useful than simply asking which model is "best."

---

# 13. Evaluation: numerical simulation offers unusually strong agent benchmarks

This may be one of the strongest research opportunities in omniD.

Many general agent benchmarks struggle with determining whether a result is actually correct.

Scientific simulation can often provide deterministic or tolerance-based checks:

```text
requested task
    |
    v
agent changes/generates simulation
    |
    v
deterministic numerical solver
    |
    v
convergence / conservation / reference result
```

Possible evaluation dimensions:

## Task completion

- case created/modified;
- command executed;
- requested output generated.

## Numerical validity

- solver convergence;
- residual behavior;
- conservation constraints;
- correct physical regime;
- expected scalar/vector quantities;
- agreement with analytical/reference solution;
- mesh-independence where appropriate.

## Tool correctness

- correct files touched;
- correct keys/fields modified;
- correct commands used;
- no unrelated modifications.

## Robustness

- recovery from solver failure;
- recovery from malformed inputs;
- ability to detect unsupported requests;
- sensitivity to prompt phrasing.

## Agent efficiency

- model tokens;
- number of tool calls;
- number of solver retries;
- wall-clock time;
- compute cost.

## Reproducibility

- repeated-run consistency;
- stochastic variance;
- equivalent results across HPC backends.

## Safety/reliability

- hallucinated file names;
- invented parameters;
- destructive operations;
- unsupported-action rate;
- false confidence after solver failure.

## Educational quality

For didactic mode:

- correctness of explanation;
- whether important physical assumptions are exposed;
- whether the explanation matches what was actually changed;
- whether a novice can trace configuration -> physics -> result.

Avoid collapsing all of these into one single "agent score."

---

# 14. Existing work most relevant to omniD

## 14.1 ALL-FEM — fine-tuned FEM models inside an autonomous agentic system

**Source:**  
https://doi.org/10.1016/j.cma.2026.118985

ALL-FEM is extremely relevant to the question:

> Can omniD use a model that another group has already fine-tuned for a numerical application?

The 2026 ALL-FEM work reports:

- an autonomous finite-element simulation system;
- domain-specific fine-tuned LLMs;
- open-weight models from **3B to 120B**;
- a verified FEniCS code dataset with **over 1,000 entries**;
- multi-agent orchestration;
- debugging and implementation consistency checks;
- a benchmark of **39 problems**;
- elasticity, plasticity, Newtonian/non-Newtonian flow, thermofluids, **fluid-structure interaction**, multiphase approximations, and moving-domain diffusion/reaction tasks.

This is a strong collaboration/comparison candidate.

### Potential joint research question

> Can a domain-specialized model developed for one numerical environment be integrated into a solver/application-agnostic orchestration framework without changing the surrounding scientific workflow?

### Why it fits omniD

Instead of reimplementing their model:

```text
ALL-FEM specialist
       |
       v
FEniCS application
```

could become one specialist application/model route inside omniD.

---

# 15. Foam-Agent — close OpenFOAM comparison and potential integration target

**Source:**  
https://github.com/csml-rpi/Foam-Agent

Foam-Agent is an end-to-end multi-agent OpenFOAM system.

The current public project describes:

- natural-language-to-CFD workflow;
- meshing;
- case setup;
- execution;
- error correction;
- post-processing;
- multi-agent roles;
- hierarchical retrieval from OpenFOAM tutorials;
- OpenFOAM configuration generation;
- MCP-exposed functions;
- an OpenFOAM benchmark (FoamBench).

This is very close to omniD's OpenFOAM use case, but the architectural emphasis differs.

### Useful comparison

Foam-Agent:

```text
prompt
 -> agent planning
 -> file/config generation
 -> execution
 -> repair
```

omniD, as currently described:

```text
prompt
 -> omniD reasoning
 -> trusted case/tutorial
 -> application tooling
 -> structured modification
 -> execution
 -> validation
```

That distinction should be empirically tested rather than argued abstractly.

### Strong possible experiment

Compare:

1. direct generation;
2. tutorial-grounded adaptation;
3. fine-tuned model + structured tools;
4. general frontier model + structured tools.

Measure physical correctness, execution success, failure recovery, cost, and unsupported-task recognition.

---

# 16. SINTEF — extremely close high-level scientific-agent philosophy

**Sources:**  
https://www.sintef.no/en/digital/departments/mathematics-and-cybernetics/applied-computational-science/agentic-ai-for-scientific-computing/  
https://blog.sintef.com/digital-en/talking-to-your-simulator-what-we-learned-building-jutulgpt/

SINTEF publicly describes work that:

- connects AI agents to simulation software;
- combines agent technology with numerical methods and simulator expertise;
- constructs simulation workflows;
- executes and inspects solver output;
- connects specialist software through interfaces;
- uses standards such as MCP;
- emphasizes that successful execution is not sufficient to establish a scientifically valid model.

This is one of the closest high-level conceptual matches to omniD.

### Collaboration angle

The pitch should not be:

> "I also built an agent."

It should be:

> "omniD is exploring application-independent scientific orchestration, trusted simulation examples, replaceable local/specialist models, deterministic validation, and portable HPC execution."

SINTEF could be useful for:

- scientific-agent architecture;
- simulator interfaces;
- validation/provenance;
- industry use;
- local/private deployments.

Public contacts named on the SINTEF page include **Jakob Torben** and **Olav Møyner**.

---

# 17. openCARP — particularly attractive cardiac application target

**Sources:**  
https://opencarp.org/  
https://opencarp.org/documentation/carputilsgui  
https://opencarp.org/download/installation/install-carputils

openCARP is especially promising because it already has:

- cardiac electrophysiology simulation;
- Python-based `carputils`;
- parameterized simulation workflows;
- example/tutorial culture;
- educational tooling;
- deterministic simulation software.

The public documentation describes `carputilsGUI` specifically as an educational interface and `carputils` as the command-line Python interface more appropriate for research workflows.

### Why this maps well to omniD

The omniD pattern:

```text
example/tutorial
 + documentation
 + Python-accessible deterministic solver
```

matches openCARP well.

### Potential collaboration experiment

Implement openCARP as an independent cardiac application adapter.

Then test:

> Can the same omniD reasoning architecture execute comparable scientific intents across two distinct cardiac simulation software environments?

That is stronger than simply adding another unrelated solver.

---

# 18. Oxford Cardiac Digital Twin code — useful complex workflow target

**Source:**  
https://github.com/juliacamps/Cardiac-Digital-Twin

The public cardiac digital twin repository includes:

- a modular mostly-Python digital-twinning pipeline;
- geometry;
- electrophysiology;
- propagation;
- conduction systems;
- cellular modeling;
- explicit templates for future use cases;
- example data available separately.

This could test omniD on something more complex than a single solver executable.

Instead of:

```text
LLM -> solver
```

the workflow is closer to:

```text
agent
 -> multi-stage scientific pipeline
 -> mechanistic components
 -> inference/calibration
 -> numerical simulation
 -> outputs
```

That is highly relevant to the broader omniD goal.

---

# 19. Collaboration map

## Tier A — very close technical fit

### ALL-FEM / Purdue ecosystem

Best for:

- fine-tuned numerical LLMs;
- open-weight specialist models;
- FEniCS;
- FSI;
- benchmark design;
- model specialization.

Suggested pitch:

> We would like to test whether your FEM-specialized model can operate as a specialist component inside an application-independent orchestration/verification architecture, and compare portability across FEniCS, OpenFOAM, and cardiac simulation workflows.

---

### Foam-Agent / RPI

Best for:

- OpenFOAM;
- agent architecture comparison;
- retrieval from tutorials;
- automated repair;
- MCP/service exposure;
- shared benchmark work.

Suggested pitch:

> Rather than build another competing OpenFOAM agent, we want to compare and potentially compose an end-to-end generation agent with a tutorial-grounded application abstraction, and evaluate both using numerical correctness.

---

## Tier B — strongest cardiac application targets

### openCARP

Best for:

- second independent cardiac simulator;
- tutorial/example-driven workflows;
- electrophysiology;
- educational use;
- open academic ecosystem.

Suggested pitch:

> We want to implement an openCARP adapter in a solver-independent scientific agent framework and test whether the same autonomous workflow transfers between different cardiac simulation environments.

---

### Cardiac Digital Twin / Oxford-related ecosystem

Best for:

- patient-specific workflows;
- multi-component cardiac pipelines;
- digital twins;
- eventual private/local model use.

Suggested pitch:

> We want to test whether an autonomous scientific agent can reliably operate a modular cardiac-digital-twin pipeline through trusted examples and explicit tool interfaces, while preserving provenance and enabling local inference.

---

## Tier C — infrastructure/scientific-agent collaboration

### SINTEF Applied Computational Science

Best for:

- agent-to-simulator interfaces;
- workflow architecture;
- simulator feedback;
- industrial deployment;
- validation;
- scientific tooling.

---

# 20. What omniD should probably NOT become

Based on the discussion, avoid drifting into these designs unless evidence shows they are needed.

## 20.1 Not a giant hard-coded encyclopedia of every solver

Do not manually encode every possible OpenFOAM combination solely so the agent never has to reason.

Instead define:

- supported capabilities;
- trusted workflows;
- structured tools;
- retrieval/context;
- validation.

---

## 20.2 Not one model per `(application × HPC)` pair

Avoid:

```text
OpenFOAM-on-SLURM agent
OpenFOAM-on-PBS agent
Cardiac-on-SLURM agent
Cardiac-on-PBS agent
...
```

Prefer:

```text
application interface + executor interface
```

---

## 20.3 Not unrestricted LLM text generation where deterministic structure is available

If `foamlib` or another library can safely manipulate a known structure, prefer:

```text
LLM decides intent / parameters
 -> deterministic structured mutation
```

over:

```text
LLM emits whole configuration file as text
```

unless generation is explicitly the object of the experiment.

---

## 20.4 Not a replacement for the numerical solver

The scientific software should remain the source of deterministic numerical execution.

omniD orchestrates it.

---

# 21. Potential paper positioning

A possible research framing:

> **omniD: an application- and infrastructure-independent agent framework for autonomous, verifiable scientific simulation**

Possible core claim:

> Separate scientific reasoning, application tooling, and execution infrastructure so that different language models, numerical applications, and HPC environments can be composed without retraining or rewriting the entire agent stack.

This must be validated against the actual implementation before being claimed.

---

# 22. Candidate research questions

## RQ1 — Model specialization

> How much does a solver/domain-specialized model improve simulation-task reliability relative to a general model when both use the same deterministic tools and trusted examples?

Compare:

- frontier commercial model;
- local open-weight general model;
- fine-tuned specialist model.

---

## RQ2 — Tutorial-grounded adaptation

> How far can agents generalize from verified simulation examples without generating complete numerical cases from scratch?

Evaluate:

- parameter interpolation;
- adaptation;
- composition;
- unsupported/OOD tasks.

---

## RQ3 — Cross-application portability

> Can the same orchestration architecture execute scientific intent across heterogeneous numerical applications by changing only the application adapter?

Candidates:

- cardiac solver A;
- cardiac solver B/openCARP;
- OpenFOAM;
- FSI/FEniCS.

---

## RQ4 — Infrastructure portability

> Can identical application logic execute across heterogeneous HPC environments by changing only the execution adapter?

Compare:

- local;
- SLURM;
- PBS/other.

---

## RQ5 — Verification

> How much more informative are deterministic numerical checks than conventional agent/task success metrics?

Measure:

- execution success;
- convergence;
- physical correctness;
- requested-output correctness;
- failure recovery;
- cost.

---

## RQ6 — Small/private models

> Which simulation tasks can be reliably executed by local/open-weight models when domain knowledge is supplied through trusted tutorials and structured application tools?

This directly supports future patient-data-sensitive use.

---

# 23. A possible evaluation matrix

| Axis | Example conditions |
|---|---|
| Model | GPT/Claude / local open-weight / fine-tuned |
| Application | cardiac A / cardiac B / OpenFOAM / FSI |
| Task complexity | interpolation / adaptation / composition / OOD |
| Execution | local / SLURM / PBS |
| Context | none / README / README + case / retrieval |
| Tooling | raw file writing / structured API |
| Validation | execute-only / numerical checks / reference solution |

Do not attempt the full Cartesian product for the first paper.

Choose a minimal subset that isolates the strongest hypotheses.

---

# 24. Recommended first-paper scope

A realistic first paper could use:

### Applications

1. Existing cardiac application A
2. Existing cardiac application B OR openCARP
3. OpenFOAM
4. One FSI/FEM application

### Models

1. one frontier commercial model;
2. one capable open-weight/local model;
3. optionally one domain-fine-tuned specialist such as an ALL-FEM-type model if collaboration/access permits.

### Task levels

1. simple parameter modification;
2. case adaptation;
3. error recovery;
4. one cross-example composition task;
5. unsupported-task detection.

### Core metrics

- valid execution;
- numerical correctness;
- convergence;
- number of retries;
- correct tool use;
- cost/latency;
- reproducibility;
- unsupported-action detection.

---

# 25. Immediate development priorities suggested by the discussion

These are **recommendations**, not verified missing features.

## Priority 1 — formalize application capabilities

Determine what each application adapter can reliably do.

Example conceptual capability set:

```text
inspect_case
modify_parameter
modify_boundary_condition
clone_reference_case
run_case
read_logs
extract_outputs
validate_result
```

Do not assume all applications implement all capabilities.

---

## Priority 2 — formalize executor boundary

Create or document the abstraction between:

```text
application workload
```

and:

```text
local/HPC launch mechanism
```

This may be a package, protocol, or configuration layer depending on current code.

---

## Priority 3 — make tutorial grounding explicit

Document exactly how:

- a tutorial is selected;
- its README is exposed;
- reference case files are exposed;
- the model knows what modifications are legitimate;
- validation expectations are represented.

---

## Priority 4 — create a minimal deterministic benchmark

Before adding many new applications, create a small suite with:

- known expected behavior;
- automated numerical checks;
- controlled modifications;
- reproducible solver versions.

---

## Priority 5 — test one local/open-weight model

Do not begin by training from scratch.

First determine whether good tools + tutorials allow a modest model to succeed.

---

# 26. Specific questions for the code-aware verification agent

The next agent should inspect the repository and answer these concretely.

## A. Top-level architecture

1. Where does model/agent reasoning live?
2. How are tools exposed to the model?
3. Is there a generic application abstraction?
4. How are applications registered/discovered?
5. Are application packages plugins, classes, modules, schemas, or ad-hoc imports?

## B. OpenFOAM implementation

6. Exact role of `foamlib`.
7. Exact custom parser/manipulation functions.
8. Can dictionaries be created, or only read/modified?
9. Can fields and boundary conditions be manipulated structurally?
10. How are valid OpenFOAM paths located?
11. How are case defaults represented?
12. Does the OpenFOAM layer itself currently launch simulations?
13. Does it parse logs/residuals?
14. Does it know the chosen solver executable from the case?
15. Are OpenFOAM versions/forks handled?

## C. Tutorials

16. Where do tutorial cases live?
17. Is every tutorial accompanied by README documentation?
18. Does the agent automatically read that documentation?
19. How does it choose a tutorial?
20. Are tutorials manually mapped to capabilities?
21. Is there any machine-readable metadata today?

## D. Cardiac packages

22. What are the two current cardiac applications?
23. Do they follow the same interface?
24. Are their simulation cases tutorial/template based?
25. What results can be automatically validated?
26. Which one is best for a cross-solver benchmark?

## E. FSI

27. What FSI software is intended?
28. Is the interface already started?
29. Can it reuse the same application abstraction?

## F. Execution/HPC

30. Is execution currently application-specific?
31. Is there already SLURM logic?
32. Is SSH involved?
33. Are resources represented in a common object?
34. Could execution be factored into a generic executor without breaking current APIs?
35. What environment/module/container assumptions are hard-coded?

## G. Model abstraction

36. Which commercial providers are currently supported?
37. Is model selection independent from application selection?
38. Is tool calling provider-neutral?
39. Could an open-weight local model be inserted without changing application packages?
40. Could a specialist model be selected per application?

## H. Verification

41. What automated correctness checks already exist?
42. Are there regression tests for solver cases?
43. Are expected values stored anywhere?
44. Is solver success currently treated as correctness?
45. Can exact/tolerance-based numerical metrics be added cleanly?

---

# 27. Claims to verify before using them in a paper

Do **not** publish the following until confirmed directly from code and experiments:

- "solver-agnostic";
- "application-independent";
- "HPC-independent";
- "model-independent";
- "supports local models";
- "supports arbitrary OpenFOAM cases";
- "autonomous";
- "self-correcting";
- "physically validated";
- "generalizes across solvers";
- "privacy-preserving";
- "works with patient data";
- "portable across schedulers".

These are excellent research objectives, but some may currently be design intentions rather than demonstrated properties.

---

# 28. Strong conceptual terminology

The discussion converged on terminology that may make the architecture clearer.

## omniD

**Reasoning and orchestration layer**

Responsibilities may include:

- understanding user intent;
- selecting application/workflow;
- planning;
- calling tools;
- deciding whether to inspect/retry;
- interpreting results;
- educational explanation.

## Application package

**Interface + application-specific structural knowledge + tooling**

Examples:

- OpenFOAM;
- cardiac solver;
- FSI package.

It knows how the application is organized and manipulated, but need not independently reason about the user's scientific goals.

## Executor package

**Infrastructure execution layer**

Examples:

- local;
- SLURM;
- PBS;
- LSF.

It knows how a prepared workload is launched and monitored.

## Numerical solver

**Deterministic scientific software**

Examples:

- OpenFOAM;
- cardiac EP solver;
- FEM/FSI solver.

This is responsible for the actual numerical calculation.

---

# 29. Potential concise project statement

After code verification, something along these lines may be useful:

> **omniD is an orchestration layer for agent-driven scientific computing that separates model reasoning from application-specific tooling and execution infrastructure. Scientific applications expose structured capabilities and trusted simulation workflows, while interchangeable language models plan and adapt simulations. Deterministic solvers execute the numerical work, enabling application-specific verification and portable execution from local systems to HPC environments.**

This is a **draft positioning statement**, not yet a verified factual description.

---

# 30. Potential novelty relative to nearby work

The novelty should probably **not** be framed as:

- "LLMs can run OpenFOAM";
- "agents can generate solver inputs";
- "agents can call HPC jobs";
- "an LLM can fix simulation errors".

Those already have significant prior work.

A more promising combination is:

1. **application-independent orchestration**;
2. **explicit separation of application and execution interfaces**;
3. **trusted-example/tutorial grounding**;
4. **replaceable specialist or local models**;
5. **deterministic numerical verification**;
6. **cross-application evaluation**;
7. **same architecture serving expert and educational use**.

The code-aware agent should determine which of these are already real and which are future work.

---

# 31. Practical collaboration strategy

Do not approach collaborators with:

> "I have another scientific LLM agent."

Instead tailor the proposal.

## ALL-FEM / numerical-model specialists

> You have a strong specialist model. We have an orchestration/application framework. Can we test your specialist as a replaceable component and study portability and verification?

## Foam-Agent / OpenFOAM specialists

> You have an end-to-end OpenFOAM agent. We have a tutorial-grounded, structured application interface. Can we compare or compose these approaches using numerical correctness rather than only execution success?

## openCARP / cardiac simulator teams

> You have a mature simulation environment and tutorials. Can we use it as an independent cardiac backend to evaluate cross-application autonomous simulation?

## cardiovascular digital-twin groups

> Can we evaluate an agent against a realistic multi-stage cardiac workflow, with an eventual path to local/private deployment?

## SINTEF / scientific-agent teams

> Can we collaborate around simulator interfaces, execution-grounded agents, validation, portability, and industry/HPC deployment?

---

# 32. External references

## ALL-FEM

**ALL-FEM: Agentic Large Language Models fine-tuned for finite element methods**  
Computer Methods in Applied Mechanics and Engineering, 2026  
https://doi.org/10.1016/j.cma.2026.118985

---

## Foam-Agent

**Foam-Agent: An End-to-End Composable Multi-Agent Framework for Automating CFD Simulation in OpenFOAM**  
Repository:  
https://github.com/csml-rpi/Foam-Agent

The current repository describes OpenFOAM case generation, execution, repair, tutorial-based retrieval, multi-agent orchestration, and HPC job submission.

---

## SINTEF Agentic Scientific Computing

https://www.sintef.no/en/digital/departments/mathematics-and-cybernetics/applied-computational-science/agentic-ai-for-scientific-computing/

Related JutulGPT discussion:  
https://blog.sintef.com/digital-en/talking-to-your-simulator-what-we-learned-building-jutulgpt/

---

## openCARP

https://opencarp.org/

carputils GUI / educational examples:  
https://opencarp.org/documentation/carputilsgui

carputils installation and Python workflow:  
https://opencarp.org/download/installation/install-carputils

---

## Cardiac Digital Twin

Repository:  
https://github.com/juliacamps/Cardiac-Digital-Twin

The project exposes a modular mostly-Python cardiac digital-twinning pipeline and explicitly describes main scripts as templates for future use cases.

---

# 33. Final takeaway for the code-aware agent

Please do **not** begin by redesigning omniD.

First verify whether the current code already realizes the architecture that emerged from the discussion:

```text
                    omniD
           reasoning / orchestration
                    |
       +------------+------------+
       |                         |
application interface      executor interface
       |                         |
  OpenFOAM / cardiac        Local / HPC
       |                         |
       +------------+------------+
                    |
            deterministic solver
                    |
                validation
```

Then classify every major statement in this document into:

1. **already implemented**;
2. **partially implemented**;
3. **easy architectural extension**;
4. **major missing capability**;
5. **research experiment rather than software feature**.

The most important question is not:

> "How do we make omniD do everything?"

It is:

> **What is the smallest clean architecture that lets one reasoning layer operate multiple trusted scientific applications, use interchangeable models, execute on heterogeneous infrastructure, and be evaluated by deterministic numerical correctness?**

That is likely the strongest path toward both a useful system and a defensible research paper.
