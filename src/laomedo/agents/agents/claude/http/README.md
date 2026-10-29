# CommandHttpServer HTTP collaborators

`CommandHttpServer` binds the existing listener to one explicit `CommandService`
instance. `CommandRequestHandler` implements its framework `do_POST` callback using
that owner; request state is not captured by a nested class or mutable global.
`server_close` / `shutdown` retain the existing HTTP server lifecycle meanings.
The caller retains responsibility for thread startup, cancellation and exact cleanup.

Authentication, route names, body limits, response shape and error behavior are
unchanged by extraction. These are internal transport collaborators, not a new
public Agent API or a second execution pipeline. Decoder/owner references are
server-instance state; credential values must never appear in diagnostics.
