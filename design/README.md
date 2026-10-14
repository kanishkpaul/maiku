# maiku

*The universal kawaii adapter (0w0/).* Maiku puts models, tools, services, people and devices
into one workspace where their capabilities, authority and results are readable. It is the
project closest to Hermes's original spirit: serious machinery with a playful face.

| | |
|---|---|
| Default skin | **Sakura** (`sakura`): pink `#FF8FC7` and mauve on plum-black; deep rose `#C2307A` on blush paper in light |
| Glyph | ✿ (mascot: `(0w0/)`) |
| Kawaii | **Full.** Faces in the spinner, empty states, onboarding and the mascot |
| Mode | Follows the OS |
| Surfaces | `maiku` CLI (Rust), web app (Svelte 5, plain CSS), optional Tauri 2 shell |
| Uses | `base.css`, `skins.css`, `components.css`, `loader.js`, `rust/theme.rs` |

## Feel

- Friendly at rest, precise under load. The mascot greets you; it never stands between you
  and an approval.
- Every participant looks like it belongs to the same system, whether it is a model, a shell
  command, a person or a sensor. Kind is shown by icon and badge, not by a different card style.
- Authority is always legible. Who can do what, and who approved it, is never hidden behind
  cuteness. The product doc says it directly: keep the playful identity "without making
  authority or uncertainty ambiguous."

## Layout

```
┌ participants ──┬ composition ──────────────────────────────┬ inspector ──────┐
│ ✿ search       │                                           │ ◉ whisper-large │
│ models         │   [audio] ──▶ [whisper] ──▶ [verifier]    │ kind  model     │
│  ◉ whisper     │                    │            │         │ can   transcribe│
│  ◉ qwen3-8b    │                    ▼            ▼         │ needs audio/*   │
│ tools          │               [you: review] ──▶ [artifact]│ authority  none │
│  ◉ ffmpeg      │                                           │ cost  local     │
│ people         │───────────────────────────────────────────│ ── runs ──      │
│  ◉ you         │ run log  ┊ ▶ invoke  whisper   2.1s       │ #14  ok   3.2s  │
│ devices        │          ┊ ⏸ await   you: review          │ #13  denied     │
└────────────────┴───────────────────────────────────────────┴─────────────────┘
 local · 3 participants · 1 waiting on you · rust 0.4.0
```

- **Sidebar: participants**, grouped by kind (models, tools, services, people, devices,
  saved compositions). Each row: status dot, name, a `.badge--muted` for where it runs.
- **Main: the composition canvas.** Nodes are flat `.widget` tiles with a 3px radius, not
  rounded cards. Edges are 1px `--ui-stroke-1`; an edge that needs a transformation is dashed
  and labelled with it; an edge with insufficient information is dotted in `--ui-warn` with a
  "Needs clarification" badge. These three states are the product's honesty about meaning.
- **Bottom of main: the run log**, `.tool-row`s in a `.tool-stack`, newest at the bottom.
- **Rail: the inspector** for the selected participant or run. Capability list in mono.

## Key screens

- **Home (empty).** `.wordmark` "MAIKU" fitted to the column, `(0w0/)` beneath in
  `--ui-text-accent`, then three starting points (the reference workflows: research, physical,
  software) as `.row`s. No feature tour.
- **Add participant.** A `.float` sheet: paste a URL, a command, an OpenAPI file or a model ID.
  Discovered capabilities stream in as rows. Anything undeclared shows as `unknown`, never
  guessed. "Add" is the primary button; it stays disabled until at least one capability is
  confirmed.
- **Approval.** The person-as-participant moment. `.approval.float`: the exact operation in
  mono (`device.valve_3.open(duration=30s)`), the requesting participant, the consequence, then
  Approve / Deny. No faces on this card.
- **Run detail.** A timeline of every call with authority, inputs, outputs and artifacts. Each
  artifact opens in the rail, never automatically.

## Project components

- `ParticipantNode`: `.widget` + kind icon + name + port list. Ports in mono at `--text-2xs`.
- `Edge`: three styles for direct / transformed / insufficient, as above.
- `AuthorityChip`: `.badge--outline` naming the scope (`read`, `invoke`, `actuate`). Actuate is
  always `.badge--warn`.
- `MascotFace`: picks from the skin's faces by state (idle, thinking, done). Hidden under
  `prefers-reduced-motion` only if it animates.

## Terminal

Banner: the six-row MAIKU block letters in sakura gradient. Prompt `❯`, label ` ✿ maiku `.
Spinner faces `(0w0/)`, `(｡◕‿◕｡)`, `(0w0)?`, `(・・?)`; verbs: adapting, wiring, handshaking,
translating, composing, negotiating, bridging, listening. Tool verbs: `invoke`, `stream`,
`read`, `await`, `approve`, `emit`.

```
  ┊ 🔌 invoke    whisper-large  audio/interview-03.m4a  2.1s
  ┊ ✋ await     you: review transcript
```

## Words

Warm, short, a little playful in greetings and empty states; plain everywhere else.
- Empty: "Nothing connected yet. Add a model, a tool or a person to start. (0w0/)"
- Approval: "qwen3-8b wants to write `report.md`. This replaces the existing file."
- Unknown: "Capabilities unknown. The service didn't declare an interface."

## Don't

- Don't put faces on approvals, errors, costs or anything about a person.
- Don't make nodes rounded bubbles. The canvas is flat and near-square like the rest.
- Don't show an adapter count or "connected to 200+ services" anywhere.
