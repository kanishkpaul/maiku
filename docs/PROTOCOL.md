# Participant and worker contracts

Status: design contract for implementation. This file specifies requirements;
it is not a released wire specification or claim of compatibility.

## Participant

A descriptor identifies a participant, its native affordances, executable
bindings, declared permissions/effects, artifact constraints, provenance,
implementation revision, and interface freshness. Keep observed health and
timestamps outside stable capability identity.

An affordance has a named operation, input/output schema, known semantic metadata,
side effects, required scopes, cancellation behavior, and examples when available.
Supported operations are invoke, streaming invoke, property read, property write,
and event subscribe. A property read and write have distinct authority even if
they refer to the same state. Subscription is long-lived work and can be revoked.

Discovery must return an executable binding or mark the capability non-executable
with a specific reason. Preserve operation IDs, HTTP method/path/parameter maps,
transport versions, authentication references, and source conflicts.
Never present inferred meaning as declared or verified, fabricate schemas, or
silently reconcile conflicts.

## Interaction semantics and evidence

An interaction contract includes preconditions, known state/freshness requirements,
observable postconditions, and limits on what can be concluded. Semantic metadata
may include units, media types, tensor layout and normalization. Use versioned
domain extensions where necessary; do not require a universal ontology.
Unknown, conflicting, absent, and incompatible are distinct states.

Record source declarations separately from inferred proposals and test observations.
Operator policy controls permitted use independently of all three. Source references
include origin and revision/hash; verification reports include the operation and
implementation/binding revision, environment, test/evaluator version, permitted
scope, observations, time, and coverage limits. Reports can be passed, failed,
inconclusive, or stale. Passing one probe does not verify every operation.

Verification tests are ordinary governed operations. Observation-only authority
cannot authorize a write probe. Test failure cannot be relabeled success by a
proposal generator. Evidence must not embed credentials or expose private payloads.
Health, schema validity, semantic correctness, and authority are separate checks.

An activated binding refers to the reviewed contract revision and applicable
evidence. Interface or semantic drift produces a diff and marks dependent evidence
stale. Pin running work to its revision; stop or request review when a required
condition no longer holds. A repair is a candidate subject to the same checks.

## Events and results

Events have a protocol version, run/task/attempt ID, sequence, durable event ID,
participant/operation reference, and typed payload. An admitted attempt starts
once and ends with exactly one terminal result: success, failure, or cancellation.
Pre-admission rejection is a distinct recorded outcome, not a malformed started stream.

Started, progress, delta, artifact written, input required, approval required,
usage, diagnostic, and terminal events retain their meanings across entry points.
After terminal completion, reject subsequent task events. Validate outputs before
publishing success; malformed output fails the contract and remains available as
diagnostic evidence under the appropriate access policy.

Approval records bind operation, arguments, revisions, caller, decision, and
expiry. Pending requests survive restart. Duplicate answers and expired responses
have defined errors. Resume rechecks authority, revocation, and relevant state.

Artifacts use validated SHA-256 digests and typed metadata. Large tensors/audio/
video are references, not base64 in logs. Small inline values have size limits.
Remote transfer checks authorization, content digest, media constraints, and byte limits.
Artifact sharing is explicit per participant/step, not automatically session-wide.

## External workers

Use versioned JSON envelopes over stdio for the first worker protocol. Stdout is
protocol-only; diagnostics go to stderr. Frames have byte limits, request IDs,
and a negotiated protocol range. Secrets are injected out of band.

The worker handshake establishes version, supported operations, implementation
revision, and declared capabilities. The host owns authority and approval.
Worker messages cannot mint grants or invoke other participants through a side door.
Nested work is requested through the host and re-enters the execution gate.

Cancellation is an acknowledged operation with a deadline. If a worker does not
stop, the host terminates its owned process tree and records the outcome.
Crash, malformed frame, unexpected EOF, timeout, duplicate terminal event, and
version mismatch are conformance cases. Restart policy never blindly repeats an
uncertain write. An external worker is trusted executable code unless an actual
isolation backend is configured and verified.

Do not freeze an ABI around Rust trait layouts or share raw pointers between
unrelated processes. Later shared-memory transport needs a separate decision,
bounded lifetime ownership, and measurements that justify it.

## Compatibility policy

Maintain a matrix of versions and operations actually tested with independent
MCP/A2A implementations. Support legacy versions explicitly; do not advertise
latest compatibility because the adapter can round-trip with itself.
Projections report fields or semantics they cannot preserve. Human interaction,
event streams, and artifact access must have an explicit projection or a clear
unsupported result, not silent degradation.

Publish schema fixtures and Rust/TypeScript/Python golden vectors before external
workers depend on the contract. Version persistence separately and provide migrations.
