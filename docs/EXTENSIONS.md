# Adding and removing abilities

Maiku's core is an execution contract. Adapters, discoverers, transformations,
presentations, worker bridges, and optional exporters extend it through small
owned interfaces. They must not become special cases in core.

## Extension classes

| Class | Responsibility | Boundary |
| --- | --- | --- |
| Adapter | Native invocation, property operations, or events | Internal object-safe adapter port or worker protocol |
| Discoverer | Read declared capabilities and executable bindings | Discoverer contract, explicit merge/conflict rules |
| Adaptation proposer | Suggest mappings from accessible evidence | Reviewable candidate; cannot activate or grant authority |
| Verifier | Test permitted behavior and report scoped evidence | Host-supervised operations through the execution gate |
| Transformation | Convert known representations/units | Ordinary participant with schemas and provenance |
| Composition | Reusable coordinated work | Ordinary participant backed by a validated graph |
| Presentation | Display/interact with an existing capability | UI feature over the API; no authority logic |
| Exporter | Optional telemetry or protocol exposure | Host event/API port; cannot grant access |

## Add a feature

1. State its responsibility, owner, dependencies, and observable contract.
2. Reuse an existing port when it fits. Add a new core operation only when its
   semantics are genuinely new; do not create a universal plugin API speculatively.
3. Keep ecosystem dependencies in the owning optional package or worker.
4. Add a manifest with a stable namespaced ID, extension/protocol version range,
   declared operations, dependencies, configuration schema, and lifecycle hooks.
   Manifest claims never authorize their own execution.
5. Validate registration and collisions. Configuration uses typed fields and
   credential references, not arbitrary dictionaries scattered through core.
6. Pass conformance, enabled/disabled packaging checks, failure tests, and a
   complete scenario. Document setup and actual limitations.
7. Add UI only where it helps a user inspect or use the capability. Generic
   invoke/inspect screens should handle ordinary additions without custom UI.

Keep built-in registration explicit at application assembly. External workers
are installed intentionally; Maiku must not auto-execute discovered packages.
Avoid native dynamic-library ABI plugins, arbitrary import hooks, and process
startup for every installed-but-disabled extension.

## Disable or remove a feature

1. Mark it draining and stop admitting new work.
2. List running tasks, subscriptions, pending approvals, and saved compositions
   that reference it. Drain or cancel according to the explicit policy.
3. Close owned tasks/processes/resources and revoke active runtime authority.
4. Disable registration and UI affordances; show a missing dependency for saved work.
5. Preserve historical events and artifacts. Do not cascade-delete user data.
6. Remove optional build dependencies or manifest entries. If durable configuration
   or schema changes, provide a migration and recovery path.
7. Verify the minimal build and unrelated reference scenarios still work.

Feature flags are additive build choices. Removing a Cargo flag is not the same
as safely uninstalling a runtime extension with durable references.

## Split only when necessary

Start with cohesive modules. Extract a package when optional dependencies,
independent lifecycle, reuse, or build isolation provide a concrete benefit.
Do not add factories, registries, traits, or configuration layers merely to
anticipate an unspecified future implementation.
