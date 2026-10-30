# Agent implementations

Concrete providers and their shared abstract execution base live together so a
provider author can find both the extension contract and real implementations.
The wider application uses [the public interface](../interface/README.md).

| Concern | Package | Object nomenclature |
| --- | --- | --- |
| Abstract lifecycle | [base](base/README.md) | `BaseAgent`: abstract extension base, initially named `Runner` |
| Codex implementation | [codex](codex/README.md) | `CodexAgent`: concrete provider, initially `CodexRunner` |
| Claude implementation | [claude](claude/README.md) | `ClaudeAgent`: concrete provider, initially `ClaudeRunner` |
| OpenCode implementation | [opencode](opencode/README.md) | `OpenCodeAgent`: concrete provider, initially `OpenCodeRunner` |

`Base` means abstract; provider names identify actual specializations. A provider
owns native authentication, discovery, launch policy, resources and interpretation.
It imports the base and public contracts, never another provider. Shared Docker
mechanics remain in py-docker; host grants and GitHub policy remain outside Agents.

Initial relocation retains provider execution overrides. Inherited lifecycle
consolidation requires separate implementation and real per-provider evidence.
