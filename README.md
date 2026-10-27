# maiku

*the universal kawaii adapter (0w0/)*

> **Under construction — Rust rebuild in progress.** This branch contains the
> project foundation and repository tooling. There is no runnable Rust runtime,
> CLI, or new app yet.

Maiku is being built as a free, open-source, local-first adapter for accessible
systems. Its goal is a common operational language through which models, tools,
services, devices, and interfaces can cooperate while keeping their native meaning
and leaving people in control.

A neural network should remain a model. A fridge should expose temperatures and
controls. A dashboard should expose views, filters, and actions. The shared unit
is an **interaction contract**: what can be observed or requested, what it requires,
what may happen, and who is allowed to do it.

Read [the thesis](docs/THESIS.md) for the full direction.

## Current state

`main` contains the architecture, design contracts, coding standards, shared
instructions for coding assistants, and repository checks. These establish the
foundation; they do not implement the system described above.

Automatic adaptation, semantic compatibility checks, verification reports,
durable execution, connectors, and the workspace app remain unimplemented in the
rebuild. There is no installer or product quickstart yet.

The previous implementation is preserved on
[`old`](https://github.com/kanishkpaul/maiku/tree/old), with its own run instructions.
New development belongs on `main`. Detailed build planning stays local.

## Direction

- **Preserve meaning.** Contracts must carry known requirements and expose unknowns.
  Matching input shapes alone does not establish compatibility.
- **Adapt from evidence.** Interfaces, signatures, source, protocols, documentation,
  and visible controls can support a proposed binding. Proposals require checks.
- **Verify within limits.** Test permitted behavior and retain its conditions,
  failures, and limits. Changes require affected assumptions to be checked again.
- **Keep authority explicit.** Discovery and approval cannot silently grant access.
  People control activation, data sharing, and consequential actions.

The accepted stack is Rust for the core and CLI, Tokio, SQLite, optional language
workers, a Svelte/TypeScript interface, and an optional Tauri shell. See the
[stack decision](docs/decisions/0001-stack.md) for the tradeoffs.
Local operation must work without an account or hosted control plane.

## Work on the foundation

Read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), and
[the coding standards](docs/CODING_STYLE.md) before editing.

```sh
python3 scripts/check_repository.py
python3 -m unittest scripts/test_check_repository.py
git diff --check
```

These check repository documents and tooling only. Python is currently used for
those checks; it is not a dependency of the planned native base runtime.

[Current status](docs/STATUS.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Interaction contract](docs/PROTOCOL.md) · [Extensions](docs/EXTENSIONS.md) ·
[Testing](docs/TESTING.md) · [Security](SECURITY.md)

The full product README, real demo, and installation guide will follow a working,
verified implementation.

## License

[Apache-2.0](LICENSE). Third-party integrations, model weights, and external
services retain their own licenses, terms, and costs.
