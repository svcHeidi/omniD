# Core expert cross-review

Date: 2026-09-22. Role: maintainer. Independent bounded review of the core
lead report and consolidated implementation roadmap. Read the repository
router, guidance manifest, `CLAUDE.md`, and maintainer guidance. No production
files changed and no broad suite rerun.

## Decision

The core lead's two requested reproductions withstand independent testing.
The consolidated Phase 2 correction is substantially better than the original
plan and preserves the right responsibility boundaries. Keep it, with the
small contract clarifications below before implementation.

## Confirmed claims and limits

1. **Hash-seed-dependent provider ordering: confirmed.** A provider `org.a`
   requiring independent `org.b` and `org.c` changes ordering across fresh
   Python 3.11 processes. Seeds 0–4 and 6 yielded `org.c, org.b, org.a`; seeds
   5 and 7 yielded `org.b, org.c, org.a`. Input order was the same throughout.
   This independently reproduces the lead's seed 0/5 example.
   `order_providers` creates `set(requires)` before `TopologicalSorter`, so
   sorting the outer dictionary does not establish a total deterministic
   order. This is a generic defect; this fixture is not evidence that today's
   shipped two-provider stacks already have a changed scientific result.

2. **Duplicate IDs silently collapse: confirmed.** Two objects with ID `same`
   return a one-element stack. Forward input retains the second object;
   reversed input retains the first. `driver_context` also constructs
   `source_by_id` before ordering; duplicate rejection must happen before
   either identity-to-object or identity-to-source information is discarded.
   Report both origins in the public error. Rejecting duplicates does not
   require changing the entire plugin architecture.

3. **Original Phase 2 serialization/mutability defects: confirmed.** Executing
   the exact proposed dataclass block yielded equal `to_json()` output for
   synthesis operations with values `{'nested': [1]}` and `{'nested': [2]}`.
   Mutating the first input dictionary afterwards changed the frozen
   operation's value to `{'nested': [1, 99]}`. These are proposal defects,
   not failures of an implemented new writer.

4. **Existing recovery provides useful mechanisms, not a drop-in lifecycle.**
   Source inspection confirms fsynced per-file replacement, durable
   before-image manifests, absent-file records, modes, rollback baseline
   verification, and transaction compare-and-swap checks. However,
   `_require_transaction_ownership` requires both a case lease and an attempt
   lease. New-case materialization can precede any attempt. The roadmap must
   retain the core lead's warning against inventing a fake attempt merely to
   call this API.

5. **The current stack digest is insufficient as the sole plan binding.**
   `provider_identity.build_stack_identity` explicitly documents that most
   capabilities do not contribute content hashes and editable changes without
   a version bump may be invisible. It hashes provider IDs, versions, provider
   digests and selected resolution information, not every relevant contract
   implementation. Reusing identity types is reasonable; claiming they alone
   bind renderer/validator semantics would be too strong. This is a documented
   limitation found in source, not a newly reproduced end-to-end stale plan.

The consolidated report renumbers/combines findings: its C1 includes lead C1
and C6; its C2 is lead C7; its C3 is lead C5. Preserve this mapping in references
or use names rather than bare IDs to avoid assigning the wrong work package.

## Narrow changes needed in the roadmap

- **Ordering versus precedence:** define deterministic tie-breaking separately
  from semantic precedence. Sorting unrelated providers makes order repeatable
  but does not establish that the lexically last provider is more specific.
  A singleton conflict between unrelated providers needs an explicit rule or
  refusal. Bump the composition rule version if resolution semantics change.
- **Case ownership before attempts:** explicitly require a case-transaction
  lifecycle that exists before execution attempts. Remediation can be a client
  with its stronger attempt binding. Name the authoritative transaction head,
  legal states, recovery owner, and recovery rule; avoid two competing heads
  for the same input mutation. Once dispatch begins, case ownership must cover
  the check-to-launch interval so an intervening framework write cannot change
  the validated inputs. Document that outside writers do not honor these
  leases and are outside the claimed concurrency guarantee.
