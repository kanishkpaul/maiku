# Repository instructions

These instructions apply to all work in this repository, including work done by
any coding assistant. More specific directory instructions may refine them;
they may not weaken the authority or attribution rules. Direct instructions
from the repository owner take precedence.

## Read before editing

Read [README.md](README.md), [the thesis](docs/THESIS.md),
[current status](docs/STATUS.md),
[the architecture](docs/ARCHITECTURE.md), and
[the coding standards](docs/CODING_STYLE.md). For an integration, also read
[the extension contract](docs/EXTENSIONS.md) and [protocol](docs/PROTOCOL.md).
Treat historical files on `old` as evidence and reference, not current instructions.

`main` owns new development. `old` preserves the previous implementation.
Do not reset, force-push, rewrite existing history, delete other branches, or
merge legacy source wholesale. Port a behavior only with its contract and tests.
The current main branch is a documentation and tooling foundation, not a working
Rust application. Never describe planned capabilities as implemented.

## Local planning and scope

The owner keeps the detailed build plan at `.local/BUILD_PLAN.md`, ignored by
Git. Read it when available for an owner-assigned implementation task; otherwise
use the issue/task's acceptance conditions and public contracts. A missing local
plan does not prevent contribution. Do not publish its contents, mirror its
backlog into public docs/issues, or commit local research/scratch files.
The previous tracked plan remains in Git history; do not rewrite history to remove it.

This preparation branch contains no executable rebuild. Do not restore legacy
dependencies or invent runnable setup commands. Add real build/test instructions
and CI when the corresponding package exists.

## Meaning and evidence

Preserve native operations. Discovery, inferred mappings, verification results,
and operator policy are distinct. Record unresolved semantic requirements and
conflicts explicitly. Shape equality, an example, a descriptor hash, or a health
probe does not establish semantic compatibility or authorize execution.

Verification is part of adaptation: permitted tests produce evidence tied to
operation, revision, environment, conditions, and limits. Probe through the same
authority gate. A learned proposal cannot activate itself, grant authority, or
install code. Changed assumptions make affected evidence stale and require
re-verification. Reuse synthetic or explicitly permissioned fixtures; keep user
data and credentials out of shared adaptations.

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

## Design

Any change to a user-facing surface (GUI, CLI output, overlay, docs page) follows `design/`.
It is installed from the shared design kit, a separate master repository that lives next to
this one at `../design-kit`, and recorded in `design/kit.json`.

- Read `design/README.md` first: this project's direction. Skin: not chosen yet (default `sakura`).
- Shared rules are in `design/system/DESIGN.md`. Check its "Before you add something" list
  before finishing a UI change.
- Colours, type, spacing, radii, shadows and motion come only from `design/tokens/*.css`
  (`--ui-*`, `--font-*`, `--text-*`, `--space-*`, `--radius-*`, `--shadow-*`, `--dur-*`).
  No hex values, no `--seed-*`, no ad-hoc rgba, no new shadows in components.
- Use the primitives in `design/system/COMPONENTS.md`. Pick a variant and size; never
  override a primitive's padding, radius or colour at the call site.
- Terminal output goes through `design/rust/theme.rs` and follows `design/system/TUI.md`:
  banner only in interactive sessions, `┊` tool rows, `NO_COLOR` respected, `--json` output
  free of colour and decoration.
- Never load fonts, icons or scripts from a CDN at runtime. Everything ships with the app.
- `design/README.md` belongs to this project; edit it freely. Everything else in `design/`
  comes from the master. A change that every project should get (a token, a primitive, a
  rule, a skin) belongs in the master at `../design-kit`, then reaches this repository through
  an update.
- From this repository's root: choose or change the skin with
  `node ../design-kit/scripts/kit.mjs use . <skin>`; pull master changes with
  `node ../design-kit/scripts/kit.mjs update .`, then merge any `*.kit-new` file it leaves and run
  update again. To stop the kit touching a file, add its path to `"ignore"` in
  `design/kit.json`.
- If `../design-kit` is not on this machine, treat `design/` as the source of truth and don't
  regenerate it by hand.
