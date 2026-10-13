# Build plan

The project keeps its broad goal. Build complete, testable mechanisms in this
order so each new ability inherits a working execution system. Stages are
acceptance gates, not calendar estimates. Check boxes only after evidence exists.

## 0. Rebuild foundation

- [x] Preserve baseline main on `old`, with its own README and run instructions.
- [x] Decide stack, module ownership, contracts, and extension lifecycle.
- [x] Record free/open-source direction and Apache-2.0 license.
- [x] Write shared agent instructions, coding/commenting standards, and attribution checks.
- [ ] Publish repository visibility and a release when the owner chooses to do so.

These checkmarks describe the foundation files. No runtime stage below is complete.

## 1. Native vertical slice

Create the protocol/core/host/CLI workspace and pinned toolchain. Start with one
process-backed command participant and a human participant, SQLite registration,
artifact write/read, typed events, explicit owner identity, narrowing grants,
approval, and cancellation. Build a small useful program before broadening adapters.

Port useful behavior from `old`; use its tests as cases, not a requirement to
retain implementation bugs. Reject unknown callers, use collision-safe external
names, validate output before success, and preserve effect/scope conflicts.

- [ ] Fresh native installation registers and calls a command without Python or Node.
- [ ] Grant refusal occurs before opening an adapter or requesting approval.
- [ ] Approval cannot widen authority; expiry during waiting is rechecked.
- [ ] A command and human produce one recorded task with correct terminal events.
- [ ] Cancellation cleans up owned processes and queues.
- [ ] Formatter, Clippy, unit/integration/doc tests, and base measurements run in CI.

## 2. Durable execution and executable discovery

Persist run events, attempts, pending human requests, and checkpoints. Add
OpenAPI and MCP readers plus native execution for their discovered bindings.
Use maintained SDKs where possible. Introduce explicit version compatibility,
credential references, freshness, schema diffs, and conflict records.
Add OpenAI-compatible model and A2A adapters as optional packages after the first
two discovery paths are executable.

- [ ] Add an address, inspect it, and call it without manually adding another URI.
- [ ] Two declared interfaces at one address have explicit binding/merge behavior.
- [ ] Equal schemas with different scopes, effects, or operations do not silently merge.
- [ ] Restart during approval recovers the same request and revalidates dispatch.
- [ ] A completed external write is not blindly repeated after uncertain failure.
- [ ] Independent MCP/A2A implementations pass the declared compatibility matrix.
- [ ] Removing an adapter preserves history and reports affected saved work.

## 3. Non-chat and physical participants

Add the Python worker contract and optional Torch/Hugging Face environments.
Keep large media/tensors in the artifact path. Port the useful property/event
mechanism from the physical branch; add WoT discovery and Home Assistant ingestion
before multiplying direct vendor integrations. Preserve reads, writes, events,
and approval as native operations.

- [ ] A specialist model works through the worker contract without becoming a chatbot.
- [ ] Worker crash, malformed frames, cancellation, and version mismatch are tested.
- [ ] Property read/write authority is distinct; subscriptions expire and cancel.
- [ ] One real trace includes a model, service, human, and device.
- [ ] Device state is observed before/after bounded writes; refusal and disconnection work.
- [ ] Fixture results and live hardware results are labeled separately.

## 4. Reusable composition and semantic contracts

Implement a versioned composition format with dependencies, conditions, fan-out,
fan-in, event triggers, transformations, human steps, and bounded retries.
A saved composition is a participant, exposing inputs/outputs and required
authority. Every nested step re-enters the same gate.

Represent compatibility as direct, transformed, or unknown. Add units, media
types, tensor layout/preprocessing, coordinate frames, and freshness only when
real cases need them. Keep capability identity separate from implementation revision.

- [ ] Save, restart, reuse, and nest a composition; expose it through an existing protocol.
- [ ] Reject a wrong-unit/layout connection and accept an explicit tested transformation.
- [ ] Pin contract revisions; rediscovery produces a reviewed diff.
- [ ] Interrupt/recover parallel work without losing approvals or repeating uncertain writes.
- [ ] Track resource/cost reservations, concurrency, and budgets across nested work.

## 5. General workspace app

Build the Svelte UI over the real application API. Add arbitrary participants,
inspect capabilities/bindings, configure credential references, view grants,
invoke native operations, build/save compositions, answer human requests, and
inspect artifacts/history. Serve static assets from the optional HTTP surface.
Add Tauri only after the same workflows work in a browser.

- [ ] An independent user builds their own workflow without editing repository code.
- [ ] Authority and failure details are understandable before and after execution.
- [ ] Reconnect resumes events; missing history has a clear response.
- [ ] Keyboard/focus, reduced motion, responsive layout, and core browser tests pass.
- [ ] Headless build excludes UI/desktop dependencies; desktop overhead is measured separately.

## 6. Isolation and cross-host work

Add authenticated remote identity, verified narrowing authority, revocation,
audience restrictions, and authorized artifact transfer. Select isolation
backends by platform and workload, with explicit guarantees. Add a ROS 2 bridge
for bounded tasks; timing-sensitive robot control stays in established controllers.

- [ ] Two machines complete a composition with narrowed authority and verified artifacts.
- [ ] Revocation, expired grants, partitions, worker death, and denied egress are exercised.
- [ ] Isolation claims match actual platform tests; trusted/in-process code is labeled.
- [ ] The minimal local product remains useful without remote infrastructure.

## 7. Assisted adaptation and an extension ecosystem

Let a model propose compositions or adapters from declared interfaces.
Validate the proposed artifact in a controlled worker, run conformance and
semantic examples, then require an explicit installation/activation decision.
Successful runs may become versioned reusable routines. Suggestions never grant
authority, invent missing interfaces, or install code silently.

- [ ] A generated proposal passes the same contracts as a handwritten extension.
- [ ] A failed or ambiguous proposal remains a legible result.
- [ ] Extensions can be installed, disabled, upgraded, and removed without core edits.
- [ ] Independent contributors add an ecosystem using the documented ports.

## Development rhythm

Keep the research, physical, and software workflows from [PRODUCT.md](PRODUCT.md)
as maintained scenarios. Every milestone closes one complete behavior and its
failure paths. Introduce tests and real setup commands in the same change.
Avoid adapter-count sprints that leave discovery, authority, or recovery unfinished.

For each release record integration code required, first useful run, repeat use,
failures/recovery, runtime overhead, artifact overhead, and the environment.
Compare with a handwritten baseline or established framework on the same task.
Separate measured results, targets, observations, and hypotheses.

The next implementation task is stage 1: one command participant, one human,
and one durable, governed native execution path. No model download is required.
