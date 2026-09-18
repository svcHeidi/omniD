# Provider integration contract

This repository is the source of truth for guidance. A provider-specific
wrapper is responsible only for delivering it; it must not fork or paraphrase
the role instructions.

## Launcher behavior

For every integrated task, the launcher must:

1. classify the requested work as builder, runner, evaluator, or maintainer;
2. resolve `agent-handbook/guidance-manifest.yaml` from the checked-out OmniD
   revision;
3. load `common` plus that role's `required` files, failing before work if a
   path is missing;
4. inject their exact contents into the provider's task context before the
   agent can plan or call tools;
5. record the repository revision, role, paths, and SHA-256 hashes in the task
   record; and
6. expose optional files only when the task calls for them.

The launcher may use a provider-native skill, system prompt, repository
instruction file, or API context field. Those are delivery mechanisms, not
separate authorities.

## Limits

Injected guidance proves what the agent received, not that it understood or
followed it. Tool permissions, transaction checks, and the evaluator's
held-out results remain the enforcement and outcome evidence.

An unconstrained external chat with no launcher cannot be required to read
these files. In that setting, attach the resolved common and role documents to
the task explicitly and label the result as manually guided.
