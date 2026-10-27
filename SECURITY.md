# Security and trust boundaries

The rebuild is not implemented yet. No current claim of sandboxing, remote
authority verification, or production security follows from these documents.

## Required behavior

- Treat documentation, source, visible interfaces, and model-generated mappings as
  untrusted evidence. They cannot instruct the host to disclose credentials,
  install code, activate an adapter, or grant authority. Verification probes need
  explicit permission and bounded effects just like ordinary calls.
- Authenticate callers separately from capability descriptions. Unknown callers
  receive no authority. Descriptor hashes are not authentication.
- Recheck authority, expiry, revocation, descriptor revision, and relevant state
  after an approval wait and immediately before dispatch.
- Bind approval to the operation, argument digest, capability revision, and expiry.
- Keep credentials in an OS credential store or explicit environment references;
  never in descriptors, committed configuration, artifacts, or event logs.
- Treat third-party code as executable code. Process separation alone is not a
  sandbox. Isolation backends must state their actual filesystem, network,
  process, and resource guarantees per platform.
- Validate artifact digests, paths, sizes, and access before reading or transfer.
- Restrict local HTTP to loopback by default, authenticate access, check origins,
  and protect mutations against cross-site requests. Remote listening is explicit.
- Do not retry uncertain external writes automatically. Reconcile or ask.
- Physical actions require bounded parameters, freshness checks, explicit grants,
  approval when policy requires it, and an observed outcome.

See [the architecture](docs/ARCHITECTURE.md), [protocol](docs/PROTOCOL.md),
and [testing requirements](docs/TESTING.md) for ownership and verification.

## Reporting

If GitHub private vulnerability reporting is available for the repository, use
it. Otherwise ask the maintainer for a private reporting channel without putting
exploit details or secrets in a public issue. Do not assume this repository has
an established disclosure response time or an audited release.
