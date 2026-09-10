# Live control-room test

This is an integration test of the actual local Maiku demo, not a mocked browser flow. It
starts the FastAPI control plane and Vite UI together, adapts the prepared recipes, runs the
evidence case, and records the human choices and approval through the browser channel.

## Prerequisites

- A local OpenAI-compatible Gemma server is available at `http://127.0.0.1:8081/v1` and
  exposes the model name `cassia`.
- Node/npm and `uv` are installed.

The launch command fetches MNIST's test split automatically on its first run. It does not
retrain the included CNN checkpoint.

## Watch the full automated run

```bash
cd /Users/kanishk/Documents/ChatGPT/maiku
git switch tests-gui
uv sync --extra web --extra net --extra torch --group dev
npm install
npx playwright install chromium
npm run test:gui:headed
```

It takes a little over two minutes because the normal product demo deliberately paces eleven
visible stages. The test prints each milestone and retains a trace, video, and screenshot if
it fails under `test-results/`.

## Run it yourself in Safari

```bash
npm run demo:live
```

Then open `http://127.0.0.1:5173`. Use the Participants tab to add the five prepared
non-human recipes individually (or **autoload the prepared five**), add **You** from Human
desk, start the case, and answer the two choices plus the final approval. The local report is
written to `.maiku-live-demo/casebook/reports/evidence-report.md` only after approval.
