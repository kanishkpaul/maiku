# Testing and verification

## Available now

```sh
python3 scripts/check_repository.py
python3 -m unittest scripts/test_check_repository.py
python3 scripts/check_repository.py --commits BASE..HEAD
git diff --check
```

The repository check validates required documents, relative file links, and
foundation consistency, and accidentally tracked local planning. It checks local
Markdown links and HTML image/navigation targets without fetching external URLs.
The commit check rejects coauthor trailers, common
coding-agent signatures, and recognizable agent identities in new commits.
It does not rewrite or police historical commits. Local hook and CI checks are
guardrails, not proof that every conceivable attribution form is detected.

The preserved implementation was verified separately: 501 tests passed and
two skipped; lint, TypeScript, and frontend build passed. Physical-branch
targeted tests: 32 passed with fixtures. Those results are not tests of the new
architecture or present-day live hardware.

## Required when Rust packages land

Pin and install the toolchain. Make these commands work with a committed lockfile:

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-features --locked
cargo test --doc --workspace --all-features --locked
```

Also test the minimal profile, default profile, and each optional feature's
supported combinations. `--all-features` does not prove that disabling works.
Exact package/profile commands are added with the first workspace manifest.
Set up dependency/license checks and meaningful cross-platform CI as packages land.

## Contracts to exercise

| Boundary | Required cases |
| --- | --- |
| Identity | Cross-language canonical vectors, ordering, distinct positions, revisions, collision-safe projection names |
| Authority | Unknown caller, attenuation widening, expiry during approval, revoked parent, wrong audience, artifact denial |
| Discovery | Multiple interfaces, equal schema/different effects, inaccessible endpoint, stale contract, executable binding |
| Semantics | Equal shape/different normalization, wrong units, ambiguous reset, stale state, explicit tested conversion |
| Evidence | Declaration vs observation, limited coverage, failed/inconclusive probe, changed revision, private payload handling |
| Adaptation | Proposal cannot activate itself, forbidden probe, conflicting source, reviewed repair, stale evidence |
| Adapter | Valid descriptor, input/output schema, one terminal event, cancellation, cleanup, timeout, failure |
| Worker | Protocol mismatch, oversized/malformed frames, crash, stdout pollution, cancel escalation, uncertain write |
| Durability | Restart before/after dispatch, duplicate events/answers, pending approval recovery, retention gaps |
| Composition | Nesting, fan-out/fan-in, missing dependency, transformation contract, budgets, interrupted work |
| Extensions | Install/disable/drain/remove, unresolved references, optional dependency absent, preserved history |
| Artifacts | Digest/path validation, atomic writes, concurrent writers, byte limits, reference retention, transfer integrity |
| UI/API | Real host flow, keyboard/focus, reconnect, refusal, human response, credential/authority boundaries |

Use shared conformance suites for each adapter/discoverer/worker. Validate actual
results, not merely event class names. Run independent MCP/A2A clients and servers
for the advertised version matrix. Self-round-trips are useful but insufficient.

Keep deterministic fixtures in ordinary CI. Run live model/device scenarios
explicitly with their prerequisites, permission, configuration, and observed
outcomes recorded. Never require paid API access for basic conformance.

## Performance and changes

Use [PERFORMANCE.md](PERFORMANCE.md) for reproducible budgets. Run affected tests
as code changes, then the required release gates. Repeat or broaden only when
new changes/failures justify it. Documentation-only changes need repository
checks, not an invented runtime test result.
