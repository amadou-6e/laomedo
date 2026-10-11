# EXP-104 amendment 06: user-authorized alternate disposable repository

Date: 2026-10-07. Status: frozen before any live mutation. The initial
read-only preflight under amendment 05 authenticated the supplied token as
`ga84jog` but GitHub returned 404 for
`amadou-6e/laomedo-exp15-disposable`; no push, issue, PR or repository
creation was attempted. This is a failed preflight, not evidence of grant
revocation or repository permissions.

The user explicitly selected a **new `ga84jog` disposable repository** for
the diagnostic. Use only `ga84jog/laomedo-exp104-disposable-20261007`, after
confirming that name is unoccupied. A single repository-create request may
be made by the credential-owning setup process, with a harmless initialized
README, and its result must be recorded separately from mediated writes. If
creation is rejected or uncertain, do not retry automatically; stop and ask
the user to create or identify a disposable repository. Do not fall back to
host `gh` or Git Credential Manager.

The diagnostic identity is now `EXP-104-D2`. Amendment 05's broad-token and
file-backed-custody limitations remain. The mediator must be configured to
this exact repository; grants, Git remote URL, baseline, remote read-back and
the negative controls must all match it. Never use an existing branch or
modify another repository. The original #104 acceptance criteria remain
unmet even if this diagnostic succeeds.
