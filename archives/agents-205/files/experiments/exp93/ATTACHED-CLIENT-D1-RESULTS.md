# Attached-client D1 bounded observation, 2026-10-11

Single execution of reviewed source3c9d0ee under fresh consumed identity
exp93-attached-client-d1-20261011, following frozen protocolb3c2f9b and
amendmentbf939ba. Zero model turns, credentials, mounts, network or provider writes.

The original [machine observation](attached-client-d1-observation.json) has SHA256
abef5bbdec993c16052f7ff3282c6433d723a5e6a02173cc15851be62459532a.
It showed the exact labelled container running before the attached client-tree
kill. At the first check (0.047s after kill completion) it was not running and
Docker reported removing. At1.062s it was absent, also absent at5s and10s checks.
No lease service was running. Exact final cleanup and client exit were verified;
the whole procedure took10.672s.

This demonstrates that client loss can accompany auto-removal for this pinned
stdin-dependent shell fixture using --rm -i. It does NOT establish native
app-server EOF behavior or retrospectively prove S2's cause. It does not prove
service-attributed removal, revocation, B continuity or Q11 acceptance. S2 remains
incomplete; shared model use remains14/16. This identity cannot be rerun.
