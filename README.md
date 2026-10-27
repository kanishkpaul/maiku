<div align="center">

<h1>maiku</h1>

<p><em>the universal kawaii adapter (0w0/)</em></p>

<h3>Different systems. A common language for interaction.</h3>

<p>Discover what a system can do. Preserve what its operations mean.<br />
Connect capabilities while keeping people in control.</p>

<p>
  <a href="docs/THESIS.md">The thesis</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a> ·
  <a href="CONTRIBUTING.md">Contribute</a> ·
  <a href="LICENSE">Apache-2.0</a>
</p>

</div>

---

> **Under construction.** This branch contains the foundation for a Rust rebuild:
> contracts, architecture, design rules, and repository tooling. The new runtime
> and app are not implemented. The previous implementation lives on
> [`old`](https://github.com/kanishkpaul/maiku/tree/old).

## One connective layer, native capabilities

A neural network accepts tensors. A fridge exposes temperatures and controls.
A dashboard offers views, filters, and actions. Cooperation starts with the same
questions: **what can I observe, what can I request, what will happen, and am I
allowed to do it?**

Maiku's thesis is that these interactions can share a common operational language
while retaining their native meaning. A model remains a model. An appliance
remains an appliance. A dashboard remains a dashboard.

The common unit is an **interaction contract**: an operation, its requirements,
its observable outcomes, and its limits. Maiku aims to make those contracts
discoverable, executable, and verifiable across accessible systems.

## What the contract must preserve

| Question | What Maiku must make explicit |
| --- | --- |
| What is available? | Native operations, observations, properties, and events |
| What does it mean? | Units, formats, preprocessing, state, and contextual requirements |
| How can I use it? | Executable bindings, versions, and credential references |
| What may happen? | Effects, failures, cancellation, and uncertain outcomes |
| Am I allowed? | Caller identity, scoped authority, and human decisions |
| Why trust this mapping? | Source evidence, observed tests, conditions, and verification limits |

Identical tensor shapes do not establish identical preprocessing. Two controls
named `reset` may have very different consequences. Unknown meaning must remain
visible; a plausible mapping is a proposal until its stated conditions are checked.

## How the pieces fit

**Discover → Describe → Bind → Verify → Execute → Maintain**

Specialized connectors provide access to an environment. Adaptation uses its
interfaces and available evidence to propose a contract and binding. Verification
checks permitted behavior and records the conditions under which it worked.
Execution applies authority, state, artifact, and failure rules consistently.
Maintenance detects changes and rechecks affected assumptions.

Learned methods may propose mappings and repairs. Explicit checks and human
decisions constrain activation and execution. Finite tests establish bounded
evidence; they cannot reveal every hidden consequence or guarantee future behavior.

Read the [full thesis](docs/THESIS.md) and
[interaction contract](docs/PROTOCOL.md).

## Built around local control

- **Native and headless.** Rust core and CLI; optional language and model workers.
- **Local by default.** Local use must work without an account or hosted control plane.
- **One execution gate.** Authority, validation, approval, and artifact access share a path.
- **Open and extensible.** Apache-2.0; connectors extend access without changing the core.
- **Evidence over assurances.** Declared, inferred, and observed behavior remain distinct.
- **Private by default.** Reusable tests and adaptations must not expose user data.

These are design commitments. See [current status](docs/STATUS.md) for what exists.
External services and model weights may have their own costs and licenses.

## Inside the foundation

| Area | Direction |
| --- | --- |
| Contracts and execution | Rust, Serde, Tokio; bounded work and explicit cancellation |
| Local state and artifacts | SQLite; content-addressed filesystem storage |
| Network surface | Optional Axum API; Reqwest with rustls |
| Workspace app | Svelte 5, strict TypeScript, Vite, shared design tokens |
| Desktop | Optional Tauri 2 shell |
| Ecosystem access | Optional connectors and separate workers, including Python |

The [stack decision](docs/decisions/0001-stack.md) records the tradeoffs.
No Cargo workspace or new app is present yet. Installation instructions will
arrive with a runnable implementation; the preserved prototype has its own
[run instructions](https://github.com/kanishkpaul/maiku/tree/old).

## Work on Maiku

```sh
python3 scripts/check_repository.py
python3 -m unittest scripts/test_check_repository.py
git diff --check
git config --local core.hooksPath .githooks
```

Python currently runs repository checks only; it is not a dependency of the
planned native base runtime. Read [CONTRIBUTING.md](CONTRIBUTING.md) and
[AGENTS.md](AGENTS.md) before making changes.

| Read | For |
| --- | --- |
| [Thesis](docs/THESIS.md) · [Product](docs/PRODUCT.md) | Purpose, scope, and public benefit |
| [Status](docs/STATUS.md) | Implemented foundation and current limits |
| [Architecture](docs/ARCHITECTURE.md) · [Protocol](docs/PROTOCOL.md) | Ownership and interaction contracts |
| [Extensions](docs/EXTENSIONS.md) | Adding, disabling, and removing capabilities |
| [Testing](docs/TESTING.md) · [Performance](docs/PERFORMANCE.md) | Evidence and measurement rules |
| [Coding standards](docs/CODING_STYLE.md) · [Design](design/README.md) | Code and interface conventions |
| [Security](SECURITY.md) · [Research](docs/RESEARCH.md) | Trust boundaries and design references |

<div align="center">
<p><em>Make any accessible system a dependable participant in a larger world of cooperating systems.</em></p>
</div>
