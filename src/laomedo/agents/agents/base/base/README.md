# Shared Agent interfaces

This directory organizes abstract contracts within the existing shared Agent
capability. Import classes directly from the defining concern module; the
initializer does not re-export them.

| Module | Objects | Responsibility |
| --- | --- | --- |
| [invocation.py](invocation.py) | `BaseAgentRunner`, `BaseInvocationJournal`, `BasePostFreezeSettlement`; stop protocols | Native execution, durable write port, surviving supervision |
| [runtime.py](runtime.py) | `BaseAgentRuntime` | Shared resource lifetime with provider plan/error hooks |
| [resources.py](resources.py) | `BaseRuntimeResource`, `ControllerStream`, builder protocols | Exact resource closure and borrowed I/O; container builders return specs |
| [credentials.py](credentials.py) | `BaseCredentialProvider` | Admit native credentials without universal borrowing/release |
| [commands.py](commands.py) | `BaseCommandExecutor` | Isolated worker admission, cancellation and drain |
| [catalog.py](catalog.py) | `BaseModelCatalog` | Zero-turn discovery |
| [activity.py](activity.py) | `BaseActivityProjector` | Read-time native evidence interpretation |
| [interim.py](interim.py) | Current live provider ABCs | Temporary implementation contracts until #277 migration |

These are the target declarations for user inspection, not migrated provider
implementations. `interim.py` retains its current behavior and remains the
production guard's selected contract owner; it is not a compatibility forwarder.
Delete it when the actual providers and callers use the target contracts.

`BaseAgent` stays in [../agent.py](../agent.py). Shared concrete Docker code stays
in [../runtime.py](../runtime.py). Target method docstrings define admitted inputs,
failure outcomes and lifecycle order. The existing interface guard remains red on
unresolved provider runtime methods; this layout does not exempt them.

## Invocation nomenclature

An invocation is one admitted provider execution: it can contain multiple native
model/tool turns and remains distinct from the host run and saved conversation.
The defining concern is invocation.py. BaseAgentRunner.run takes InvocationRequest
and returns InvocationResult; InvocationContext carries the host context.
BaseInvocationJournal owns durable writes, not execution-state checkpoint restoration.

Persisted attempt_id and activity-attempt records keep their established schemas
and stable codes. open_activity_attempt names that existing activity record boundary.
StopContext still combines requesting and observing; it must not be called a
read-only cancellation token. ContainerBuilder/OwnedResourceBuilder remain an
unresolved construction/allocation design concern, not repaired by these renames.
