# How an agent learns a solver it has never seen

**Status:** a living record, started 2026-09-25 from learning openCARP (the log is
[`opencarp.md`](opencarp.md)). The owner wants this to become how a future agent
learns any solver, so it records what was **actually done**, including probes
that failed, not an idealised procedure. Refine it each time a solver is
learned. When a step turns out wrong, correct it with a date instead of
silently rewriting it.

## The rule underneath every step

**Only the solver can settle a claim about the solver.** Documentation, memory,
papers and a sibling tool's conventions produce *questions*. A run of the real
binary produces *answers*. Every claim this method yields carries the command
that established it and what the command printed. This is the same rule as
"fixtures can't settle external claims" and "real case or native-source drift
gate, nothing in between".

## Phase A: locate it and make it run

1. Find the install. Look for the binary (`which <solver>`) and its sibling
   tools in the same directory, and check any Python bindings (`import ...`).
   Absent bindings are a finding, not a blocker.
2. Run the cheapest possible command: a version, build-info or help flag.
   **The first run tells you what the environment really is.** For openCARP it
   failed with a missing dynamic library, which showed that its whole
   environment is one library path, not a shell profile. Record the failure
   verbatim, find the cause (a missing library was installed elsewhere), and
   record the fix. That fix is the solver's environment contract, and later its
   preflight check.
3. Record the version and build identity (git tag and hash) from the binary
   itself.
4. **Redact secrets that appear in tool output.** openCARP's build info embeds a
   CI URL containing a token. Build output, logs and metadata can carry
   credentials. Never copy them into docs, commits or chat.

## Phase B: ask the solver to describe itself

5. Look for self-description: a help flag, a parameter dump, a schema, a
   defaults export. openCARP's `+Help` lists every parameter with a type;
   `+Help <name>` adds a description, the default, bounds and allowed values.
   **If the binary describes its own parameters, that is the catalog.** Build
   it from the binary and gate it with a drift test against the binary. No
   source scanning, no hand transcription.
6. Probe the self-description's edges and record which forms work. With
   openCARP, `+Help` on an indexed name works only with a concrete index
   (`stim[0].pulse.strength`), not with the listed template
   (`stim[Int].pulse.strength`), and `+Default +Save file` produced nothing.
   Failed probes are findings.
7. **Read defaults for the parameters that matter, and flag surprising ones.**
   openCARP's `num_stim` defaults to 2, so a case that omits it silently gets
   two stimuli. Silently inherited defaults were the worst failure in SINTEF's
   JutulGPT study. Any default that differs from what a reader would assume
   belongs in the log.

## Phase C: inventory the native examples

8. Find the tutorials or examples that ship with the solver. List every
   example's files in one pass. Do not sample a few.
9. **Classify each example by where its physics lives:** in native input files
   (config and mesh files a tool can read and patch) or in a script (a Python
   driver that builds arguments in code). omniD treats a native case as the
   pointer (tutorials-are-pointers), so file-native examples are candidates
   and script-built ones are not, unless their script's facts can be moved into
   files.
10. Read one minimal example end to end, script and config together, to learn
    the solver's idioms. Note the defects you find: openCARP's `00_simple/run.py`
    has a missing comma that silently fuses two arguments. Examples are not
    automatically correct.

## Phase D: the smallest real run, and the anatomy of its outputs

11. Build the smallest case that exercises the real path: generate the smallest
    mesh the native tools make, reuse a real example's config, and add only the
    arguments the script would have added. Record shell pitfalls (zsh globbing
    bracketed arguments) and units (openCARP's `mesher` takes sizes in cm and
    resolution in µm).
12. Time it. If it runs in seconds, real-binary tests are affordable in the
    native test tier. openCARP took 0.25 s.
13. **Take apart every output file:** names, formats, headers (use the solver's
    own inspection tools, such as `igbhead`), line counts against mesh size, and
    which file records the configuration that actually ran. openCARP writes
    `parameters.par`, which holds the supplied input, the command line, the git
    hash and every command-line override. That is effective-configuration
    provenance for free. Defaults still come from Phase B.

## Phase E: map the solver onto omniD's nouns

14. Fill the table:

    | omniD noun | question |
    |---|---|
    | native case | which files are the case? |
    | study key | how is one value addressed (`document:path`)? |
    | axis | which study values become several patches or command arguments? |
    | key validator | where does the catalog come from? |
    | value reader and comparator | how is a value read back, and when are two spellings equal? |
    | workflow steps | which commands, in which order? |
    | artifacts | which outputs, and where? |
    | environment | what must be supplied? |

    Every cell cites Phase A–D evidence.
15. Choose the first case. Prefer one that is **file-native and backed by an
    independent benchmark**, so the later cross-solver comparison has a
    reference that is not either solver's own output. For openCARP this is
    `03E_study_resolution` (the Niederer N-version benchmark), which cardiacFoam
    also has.

## Phase F: list what only the binary can settle, then settle each

16. Write each open question with the run that would settle it. Never fill a
    gap with an assumption, even a plausible one.
17. Settle questions one at a time. Record the command, the observed output and
    the conclusion in the solver's log, then promote the conclusion into the
    design (catalog, validator, record). A question that changes the design
    goes back to the owner.

**Refined 2026-09-25, while settling openCARP's F1–F7:**

18. **Probe the spellings a reader would try, not just the documented one.**
    For a boolean-like parameter, try `1 0 yes no true false on off 2`.
    openCARP accepts all of them with exit 0, but only `0` and `false` mean
    off. The failure mode is silent, so only an output difference shows it
    (here, whether APD files appear).
19. **When a probe fails, read why before drawing a conclusion.** Every first
    Flag probe exited 5. The cause was an unrelated cross-parameter bound
    (`spacedt = 3 is above the 2 maximum`), not the Flag. A failed probe
    settles nothing until its error is read.
20. **Settle a behavioural question by comparing outputs byte for byte.** F4
    (are the physics-region options needed?) was settled by `cmp` on `vm.igb`
    and the LAT file with and without them. "It ran both ways" would not have
    settled it.
21. **Check geometry against the independent reference, not the solver's
    wrapper.** F3 compared `mesher` point extents with the benchmark's
    20×7×3 mm slab and the stimulus cube's position, which carputils is not
    needed for.
22. **Check where relative paths resolve.** Run once from the case directory
    and once from elsewhere (F5). A staged clone moves the case, so this
    decides the working directory of every step.

## What this method produced for openCARP

See [`opencarp.md`](opencarp.md): the evidence log, the noun mapping, and the
open questions with their state.

