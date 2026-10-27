# Architecture

Status: target architecture. Packages below are created as their build gates
land; this foundation does not contain an implemented runtime.

## Boundaries

| Layer | Owns | May depend on |
| --- | --- | --- |
| `maiku-protocol` | IDs, descriptors, operations, events, worker envelopes, version rules | Small serialization/validation libraries |
| `maiku-core` | Authority, lifecycle transitions, composition validation, compatibility rules | Protocol and small pure libraries |
| `maiku-host` | Scheduler, task supervision, persistence, artifact I/O, adapter ports, plugin lifecycle | Core, protocol, Tokio, selected storage libraries |
| Adapter packages | Discovery and native execution for one ecosystem | Protocol and host extension ports; ecosystem SDK |
| `maiku` binary | CLI, assembly of enabled adapters, optional HTTP surface | Host, adapters, CLI/HTTP libraries |
| `apps/web` | Workspace presentation and interaction | Generated wire types; API client |
| `apps/desktop` | OS integration and desktop packaging | Tauri and host-facing commands; web assets |
| `workers/*` | Language/model environments | Worker protocol, own optional dependencies |

Dependency direction is inward. Core never imports host, adapters, HTTP, SQLite,
UI, or ML frameworks. Host discovers adapters through an interface; it does not
branch on vendor names. Entry points assemble enabled implementations explicitly.
Do not use a global service locator or mutable plugin registry hidden in core.

Create these as cohesive modules before making more crates. Split a crate when
an actual optional dependency, ownership boundary, reuse need, or build constraint
justifies it. Do not create one crate per struct or twenty empty adapter packages.

## Planned tree

```text
crates/
  maiku-protocol/src/      descriptors, operations, events, IDs, worker envelopes
  maiku-core/src/          authority, lifecycle, composition, compatibility
  maiku-host/src/          scheduler, storage, artifacts, extensions, supervision
  maiku/src/               CLI, application assembly, optional HTTP
  adapters/               packages added one at a time
apps/
  web/src/features/       participants, runs, compositions, approvals, artifacts
  desktop/                optional Tauri shell
workers/                  optional language bridges
tests/
  conformance/            shared adapter/discoverer/worker contracts
  interoperability/       independent protocol implementations
  scenarios/              the three reference workflows and recovery cases
benchmarks/               reproducible runtime and packaging workloads
docs/                     decisions and contracts
```

Frontend features own their components and local state. Shared UI contains
actual reusable primitives, not a generic framework. API/wire types are generated
from the same versioned contracts; the browser cannot make authority decisions.

## Adaptation lifecycle

Discover, describe, bind, verify, execute, and maintain are separate responsibilities.
Discovery gathers accessible interface evidence without treating access as
authority to probe or mutate. Description preserves native operations, requirements,
semantic unknowns, and source conflicts. Binding supplies the native call mapping.
Verification runs explicitly permitted tests and records scoped evidence before
activation. Execution mediates approved contracts. Maintenance detects drift and
returns changed contracts to review and verification.

Protocol owns evidence references and contract versions; core owns compatibility
and activation rules; host owns evidence storage, test supervision, and source
freshness; connectors own environment-specific extraction and bindings. Learned
proposal generators are optional clients of these ports. They do not enter the
authority engine or gain permission from the text they inspect.

Keep source declarations, inferred mappings, observations, and operator policy
separate. Evidence is bound to operation, implementation/interface revision,
environment, tested conditions, and limits. A source change invalidates affected
assumptions; repairs remain candidates until rechecked. Active runs retain pinned
contracts. Sharing reusable knowledge requires explicit sanitization and permission.

## One execution gate

Resolve caller identity and capability revision. Check grant, scopes, effects,
argument constraints, and readable artifacts. Persist admission and any approval
request. Wait if needed. Revalidate authority and relevant state after waiting.
Dispatch through the selected adapter. Validate and record emitted events and
outputs. Persist completion and release resources.

Every entry point, delegated operation, composition step, property access, event
subscription, and worker call uses this gate. Unknown caller identities are denied.
Local operator authority is explicit and never a fallback for failed lookup.

Authorization and approval are distinct: approval cannot confer a capability
the caller lacks. Extension-declared hints are evidence, not trusted authority.
Merge conflicts in scopes, effects, operation kinds, or schema are recorded and
resolved explicitly; equal schemas do not prove equal capabilities.

## Execution and storage

- Typed lifecycle transitions are owned by core. Host owns asynchronous execution.
- A supervised task has a cancellation token, deadline, concurrency reservation,
  bounded event channel, and cleanup path. No detached work without a tracked owner.
- Queue overflow has an explicit policy. Durable state changes are not silently
  dropped; high-volume progress can be coalesced only when the contract permits it.
- The storage worker serializes SQLite transactions and disk work off the executor.
  Do not hold a database transaction during network calls or approval waits.
- Event records, approvals, attempts, and composition checkpoints are durable.
  SSE resumes from a stable event ID, with a retention-gap response.
- Event replay reconstructs state. Rerunning a task may produce side effects and
  is a separate operation with idempotency/reconciliation rules.
- Artifact writes use unique temporary files, streaming hashes, atomic promotion,
  checked digest syntax, size limits, and garbage collection tied to durable references.

## Identity and compatibility

Keep participant position, capability fingerprint, implementation revision, and
endpoint revision separate. A structural schema hash does not establish equal
behavior, model weights, or trustworthy authorship. Canonical cross-language
serialization and sorting rules need golden vectors before IDs become durable.

Bindings retain the operation metadata needed for execution, not just a URL.
Discovery reads a declared interface and records its origin and freshness.
Rediscovery produces a diff; it cannot silently change a running composition's contract.

Compatibility is direct, requires an explicit transformation, or unknown. Units,
tensor layout, preprocessing, coordinate frames, and freshness are represented
when known. Transformation participants use the ordinary gate and record provenance.

## Optional capabilities

Use additive Cargo features to include optional adapters, HTTP, and telemetry.
Audit feature unification so optional transitive packages do not enter base builds.
Runtime enablement is separately controlled through installed manifests and config.
The permission engine, validation, and durable execution invariants are never optional.

The lifecycle is register -> enable -> ready -> draining -> disabled -> remove.
Disabling stops new work and drains/cancels existing work according to policy.
Removal refuses unresolved references or requires an explicit migration.
Keep history and artifacts readable after an extension is removed.

See [EXTENSIONS.md](EXTENSIONS.md) for the full change/removal checklist and
[PROTOCOL.md](PROTOCOL.md) for wire guarantees.
