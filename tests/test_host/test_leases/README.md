# Lease controls

The suite protects complete registration, daemon binding, wall and monotonic
heartbeats, grant expiry/revocation, readiness publication, cleanup and client
shutdown. Internal lease services own only temporary files, sockets and threads;
container inspection and cleanup use internal transports. These checks do not
establish real Docker or provider acceptance. Run with normal core discovery or
`python -m unittest discover -s tests/test_host/test_leases -t tests -v`.