- **Plan read set and canonical identity:** step 4 should name a canonical
  serialization and digest algorithm/schema, strict supported values (including
  finite numerical values), and an explicit read set as well as a write set.
  Bind includes, source templates and other dependencies used to render or
  validate, not only destination before-images. Preserve missing-file
  preconditions. Recheck the declared read set/build/contract bindings under
  the commit lease and refuse unresolved required dependencies. Do not use the
  existing stack digest as the only renderer/validator implementation binding.
- **Commit receipt and retries:** define a durable result binding plan digest,
  transaction ID/revision, committed target digests, validation evidence and
  eventual execution attempt. Specify how a caller reconnects after an unknown
  commit outcome and how duplicate/replayed commits behave. A successful write
  receipt is separate from a successful simulation result. Recovery must remain
  blocking if rollback is incomplete; do not mark the transaction clean merely
  because an exception handler returned.
- **Failure tests:** retain the roadmap's interruption tests and explicitly
  include crashes at journal persistence/commit/receipt boundaries, retry after
  lost response, changed external read dependency, and preservation of the
  pre-attempt lifecycle. A monkeypatched render error only establishes that
  rendering failed before commit, not durable recovery.

These clarify G1/G2 acceptance criteria. They do not justify additional generic
service layers or a new standalone transaction framework.

## Reproduction commands

Run from the repository root with the existing all-package environment:

```bash
/tmp/od311/bin/python - <<'PY'
import os
import subprocess
probe = '''
from types import SimpleNamespace
from omnidriver.core.provider_stack import order_providers
class Provider:
    def __init__(self, ident, req=(), marker=None):
        self.plugin_id, self.req, self.marker = ident, req, marker
    def get_profile(self):
        return SimpleNamespace(requires=self.req)
a = Provider('org.a', ('org.b', 'org.c'))
b = Provider('org.b')
c = Provider('org.c')
print([p.plugin_id for p in order_providers([c, a, b])])
'''
for seed in range(8):
    result = subprocess.run(
        ['/tmp/od311/bin/python', '-c', probe],
        env={**os.environ, 'PYTHONHASHSEED': str(seed)},
        check=True, capture_output=True, text=True,
    )
    print(seed, result.stdout.strip())
exec(probe.split('a = Provider')[0])
first = Provider('same', marker='first')
second = Provider('same', marker='second')
for providers in ([first, second], [second, first]):
    print([(p.plugin_id, p.marker) for p in order_providers(providers)])
PY
```

```bash
/tmp/od311/bin/python - <<'PY'
from pathlib import Path
from types import ModuleType
import sys
text = Path('docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md').read_text()
start = text.index('from dataclasses import dataclass, field', text.index('## Task 1'))
end = text.index('\n```', start)
module = ModuleType('phase2_review_probe')
sys.modules[module.__name__] = module
exec(text[start:end], module.__dict__)
payload = {'nested': [1]}
a = module.CaseWriteOperation('synthesize', 'system/probe', None, payload, 'org.probe')
b = module.CaseWriteOperation('synthesize', 'system/probe', None, {'nested': [2]}, 'org.probe')
print('distinct values same JSON:', a.to_json() == b.to_json())
payload['nested'].append(99)
print('frozen proposal value changed:', a.value)
PY
```

Both commands were run successfully. Expected final lines of the second probe:
`distinct values same JSON: True` and
`frozen proposal value changed: {'nested': [1, 99]}`.

Source evidence: `core/provider_stack.py` (`order_providers`, `_first_non_none`,
`resolutions`); `core/plugin_interface.py` (`driver_context`);
`core/provider_identity.py` (`build_stack_identity`); and
`core/runtime/remediation_transaction.py` (`_require_transaction_ownership`,
`_current_transition`, `_snapshot_paths`, `_validated_manifest`,
`restore_remediation_transaction`, `baseline_is_restored`). Paths are beneath
`packages/omnidriver/src/omnidriver/`.
