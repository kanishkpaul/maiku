# maiku bug-fix brief

Eleven verified defects, ordered. Written to be executed by an agent that was not present
when they were found, so every one carries its own reproduction. Nothing here is a
refactor and nothing here is new feature work.

**Every defect below was reproduced by running code.** Reproduce it yourself before fixing
it, and paste the output. Do not fix from the description alone.

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

Environment is `uv`. The two commands that gate everything:

```
uv run pytest -q
uv run ruff check src tests examples
```

Both are green right now (485 passed). None of the defects below is caught by the suite —
that is part of what makes them defects. Every fix ships with a test that fails before it
and passes after.

### The four rules that decide code

When an implementation choice is unclear, resolve it against these in order. If you think
a rule is wrong for a particular fix, stop and say so in your summary rather than working
around it.

1. **Identity is capability alone.** A participant is what it affords. Not where it runs,
   not what it is called, not who made it. The content hash excludes `runtime`, `bindings`,
   `display`, `provenance`, `liveness`, `signature`.
2. **An affordance is a relation, not a property.** There is no "what this participant can
   do", only "what it can do for this caller". A grant is what brings an affordance into
   existence; it is not a filter applied afterwards.
3. **Derived, never declared.** Capability is read from what a thing publishes about
   itself. Where nothing is published, maiku reports that it could not read. It never
   guesses.
4. **The instrument shows the field, it does not choose within it.** No planner, no
   automatic composition, no capability matching from schemas.

Two standing requirements that several of these defects violate:

- **Never guess.** A failed read names every source tried and what each returned.
- **Never silently drop.** Anything discarded is recorded, not dropped.

### House style

- Comments say **why**, never what or how. If a comment restates the code, delete it.
- Modular over monolithic. Small functions with real names.
- Tests ship in the same commit as the code they cover, never afterwards.
- Commit messages: lowercase area prefix, one line, describing what changed rather than
  what was added. Examples from the log: `registry: a capability change under a known
  handle is reported, not overwritten in silence`, `discovery: a binding names the
  affordances it actually serves`.
- **Do not add a `Co-Authored-By` trailer.** Do not add "Generated with" footers.
- Commit and push after each logical unit, not in one batch at the end.

### Out of scope

Do not start new feature work. In particular there is a build document at
`docs/designs/maiku-v2-build.md` describing Stages 5 and 6 (properties and events in the
router, W3C WoT discovery). **Do not begin either.** Do not rename things, do not
restructure modules, do not "improve" code you are not fixing.

---

## Group A. The registry cannot read what it wrote

These three are one piece of work and should be done together, first. Everything else in
the project writes registry rows, so this compounds.

### A1. Descriptors written before the identity change are unreadable

**Severity: P0.**

`src/maiku/descriptor/participant.py:172` — `_verify_declared_id` rejects any descriptor
whose serialized `id` does not match a freshly computed hash. This is a deliberate tamper
check and it should stay.

The problem is that the hash changed. `VOLATILE_FIELDS` in
`src/maiku/descriptor/canonical.py` recently gained `bindings`, `display` and `provenance`,
so every descriptor persisted before that change now fails to load. `Registry._entry`
(`src/maiku/runtime/registry.py:288`) validates on every read, so an existing
`~/.maiku/registry.sqlite` is now unreadable.

**Reproduce:**

```python
import json, sqlite3, sys, tempfile
from pathlib import Path
sys.path[:0] = ["tests", "."]
from maiku.runtime.registry import Registry
from tests.conftest import make_descriptor

d = make_descriptor()
row = d.model_dump(mode="json")
row["id"] = "mk:" + "a" * 32          # an id computed under the old rule

path = Path(tempfile.mkdtemp()) / "registry.sqlite"
with Registry(path) as r:
    r.add(d, "u")
    r._db.execute("UPDATE participants SET descriptor = ? WHERE handle = ?",
                  (json.dumps(row), d.handle))
    r._db.commit()

with Registry(path) as r:
    r.list()      # ValidationError
```

**Expected:** an existing home keeps working. A row whose declared id no longer verifies is
recognised as written under an older rule, re-derived, and rewritten — once, on read or on
open — rather than rejected.

**Constraint:** do not weaken `_verify_declared_id` for descriptors arriving over the wire.
A document handed to maiku by someone else must still be tamper-checked. The tolerance
belongs in the registry's own read path, which knows the row is its own.

**Acceptance:** a test that stores a pre-change descriptor and asserts the registry reads,
lists and re-hashes it; and that a *tampered* wire descriptor is still rejected.

### A2. One unreadable row breaks the entire listing

**Severity: P0.**

`Registry.list()` (`registry.py:246`) and `find()` (`registry.py:259`) build an `Entry` per
row and let the first validation failure propagate.

**Reproduce:** as A1, but add a second, valid participant first. Then:

```
handles()            -> ['local/bad', 'local/good']
get(local/good)      -> ['local/good']
list()  [maiku ls]   -> ValidationError
find('sentiment')    -> ValidationError
```

