# maiku

*the universal kawaii adapter (0w0/)*

> 🏗️ **Under construction.** Maiku is being rebuilt in Rust. The new runtime
> and app are not implemented yet; this branch contains the foundation and build plan.

Bring models, tools, services, people, and physical systems into one composable
workspace. Keep their native capabilities. Make their interfaces, authority,
artifacts, and execution understandable.

Maiku is free and open source under [Apache-2.0](LICENSE). Local use must
work without an account, subscription, or hosted control plane. Optional external
services can have their own costs; the app must show those before use.

## Current state

`main` is the rebuild foundation: decisions, contracts, a build plan, contributor
instructions, and repository checks. The Rust runtime and new app are not
implemented yet. Proposed performance budgets are targets, not measurements.

The complete previous implementation is on
[`old`](https://github.com/kanishkpaul/maiku/tree/old). Its README explains how to
run it. The transition preserves Git history and does not delete other branches.

The next implementation milestone is a native execution path with one command
participant, one human participant, permissions, approval, and cancellation. Follow
the [build plan](docs/BUILD_PLAN.md) for progress and acceptance gates.

## Planned stack

| Area | Decision |
| --- | --- |
| Core and CLI | Rust, stable toolchain, Cargo workspace |
| Async execution | Tokio with bounded queues and explicit cancellation |
| Local persistence | SQLite through rusqlite; filesystem artifact store |
| HTTP interface | Axum; Reqwest with rustls for outbound HTTP |
| Contracts | Serde types, versioned JSON, JSON Schema |
| Web app | Svelte 5, strict TypeScript, Vite, plain CSS |
| Desktop distribution | Optional Tauri 2 shell around the same app |
| ML and language-specific integrations | Optional separate workers, including Python |

See [the stack decision](docs/decisions/0001-stack.md) for comparisons and
tradeoffs. The planned headless base installation will not require a Python
interpreter, Node server, model weights, or desktop webview.

## Start here

- [Product direction](docs/PRODUCT.md)
- [Build plan and acceptance gates](docs/BUILD_PLAN.md)
- [Architecture and module ownership](docs/ARCHITECTURE.md)
- [Participant and worker contracts](docs/PROTOCOL.md)
- [Adding and removing abilities](docs/EXTENSIONS.md)
- [Coding and commenting standards](docs/CODING_STYLE.md)
- [Testing](docs/TESTING.md) and [performance](docs/PERFORMANCE.md)
- [Research and primary sources](docs/RESEARCH.md)
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), and
  [repository instructions](AGENTS.md)

## Check this foundation

```sh
python3 scripts/check_repository.py
git config --local core.hooksPath .githooks
```

Python is used only for the current development check, not the planned product
runtime. Build commands will be added when the corresponding packages exist.
Installation and quickstart instructions for the rebuild will be added when a
runnable implementation is available. To try the previous implementation, use
the instructions on [`old`](https://github.com/kanishkpaul/maiku/tree/old).
