# maiku bug-fix brief, round two

Five defects. Three matter, two are polish. Written to be executed by any coding agent that
was not present when they were found, so each one carries a complete, runnable
reproduction.

This follows an earlier round of eleven fixes, all of which landed correctly. Two of the
defects below were introduced *by* those fixes, and both are the same mistake: a semantic
was changed without asking what data already written to disk means under the new rule. The
third has been latent since the discovery layer was built. You do not need to read the
first brief; everything required is here.

**Reproduce before you fix. Paste the output.** Do not fix from the description alone, and
do not report a fix as done because the test suite is green — every defect below is
invisible to the suite, which is part of why it survived.

---

## Part 0. Orientation

`maiku` adapts anything that computes — a model, a script, an HTTP API, an MCP server, a
person — into one descriptor format, then lets those things call each other through one
runtime with one event stream.

```
src/maiku/descriptor/   the document format and its content hash
src/maiku/adapters/     one module per scheme; turns a URI into a participant
src/maiku/discovery/    reads an address and assembles one descriptor from many readers
src/maiku/runtime/      registry (sqlite), grants, router, session, workspace
src/maiku/projections/  descriptor -> MCP tools / OpenAI tools / A2A AgentCard
src/maiku/gateways/     serves participants back out over MCP and A2A
src/maiku/cli/          the `maiku` command
tests/unit/  tests/e2e/  tests/conformance/
```

### Setup

The project uses `uv`. From the repository root:

```
uv sync
uv run pytest -q                        # 497 passed
uv run ruff check src tests examples    # clean
uv run maiku --help
```

Both gates are green right now. They must still be green when you finish.

Reproductions below are written as complete scripts. Save each to a scratch file outside
the repository and run it with `uv run python <file>`. Several need the test helpers, which
is why they put `tests` on the path.

### Four rules that decide code

When an implementation choice is unclear, resolve it against these in order. If you believe
a rule is wrong for a particular fix, say so in your report rather than quietly working
around it.

1. **Identity is capability alone.** A participant is what it affords. The content hash
   covers `schema_version`, `handle`, `kind`, `affordances`, `io_defaults`, `artifacts`,
   `permissions`, `extensions`. It excludes `runtime`, `bindings`, `display`, `provenance`,
   `liveness`, `signature`. Defect 2 turns on the fact that `affordances` is inside and
   `bindings` is outside.
2. **An affordance is a relation, not a property.** There is no "what this participant can
   do", only "what it can do for this caller". A grant brings an affordance into existence;
   it is not a filter applied afterwards.
3. **Derived, never declared.** Capability is read from what a thing publishes about
   itself. Where nothing is published, maiku reports that it could not read. It never
   guesses.
4. **The instrument shows the field, it does not choose within it.** No planner, no
   automatic composition, no capability matching from schemas.

Two standing requirements, both load-bearing below:

- **Never guess.** A failed read names every source tried and what each returned.
- **Never silently drop.** Anything discarded or rewritten is recorded, not dropped.

### House style

- Comments say **why**, never what or how. A comment that restates the code should be
  deleted.
- Modular over monolithic. Small functions with real names.
- Tests ship in the same commit as the code they cover, never in a follow-up commit.
- Commit messages: lowercase area prefix, one line, describing what changed rather than
  what was added. Real examples from this log:
  - `registry: tolerate old identity hashes, surface unreadable rows, and fix migration resilience`
  - `discovery: a binding names the affordances it actually serves`
- **No `Co-Authored-By` trailer. No "generated with" footer.** Author the commits plainly.
- Commit and push after each logical unit, not once at the end.

### Out of scope

- Do not start new feature work. `docs/designs/maiku-v2-build.md` describes Stages 5 and 6
  (properties and events in the router; W3C WoT discovery). **Do not begin either.**
- Do not rename modules, restructure packages, or reformat files you are not fixing.
- Do not weaken `ParticipantDescriptor`'s declared-id check for documents arriving from
  outside. A descriptor handed to maiku by someone else must still fail if it was edited in
  transit. There is an existing test for this — `test_tampered_descriptor_is_rejected` in
  `tests/unit/test_descriptor.py` — and it must keep passing.

---

## Defect 1. Every discovery failure prints a traceback instead of a sentence

**Severity: P1. Fix this first — it is one line plus a test, and it is the failure an
operator hits most.**

`maiku add <address>` runs the discovery layer, which reads whatever a thing publishes
about itself. When nothing at that address can be read, discovery raises `NothingReadable`
carrying every URL it tried and what each returned. That message is exactly right. It is
delivered wrongly.

`_run` in `src/maiku/cli/main.py:312` turns adapter failures into messages:

```python
    except (AdapterError, InvalidURI) as exc:
        fail(f"error: {exc}")
```

`NothingReadable` (`src/maiku/discovery/assemble.py:78`) inherits from `Exception` and
`InvalidAddress` (`src/maiku/discovery/base.py:21`) from `ValueError`. Neither is caught, so
both escape as an unhandled exception and Typer renders a Rich traceback.

