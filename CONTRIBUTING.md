# Contributing

Maiku is being rebuilt as a free, local-first interoperability system. Start with
[the thesis](docs/THESIS.md) and [current status](docs/STATUS.md). Scope a
contribution through a concrete issue or task with observable acceptance conditions.
Read [AGENTS.md](AGENTS.md) and
[the coding standards](docs/CODING_STYLE.md) first.

Detailed owner planning stays local. No private file, model download, hosted
account, or paid API is needed for the repository checks. Architecture and
protocol documents describe target behavior; the Rust rebuild is not executable yet.

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
python3 -m unittest scripts/test_check_repository.py
git diff --check
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
- Semantic unknowns and conflicts are explicit; declarations and observed evidence differ.
- Verification probes use explicit authority and record their conditions and limits.
- Local planning, scratch material, secrets, and private user data stay out of changes.

Review descriptions should explain the problem, resulting behavior, validation,
and any material limitation. Avoid a transcript of the implementation process.
