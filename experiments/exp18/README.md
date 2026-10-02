# EXP-18: Docker stage protection preflight

This directory prepares the [E05 protocol draft](https://github.com/amadou-6e/specs/pull/195).
`preflight.py` compares a created container's effective Docker inspect fields
with a preapproved mount and protection manifest. It returns mismatch codes so
the caller can refuse to start a stage. Unit tests cover an exact match, a
writable source-skill mount, an unexpected host mount, and missing protection.

No E05 Docker stage or agent turn has been launched. The protocol requires
review before stage testing. This verifier alone does not establish a Docker
write boundary or an agent-originated denial. It also does not relax the
current runner's permissions.
