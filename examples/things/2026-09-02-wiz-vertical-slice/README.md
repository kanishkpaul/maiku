# WiZ physical vertical slice

This is one deliberately narrow, real path through Maiku:

```text
DigitCNN -> local language model -> human approval -> WiZ write -> WiZ push event
```

The light is a Philips Smart Wi-Fi bulb powered by WiZ, not a Hue Bridge light. Bluetooth
is used by the WiZ app during first-time commissioning; after that, Maiku reaches the bulb
directly over Wi-Fi using WiZ's local UDP API. No WiZ cloud credential is stored or required.

## Before running

1. Pair the bulb in the WiZ app and leave it powered on.
2. Put this machine on the same local network as the bulb.
3. In WiZ, leave local communication enabled.
4. Start the local OpenAI-compatible model expected by `examples/real` on port 8081.
5. Prepare the CNN once if its weights are absent: `uv run python -m examples.real.cnn`.

Discovery is automatic when exactly one WiZ light is visible. If broadcast discovery is
blocked or several lights answer, set the bulb's LAN address explicitly:

```bash
export WIZ_BULB_IP=192.168.1.50
```

Then run:

```bash
uv sync --extra wiz --group dev
uv run python examples/things/2026-09-02-wiz-vertical-slice/run.py
```

The program reads the current light state, classifies a real MNIST sample, asks the local
language model for a bounded rationale, and proposes a brightness. The write is not sent
until the CLI human participant approves it. A concurrent WiZ subscription records the
light's own pushed state update. The JSONL trace contains every runtime event, approval,
task record, before/after state, and observed device event.

If discovery returns no bulb, verify that the computer is not on guest Wi-Fi or a VPN and
that WiZ local communication is enabled. Direct-IP mode avoids networks that block UDP
broadcast but still requires local reachability to the bulb.
