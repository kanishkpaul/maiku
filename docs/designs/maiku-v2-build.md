# maiku v2 build document

Target: the second prototype. Written to be executed without the conversation that
produced it. Read Part 0 before writing any code; it resolves most of the ambiguity you
will hit later.

Repo state assumed: `main` at 27 commits, 7,132 lines `src/`, 3,449 lines `tests/`, nine
adapter schemes, three projections, two gateways, one conformance contract.

---

## Part 0. The four rules that decide code

These are not philosophy notes. Each one settles a specific implementation question, and
each is cited below where it does so. When a design choice is unclear during
implementation, resolve it against these in order.

**Rule 1. Identity is capability alone.**
A participant is what it affords and nothing else. Not where it runs, not what it is
called, not who made it. Consequence: `canonical.py:VOLATILE_FIELDS` is currently wrong
and Stage 1 fixes it.

**Rule 2. An affordance is a relation, not a property.**
There is no "what this participant can do." There is only "what this participant can do
for this caller." A grant does not filter a capability that already existed; the grant is
what brings the affordance into existence. Consequence: every projection and description
must be caller-relative. Stage 4.

**Rule 3. Derived, never declared.**
Nothing may author what it is. maiku reads capability from whatever a thing already
publishes about itself in a machine-readable form. Where nothing is published, maiku
reports that it could not read, and never guesses. Consequence: the discovery layer reads
declared interfaces only; inferring affordances from undocumented protocols is out of
scope and stays out of scope. Stage 3.

**Rule 4. The instrument shows the field. It does not choose within it.**
`maiku find` stays search. No planner, no automatic composition, no capability matching
from schemas. This is already the documented position in README and it is now load-bearing
rather than defensive: an instrument that decides what you should look at is an oracle,
and nobody trusts the readings. Consequence: no stage below adds a planner, and any
future proposal to add one is a product decision, not an implementation detail.

One derived rule that resolves the hardest question in this build:

**One address, one descriptor.** Discovery against a single address runs every applicable
prober and assembles exactly ONE descriptor: union of bindings, merged affordances, one
handle. Probers contribute to an in-progress descriptor; they do not each produce a
competing descriptor that has to be reconciled afterwards. There is never a moment where
two participants exist for one address. See Stage 3.

---

## Part 1. Confirmed defects

Each was verified by reading the code and, where marked, by running it. Fix in the stage
order given; they are not independent.

### D1. Identity includes things that are not capabilities

`src/maiku/descriptor/canonical.py:16`

```python
VOLATILE_FIELDS = frozenset({"id", "signature", "liveness", "runtime"})
```

Everything not listed is inside the content hash, including `bindings`, `display` and
`provenance`. `bindings` carries the endpoint: `src/maiku/adapters/openai_compat.py:244`
writes `uri=f"{self._base}/chat/completions"`.

Verified by running:

```
runtime.host changed -> same id : True    (runtime excluded, correct)
port changed         -> same id : False   (SPEC.md says this MUST be True)
rename display       -> same id : False
add an icon          -> same id : False
set vendor string    -> same id : False
add a tag            -> same id : False
```

This contradicts three places that promise otherwise: the `canonical.py` module docstring
("restarting Ollama on another port must not mint a new participant"), `docs/SPEC.md`
("restarting a model on another port does not mint a new participant"), and `README.md`
("moving a model to another host does not mint a new participant").

Severity: P0. Every stage below inherits it if not fixed first.

### D2. The registry silently overwrites on handle collision

`src/maiku/runtime/registry.py`

```sql
handle      TEXT PRIMARY KEY,
content_id  TEXT NOT NULL,
```

and

```sql
ON CONFLICT(handle) DO UPDATE SET
    content_id = excluded.content_id,
    ...
```

Two writers that agree on the handle and disagree on the descriptor silently overwrite,
last write wins, with no record that anything was replaced. `content_id` is stored but
never used for lookup, comparison or conflict detection.

Severity: P1.

### D3. There is no way to point maiku at an address

`src/maiku/adapters/uri.py:parse()` raises `InvalidURI` when there is no scheme.
`src/maiku/adapters/registry.py:resolve()` maps one scheme to exactly one adapter class.
`BUILTIN_SCHEMES` contains no `https`.

