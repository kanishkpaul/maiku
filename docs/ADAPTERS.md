# Writing an adapter

Four methods. Everything else — authorization, validation, artifact scoping, human
escalation, sequencing, cancellation, tracing — is the runtime's job.

```python
from maiku.adapters import Adapter, register

@register
class MyAdapter(Adapter):
    scheme = "mine"

    @classmethod
    async def open(cls, uri): ...          # connect; called once
    async def describe(self): ...          # produce the descriptor
    def invoke(self, affordance, arguments, ctx): ...   # async generator of events
    async def probe(self): ...             # optional; defaults to describe()
    async def close(self): ...             # optional
```

Register the scheme lazily in `BUILTIN_SCHEMES` (`src/maiku/adapters/registry.py`) so
`import maiku` stays free of your dependency.

## The rules

**Derive the descriptor; do not ask for one.** Reuse `maiku.adapters.introspect` for Python
objects. Every registry that required hand-authored metadata died of it.

**Never raise into the caller.** Raise `AdapterError` (or a subclass) and `guarded()` converts
it to a `Failed` event. Anything else becomes a generic failure with the exception's text.

**Yield exactly one terminal event.** Or none — `guarded()` appends `Finished()` if you
finish quietly. It also drops anything after a terminal event.

**Keep blocking work off the loop.** `await asyncio.to_thread(...)`. A blocking forward pass
stalls every other participant in the session.

**Check `ctx.raise_if_cancelled()`** inside any loop.

**Be honest in the descriptor.** `side_effects`, `determinism` and `device` are what the
runtime and other participants act on. Declaring `cuda` on a machine with `mps`, or `none` on
a call that posts to Slack, is the kind of small lie that makes the whole registry untrustworthy.
When you do not know, say the more cautious thing — the MCP adapter treats an unannotated tool
as `write`, not `none`.

## What `ctx` gives you

```python
await ctx.artifacts.read(digest)                 # only what was granted
await ctx.artifacts.write(data, media_type=...)  # self-granting
await ctx.ask("which of these?")                 # reaches a person
await ctx.approve("delete the bucket", side_effects="irreversible")
ctx.emit(Progress(message="halfway"))            # out-of-band events
ctx.raise_if_cancelled()
ctx.remaining                                    # seconds left, or None
```

`ask` and `approve` work from a plain function — you do not have to be a generator to talk to
a human.

## Conformance

Subclass the contract and supply two fixtures:

```python
class TestMine(AdapterContract):
    @pytest.fixture
    async def adapter(self):
        adapter = await open_participant("mine:something")
        yield adapter
        await adapter.close()

    @pytest.fixture
    def sample_call(self):
        return "do_thing", {"x": 1}
```

You then inherit checks for descriptor validity, hash stability, binding coverage, probe
honesty, stream discipline, sequencing, unknown affordances, argument rejection, cancellation
and projection to MCP, OpenAI and A2A.

Twelve adapters written to a convention become twelve dialects. Written to a suite, they stay
one protocol.

## Test against the real thing

Where a stub is unavoidable, make it speak the actual protocol.
`tests/fixtures/mcp_server.py` is a genuine MCP server doing a real initialize handshake;
the HTTP and A2A adapters run against `httpx.MockTransport` with real request and response
shapes. Mocking your own adapter's expectations proves only that you are consistent with
yourself.
