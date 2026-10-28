# Vision and goals

Laomedo supports designing, inspecting and running agent workflows as a graph
of focused nodes. Agents perform work, Skills supply versioned instructions,
and GitHub nodes connect work to issues and pull requests.

## Goals guiding the implementation

- Keep each node responsible for its own domain and controls, with explicit
  contracts for data and operations exchanged with other nodes.
- Make skill changes reviewable through immutable revisions and file diffs.
- Make agent execution inspectable through retained activity and run identity.
- Keep host credentials and authorization outside the agent's command surface.
- Distinguish completed work, uncertain remote outcomes and historical evidence.

These goals summarize the existing [implementation overview](../../README.md)
and feature guides; they do not certify that every target behavior is delivered.
The [canonical project specifications](https://github.com/amadou-6e/specs/tree/main/projects/laomedo)
retain the governing requirements, decisions and capability limitations.

Continue with [architecture](../architecture/README.md) or the
[feature guides](../README.md#features).
