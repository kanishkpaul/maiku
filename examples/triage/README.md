# Frame triage

Five participants, one task, nothing in common.

```bash
uv run python -m examples.triage.run          # scripted approvals
uv run python -m examples.triage.run --ask    # approve at the terminal
```

## Who is in the room

| Participant | What it is | What it deals in |
|---|---|---|
| `demo/vision` | a Python module | files in, tensors out — no prompt anywhere |
| `mcp/fixture` | an MCP server, unchanged | JSON-RPC over stdio |
| `human/reviewer` | a person | approvals, at human latency |
| `ollama/*` | a local LLM, **if one is running** | streaming text |

The LLM is optional on purpose. If Ollama is reachable the summary is written by a model;
if not it is written by arithmetic, and the report says which. Stubbing a model and calling
that a demo of model integration would prove nothing.

## What it shows

1. **A classifier stays a classifier.** `classify` takes an artifact digest and returns a
   logit vector. It never becomes a chatbot to participate.
2. **Files move by reference.** Frames are content-addressed artifacts; a participant reads
   only the digests granted to that call.
3. **Delegation narrows.** The pipeline holds a grant covering four affordances with a
   `write` ceiling. When it tries to publish, it is refused — not by a prompt, by the grant.
4. **Irreversible work stops for a person.** Publishing is `side_effects: irreversible`, so
   it routes to `human/reviewer#approve`, which is an ordinary call and shows up in the task
   log as one.
5. **It is all one trace.** The run ends by printing every task, including the one that was
   correctly refused.

## The same participants, from Claude Code

Nothing above is maiku-specific from the client's side:

```bash
maiku add python:examples.triage.participants
maiku serve mcp
```

Every affordance is now an MCP tool. The classifier is callable from any MCP client, still
as a classifier.
