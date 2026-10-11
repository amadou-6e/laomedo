# EXP-100/S8: bounded binary stream passed on Docker Desktop

S8 followed [PROTOCOL-08](PROTOCOL-08.md), frozen at `af959d9`, with product
and probe code at `e90b2d194fd0cd5accdad61cca97caae3e52938f`. The fresh
identity `exp100-s8-20261009-a` was run once. Its original
[observation](observation-s8.json) was committed unchanged at `04b5cbb`;
SHA-256 of the committed bytes is
`7ab3533bd247b04eac55591211b086e430e7d8ec2c068bef54d2ee93d3f67605`.
No model turn, provider request, GitHub credential or GitHub write occurred.
Do not rerun this identity.

The positive case created one container with the pinned image. Its limits
were verified before start, the success marker was observed, and the fixed
`docker exec` stream returned 562 binary bytes with class `ok` and exit code
0. The output hash in the product result matches the independently measured
file hash, `04fde221597a66565562b71156850030349739e761409c91bc44f6b251d851ec`.
Independent import confirmed `refs/heads/validated` points to the intended
commit, its object type is `commit`, strict fsck passes and it descends from
the trusted baseline. Cleanup was verified and the exact container was absent
afterwards. `policy_approved` remained false. The negative case returned
`candidate_commit_mismatch`, created no container and produced no output.
The observation's overall class is `passed`.

This directly supports a bounded, credential-free export from this pinned
Git container on this Docker daemon. It does not establish remote GitHub
push safety, a trusted workflow-file diff, literal `gh` command parity,
runner-loss revocation, real-agent timeout/cancellation, or #100/#104
completion. S7's failed `docker cp` result remains in [RESULTS-S7.md](RESULTS-S7.md)
and was not rewritten or retried.
