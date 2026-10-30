# Agent handoff orchestration

`controller.py` owns `AgentHandoffController` (formerly `BoundedController`). Its
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
# Handoff value vocabulary

`AgentHandoff` groups target, task, pinned skill references, selected artifacts,
source identity and optional resume binding. `HandoffTarget`, `HandoffSource`,
`HandoffPrior` and `HandoffSkillReference` in `models.py` give those concepts one
owner. `to_payload()` preserves the existing envelope, including explicit null
source/prior and omitted optional target keys. `envelope()` retains manual
admission and its stable errors; the controller and HTTP bridge retain effects.

Legacy target/identity metadata is JSON data where the old admission did not
restrict its type. A model must not turn that into a new public ValidationError.
Admitted artifact maps remain the existing verified cross-provider manifest
boundary; a handoff identity itself grants no access to another run or repository.