So both of these fail today:

```
maiku add 192.168.1.42          -> InvalidURI: not scheme:target
maiku add https://device.local  -> InvalidURI: no adapter for scheme 'https'
```

"Point maiku at an address and it adapts" has no entry point.

Severity: P1. Blocks Stage 3.

### D4. `AffordanceKind` is a label nothing reads

`src/maiku/descriptor/enums.py:32` defines `PROPERTY` and `EVENT`.
`src/maiku/adapters/base.py:51` declares exactly one abstract call method: `invoke`.
`grep -rn "AffordanceKind" src/maiku/runtime/router.py` returns nothing.

So the runtime has no code path for properties or events. An affordance declaring
`kind: property` is routed through `invoke` like everything else. Zero usages of
`PROPERTY` or `EVENT` across `src/`, `tests/` and `examples/`.

This is the half of the vocabulary that spans physical things. It is currently decorative.

Severity: P1 for the product claim, P3 for anything shipping today.

### D5. Descriptions are not caller-relative

```python
def to_tools(descriptor: ParticipantDescriptor) -> list[dict[str, Any]]:
```

Same shape in `projections/mcp.py`, `projections/openai_tools.py`, `projections/a2a.py`.
`grep -n "grant" src/maiku/gateways/*.py src/maiku/projections/*.py` returns nothing.

maiku publishes an identical tool list to every caller in the world, then applies the
grant afterwards as a filter at call time. Violates Rule 2.

Severity: P1. Also a security-relevant information leak: a caller sees affordances it can
never invoke, including their schemas and examples.

### D6. The name `probe` is taken

`Adapter.probe()` (base.py:87 plus six adapters), `ProbeKind`, the `Probe` model,
`maiku probe` in `cli/main.py:115`, and `test_probe_answers` in the conformance contract.
All of it means liveness checking.

The new subsystem must not be called probe. Use **discovery**: `Discoverer`, `discover()`,
`src/maiku/discovery/`, `maiku add auto:<address>`.

Severity: P2, but decide it before writing the module or the rename is expensive.

---

## Part 2. Build stages

Stages are ordered by dependency, not by size. Do not reorder. Each stage ends with a
verification step that must pass before the next begins.

---

### Stage 1. Identity correction

Fixes D1. Blocking for everything else.

**Change** `src/maiku/descriptor/canonical.py`:

```python
VOLATILE_FIELDS = frozenset({
    "id", "signature", "liveness", "runtime",
    "bindings",     # where and how to reach it, not what it is
    "display",      # a name is not a capability
    "provenance",   # who made it is not what it can do
})
```

Identity therefore covers: `schema_version`, `handle`, `kind`, `affordances`,
`io_defaults`, `artifacts`, `permissions`, `extensions`.

**Why `handle` stays in.** A handle is the participant's address in the graph. Two people
who both afford only `approve` are genuinely different positions, and collapsing
`human/alice` and `human/bob` to one id would be wrong. Rule 1 is about substrate, not
about position. The prober merge problem that removing `handle` would have solved is
solved instead by the one-address-one-descriptor rule in Stage 3.

**Why `provenance` goes out.** It is currently in identity, so setting a vendor string
mints a new participant. Provenance is the answer to "who made this", which the record
needs and identity does not.

**Update the docs that assert the old behaviour** in the same commit:
`docs/SPEC.md` Identity section, and the `canonical.py` module docstring. State the new
rule positively: identity is the affordance set plus the address, and everything about
where, how, who and what-it-is-called sits outside.

**Tests** (add to `tests/unit/test_descriptor.py`):

- Same affordances, different binding URI: ids are equal.
- Same affordances, two bindings vs one: ids are equal.
- Same affordances, different `display.name` / `icon` / `tags`: ids are equal.
- Same affordances, different `provenance.vendor` / `version` / `adapter`: ids are equal.
- Different affordance set: ids differ.
- Different `permissions.side_effects`: ids differ.
- An affordance whose `input_schema` changed: ids differ.
- Round trip: serialize, mutate a non-identity field, reload, declared id still verifies.

