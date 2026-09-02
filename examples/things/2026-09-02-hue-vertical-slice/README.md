# The first physical Maiku trace

This is one deliberately narrow proof:

```
DigitCNN -> local language model -> human approval -> Hue write -> Hue event
```

The orchestration is explicit Python. This does **not** claim automatic composition. It
tests whether a model, a person and a physical light can use the same descriptor, grant,
approval, task and event machinery without a privileged device side door.

## Hardware boundary

The Hue CLIP v2 API runs on a Hue Bridge on the local network. A Bluetooth-only bulb with
no bridge cannot run this example. The adapter uses the supported local HTTPS resource API
and its SSE event stream. The bridge application key is read from an environment variable
and never enters the descriptor, registry or trace.

Discover the bridge using the official Hue app or mDNS, press the bridge link button, and
create an application key following the Hue developer setup. Then export:

```bash
export HUE_BRIDGE_URL=https://192.168.x.x
export HUE_APPLICATION_KEY=...
export HUE_LIGHT_ID=...    # optional when the bridge contains exactly one light
```

Start the local model and prepare the already-committed CNN:

```bash
llama-server -m <gemma-or-compatible-gguf> \
  --host 127.0.0.1 --port 8081 -c 8192 -ngl 99 --jinja
uv run python -m examples.real.cnn
```

Run the trace:

```bash
uv run python examples/things/2026-09-02-hue-vertical-slice/run.py
```

The write always stops at the terminal for a human decision. Approval changes the light,
then the run waits for the bridge to report that change independently on its event stream.
The JSONL trace is written under `/tmp` by default. A denied write is also recorded and the
bulb is not changed.

## Honest success condition

Success requires all five facts in one run:

1. the CNN returns a real classification;
2. the local language model explains the proposed signal without claiming vision;
3. `human/reviewer` approves the state-changing affordance;
4. the Hue read after the write reports the requested state;
5. the Hue event stream independently emits an update for the same light.

Tests use protocol-faithful mock bridge responses. They prove dispatch, authorization,
approval and cancellation, but they do not count as the physical trace.
