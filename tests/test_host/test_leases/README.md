# Lease controls

The suite protects complete registration, daemon binding, wall and monotonic
heartbeats, grant expiry/revocation, readiness publication, cleanup and client
shutdown. Internal lease services own only temporary files, sockets and threads;
container inspection and cleanup use internal transports. These checks do not
establish real Docker or provider acceptance. Run with normal core discovery or
`python -m unittest discover -s tests/test_host/test_leases -t tests -v`.

`test_http.py` owns request admission and exact response bytes: readiness,
lease-write precedence, instance/auth/body ordering, malformed and maximum-size
bodies, safe errors, forwarding and suppressed access logs. Its recording grant
book and mediator live in `collaborators.py`; `RunningHTTPServer` owns each
ephemeral listener and thread. These are internal wire regressions, not live
Agent or GitHub acceptance.
