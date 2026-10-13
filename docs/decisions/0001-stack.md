# 0001: Native core with optional workers and a compiled web UI

Status: accepted for the rebuild on 2026-10-13.

## Problem

Maiku needs broad interoperability, a responsive app, controlled concurrency,
durable local work, predictable resource use, and an installation that does not
inherit the dependencies of every model or ecosystem it can use.

## Alternatives

| Option | Strengths | Cost for this project |
| --- | --- | --- |
| Python core | Direct ML integration; existing prototype | Interpreter and environment management in the base runtime; blocking work and heavy packages need separation anyway |
| Go core | Simple deployment; strong networking and concurrency | Garbage collection adds a memory/CPU tradeoff; less direct control of allocation in the runtime |
| Rust core | Native performance; ownership; explicit resource lifetimes; rich networking ecosystem | Longer builds and a steeper contributor learning curve; abstractions need restraint |
| C++ or Zig core | Native execution and allocation control | More manual lifetime/safety responsibility for untrusted interfaces and concurrent orchestration |
| TypeScript/Node core | Convenient app and protocol development | JS runtime in the base installation; heavy ML/device work still needs workers |

Choose Rust for the core. This is the best fit for the stated constraints, not
a measured claim that Rust beats every alternative on every workload. Keep
Python and other ecosystems available through separate, optional workers.

## Decision

| Component | Stack and reason |
| --- | --- |
| Domain contracts | Rust enums/newtypes + Serde + JSON Schema; explicit state and versioned boundaries |
| Execution | Tokio; bounded channels, tracked tasks, deadlines, cancellation |
| CLI | Clap; the same application services used by HTTP |
| Persistence | SQLite + rusqlite behind a dedicated bounded storage worker; small local deployment |
| Artifacts | Filesystem blobs addressed by SHA-256; streaming I/O; metadata in SQLite |
| HTTP | Axum; static app assets and versioned local API; SSE for resumable events |
| HTTP clients | Reqwest + rustls, optional within the owning adapter |
| Diagnostics | tracing; OpenTelemetry export as an optional integration |
| UI | Svelte 5 + strict TypeScript + Vite + plain CSS; compiled components, no production Node server |
| Desktop | Tauri 2, optional; native system webview, same UI and host services |
| ML | Separate worker processes; Python/Torch/HF environments installed only when selected |
| Protocol SDKs | Reuse maintained official SDKs where compatible; isolate them behind optional adapter packages |

React is viable and familiar from the prototype. Svelte is chosen for the new
small app and its compiled component model, not because a comparable Maiku UI
has been benchmarked yet. Avoid SvelteKit SSR, Electron, a mandatory Python
daemon, distributed storage, or a message broker in the base product.

Pin actual toolchain and package versions when the first packages land. Use
stable Rust, edition 2024, and Cargo resolver 3, with a documented MSRV and a
committed application lockfile. Do not select a nightly-only dependency without
a decision. Do not add every package in this table on day one.

## Consequences

The smallest useful installation is a headless native binary and local workspace.
UI assets, desktop shell, providers, workers, model weights, and telemetry are
separate costs. A webview and model memory must be measured separately from the
core, and process isolation must not be advertised as sandboxing.

rusqlite is synchronous: the scheduler must not call it or filesystem operations
on async executor threads. Storage work uses a bounded queue and explicit error
propagation. Adopt another backend only after local measurements justify it.

Native Rust dynamic-library plugins do not provide a stable extension ABI.
Use an object-safe internal adapter interface for built-ins and a versioned
process protocol for external extensions. Optional Cargo features control
packaging; runtime configuration controls enablement and lifecycle.

## Evidence

- [Rust performance and ownership](https://rust-lang.org/)
- [Go GC tradeoffs](https://go.dev/doc/gc-guide)
- [Zig overview](https://ziglang.org/learn/overview/)
- [Tokio bounded channels](https://docs.rs/tokio/latest/tokio/sync/mpsc/index.html)
- [SQLite deployment fit](https://www.sqlite.org/whentouse.html)
- [Svelte compiled components](https://svelte.dev/docs/svelte/overview)
- [Tauri architecture](https://tauri.app/concept/architecture/)
- [Cargo features and feature unification](https://doc.rust-lang.org/cargo/reference/features.html)

See [PERFORMANCE.md](../PERFORMANCE.md) for proposed budgets and measurement gates.
