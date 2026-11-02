# Prospective S12 B amendment

Record before implementing or executing the revised controller. Preserve
S12 A's original protocol/result and consumed identity; never run it again.

Fresh identity: exp104-native-managed-s12-20261010-b. All identities derive
from this fresh value. Same repository/baseline/spec, four-write/no-model
budget, real authority/lease, independent Windows tasks, ownership guards,
unknown/no-retry rules, evidence and cleanup requirements as original S12.
Exact final source requires independent pre-run review and green CI.

Fix the controller-created workspace only: assert its origin is exactly the
controller's trusted local clone path, then remove that origin before calling
configure_remote. Do not relax configure_remote or replace arbitrary remotes.
Add a real local Git clone regression and a wrong-origin negative control.

Record a fixed-code phase diagnostic for setup failures without arbitrary
exception text, paths, credentials or content. This does not reclassify A's
original result or infer unknown external outcomes. Preserve controller failure
and no-retry semantics. No broader native-command coverage or model invocation.
