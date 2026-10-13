# Research behind the rebuild

Reviewed 2026-10-13. Sources support design choices; they do not establish Maiku
performance, customer demand, universality, or production readiness.

## Protocols, meaning, and execution

- [Agent interoperability survey](https://arxiv.org/html/2505.02279v2): distinguish
  tool access, delegation, and discovery; do not collapse them into one protocol.
- [Beyond Message Passing](https://arxiv.org/html/2604.02369v3): transport/schema
  interoperability leaves clarification, context alignment, and verification work.
  Maiku's transformations and unknown-compatibility states address a concrete subset.
- [Governance Gaps](https://arxiv.org/html/2606.31498v1): community governance covers
  membership, deliberation, voting, dissent, escalation, and audit/replay. Narrowing
  grants alone do not implement that taxonomy. Do not cite this as evidence that
  Maiku already solves signed delegation or revocation.
- [NANDA/AgentFacts](https://arxiv.org/pdf/2507.14263): distinguish stable identity,
  fresh endpoints, declarations, and attestations. Internet-scale claims remain
  proposals rather than Maiku requirements for the first release.
- [AGNTCY directory](https://arxiv.org/html/2509.18787v1): content-addressed records,
  federation, versioning, and provenance are useful precedents; a global directory
  is not necessary for a local workspace.
- [Agora](https://arxiv.org/html/2410.11905v1): routine reuse and language-mediated
  negotiation suggest a later assisted-composition path. Its agent experiments
  do not demonstrate arbitrary device interoperability or safe generated adapters.
- [Crash-stop multiparty session types](https://arxiv.org/pdf/2311.11851): model
  failures as interaction semantics, not just exception strings. Full formal
  session typing is not a prerequisite for the first release.
- [WoT Thing Description](https://www.w3.org/TR/wot-thing-description11/): native
  properties, actions, events, and bindings fit heterogeneous systems.
- [UCAN](https://github.com/ucan-wg/spec): a reference for verifiable narrowing
  authority, not a reason to invent an unsigned lookalike and claim equivalence.

## Current ecosystem

- [MCP 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/) and
  [roadmap](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/): protocol
  evolution makes compatibility/version tests necessary. The old runtime hardcodes
  MCP 2025-06-18; its self-tests do not prove current remote compatibility.
- [A2A specification](https://a2a-protocol.org/latest/specification/): preserve
  native lifecycle and version negotiation; record projection loss explicitly.
- [Official MCP Rust SDK](https://github.com/modelcontextprotocol/rust-sdk):
  evaluate support for required versions before using it behind an adapter port.
- [FastMCP proxy](https://gofastmcp.com/servers/providers/proxy): aggregation and
  transport bridging are established features, not unique Maiku differentiation.
- [UTCP](https://www.utcp.io/about/RFC): native calls from declared interfaces
  overlap with self-adaptation; execution and reusable composition must add value.
- [Composio](https://docs.composio.dev/docs): tools, auth, triggers, and managed
  execution. Ingest useful services rather than rebuilding its connector catalogue.
- [Arcade/Smithery](https://www.arcade.dev/blog/smithery-joins-arcade/): discovery,
  distribution, authorization, and governance overlap; Smithery is part of Arcade.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
  and [Temporal tasks](https://docs.temporal.io/tasks): durable state and recovery
  precedents; compose them as appropriate rather than assuming Maiku has their guarantees.
- [Home Assistant MCP](https://www.home-assistant.io/integrations/mcp_server/):
  practical device coverage and auth; a strong integration substrate.
- [ROS 2 actions](https://design.ros2.org/articles/actions.html): preserve goals,
  feedback, results, and cancellation for bounded robotics tasks.

The engineering opportunity is an inspectable local workspace that combines
these ecosystems with non-chat models and humans. This is a hypothesis tested
by complete workflows and independent users, not an established market claim.

## Code and stack research

See [the stack decision](decisions/0001-stack.md) for language/stack comparisons
and primary documentation. See [CODING_STYLE.md](CODING_STYLE.md) for the Rust,
TypeScript, rustdoc, and kernel guidance translated into repository review rules.

Recheck volatile protocol/product facts when implementation depends on them.
Keep claims narrowly tied to what a source or actual experiment establishes.
