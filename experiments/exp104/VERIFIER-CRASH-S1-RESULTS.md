# Verifier loss S1: stopped before crash case

Single-use identity exp104-verifier-loss-s1-20261009 executed once after
independent positive pre-run review at source f0ba073a8f5fce6356dc7784543d147bb4e14f11.
It failed before the deliberate export pause, so no worker-crash conclusion
is supported. Both exact stage/control containers were removed. No provider,
grant or model turn was used. Do not retry this identity.

The machine observation is preserved unchanged with SHA-256
8df630dafa61eba8c2020b720a2f20ac21539e5b37cf93fec14b7e25f0617f76.
Read-only post-diagnosis found verification status failed, exit code 2,
limits_verified true, cleanup_verified true, no stage marker and no export.

Coordinator diagnosis: git ls-files --eol reported index LF, working-tree CRLF,
even with the resource's eol=lf attribute. The mounted script had 42 CR bytes.
This is consistent with shell startup rejecting CRLF before stage markers; it
is not yet an independently replicated causal proof. The next implementation
will stage an LF-normalized copy of the trusted resource only after checking
its fixed SHA-256. New source plus a fresh frozen diagnostic identity and
independent pre-run review are required before a follow-up.
