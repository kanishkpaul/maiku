# Coding and commenting standards

Tasteful code makes the important behavior easy to find and change. It uses
precise names, visible state and ownership, restrained abstractions, and tests
that explain the contract. A short file is not automatically simple; a clever
expression is not automatically better than a direct branch.

These standards apply to humans and every coding assistant. Read
[AGENTS.md](../AGENTS.md) before writing or publishing changes.

## Names and shape

- Use domain names: `Grant`, `PendingApproval`, `ArtifactDigest`, `RunAttempt`.
  Avoid `Manager`, `Helper`, `Engine`, `Utils`, and vague abbreviations unless
  they name a real responsibility. Prefer `resolve_binding` to `handle_thing`.
- Use Rust newtypes for IDs, digests, and other values that must not be mixed.
  Validate at construction/boundaries. Model lifecycle states and outcomes with
  enums instead of strings or combinations of booleans.
- Keep one responsibility per function/module. Split when readers must keep
  unrelated decisions in mind, not when an arbitrary line limit is reached.
- Put the normal path in a readable order. Use early returns for rejection.
  Do not hide mutation, authorization, or network work inside predicates.
- Prefer explicit named fields/options to ambiguous boolean arguments.
- Keep mutable state close to its owner. Inject actual ports/dependencies;
  avoid hidden globals, service locators, and shared bags of configuration.
- Use concrete types until a real boundary requires an interface. Traits belong
  at extension/storage/transport seams, not around every function.
- Introduce abstractions from repeated behavior or an established extension
  contract. Do not generalize an imagined third use case.

## Rust

Use rustfmt and Clippy, stable Rust, edition 2024, and the pinned project toolchain.
Keep public APIs small. Use typed errors for contract distinctions; use contextual
application errors only at entry points. `Result` and `?` are the normal error path.
Do not panic on external input or use `unwrap` to avoid error handling in product code.
An invariant assertion must state a programmer error and remain valid in all modes.

Prefer borrowed values and bounded collections where they clarify ownership.
Do not clone reflexively to silence the borrow checker, or contort lifetimes to
avoid a small measured allocation. Explain material tradeoffs in the owning decision.
Keep `unsafe` narrow and document the precise caller/implementation obligations.

Async code must own its tasks and cleanup. No blocking I/O on executor threads,
locks across awaits without a deliberate reason, unbounded channels, or silent
background task failures. Cancellation and side-effect uncertainty are part of
the function's contract. Optimize from a representative benchmark, not intuition.

## TypeScript and UI

Use strict TypeScript, domain types, and discriminated unions for states.
Parse/validate external data at the API boundary; a type assertion is not validation.
Avoid `any`, non-null assertions, and broad type casts as routine fixes.
Keep business rules and authorization on the host. Components present state and
collect intent. Use feature-local components, semantic HTML, explicit focus,
plain CSS/tokens, and the smallest useful dependency.

## Comments

First improve the name, type, or control flow. Add a comment when it supplies
information the code cannot conveniently express: a protocol constraint,
invariant, surprising tradeoff, compatibility reason, or operational consequence.
Put it next to the relevant code. Keep it short, factual, and durable.

```rust
// Poor: narrates the statement.
// Check whether the grant expired.
if grant.is_expired(now) { /* ... */ }

// Useful: explains the second check.
// Approval may outlive the grant; recheck immediately before dispatch.
authority.check(&request, now)?;
```

```rust
// Useful: preserves an ordering constraint that a refactor could break.
// Commit the approval before publishing its ID so a reconnect can resolve it.
store.insert_approval(&approval).await?;
events.publish(approval.event()).await?;
```

Do not add decorative banners, numbered narration, motivational prose,
implementation diaries, commented-out code, or a comment above every statement.
Do not repeat the function name or parameter types in prose.
Use TODOs only with a concrete missing behavior and an issue/reference or a
testable condition for removal. An unexplained `TODO: improve this` is not useful.

Public APIs use rustdoc (`///`, `//!`) or JSDoc where appropriate. Document what
the caller can rely on: outcome, errors, cancellation, side effects, and relevant
examples. Include `Errors`, `Panics`, or `Safety` sections when they apply; omit
empty boilerplate. Share/link examples rather than mechanically duplicating them.
Internal obvious accessors do not need narration. When behavior changes, update
or remove the comment in the same diff.

## Tests and review

Test behavior at its natural boundary. Prefer small readable fixtures and
assertions about outputs, effects, authority, lifecycle, and cleanup. Include
invalid input, cancellation, and recovery when applicable. Avoid mocks that
recreate the whole implementation or tests that merely assert a private method
was called. A failure should reveal which contract broke.

Review questions:

1. Can a new reader find admission, dispatch, and failure without decoding tricks?
2. Does each module own a clear decision and its mutable state?
3. Is an abstraction necessary for an actual boundary or repeated behavior?
4. Do comments preserve information rather than repeat syntax?
5. Are errors, cancellation, effects, and cleanup explicit?
6. Can this optional feature be removed without editing core or losing history?
7. Do tests challenge failure cases and do measurements support optimization claims?

Formatters check form; reviewers check meaning and taste. No lint can guarantee
good judgment. Every assistant must run the checks and perform this review.

## Research basis

- [Rust API naming](https://rust-lang.github.io/api-guidelines/naming.html):
  consistent names and conventions.
- [Rust API documentation](https://rust-lang.github.io/api-guidelines/documentation.html):
  useful examples, errors, and safety obligations.
- [Rustdoc writing guide](https://doc.rust-lang.org/rustdoc/how-to-write-documentation.html):
  document public contracts.
- [Google TypeScript style](https://google.github.io/styleguide/tsguide.html):
  comments that add information, useful types, and restrained documentation.
- [Linux kernel commenting guidance](https://www.kernel.org/doc/html/latest/process/coding-style.html#commenting):
  readable code and avoidance of redundant commentary. Borrow the principle,
  not the kernel's C formatting rules.