`_run`'s own docstring states the intent: *"Adapting a thing that is missing, misspelled or
refusing to start is the single most common way to use this tool wrong; it should read as a
sentence."*

### Reproduce

```bash
H=$(mktemp -d)
for target in "http://device.local" "raspberrypi:8080" "auto:http://127.0.0.1:1"; do
  printf '%-28s -> ' "$target"
  out=$(uv run maiku add "$target" --home "$H" 2>&1)
  echo "$out" | grep -q "Traceback" && echo "TRACEBACK" || echo "$out" | head -1
done
```

Observed:

```
http://device.local          -> TRACEBACK
raspberrypi:8080             -> TRACEBACK
auto:http://127.0.0.1:1      -> TRACEBACK
```

### Expected

All three print the discovery failure as a message and exit non-zero. The message content
must not be truncated or summarised — it currently names every candidate URL each reader
tried and the error each got back, and that detail is the whole point under "never guess".

Check whether any other command routes through discovery and needs the same treatment.

### Acceptance

A CLI test asserting `"Traceback" not in result.output` for an unreachable address in all
three forms (`http://host`, `host:port`, `auto:<url>`), and that the output still names at
least one attempted URL.

---

## Defect 2. Bindings written before a recent change now claim to serve nothing

**Severity: P1.** Introduced by an earlier fix. Fix it in the same place the registry
already tolerates old data.

`Binding.affordances` (`src/maiku/descriptor/binding.py:34`) recently changed:

```python
# before
affordances: list[str] = Field(default_factory=list)
def serves(self, affordance): return not self.affordances or affordance in self.affordances

# now
affordances: list[str] | None = None
def serves(self, affordance):
    if self.affordances is None:
        return True
    return affordance in self.affordances
```

The change itself is correct and should stay. It was made so a binding could distinguish
*serves everything* (`None`) from *serves nothing* (`[]`), which the discovery layer needs.

The problem is what it does to data already on disk. Under the old model every `Binding`
constructed without an explicit list got `[]`, and `[]` meant *serves everything*. So every
descriptor ever persisted — in `~/.maiku/registry.sqlite`, in any exported JSON —
serialized `"affordances": []` on each binding. Read back under the new model, `[]` now
means *serves nothing*.

The descriptor's own tamper check cannot catch this, because `bindings` sits outside
identity (Rule 1). The document loads clean and is wrong underneath.

### Reproduce

```python
import sys
sys.path[:0] = ["tests", "."]

from maiku.descriptor import ParticipantDescriptor
from tests.conftest import make_descriptor

fresh = make_descriptor()
print("built today      :", repr(fresh.bindings[0].affordances),
      "serves:", fresh.bindings[0].serves("classify"))

stored = fresh.model_dump(mode="json")
stored["bindings"][0]["affordances"] = []          # what the old model wrote
revived = ParticipantDescriptor(**stored)

print("read from before :", repr(revived.bindings[0].affordances),
      "serves:", revived.bindings[0].serves("classify"))
print("id still verifies:", revived.id == fresh.id)
try:
    revived.binding_for("classify")
except KeyError as exc:
    print("binding_for      : KeyError(%s)" % exc)
```

Observed:

```
built today      : None serves: True
read from before : []   serves: False
id still verifies: True
binding_for      : KeyError("local/sentiment has no binding serving 'classify'")
```

### Why it matters more than it looks

`binding_for` has exactly one caller in `src` today, so nothing routes through it yet. The
build document's next stage makes the router resolve a binding per affordance, at which
point every participant adapted before this change stops being callable. Fix it while it is
still cheap.

### Expected

A descriptor written under the old model reads back with the old meaning. There is already
a precedent for exactly this kind of tolerance in the same codebase: `Registry` detects
descriptors whose declared id was computed under a superseded rule, re-derives them and
rewrites the row — see `_parse_descriptor` at `src/maiku/runtime/registry.py:337`. Follow
that pattern rather than inventing a second one.

Points worth deciding explicitly, and stating in your commit message:

- Where the normalisation belongs. The registry read path knows the row is its own. A
  `ParticipantDescriptor` validator would also catch documents from elsewhere — but it
  cannot distinguish "written by an old maiku" from "genuinely serves nothing", so think
  about whether that is acceptable before choosing it.
- Whether normalisation should be one-way. `[]` from an old document means everything; `[]`
  from the discovery layer today means nothing, and that meaning must survive.

### Acceptance

- A test storing a descriptor with `"affordances": []` in a binding and asserting it reads
  back as *serves everything*, including through `Registry`.
- A test asserting a descriptor written *today* with `affordances=[]` still means *serves
  nothing* — `tests/conformance/test_discoverers.py` already has
  `test_binding_that_won_no_affordances_serves_none`; it must keep passing.
