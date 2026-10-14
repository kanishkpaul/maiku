# 0002: Shared design system, copied into design/

Status: accepted on 2026-10-14.

## Problem

The web app, the optional desktop shell and the CLI need one visual and interaction
system. The owner's other projects need the same one. This repository must still
build and read on its own, without anything outside it.

## Alternatives

| Option | Strengths | Cost for this project |
| --- | --- | --- |
| Design locally | Full control | Drifts from the other projects and repeats their work |
| Git submodule of the master | One copy of the files | Extra clone step; awkward for contributors and coding agents |
| Package from a registry | Versioned releases | The master is not published |
| Copy this project's slice into `design/` with the kit tool | Self-contained; versioned in `design/kit.json`; local edits survive updates | Updating is a deliberate step |

## Decision

Copy the slice. `design/` holds Maiku's direction, the shared system documents,
CSS tokens and primitives, and the Rust terminal module. The master lives next to
this repository at `../design-kit`; `node ../design-kit/scripts/kit.mjs update .`
pulls its changes. No skin is chosen yet; the default is `sakura`.

## Consequences

Interface and CLI work reads `design/README.md` and `design/system/` first (see
AGENTS.md). Changes every project should get belong in the master, not here.
