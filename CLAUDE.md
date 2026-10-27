# Repository instructions

Read and follow [AGENTS.md](AGENTS.md). It is the authoritative instruction file
for every coding assistant in this repository. Also read
[docs/CODING_STYLE.md](docs/CODING_STYLE.md) before writing code or comments.

New development belongs on `main`; `old` is the preserved implementation.
Use the decided Rust core and optional-worker architecture. Do not quietly
restore the Python runtime, flatten every participant into chat, or invent
schemas for undocumented systems.

Read [the thesis](docs/THESIS.md) and [status](docs/STATUS.md). The owner's build
plan is local at `.local/BUILD_PLAN.md` when available; never publish it or copy
its backlog into tracked files. Public contracts and the assigned task are enough
for contributors without that file. Keep declarations, inferred mappings,
verification evidence, and operator authority separate. An adaptation proposal
must be verified within permitted conditions before activation.

Never add Claude Code or any other coding-agent attribution. No coauthor
trailers, generated-by signatures, agent authors, or agent credits may appear
in new commits, code, documentation, pull requests, or releases. Preserve
existing history and legitimate third-party license notices.

Install the local hook and run the repository and new-commit checks described in
AGENTS.md. Review the actual diff and report verification accurately.
