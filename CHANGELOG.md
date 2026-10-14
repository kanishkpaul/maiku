# Changelog

## Unreleased — design system, 2026-10-14

- Added the shared design system in `design/`, copied from the design kit master
  that lives next to this repository. See `docs/decisions/0002-design-system.md`.
- Made the repository public, by the owner's decision. The license and
  development direction are unchanged.

## Unreleased — rebuild foundation, 2026-10-13

- Preserved the previous main implementation at
  `3475192e838a6dcac89947c58743d2f0a76916f0` on `old`, with a new branch README
  and a verbatim copy of the original README.
- Decided on Rust, Tokio, SQLite, Svelte/TypeScript, optional Tauri, and separate
  language workers.
- Defined the architecture, extension boundaries, execution contracts, build
  gates, performance targets, testing, and coding/commenting standards.
- Added instructions for all coding assistants and new-commit attribution checks.
- Removed legacy implementation files from the main working tree so new
  development starts from the rebuild foundation; existing history remains.

No new product runtime or UI is shipped in this change. The repository remains
private until the owner changes its visibility; an open-source license and
development direction do not themselves publish it.
