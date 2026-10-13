# Contributing

Maiku is being rebuilt as a free, local-first composition workspace. The first
contribution should close a specific acceptance gate in
[the build plan](docs/BUILD_PLAN.md). Read [AGENTS.md](AGENTS.md) and
[the coding standards](docs/CODING_STYLE.md) first.

## Make a change

1. Identify the owning module and observable behavior.
2. Describe inputs, outputs, permissions, failure cases, and the proof of completion.
3. Implement the smallest complete slice. Include applicable conformance tests.
4. Run repository checks and the package checks that exist.
5. Review the diff for dependency leakage, unnecessary abstraction, stale comments,
   attribution, and misleading claims.
6. Commit with a short lowercase area prefix, for example
   `runtime: reject expired grants before dispatch`.

Use short-lived branches for review when appropriate; accepted new development
lands on `main`. Do not develop the new runtime on `old`.
An architectural change needs a short decision file in `docs/decisions/`
explaining the problem, alternatives, decision, and consequences.

## Checks available now

```sh
git config --local core.hooksPath .githooks
python3 scripts/check_repository.py
python3 scripts/check_repository.py --commits BASE..HEAD
```

Replace `BASE` with the actual integration base. Do not run a history-wide
attribution cleanup. New commits must use the configured human identity and
contain no coauthor trailers or coding-agent signatures.

Rust and UI check commands in [TESTING.md](docs/TESTING.md) are planned until
their packages exist. Each package must ship its real setup and check commands
when introduced. There is no blanket percentage-coverage target; test contracts
and failure paths that matter.

## Review checklist

- The behavior and affected module are clear.
- The core remains independent of optional integrations and presentation.
- New work uses the same authority and artifact gates.
- Disabling the feature does not break unrelated work.
- Error, cancellation, recovery, and version behavior are tested where applicable.
- Public contracts and unusual invariants are documented without narration.
- Claimed measurements include the workload and environment.
- New commits and changed material contain no coding-agent attribution.
- Third-party notices are preserved.

Review descriptions should explain the problem, resulting behavior, validation,
and any material limitation. Avoid a transcript of the implementation process.
