# Shared HTTP redirect policy

This dependency-free leaf owns `NoRedirect`, the standard-library handler whose
`redirect_request` method returns `None`. urllib then refuses the redirect through
its existing HTTPError path. It neither authenticates a request nor translates
feature-specific failures, starts servers, reads settings or loads credentials.

| Object | Interface | Consumers |
| --- | --- | --- |
| `NoRedirect` in `redirect.py` | `redirect_request(*args, **kwargs)` refuses redirect forwarding | GitHub REST and local node clients, Skill source/operation clients, Langflow join transport |

The REST adapter keeps its existing handler-class opener construction; other
consumers keep instance construction. No new HTTP client framework is introduced.
Tests preserve redirect status/error behavior and prevent request forwarding.

Four deliberate copies stay separate: the self-contained Agent and PR publisher
components, and the SIWC/OpenCode credential handlers. The credential handlers
raise their own distinct stable errors and must not use this return-None policy.
Structural checks name these exceptions so accidental copies do not accumulate.