One row nobody can parse takes every other row with it. This inverts the standing rule: it
does not silently drop one row, it loudly drops all of them.

**Expected:** `list()` and `find()` return every row they can read, and the unreadable ones
are surfaced — named, with the reason — not swallowed and not fatal. `maiku ls` should
print the participants it has and then say which handles it could not read and why.

**Acceptance:** a test with one good row and one corrupt row asserting the good one is
listed and the bad one is reported by handle.

### A3. The capability-id migration half-applies and then goes quiet

**Severity: P1.**

`Registry._migrate` (`registry.py:125`) adds a `capability_id` column and backfills it from
each stored descriptor. Two faults:

1. It guards on the column being absent. The `ALTER TABLE` commits before the backfill
   runs, so if the backfill dies part-way the next open sees the column, returns early, and
   leaves every remaining row blank.
2. One unparseable descriptor aborts the whole backfill (same root cause as A1).

**Reproduce:** build an old-schema registry (columns: `handle, content_id, uri, kind,
descriptor, health, first_seen, last_seen`) holding one valid row and one row with a stale
`id`, then open it twice with `Registry`:

```
open 1: ValidationError
open 2: ValidationError
capability_id column present : True
  local/good   capability_id=''
  local/stale  capability_id=''
```

Blank `capability_id` means `by_capability_id` (`registry.py:234`) answers with silence for
those rows — exactly what its own docstring promises it will not do.

**Expected:** the backfill is per-row fault tolerant, and it runs whenever rows are blank
rather than only when the column is missing. A row it genuinely cannot backfill is reported,
not left blank and forgotten.

### A4. `Registry.__init__` leaks its connection when it fails

**Severity: P1.** Same file, and cheap to fix while you are in there.

`registry.py:118` opens a sqlite connection; `registry.py:120` calls `_migrate`, which can
raise. Nothing closes the connection on that path, so within a single process the file stays
locked and the next open reports `database is locked`.

**Expected:** any failure during `__init__` closes the connection before propagating.

---

## Group B. A gateway gives away more than it should

### B1. `maiku serve a2a` hands every client the operator's root grant

**Severity: P1.**

`src/maiku/cli/main.py:218` constructs `A2AGateway(..., grant=session.root_grant)`. The
gateway machinery is grant-aware — it will serve exactly what a client's grant covers — but
`serve` has no way to supply one, and `src/maiku/gateways/http_server.py` has no
authentication at all. `maiku serve a2a --host 0.0.0.0` therefore publishes irreversible
authority over every adapted participant to anyone who can reach the port.

The MCP branch (`main.py:214`) is stdio and genuinely serves one local client. Leave it.

**Expected:** `serve` grows the same `--grant` option `describe` already has
(`main.py:53`, `grant_from`, which parses capability specs like `ns/name#affordance`).
Decide and state a default. Serving the root grant to a loopback listener is defensible;
serving it to `0.0.0.0` is not. At minimum, binding a non-loopback host without an explicit
grant should refuse or warn loudly.

**Acceptance:** a test that a gateway constructed the way `serve` constructs it honours a
narrowed grant, plus whatever guard you add for the non-loopback case.

### B2. The A2A card describes a participant to a caller who holds nothing

**Severity: P2.** Violates Rule 2 and is the information leak the caller-relative work
existed to close.

`A2AGateway.agent_card(slug)` (`src/maiku/gateways/a2a_server.py:102`) returns a full card
when the client's grant covers none of that participant's affordances.

**Reproduce:** build a session, adapt `python:tests.fixtures.sample_module`, issue
`session.grant("stranger", capabilities=[Capability.parse("somewhere/else#nothing")])`, then
ask both gateways:

```
mcp tools for a caller holding nothing : []
a2a card for the same caller           : a full card
  skills   : []
  but name : 'Sample'
      desc : 'A module exercising all four callable shapes an adapter must handle.'
      url  : 'http://localhost:8080/agents/test_sample'
      _meta: {'maiku/handle': 'test/sample', 'maiku/id': 'mk:ac500b0d...'}
```

MCP is correct. A2A discloses the participant's existence, name, description, URL and
content id.

**Expected:** a participant no affordance of which is visible to this caller does not
resolve for that caller. `agent_card(slug)` returns `None` — the same answer it already
gives when there is no grant at all — and the HTTP route 404s. Check `_aggregate_card`
in the same file behaves consistently (it already contributes no skills; confirm it also
leaks no participant names).

---

## Group C. Things that lie or go quiet

### C1. `maiku add http://device.local` fails confusingly instead of discovering

**Severity: P2.**

`http` is one of maiku's own schemes, so `ParticipantURI.parse` reads `http://device.local`
as scheme `http` with target `//device.local`, which `HTTPAdapter.open` then rejects:

```
$ maiku add http://device.local
error: '//device.local' is not an http(s) URL
```

Meanwhile `maiku add https://device.local` works — `https` is not a maiku scheme, so
`coerce` in `src/maiku/adapters/registry.py` sugars it to `auto:` and it goes through
discovery. The two most natural things an operator can type behave completely differently,
and the one that fails does so with a message about a URL it silently mangled.

