# Graph dispatch persistence

`WorkflowRunStore` in `store.py` owns SQLite graph reservations, invocation
correlations and trace receipts. It does not execute providers or grant access.
Its `runner_*` records correlate remote Agent work with a graph invocation; they
are graph-side state, not the Agent's native run store.

| Method family | Meaning / effects |
| --- | --- |
| `reserve`, `reserve_invocation`, `claim_langflow_client` | Persist identity before dispatch; enforce conflict/duplicate rules. |
| `get`, `langflow_client_snapshot`, `trace_snapshot`, `counters` | Read retained state without replaying work. |
| `freeze_runner_request`, `bind_runner_ack` | Persist the exact dispatched request and acknowledged remote identity. |
| `record_runner_*`, `record_timeout`, `record_job_status`, `record_effect` | Record observed outcomes; uncertainty remains explicit. |
| `request_langflow_cancel`, `langflow_cancel_requested` | Persist/read cancellation intent. |
| `begin_invocation`, `begin_langflow_client`, `dispatch` | Control admitted state transitions and dispatch reservations. |
| `sweep_crashed` | Reconcile interrupted reservations without replay. |

`LaunchError` and `ExternalOutcomeUnknown` stay here. Existing table names,
persisted fields and transaction semantics survive relocation. `record_synthetic_dispatch`
is an existing internal control, not real execution evidence or a deliverable.
