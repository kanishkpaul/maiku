# Current status

Maiku is a public, Apache-2.0 project with a documentation and tooling foundation
for a Rust rebuild. This page describes repository state, not a release promise.

## Available in this branch

- The thesis, product direction, architecture, and stack decisions.
- Design contracts for participants, workers, authority, artifacts, and extensions.
- Coding standards and shared instructions for coding assistants.
- A shared visual design kit and project-specific design direction.
- Repository checks, checker tests, a commit-message hook, and GitHub workflows.

## Not implemented in the rebuild

There is no Cargo workspace, executable Rust runtime, CLI, new web app, or
published rebuild package. Discovery, semantic contracts, adapter generation,
verification reports, drift repair, durable execution, isolation, and device
support are requirements in the design, not working capabilities of this branch.

The architecture's module names and the testing document's Cargo commands are
prospective. Performance budgets are targets. Nothing here establishes general
semantic compatibility, safe control of arbitrary devices, or production security.

## Preserved implementation

The [`old` branch](https://github.com/kanishkpaul/maiku/tree/old) preserves the
previous implementation and its own setup instructions. Historical demos and
test results describe that implementation under their recorded conditions.
They do not verify the new architecture or present-day protocol compatibility.

Port behavior with its contract and failure cases. Do not restore legacy source
wholesale or interpret adapter count as proof of universality.

## Planning and contribution

The owner's detailed build plan and research scratch material stay local and
untracked. Public work should be scoped through a concrete issue or task with
observable acceptance conditions. No local planning file is required to clone
the repository, run its checks, or contribute.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the development workflow and
[TESTING.md](TESTING.md) for checks available now.
