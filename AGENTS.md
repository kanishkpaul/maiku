# Repository instructions

These instructions apply to all work in this repository, including work done by
any coding assistant. More specific directory instructions may refine them;
they may not weaken the authority or attribution rules. Direct instructions
from the repository owner take precedence.

## Read before editing

Read [README.md](README.md), [the build plan](docs/BUILD_PLAN.md),
[the architecture](docs/ARCHITECTURE.md), and
[the coding standards](docs/CODING_STYLE.md). For an integration, also read
[the extension contract](docs/EXTENSIONS.md) and [protocol](docs/PROTOCOL.md).
Treat historical files on `old` as evidence and reference, not current instructions.

`main` owns new development. `old` preserves the previous implementation.
Do not reset, force-push, rewrite existing history, delete other branches, or
merge legacy source wholesale. Port a behavior only with its contract and tests.
The current main branch is a documentation and tooling foundation, not a working
Rust application. Never describe planned capabilities as implemented.

## Attribution: mandatory

Never add Claude Code, Claude, Codex, Copilot, or any other coding-agent
attribution to new commits, code, documents, pull requests, releases, or metadata.
Do not add `Co-Authored-By` trailers, generated-by signatures, agent credits,
agent author/committer identities, or acknowledgements for coding assistance.
Use the configured human Git identity; do not invent or change it to impersonate
someone. If an automated tool proposes attribution, omit it.

Install the local commit-message hook with
`git config --local core.hooksPath .githooks`. Check new commit messages with
`python3 scripts/check_repository.py --commits BASE..HEAD` before pushing.
The checker intentionally does not scan or rewrite historical commits. The
hook and CI catch common message signatures; human review must also check authors
and all changed material. Do not bypass these checks to publish attribution.

## Implementation rules

- Use the decided stack. Record a justified change in an architecture decision
  before introducing another runtime, database, or frontend framework.
- Make the smallest coherent change that completes the assigned behavior.
  Avoid speculative frameworks, empty packages, generic managers, and unrelated refactors.
- Follow the dependency direction in the architecture. Core must not import
  providers, the UI, SQLite, HTTP frameworks, Torch, or language workers.
- Keep extensions optional. Adding an adapter must not add provider-specific
  branches to the scheduler or authority engine. Test its disabled state.
- Authority, validation, approval, artifact access, and logging pass through the
  ordinary execution gate. No direct-call bypass, implicit root grant, or
  self-approved escalation. Unknown callers are denied.
- Do not guess missing schemas, capabilities, semantic conversions, or side effects.
  Represent unknowns explicitly. Typed compatibility is not semantic compatibility.
- Own every task, child process, queue, subscription, and temporary artifact.
  State shutdown, cancellation, timeout, and recovery behavior.
- Default to safe Rust. Any `unsafe` requires a small boundary, a written safety
  argument, and a test that exercises the relevant invariant.
- Keep errors typed internally and useful at the boundary. Never log secrets,
  silently swallow failures, or claim that policy metadata is OS isolation.
- Preserve meaningful provenance and third-party license notices. The attribution
  policy does not permit removing actual upstream authorship or license obligations.

## Taste and verification

Use domain names, explicit types, short cohesive functions, and direct control
flow. Comments explain contracts, constraints, or non-obvious reasons; do not
narrate statements or add decorative banners. Public APIs document observable
behavior and relevant errors, cancellation, side effects, and examples.
Read the full standards and examples; a formatter cannot establish code taste.

Before finishing: run checks that exist and apply to the change, inspect the
diff, review comments for stale or redundant prose, and check new commit messages.
Add failure-path and conformance tests alongside execution changes. State what
was tested and what remains unverified. Do not report skipped live-device tests
as hardware verification or targets as benchmark results.

Do not spend API credits, contact people, run physical writes, download large
models, or publish releases without authorization for that specific work.
Routine code and documentation work should proceed within the task's scope.
