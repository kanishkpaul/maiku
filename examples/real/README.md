# Four real participants

No fixtures. Every participant here is a real system that exists independently of maiku.

| Participant | What it actually is | How it is reached |
|---|---|---|
| `openai/cassia` | **Gemma 4 E4B**, 4-bit, on llama.cpp | OpenAI chat format over HTTP |
| `local/digits` | a **CNN trained here on MNIST** to 98.2% test accuracy | a Python object, in-process |
| `mcp/files` | **Anthropic's MCP filesystem server**, unmodified | JSON-RPC over stdio |
| `human/reviewer` | a person | a terminal prompt |

## Run it

```bash
llama-server -m ~/Models/gemma-4-e4b-qat/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 --port 8081 -c 8192 -ngl 99 --jinja
```

```bash
uv run python -m examples.real.cnn          # train the CNN (~1 min, downloads MNIST)
uv run python -m examples.real.run          # scripted approvals
uv run python -m examples.real.run --ask    # approve at the terminal
```

## What actually happened

Gemma was told to identify a digit and file a report. It was given the CNN and the
filesystem server as tools — in OpenAI tool-schema format, projected from their descriptors.
It knows nothing about maiku.

```
  mcp/files#read_text_file     {'content': 'camera 3 faces the loading bay; ...'}
  local/digits#sample_digit    sha256:e140790e533a...
  local/digits#classify        {'digit': 4, 'confidence': 0.999, 'runner_up': 9}
  mcp/files#write_file         {'content': 'Successfully wrote to report.md'}
```

> The digit in MNIST test image 42 was identified as 4 with a confidence of 0.999. This
> observation is consistent with the nightly logging procedures mentioned in notes.md.

That last sentence is the interesting one: Gemma tied the CNN's judgement to a note it read
through a different participant. The CNN independently agrees with the MNIST ground-truth
label, and Gemma asked alone cannot answer at all — *"I do not have the capability to access
or process external datasets."*

## What the runtime did about it

**The irreversible step stopped.** The MCP server declares `write_file` destructive; adapting
it with `?approval=on_scope` turns that declaration into a gate, so the write routed to
`human/reviewer#approve` before it happened. Nothing in Gemma or in the MCP server knows a
person was involved.

**The grant held.** The planner was granted five specific affordances. Asked to call
`ground_truth`, it was refused by the grant rather than by a prompt — and the refusal was
handed back so it could report the situation rather than fail silently.

**It is one record.** Every delegated call appears in the task log next to the human
approval, at the same level, because they went through the same door.

## What this exercise found

Running two real models against each other found a bug no test had: Gemma correctly chained
`sample_digit` into `classify`, and the second call could not read the artifact the first had
produced. A pipeline that cannot hand a file along is not a pipeline. The session is now the
sharing boundary for artifacts, with grants still governing what may be *done*.
