# Shared HTTP redirect policy

This dependency-free leaf owns `NoRedirect`, the standard-library handler whose
`redirect_request` method returns `None`. urllib refuses forwarding through its
HTTPError path. Authentication, feature errors, service lifetime and credential
loading belong to callers.

| Object | Defining module | Interface |
| --- | --- | --- |
| `NoRedirect` | `redirect.py` | `redirect_request(*args, **kwargs)` refuses redirect forwarding |

GitHub REST, local node clients, Skill source/operation clients and Langflow join
transport import the defining class. REST constructs its opener with the handler
class; other clients use an instance. Socket tests verify refusal without forwarding.

Self-contained Agent and PR publisher components carry their own handler.
SIWC/OpenCode credential handlers raise distinct stable errors and therefore use
their own policies. Structural checks enumerate these deliberate exceptions.

Archived probe sources are historical evidence, not runtime API consumers.
Run a selected probe through explicit import migration before executing it with
the installed package. Its archived bytes and observations remain unchanged;
current application code exports no private redirect compatibility alias.
