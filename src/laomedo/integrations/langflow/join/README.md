# Join HTTP adapter

`JoinServer` owns the explicitly supplied controller and token and binds only
loopback. `JoinRequestHandler` is a module-level HTTP class in `handler.py`;
its state comes from the server, rather than a hidden class closure.
`authorized()` performs the existing constant-time bearer comparison;
`execute()` retains the existing conflict/unknown/failure HTTP mappings;
`presented()` delegates to the leaf `RunnerStatusRecord.from_snapshot()`.
`reply()` writes the same sorted JSON content and length headers.

This is an integration adapter. The interface model owns output shape, the
controller owns coordination and run persistence, and providers own execution.
Reading status never asserts that the graph was executed or cancellation confirmed.