The supported form for the HTTP adapter has always been `http:<url>` (note the single
colon, e.g. `http:https://api.example.com/openapi.json`); that is what the existing tests
use and it must keep working.

**Expected:** `maiku add http://host` reaches discovery like `https://host` does, or fails
with a message that names both the `http:<url>` form and the `auto:` form. Decide which,
say why in the commit message, and keep `http:<url>` working either way.

**Acceptance:** tests covering `http://host`, `https://host`, `http:<url>` and a bare
`host:port`, each asserting which path it takes.

### C2. `--grant` is silently ignored by two of five output formats

**Severity: P2.**

`maiku describe X --as <fmt>` (`src/maiku/cli/main.py:112`) projects through the grant for
`mcp`, `a2a` and `openai`, and ignores it entirely for `json` and `maiku`:

```
$ maiku describe test/sample --as json --grant 'test/sample#fetch'
affordances shown: ['fetch', 'narrate', 'score', 'tokens']
```

**Expected:** either those two formats honour the grant as well, or passing `--grant` with a
format that cannot honour it says so instead of quietly producing the unfiltered document.
The second is acceptable and cheaper; a flag that silently does nothing is not.

### C3. A binding that won no affordance claims all of them

**Severity: P2.**

`Binding.serves` (`src/maiku/descriptor/binding.py:37`) treats an empty `affordances` list
as "no restriction". `_binding` in `src/maiku/discovery/assemble.py:158` sets that list to
the names a reader actually won. A reader whose every affordance lost a schema conflict
therefore ends up with an empty list, which means "everything".

**Reproduce:** two fake discoverers at precedence 30 and 20 both reading one affordance
named `classify` with different input schemas:

```
openapi  serves: ['classify']
mcp      serves: EVERYTHING (an empty list means no restriction)
```

It does not misroute today, because `binding_for` returns the precedence-ordered winner
first. But `maiku describe` prints `serves: all` for that binding, which is false.

**Expected:** a binding that serves nothing says so. Consider whether `serves()` needs to
distinguish "unrestricted" from "empty", or whether assembly should omit such a binding and
record why under `extensions["maiku.discovery"]` — the union-of-bindings rule says every
reading contributes a binding, so record rather than drop, and read
`docs/designs/maiku-v2-build.md` Stage 3 rule 3 before choosing.

### C4. A discoverer that reads nothing produces a validation error, not a legible failure

**Severity: P3.**

If every discoverer returns a `Reading` with an empty `affordances` list, `discover()` in
`assemble.py` builds a `ParticipantDescriptor` with zero affordances and pydantic raises:

```
raises ValidationError: 1 validation error for ParticipantDescriptor
```

Neither shipped discoverer can trigger this — both raise `NotReadable` when they find
nothing — but a third-party one would, and `tests/conformance/discoverer_contract.py` does
not cover it.

**Expected:** an assembly that ends with no affordances raises `NothingReadable`, naming
every source and what each returned, like every other failed read. Add the case to
`DiscovererContract`.

### C5. A mistyped `--grant` looks exactly like a caller holding nothing

**Severity: P3.**

```
$ maiku describe test/sample --as mcp --grant 'test/sampl#fetch'
[]
(exit 0)
```

A typo in the participant handle is indistinguishable from a correct spec for a caller with
no access. **Expected:** a `--grant` spec naming a participant that is not the one being
described should say so. Do not make it an error if the grant legitimately covers other
participants — a note on stderr is enough.

### C6. Single-label hostnames cannot be discovered

**Severity: P3.**

`looks_like_an_address` in `src/maiku/adapters/registry.py` requires a dot, or the literal
`localhost`, before treating a bare string as an address:

```
myserver         -> InvalidURI: no adapter for scheme 'myserver'
myserver:8080    -> InvalidURI: no adapter for scheme 'myserver'
localhost        -> auto
```

This exists for a good reason: it is what stops a mistyped `ollma:qwen3` from being treated
as a hostname and producing a discovery error about a host that was never meant to be one.
But `raspberrypi:8080` is exactly the LAN-device case discovery is aimed at.

**Expected:** your call, argued in the commit message. A numeric port is a reasonably strong
signal that the left side is a host. Whatever you choose, `ollma:qwen3` must still fail with
`no adapter for scheme 'ollma'`, and there must be tests for both.

---

## Part 5. Definition of done

Per fix:

- The reproduction above runs clean, and you have pasted the before/after output.
- A test exists that fails without the fix.
- `uv run pytest -q` green and `uv run ruff check src tests examples` clean.
- Committed and pushed, one logical unit per commit, in the style above, with no
  `Co-Authored-By` trailer.

Overall, report:

- What you fixed, with the output that proves it.
- Anything you chose differently from this brief, and why.
- Anything you found that is not in this brief.
- Anything you could not fix, and what blocked you. Say it plainly; a defect left open and
  named is a better outcome than one papered over.

Do not report a fix as done from reasoning. Report it from output.
