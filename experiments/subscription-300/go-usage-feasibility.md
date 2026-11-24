# OpenCode Go quota feasibility,2026-11-24

Official source: https://opencode.ai/docs/console/go/#usage

The documented GET https://opencode.ai/inference/go/v1/usage uses the existing
Go bearer key and reports rolling, weekly and monthly usage/reset meters. No
separate login or inference call is needed. Do not substitute per-run tokens,
model prices or pay-as-you-go balance for remaining subscription allowance.

Two direct read-only checks with the explicitly selected saved Go connection
returned HTTP403 and submitted zero model turns. The second retained only a
whitelisted error category, which remained unclassified. No raw provider body,
key, credential file, profile identifier or account identity is archived here.
The result does not establish invalid credentials, missing entitlement, edge
filtering or any other particular cause. No model request was made to diagnose it.

The supported API establishes implementation feasibility. Live acceptance with
the current saved connection remains unverified. A production implementation
must deliberately represent all three windows and preserve the existing
connection/generation/lease checks, explicit refresh and no-turn guarantees.
This probe is not a production dependency or a normal verification prerequisite.
Run check_go_usage.py only with an explicitly selected private runtime root and
connection UUID; it never discovers ambient host provider credentials.
