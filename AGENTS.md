# Repository instructions

This branch preserves the implementation at
`3475192e838a6dcac89947c58743d2f0a76916f0`. New development belongs on `main`.
Read [README.md](README.md) before changing anything here. Do not port the rebuild
into this branch or alter historical code without an explicit legacy task.

Never add coding-agent attribution anywhere in new work. This includes Claude
Code, Claude, Codex, Copilot, and every other coding agent. Do not add
`Co-Authored-By` trailers, generated-by signatures, agent authors, or agent credits
in commits, code, documentation, pull requests, or releases. Use the configured
human Git identity. Do not rewrite historical commits as part of ordinary work.

For an authorized legacy code change, run the relevant tests, then
`uv run pytest -q` and `uv run ruff check src tests`. Report missing model or
hardware prerequisites honestly. Existing adapters must pass their conformance
contract; do not substitute fixtures for claims about real hardware.