**Verify:** `uv run pytest -q` green, and the four probe lines from D1 all report `True`.

---

### Stage 2. Registry keyed on identity

Fixes D2. Depends on Stage 1.

**Schema change** in `src/maiku/runtime/registry.py`. Keep `handle` as PRIMARY KEY (it is
the address and must stay unique), and start actually using `content_id`:

```sql
CREATE INDEX IF NOT EXISTS participants_content ON participants(content_id);
```

**Change `add()` to detect and report identity change rather than silently overwrite.**
Three cases, all explicit:

| Existing row | Incoming descriptor | Behaviour |
|---|---|---|
| none | any | insert, `first_seen = now` |
| same handle, same `content_id` | bindings differ | update bindings, keep `first_seen`, no warning |
| same handle, different `content_id` | capabilities changed | update, preserve `first_seen`, and **return a signal that identity changed** |

The third case is the one that currently vanishes. `add()` should return an `Entry` plus
enough information for the caller to say "this participant's capabilities changed". Add a
field to `Entry` or return a small result object; do not log and move on. A capability
change is the only kind of change that matters under Rule 1, and it is exactly the one
being discarded today.

**Add** `Registry.by_content_id(content_id) -> list[Entry]` so two handles that resolve to
the same capability set are discoverable. Under Rule 1 those are the same thing wearing
two names, and an operator should be able to see that.

**Tests** (`tests/unit/test_registry.py`):

- Re-adding an identical descriptor preserves `first_seen` and reports no identity change.
- Re-adding with a changed binding reports no identity change.
- Re-adding with an added affordance reports an identity change.
- `by_content_id` returns both handles when two participants share a capability set.
- FTS index is rebuilt on update, not duplicated.

**Verify:** `uv run pytest -q` green.

---

### Stage 3. The discovery layer

The heart of v2. Depends on Stages 1 and 2.

**New module** `src/maiku/discovery/`. Do not call anything in it `probe` (D6).

```
src/maiku/discovery/
  __init__.py
  base.py          Discoverer protocol
  assemble.py      one-address-one-descriptor assembly + precedence
  openapi.py       wraps adapters/openapi.py
  mcp.py           wraps adapters/mcp_client.py
  wot.py           W3C WoT Thing Description  (Stage 6, not now)
```

**The `Discoverer` protocol** in `base.py`:

```python
class Discoverer(Protocol):
    name: str
    precedence: int          # higher wins on conflict; see below

    async def applies(self, address: Address) -> bool:
        """Cheap, non-mutating check. May do one HEAD/GET, must not write."""

    async def read(self, address: Address) -> Reading:
        """Return affordances + a binding, or raise NotReadable with what was tried."""
```

