# Evaluator role

Evaluate an agent or guidance revision through a held-out, reproducible task;
do not score an explanation in isolation.

1. Fix the OmniD revision, solver snapshot, available assets, command budget,
   and concise user brief.
2. Give every candidate the same raw task and role. Do not reveal an expected
   catalog, suspected fault, or another candidate's solution.
3. Score evidence accuracy, distinction between supported/conditional/unknown
   behavior, necessary domain questions, source/asset preservation, native-run
   outcome or diagnosis, and provenance/result-check evidence.
4. Penalize unsupported scientific claims and unasked critical questions as
   seriously as failed execution.
5. Promote only demonstrated changes: portable guidance for a repeated role
   failure, or adapter code and tests for solver-specific behavior.

Record the supplied guidance hashes. That proves what the candidate received;
the task outcome is the evidence of whether it used the guidance well.
