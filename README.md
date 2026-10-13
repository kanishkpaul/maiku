# maiku — preserved implementation

This is the `old` branch. It preserves the Python runtime, adapters, schemas,
tests, examples, and React control-room demo from main at
`3475192e838a6dcac89947c58743d2f0a76916f0`.

New development happens on [main](https://github.com/kanishkpaul/maiku/tree/main).
The rebuild keeps Maiku's ambition: bring models, services, tools, people, and
physical systems into one composable workspace. The new direction is free and
open source, with a Rust core and optional integrations.

## What is preserved

- Derived participant descriptors and capability identities.
- Python, CLI, HTTP, MCP, A2A, local/hosted model, Torch, Hugging Face, and human adapters.
- A grant-checked router, human escalation, shared sessions, typed artifacts,
  delegation, protocol projections, and a SQLite registry.
- The conformance suite and real-system examples.
- The prepared live control-room frontend and its backend.

All 165 tracked files from the baseline remain at their original paths except
this README. The baseline README is copied verbatim to
[docs/archive/original-readme.md](docs/archive/original-readme.md).
This branch changes documentation only; it does not merge other development branches.

## Run the preserved project

```sh
git switch old
uv sync --group dev
uv run pytest -q
uv run ruff check src tests
```

The baseline was checked on 2026-10-13: 501 Python tests passed and two skipped;
Ruff, TypeScript checking, and the frontend production build passed. This is
historical verification, not a guarantee for every future dependency environment.
The skipped cases require MNIST test images or a live model server.

For the browser demo, follow the prerequisites in
[the preserved README](docs/archive/original-readme.md) and
[the GUI test guide](tests/gui/2026-09-01-live-control-room/README.md).
The demo uses real local systems and may download MNIST images on first use.

## Known limits

`auto:` discovers descriptors but refuses execution; the session grant lookup
falls back to owner authority for unknown callers; discovery can merge conflicting
effect/scope declarations when schemas match; projected names can collide.
Sessions and approvals are not durable, remote authority is not cryptographically
verified, and this is not an isolation boundary for hostile code.

Physical property/event work is preserved separately on
[`codex/stage5-physical-vertical-slice`](https://github.com/kanishkpaul/maiku/tree/codex/stage5-physical-vertical-slice).
Its 32 targeted fixture tests passed on 2026-10-13. That does not verify a live
device today. Other historical branches remain separate references.

## Contribution policy

Use this branch for reference and explicit legacy fixes. Do not treat it as the
new architecture. See [AGENTS.md](AGENTS.md) for repository instructions.
Never add coding-agent attribution, generated-by signatures, or coauthor trailers
to new commits, code, documents, or release metadata. Existing Git history is
preserved; the branch transition does not rewrite earlier commits.
