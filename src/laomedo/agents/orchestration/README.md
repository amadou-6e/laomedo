# Agent handoff orchestration

`controller.py` owns `AgentHandoffController` (initially `BoundedController`). Its
responsibility is coordinating explicit successive runs, not graph edge scheduling.
All controllers have mandatory iteration, turn and deadline limits; `Bounded` is
therefore not a distinguishing class qualifier. The HTTP bridge is composed from
`agents/interface/bridge.py`, not inherited or duplicated here.

| Method | Contract / effects |
| --- | --- |
| `run(...)` | Coordinate admitted handoffs within configured limits and persist reservations before dispatch. |
| `cancel()` | Set cancellation intent and ask the bridge to cancel known active work. |
| `inspect(...)` | Inspect retained controller state without replaying uncertain dispatch. |

`_finish` and `_persist` are private transition/persistence helpers. `HandoffError`
owns this concern's stable codes. A local timeout does not prove that remote work
stopped; retained uncertainty must not trigger a blind retry. Cross-node PR/Skill
feedback remains in `integrations/langflow/feedback`.
