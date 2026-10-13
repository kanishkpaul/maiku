# Performance and footprint

Rust is a stack choice, not a benchmark result. Measure the actual runtime and
publish hardware, OS, build profile, enabled features, workload, sample count,
and variability. Keep model, worker, browser, and desktop memory separate.

## Initial targets

These are proposed budgets for the first useful release. They are unmeasured
and may be revised by an explicit decision with evidence.

| Metric | Target | Measurement boundary |
| --- | --- | --- |
| Stripped headless executable | <= 20 MiB | Base release build; no UI/optional network or ML adapters |
| Idle daemon RSS | <= 40 MiB | Registered fixture participants, no active worker/model/UI |
| Ready time | <= 150 ms warm p95 | Process launch to local workspace ready; model startup excluded |
| Pure admission overhead | <= 2 ms p95 | Resolve/check/validate only; no disk/network/model execution |
| Initial web JS | <= 150 KiB gzip | Production initial route; lazy-load composition visualization |
| Disabled extension startup | Zero processes | Installed but disabled worker/adapter |

Start measurements on an identified Apple Silicon macOS machine and a specified
Linux x86-64 reference runner. Report both; do not compare raw numbers across
different machines as language speedups. Cold startup, fsync, persistence,
artifact transfer, and end-to-end latency are separate measurements.

## Workloads

- Register/list/find 10, 100, and 1,000 fixture participants.
- Admit/invoke deterministic no-op work at concurrency 1, 10, and 100.
- Run parallel compositions with waiting humans and event subscriptions.
- Write/read/hash 1 MiB, 100 MiB, and a streamed 1 GiB artifact.
- Stop a slow consumer, cancel work, remove a worker, and measure bounded memory.
- Recover after restart with pending approval and an uncertain side effect.
- Measure the same useful research/physical/software task against its handwritten baseline.

Use repeated release-mode samples and report p50/p95/p99 where meaningful.
Measure SQLite durability settings explicitly; do not improve a benchmark by
silently weakening persistence. Exclude external model time only when labeled.

## Resource rules

Bound event queues, tool output, inline payloads, open processes, subscriptions,
concurrency, retry counts, and in-memory history. Stream large data. Load optional
integrations lazily. Never import/load all models at registration or startup.
Use retention/garbage collection with durable references, not unbounded logs.

Track binary size and dependency/feature trees for base and optional builds.
Compare release size settings and execution throughput; LTO/size optimization
tradeoffs must be measured. No premature zero-copy, custom allocator, or unsafe
optimization without a representative bottleneck and correctness evidence.

Performance regressions need workload-specific thresholds after stable baselines
exist. Do not fail CI on noisy shared-runner latency before variability is understood.