- `uv run python scripts/emit_schema.py` produces no diff in `schemas/`, or the diff is
  committed alongside.

---

## Defect 3. `maiku describe --as json --grant` emits a document that cannot be read back

**Severity: P2.** Introduced by an earlier fix.

`maiku describe X --as json` prints the participant's descriptor. It takes an optional
`--grant`, which restricts the output to the affordances a given caller could actually
invoke. The filtering is implemented in `_json_view` at `src/maiku/cli/main.py:137`: it
dumps the descriptor, replaces `d["affordances"]` with the visible subset, and prints it.

The `id` is left as the original. `affordances` is *inside* the identity hash (Rule 1), so
the printed document declares an id that does not match its own contents. Loading it back
fails the tamper check — which is working correctly; the document really is inconsistent.

### Reproduce

```bash
H=$(mktemp -d)
uv run maiku add python:tests.fixtures.sample_module --home "$H" >/dev/null
uv run maiku describe test/sample --as json --grant 'test/sample#fetch' --home "$H" \
  2>/dev/null > /tmp/narrow.json

uv run python -c "
import json
from maiku.descriptor import ParticipantDescriptor
payload = json.load(open('/tmp/narrow.json'))
print('declared id :', payload['id'])
try:
    ParticipantDescriptor(**payload); print('reloads : yes')
except Exception as exc:
    print('reloads : NO ->', str(exc).splitlines()[1].strip()[:80])
"
```

Observed:

```
declared id : mk:ac500b0d8f8c4015f95902177ba41e8e
reloads : NO -> Value error, declared id 'mk:ac500b0d...' does not match content hash 'mk:67b0b948...'
```

Without `--grant` the output is unfiltered and reloads fine. The bug only appears on the
path the flag exists to serve.

### Expected

Pick one and argue it in the commit message:

- **Omit `id`** from a filtered dump. Honest — this is a view, not a document — but callers
  parsing the output lose the field.
- **Recompute `id`** for the filtered document, so it is a valid descriptor of a smaller
  participant. Coherent under Rule 2: this genuinely is what the participant is, for that
  caller.
- **Refuse to filter this format**, and say so on stderr.

Whichever you choose, `--as json` must never emit a document that fails its own check.
Check `--as maiku` (the human-readable view, `render.detail`) for the same class of problem
while you are there.

### Acceptance

A test that `--as json --grant <spec>` output round-trips through
`ParticipantDescriptor(**payload)`, or — if you chose to omit `id` — that the field is
absent and the rest still validates.

---

## Defect 4. A rewritten identity is not recorded anywhere

**Severity: P3.**

`Registry._parse_descriptor` (`src/maiku/runtime/registry.py:337`) does the right thing
with a descriptor whose declared id was computed under a superseded hash rule: it
re-derives the id and rewrites the row. But it does so silently. The row is not unreadable,
so it does not appear in `Registry.unreadable` (`registry.py:132`), and nothing logs it.

Rewriting a stored identity is a real mutation of the operator's data. The standing rule is
that nothing is silently dropped or changed.

### Expected

Re-derived rows are surfaced the way unreadable rows already are — a companion to
`unreadable`, reported by `maiku ls` once, with the old and new id. Do not turn it into a
failure; re-deriving is correct behaviour, it just needs to be visible.

### Acceptance

A test asserting that reading a stale row records the handle and both ids, and that `maiku
ls` mentions it.

---

## Defect 5. `maiku ls` prints an entire pydantic error per unreadable row

**Severity: P3.**

Reproduce by corrupting a stored descriptor:

```bash
H=$(mktemp -d)
uv run maiku add python:tests.fixtures.sample_module --home "$H" >/dev/null
uv run python -c "
import sqlite3
db = sqlite3.connect('$H/registry.sqlite')
db.execute(\"UPDATE participants SET descriptor = '{\\\"kind\\\": \\\"nope\\\"}'\")
db.commit()"
uv run maiku ls --home "$H"
```

Observed: a warning line followed by every field-level validation error, several lines per
row. **Expected:** one line per unreadable row — handle and a short reason. The full detail
can stay available programmatically on `Registry.unreadable`.

---

## Part 5. Definition of done

Per defect:

- The reproduction above runs clean. Paste the before and after output.
- A test exists that fails without your fix and passes with it. Confirm the failure first.
- `uv run pytest -q` green and `uv run ruff check src tests examples` clean.
- `uv run python scripts/emit_schema.py` leaves `schemas/` unchanged, or the change is
  committed with it.
- Committed and pushed, one logical unit per commit, in the house style, no
  `Co-Authored-By` trailer.

In your final report:

- What you fixed, with the output that proves it — not a description of the change.
- Every decision where this brief offered options: which you chose and why.
- Anything you found that is not in this brief.
- Anything you could not fix, and what blocked you. A defect left open and named is a
  better outcome than one papered over.

Two of these defects exist because a change was made without asking what already-written
data means under the new rule. Before you finish, check your own changes against that
question.
