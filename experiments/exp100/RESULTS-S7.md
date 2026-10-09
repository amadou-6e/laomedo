# EXP-100/S7: Docker tmpfs export failed

S7 used the frozen [protocol](PROTOCOL-07.md) at `83fa100` and product/probe
revision `f57a9157397b7657b98f4551b876251e009db092`. The one-shot identity
`exp100-s7-20261009-a` was dispatched once, with no model or provider/GitHub
call. Its direct [observation](observation-s7.json) was committed unchanged at
`473fe82`; the committed file's SHA-256 is
`640ec776d228f1e77ef623f58f1b1b6ec37bd8e6f06010d2fd37db868f24a71a`.
It must not be rerun.

The positive case created one container and verified its limits. It ended
`output_unavailable` with no output bytes or hash after 0.813 seconds; exact
container cleanup was confirmed. The wrong-commit case refused before Docker,
with zero new creates. Thus the safety/refusal behavior held, but the central
export mechanism did not work. S7 is a failed result and does not support
merging draft PR #122 or completing #100/#104.

The product code uses `output_unavailable` both if the success marker appears
after the container has stopped and if `docker cp` returns nonzero. S7 did not
record which path fired or Docker's stderr. The short elapsed time and absence
of a failure marker suggest the latter, but that is **an inference**, not an
observed error. Separately, [Docker's `docker cp` documentation](https://docs.docker.com/reference/cli/docker/container/cp/#corner-cases)
states that it cannot copy resources under tmpfs mounts and describes
streaming them with a command inside the container. The next candidate will
use a bounded stream from the still-running container and a fresh identity;
S7's failure remains part of the record.
