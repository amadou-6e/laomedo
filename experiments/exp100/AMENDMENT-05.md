# EXP-100/S4 amendment 05: avoid self-defeating controls

Frozen before any S4 Docker run. This amendment changes no identity, image,
resource limit, fixture, or acceptance threshold in `PROTOCOL-04.md`.

- Capture `dd`'s error in the shell process rather than in the tmpfs being
  filled. The quota control still requires that an attempted 40 MiB write fail
  with `No space left on device` under the 32 MiB limit.
- The local-listener failure is a diagnostic, not causal evidence of network
  isolation: hostname resolution and host-loopback reachability may fail under
  other network modes too. The isolation claim rests on the Docker-inspected
  `NetworkMode=none` setting. The listener must remain untouched, but its
  failure alone does not establish that setting.
- Read back UID, dropped capabilities, no-new-privileges and read-only mounts
  in addition to the already inspected limits. If cleanup inspection fails,
  keep `cleanup_verified=false` instead of losing the result record.
