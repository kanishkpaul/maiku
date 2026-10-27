# Product direction

Maiku's [thesis](THESIS.md) is that accessible systems can share a common
operational language while retaining their native meaning. Its fundamental unit
is an interaction contract: an operation, its requirements, observable outcomes,
and limits. See [current status](STATUS.md) for what exists in the rebuild.

Maiku connects systems that compute or interact and lets people use them together.
A language model, classifier, mathematical program, service, command, agent,
person, sensor, and actuator should retain their native capabilities while sharing
one inspectable execution system.

The destination is an app backed by a reusable runtime. The runtime is useful
headlessly and through existing protocols. The app lets a person add, inspect,
connect, run, intervene, understand, and reuse work.

## Commitments

- The runtime, app, schemas, composition format, adapters, and conformance suite
  are free and open source under Apache-2.0.
- Local operation needs no account or hosted service. Model weights and external
  APIs are optional and follow their own licenses and costs.
- Adaptation draws on declared interfaces, signatures, source, device protocols,
  documentation, and visible interfaces as evidence. Missing information remains
  unknown; inferred proposals are distinguished from declarations and observations.
- A person is a participant. Approval and input are durable interactions.
- Native operations include invocation, streaming, property access, and events.
- Every call follows the same authority, validation, artifact, and execution path.
- Saved compositions become participants and can be composed again.
- A plugin may extend capability but cannot silently widen authority.
- Verification is part of adaptation. Evidence records conditions and limits;
  changing assumptions require re-verification before dependent use.
- Shared adaptations and tests must not expose private user data.

## What universality means

Universality needs both an extensible contract and an adaptation process with
progressively less manual translation. It is not a claim
that arbitrary undocumented systems can be understood automatically.
The architecture must allow a new ecosystem without modifying the execution
engine. Each release proves another complete use of that contract.

Connecting two schemas is not sufficient to connect their meanings. The app
must distinguish direct compatibility, compatibility through an explicit
transformation, and insufficient information. Language models may suggest
connections; the runtime validates contracts and requires clarification when needed.

The research question is how much integration can be automated while preserving
meaning, authority, and observable correctness. Measure human corrections and
maintenance effort alongside task success. A proposed mapping and finite tests
cannot establish every hidden consequence or future behavior.

## Reference workflows

1. Research: text/audio -> specialist model -> deterministic verifier -> human
   review -> artifact. Include a real multilingual workload.
2. Physical: observation -> interpretation -> bounded proposal -> approval ->
   device operation -> observed state/event.
3. Software: remote service/agent -> local analysis -> proposed change -> approval
   -> external action and verification.

These are integration tests of breadth, not separate appliances. Measure the
custom integration code, time to first useful run, successful reuse, recovery,
and returning independent users. Adapter counts and stars are supporting signals.

## Presentation

Make serious mechanisms approachable. Use clear capability names, readable state,
useful failures, and visible consequences. Preserve the playful Maiku identity
without making authority or uncertainty ambiguous. Do not fabricate customer
claims, testimonials, implemented features, or benchmark results.
