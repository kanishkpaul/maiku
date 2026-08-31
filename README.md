# maiku

*the universal kawaii adapter \\(0w0/)*

**Add anything intelligent, and it can work with everything else.**

maiku turns any system that computes — a frontier model, a local LLM, a PyTorch module, a
Hugging Face pipeline, an MCP server, a REST API, a command-line tool, a remote A2A agent, a
Python function, or a person — into a **Participant**: one descriptor, one call convention,
one event stream.

It does not make everything a chatbot. A classifier stays a classifier. A video model stays
a video model. A person stays a person. Only their *capabilities* become legible in a common
format, so the runtime can route work between them, share files, check permissions, and stop
for a human when it should.

```
anything that computes  →  Adapter  →  Participant  →  shared runtime
```

## Install

```bash
uv sync
```

Heavy runtimes are optional extras: `maiku[torch]`, `maiku[hf]`, `maiku[llm]`, `maiku[net]`.
`import maiku` pulls in none of them.

## Sixty seconds

```bash
maiku add python:mypackage.scoring          # a module becomes a participant
maiku add ollama:qwen3:8b                   # a local model
maiku add "mcp:npx -y @modelcontextprotocol/server-filesystem ./work"
maiku add "human:you?channel=cli"           # yes, a person

maiku ls
maiku find "transcribe audio"
maiku call mypackage/scoring score --arg text="how did we do"
maiku serve mcp                             # all of it, as MCP tools
maiku serve a2a                             # or as an A2A agent
```

That last line is the point. Adapt a PyTorch model and Claude Code can call it — still as a
model, not as a chatbot.

See [`examples/triage`](examples/triage/README.md) for five participants collaborating on
one task, including the moment the runtime refuses an over-reaching call.

## The model

**Descriptor** — one JSON document per participant: who it is, what it can do, what it takes,
what it returns, where it runs, whether it is up, what it may do, and how to reach it. The id
is a content hash over what a participant *is and can do*, so moving a model to another host
does not mint a new participant, and a descriptor read back off disk verifies itself.

**Affordance** — one thing a participant can do. Four kinds, borrowed from
[W3C Web of Things](https://www.w3.org/TR/wot-thing-description11/): `invoke`, `stream`,
`property`, `event`. That vocabulary is what survives non-chatbots — a classifier invokes, an
LLM streams, a robot joint is a property, a monitor emits events.

**Events** — every call, whatever it is underneath, is a stream of the same events:
`Started · Progress · Delta · ArtifactWritten · NeedsInput · NeedsApproval · Log · Usage ·
Finished · Failed`, terminating exactly once. This is the load-bearing abstraction: it is why
a video model and a coding agent are commensurable.

**Artifacts** — content-addressed. Participants exchange digests, never payloads, which keeps
large files out of the message log and makes "this participant may read that file" something
the runtime can actually enforce.

**Grants** — attenuated capability tokens. A derived grant may only *narrow*: fewer
capabilities, fewer scopes, fewer artifacts, a lower side-effect ceiling, an earlier expiry.
Bounded delegation is the thing MCP, A2A and ACP all leave to trust.

## Adapters

| Scheme | Adapts | Example |
|---|---|---|
| `python` | a function, object, or whole module | `python:mypkg.mod:score` |
| `openai` `ollama` `lmstudio` `vllm` `openrouter` | anything speaking the OpenAI chat format | `ollama:qwen3:8b` |
| `mcp` | an MCP server over stdio | `mcp:npx -y @some/server` |
| `a2a` | a remote A2A agent | `a2a:https://host/.well-known/agent-card.json` |
| `http` | a REST API, with or without OpenAPI | `http:https://api.host/openapi.json` |
| `cli` | any binary; the template is the schema | `cli:wc -l {path}` |
| `torch` | an `nn.Module` or TorchScript file | `torch:mypkg:Model` |
| `hf` | a Hugging Face pipeline | `hf:openai/whisper-tiny?task=automatic-speech-recognition` |
| `human` | a person | `human:you?channel=cli` |

Descriptors are **derived**, not written. A Python signature becomes an input schema, a
docstring becomes the summary, a generator becomes a streaming affordance, an OpenAPI
operation becomes an affordance, an MCP annotation becomes a side-effect class. A descriptor
someone has to hand-author is a descriptor nobody writes — that is the lesson of every
service registry that came before this one.

## It speaks the ecosystem's languages

The descriptor is a superset with projections, not a rival format:

```bash
maiku describe local/vision --as mcp      # MCP tools
maiku describe local/vision --as a2a      # A2A AgentCard
maiku describe local/vision --as openai   # OpenAI function tools
```

Both directions work, and there are tests for the round trips: an ingested MCP server can be
served back out over A2A; an ingested A2A agent can be called as MCP tools. Calls emit
OpenTelemetry spans using the GenAI conventions when the SDK is installed, and stay silent
when it is not.

## What this does not do

- **No automatic composition.** `maiku find` is search over what participants say about
  themselves, not a planner. Automatic capability matching from schemas has never worked and
  claiming otherwise is how registries lose trust.
- **Sandboxing is partial.** Subprocess adapters run with declared roots and egress, which is
  not a boundary against hostile code. microVM/WASM isolation is designed for, not built.
- **Local-first.** One machine, a SQLite registry, remote participants reached as clients.
  Cross-host federation is designed for, not built.

## Development

```bash
uv sync --group dev
uv run pytest -q
uv run ruff check src tests
```

Every adapter subclasses one conformance contract (`tests/conformance/contract.py`) covering
descriptor validity, hash stability, stream discipline, cancellation, schema enforcement and
projection. Twelve adapters written to a convention become twelve dialects; written to a
suite they stay one protocol.

Further reading: [the design](docs/SPEC.md) · [the landscape](docs/LANDSCAPE.md) ·
[writing an adapter](docs/ADAPTERS.md)
