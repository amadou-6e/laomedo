# Protocol controls

Existing Agent regressions for this concern. Run `python -m unittest discover -s tests/test_agents -t tests -v`. Internal controls do not establish real provider acceptance.

`wire.py` owns credential-free in-memory ACP peers. `NotificationWire` replies to
initialize/new-session requests and emits native completion before prompt return;
`PrecheckWire` holds prompt completion until the host answers the actual
`_laomedo/outputPrecheck` request. These objects exercise SDK dispatch and ordering,
not an agent or a container.

Both expose `write` (consume one host message), `read_line` (receive one peer
message) and `close` (release a blocked reader). Their `on_prompt` and `on_reply`
methods model the distinct peer state transitions; `emit` queues a wire message.