A `Reading` carries: `affordances`, one `Binding`, optional `display` / `provenance`
hints, and `source` (the discoverer's name). A `Reading` is not a descriptor. Only
`assemble.py` produces descriptors.

**Assembly rules** (`assemble.py`). This is the answer to prober conflict, and it is a
design rule rather than a runtime negotiation:

1. Run `applies()` on every registered discoverer, concurrently, against the address.
2. Collect a `Reading` from each that applies. A failure from one discoverer never fails
   the whole discovery; it is recorded.
3. **Bindings union.** Every successful reading contributes its binding. A participant
   reachable three ways has three bindings. Since Stage 1 removed bindings from identity,
   this does not change the id.
4. **Affordances merge by name.** Same name from two sources:
   - Identical schemas: keep one, note both sources.
   - Different schemas: the higher `precedence` wins, and the loser is recorded verbatim
     under `extensions["maiku.discovery"]["conflicts"]`. Never silently drop. Never
     attempt to union or reconcile two schemas: guessing a type nobody stated is how a
     registry starts lying, and `docs/SPEC.md` already commits against it.
   - Names unique to one source: included.
5. **Precedence order**, most semantically specific first, declared in one place:
   `wot(40) > openapi(30) > mcp(20) > generic-http(10)`. A more specific protocol carries
   more meaning, so it wins. The number lives on the discoverer, and the ordering is one
   sorted list in `assemble.py`, not scattered conditionals.
6. **Handle** is chosen once: the `--as` flag if given, else derived from the address, and
   recorded. Never derived per-discoverer.
7. **Provenance** records every discoverer that contributed, so a descriptor can always
   answer how it was read.
8. If no discoverer applies, fail with a message naming **every** discoverer that was
   tried and what each got back. Under Rule 3, a failed reading is a legitimate result and
   must be legible. Never emit a guessed descriptor.

**Entry point** (fixes D3). Add an `auto` scheme rather than changing URI grammar:

```
maiku add auto:https://device.local
maiku add auto:192.168.1.42:8080
```

Then, and only as a convenience layer on top: if `ParticipantURI.parse()` yields a scheme
not in `known_schemes()` and the raw string parses as a host or URL, retry as `auto:`.
Explicit form first, sugar second. Do not make bare addresses the primary path; the
explicit `auto:` keeps `maiku add` unambiguous and keeps the error messages honest.

**Discoverers for this stage: exactly two, `openapi` and `mcp`.** Both must be able to
answer for one address, because that is what forces the assembly and precedence code to be
real rather than assumed. Do not write six. The third (`wot`) arrives in Stage 6 with a
physical device behind it.

Both wrap existing code. `adapters/openapi.py` and `adapters/mcp_client.py` already derive
affordances; the discoverer is a thin `applies()` plus a call into what exists. If that
wrapping is awkward, extract the derivation rather than duplicating it. Duplicated
derivation logic is the single worst outcome of this stage.

**A `DiscovererContract` in `tests/conformance/`**, mirroring `contract.py`. Every
discoverer subclasses it from the first one, not retrofitted. Minimum tests:

- `applies()` is non-mutating and returns False rather than raising on an unreachable address.
- `applies()` returns False for an address of a different protocol.
- `read()` on a known fixture returns affordances matching a recorded expectation.
- `read()` raises `NotReadable` carrying what was attempted, never a partial descriptor.
- The assembled descriptor passes `ParticipantDescriptor` validation and self-verifies its id.
- Two discoverers on one address produce one descriptor with two bindings and one id.
- A schema conflict is resolved by precedence AND recorded in `extensions`.

**Tests** (`tests/e2e/test_discovery.py`): discover a local fixture that serves both an
OpenAPI document and an MCP endpoint, assert one participant with two bindings, assert the
conflict record is present, assert `maiku ls` shows it once.

**Verify:** `maiku add auto:<fixture>` produces one participant, `maiku ls` shows one row,
`maiku describe` shows both bindings.

---

### Stage 4. Caller-relative description

Fixes D5, implements Rule 2. Depends on Stage 3 only for ordering, not technically.

**Change every projection to take the caller's grant:**

```python
def to_tools(descriptor: ParticipantDescriptor, grant: Grant) -> list[dict[str, Any]]:
```

Same for `openai_tools.to_tools` and `a2a.to_agent_card`. The projection emits only the
affordances the grant actually permits. An affordance the caller cannot invoke does not
appear, and neither does its schema or its examples.

**Change the gateways** (`gateways/mcp_server.py`, `gateways/a2a_server.py`) to hold a
grant per connected client and project through it. A gateway with no grant serves nothing,
not everything: the safe default matches `router.deny_everything`, which already documents
the principle ("a runtime with nobody watching must not self-approve").

**Change the CLI:** `maiku describe X --as mcp` needs a grant. Default to the root grant
for local operator use, with `--grant <id>` to see what a specific caller would see. The
ability to ask "what does this look like to that participant" is the observable form of
Rule 2 and is worth having as a first-class command.

**Tests** (`tests/unit/test_projections.py`, `tests/e2e/test_mcp_gateway.py`):

- Root grant projects all affordances.
- A grant covering one affordance projects exactly one tool.
- A grant covering none projects an empty tool list, not an error.
- A grant with a `max_side_effect` ceiling hides affordances above the ceiling.
- Two different grants against one descriptor produce different tool lists.
- The A2A AgentCard is filtered the same way.
- Regression: no projection function accepts a descriptor without a grant.

**Verify:** `grep -rn "def to_tool" src/maiku/projections/` shows a grant parameter on every one.

---

### Stage 5. Properties and events in the runtime

Fixes D4. Makes the differentiating half of the vocabulary real. Depends on Stage 4.

**Extend the `Adapter` ABC** (`src/maiku/adapters/base.py`). Today it declares one call
method. Add, as non-abstract methods that raise `UnknownAffordance` by default so the
nine existing adapters keep working untouched:

```python
async def read_property(self, affordance: str, ctx: CallContext) -> AsyncIterator[Event]
async def write_property(self, affordance: str, value: Any, ctx: CallContext) -> AsyncIterator[Event]
def subscribe(self, affordance: str, ctx: CallContext) -> AsyncIterator[Event]
```

All three return the same event stream and terminate exactly once, through `guarded()`.
That invariant is the whole reason a bulb and a language model are commensurable; do not
add a second event discipline for devices.

**Teach the router to dispatch on `AffordanceKind`** (`src/maiku/runtime/router.py`, which
currently never mentions it). Same authorization path, same validation, same artifact
scoping, same approval gate for every kind. The only difference is which adapter method is
called. Concretely:

- `INVOKE`, `STREAM` -> `invoke` (unchanged).
- `PROPERTY` -> `read_property` with no value, `write_property` with one. A property write
  is a state change: it must go through the same `needs_approval` check as anything else,
  and `side_effects` on the affordance decides it.
- `EVENT` -> `subscribe`, a long-lived stream that terminates on cancellation. Cancellation
  is already tested in the conformance contract; reuse that path.

**Extend the conformance contract** (`tests/conformance/contract.py`) with kind-aware
tests that skip cleanly for adapters that declare no such affordance:

- A property read returns a value matching `output_schema`.
- A property write is refused when the grant's ceiling is below the declared side effect.
- A property write with `approval: on_scope` routes to the approver before taking effect.
- An event subscription yields at least one event and terminates exactly once on cancel.
- An event subscription with no matching grant fails without raising.

**Verify:** `grep -rn "AffordanceKind.PROPERTY\|AffordanceKind.EVENT" src tests` returns
non-zero, for the first time in the project's history.

---

### Stage 6. The first real thing

Depends on Stage 5. This is the stage the whole product claim rests on.

Add `src/maiku/discovery/wot.py`, implementing the existing
[W3C WoT Discovery](https://www.w3.org/TR/wot-discovery/) specification: fetch a Thing
Description from the Thing's own `.well-known` endpoint, and separately support a Thing
Description Directory. Do not invent a discovery mechanism. The vocabulary was borrowed
from WoT already; borrow the discovery too. Reference implementation to read, not vendor:
[thingweb-directory](https://github.com/thingweb/thingweb-directory).

A WoT Thing Description maps onto the descriptor almost directly, which is the point:
TD `properties` -> `AffordanceKind.PROPERTY`, TD `actions` -> `INVOKE`, TD `events` ->
`EVENT`, TD `forms` -> `Binding`. Where the TD carries something the descriptor cannot
express, record it under `extensions` rather than dropping it or approximating it.

**The deliverable is one trace**, in `examples/things/`, following the pattern already set
by `examples/real/`: a real physical device, the MNIST CNN, a language model, and a human
approver, in one session, as peers, with one event log. The write-up follows the honesty
convention of `examples/real/README.md`: say what actually happened, including what broke.

Hardware is the only dependency on someone else's calendar. Get the device in hand before
Stage 5 ends so this stage is not blocked waiting.

---

## Part 3. Explicitly not in scope

Each of these was considered and deferred, with the reason.

| Deferred | Why |
|---|---|
| Four more discoverers (Matter, Zigbee, Home Assistant, mDNS/SSDP) | Two that can answer for one address is what forces the assembly code to be real. The rest are repetitions of a solved shape once Stage 3 lands |
| Composition as a participant (`Kind.PIPELINE`) | The largest idea in the design and it needs identity, discovery and caller-relative description settled underneath it. v3 |
| The app or webapp | Zero lines of UI exist. Building the window before knowing what is outside it. Reassess after Stage 6 |
| Any planner or automatic composition | Rule 4. Not a scheduling decision, a standing position |
| Inferring affordances from undocumented protocols | Rule 3. This is the failed-service-composition graveyard `docs/LANDSCAPE.md` already refuses to enter |
| Federation across hosts | Stage 1 makes it possible; nothing else here needs it |
| Metering and settlement on the `usage` event | Real, and downstream of Stage 4 |
| microVM or WASM isolation | Already documented as designed-for, not built. Unchanged by this work |
| Distribution: LICENSE file, CI, tags, packaging | Repo is private and stays private. One live item: `pyproject.toml:6` declares `license = { text = "Apache-2.0" }` with no LICENSE file in the tree. Harmless while private, gives the work away on the first wheel build or the moment the repo flips public. One-line fix whenever that becomes relevant |

---

## Part 4. Standing requirements

Applies to every stage.

- **Conformance first.** Every new discoverer subclasses `DiscovererContract` from the
  first one written, never retrofitted. This is the mechanism that keeps many readers from
  becoming many dialects, and it is the thing that makes this build safe to do quickly.
- **Idempotent and re-runnable.** Discovery against the same address twice produces the
  same descriptor and the same id.
- **Never guess.** A failed reading names every source tried and what each returned. An
  empty result is a legitimate answer. A fabricated schema is not.
- **Never silently drop.** Anything the assembly discards on precedence is recorded in
  `extensions["maiku.discovery"]`.
- **One terminal event.** Every new code path goes through `guarded()`. Properties and
  events included. No second event discipline for devices.
- **ASCII diagrams in code** for the assembly pipeline in `assemble.py` and the kind
  dispatch in `router.py`. Both are non-obvious multi-step flows. Update any diagram you
  invalidate in the same commit.
- **Tests alongside, not after.** Each stage's tests ship in that stage's commits.
- **Commit style** follows the existing log: lowercase area prefix, one line, describing
  what changed rather than what was added. Push after each stage.

---

## Part 5. Verification checklist

The build is done when every line is true.

```
Stage 1  [ ] port change keeps the id
         [ ] rename, icon, tag, vendor change keep the id
         [ ] affordance change alters the id
         [ ] SPEC.md and canonical.py docstring match the code
Stage 2  [ ] capability change on an existing handle is reported, not swallowed
         [ ] by_content_id finds two handles sharing one capability set
Stage 3  [ ] maiku add auto:<addr> works with no scheme knowledge
         [ ] two discoverers on one address -> one participant, two bindings
         [ ] a schema conflict is resolved by precedence and recorded verbatim
         [ ] a total failure names every source tried
         [ ] DiscovererContract exists and both discoverers pass it
Stage 4  [ ] no projection function accepts a descriptor without a grant
         [ ] two grants on one descriptor produce different tool lists
         [ ] a gateway with no grant serves nothing
Stage 5  [ ] router dispatches on AffordanceKind
         [ ] a property write goes through the approval gate
         [ ] an event subscription terminates exactly once on cancel
         [ ] grep for PROPERTY/EVENT in src and tests is non-empty
Stage 6  [ ] a physical device is a participant with property and event affordances
         [ ] one trace contains a device, a CNN, a model and a person as peers
         [ ] the write-up says what broke
Always   [ ] uv run pytest -q green
         [ ] uv run ruff check src tests clean
```

---

## Part 6. Why this order

Stage 1 first because every later stage writes descriptors, and descriptors written under
the current hash carry an identity that is wrong in a way that is expensive to correct
after data exists.

Stage 2 before Stage 3 because discovery is the first thing that will write two
descriptors for one thing, and the registry currently resolves that by silently
overwriting.

Stage 3 with exactly two discoverers because the hard part is assembly and precedence, and
a single discoverer lets you skip both without noticing.

Stage 4 before Stage 5 because properties and events are the affordances most likely to be
caller-dependent (an operator may write a property that a guest may only read), and adding
them before descriptions are caller-relative bakes the wrong shape into the new code
rather than only into the old.

Stage 6 last because it is the only stage whose dependency is a physical object, and the
only one whose result is evidence rather than machinery.
