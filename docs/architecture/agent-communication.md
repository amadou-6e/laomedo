# Shared agent communication

Status: migration in progress. The existing runners have not all been switched.

Laomedo is moving agent execution to one ACP v1 client, using the published
`agent-client-protocol` Python SDK over a creator-owned py-docker stdio session.
Provider-specific policy supplies the image, entry point, credential mounts and
configuration. py-docker remains independent of agents and ACP.

The client advertises no host filesystem or terminal capabilities, rejects every
permission request and extension request, and cannot execute host commands. Model
tools must reach a separately authorized, credential-free Docker worker through
MCP. Protocol cancellation is followed by exact container cleanup; an acknowledgement
alone does not prove descendant termination. Failed session loading never creates a
replacement fresh run.

Candidate adapter pins preserve the current CLI families: Codex ACP 2.1.1 with
Codex 0.159.2; Claude Agent ACP 0.98.0 with Claude CLI 2.1.310; OpenCode's native
`opencode acp` in 1.18.33. Candidate validation images are not accepted release
images. Source recipes, package locks and immutable image identities must accompany
the eventual provider cutovers.

Required acceptance paths are Fresh, Resume (including a pre-migration native
session), cancellation during actual worker execution, worker refusal and loss,
authentication failure, dynamic model/effort discovery, pinned skill use, output
precheck, activity capture and cleanup after both normal and interrupted execution.
Codex's separate executor isolation and scoped GitHub mediation must be preserved
or explicitly redesigned and reviewed before removing their old implementations.

Container protocol probes and internal tests support this migration. They do not
establish graph acceptance. Final graph/user-story evidence and owner review remain
required before merging.

Upstream references: [ACP transport](https://agentclientprotocol.com/protocol/v1/transports),
[Python SDK](https://github.com/agentclientprotocol/python-sdk),
[Codex adapter](https://github.com/agentclientprotocol/codex-acp),
[Claude adapter](https://github.com/agentclientprotocol/claude-agent-acp),
[OpenCode ACP](https://opencode.ai/docs/acp/).
