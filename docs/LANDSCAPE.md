# The landscape, and why maiku is shaped this way

Research notes behind the design. Every decision below is a reaction to something that
already exists — or to something that already failed.

## There are already seven descriptor formats

| Format | Owner | Describes | Why it is not enough |
|---|---|---|---|
| [A2A AgentCard](https://a2a-protocol.org/latest/specification/) | Linux Foundation | agent identity, skills, IO modes, auth | agent-shaped only; skills carry no schemas; no tensors, no residency, no device |
| [MCP](https://blog.modelcontextprotocol.io/posts/2026-07-28/) tools + `server.json` | Anthropic | tools, resources, prompts | the *server* is the unit, not the participant; no identity, liveness or delegation |
| [OASF](https://github.com/agntcy/oasf) ([paper](https://arxiv.org/pdf/2509.18787)) | AGNTCY / Linux Foundation | agent records, capability taxonomy, OCI-addressed | enterprise directory framing; heavy for a local runtime |
| [AgentFacts / NANDA](https://arxiv.org/abs/2507.14263) | MIT Media Lab | signed JSON-LD metadata, "DNS for agents" | a discovery and identity layer, not a call convention |
| [WoT Thing Description](https://www.w3.org/TR/wot-thing-description11/) | W3C | properties, actions, events + protocol bindings | not adopted in AI — but structurally the best of the lot |
| [UTCP](https://www.utcp.io/utcp-vs-mcp) | community | a "manual" so the agent calls the tool natively | tools only; the descriptor-not-proxy instinct is right |
| `agents.json`, `agents.txt`, `llms.txt`, `.well-known/agent-card.json` | various | web discovery pointers | discovery only |

**What maiku does:** does not add an eighth rival. The descriptor is a **superset with
projections** (`src/maiku/projections/`), so an adapted participant is immediately usable by
clients that have never heard of maiku, and round trips are tested in both directions.

## The best structural idea is a decade old and outside AI

W3C Web of Things solved "one abstraction over wildly different devices" with **properties,
actions, events** plus **protocol bindings**. That triad is exactly what survives
non-chatbots. Nobody in the agent-protocol space adopted it. maiku's `AffordanceKind` is it,
plus `stream`.

## The cautionary tales

**UDDI/WSDL.** Rich, hand-authored semantic descriptions in a heavyweight central registry.
*"The complexity of the UDDI API made this ridiculously hard… architects quietly abandoned
it."* ([CIO](https://www.cio.com/article/2433285/why-uddi-sucks.html),
[Registries Reloaded](https://architecturalbytes.substack.com/p/registries-reloaded))

> Mitigations: descriptors are **derived by introspection**, discovery works with **no central
> registry**, and the calling convention shipped before any ontology.

**[mozilla-ai/any-agent](https://github.com/mozilla-ai/any-agent)** is in soft deprecation. A
thin unifying wrapper over agent SDKs did not sustain itself.

> Mitigation: the value is placed in the runtime and gateways, not in adapter count.

**Semantic capability matching.** Twenty years of automatic service composition research; it
never worked in practice.

> Mitigation: `maiku find` is search, and says so. No composition claims.

## The gaps that were actually open

**[Beyond Message Passing (2604.02369)](https://arxiv.org/html/2604.02369v3)** surveys 18
protocols: transport and schema support are mature, but *"semantic responsibilities are pushed
into prompts, wrappers, or application-specific orchestration logic."*

> Answer: affordances carry worked **examples**, determinism, latency class, idempotency and
> side effects — the facts a caller needs that a JSON Schema cannot state.

**[Governance Gaps (2606.31498)](https://arxiv.org/pdf/2606.31498)**: MCP, A2A and ACP cannot
express conditional authority, delegation chains, revocation or accountability.

> Answer: `src/maiku/runtime/grants.py`. [UCAN](https://github.com/ucan-wg/spec)-shaped
> attenuated grants where a child may only narrow, across capabilities, scopes, artifacts,
> side-effect ceiling and expiry.

**Non-chat modality handoff.** Every agent protocol assumes text and JSON parts.

> Answer: `TensorPart` and content-addressed artifacts. A model's output reaches the next
> participant as a typed reference, not base64 in a message body.

**Humans.** [HumanLayer](https://www.humanlayer.dev) proved the demand but bolts on at the
tool-calling layer.

> Answer: a person is a participant with `latency_class: human`, passing the same conformance
> suite as everything else. Escalation is an ordinary call to `human/<name>#approve`.

## Borrowed rather than invented

A2A task lifecycle states · MCP behavioural hints · JSON Schema 2020-12 ·
[UCAN](https://github.com/ucan-wg/spec) delegation semantics · the OpenAI chat wire format ·
OpenAPI · W3C WoT affordances · content addressing.

## Reading list

- [A survey of agent interoperability protocols (2505.02279)](https://arxiv.org/abs/2505.02279)
- [Beyond Message Passing (2604.02369)](https://arxiv.org/html/2604.02369v3)
- [Governance Gaps in Agent Interoperability Protocols (2606.31498)](https://arxiv.org/pdf/2606.31498)
- [Beyond DNS: the NANDA Index and Verified AgentFacts (2507.14263)](https://arxiv.org/abs/2507.14263)
- [The AGNTCY Agent Directory Service (2509.18787)](https://arxiv.org/pdf/2509.18787)
- [W3C WoT Thing Description 1.1](https://www.w3.org/TR/wot-thing-description11/)
- [How to sandbox AI agents](https://northflank.com/blog/how-to-sandbox-ai-agents)
