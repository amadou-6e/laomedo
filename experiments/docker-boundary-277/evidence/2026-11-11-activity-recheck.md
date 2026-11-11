# Activity reviewer correction acceptance attempt

Implementation3778e2714ac65b06071224fa915da171df489225, PR250.
Harness activity_acceptance.py uses authorized current-session access credential
in memory; no credentials, native receipts or session identity retained here.

Corrected-head rerun: admitted existing image
sha256:e0eddf0e62cd7a46e6050d3ec44adf87150965139e44f6dced15b748845e21ba,
model discovery returned8 models. Fresh execution statusfailed; capturepartial,
closedtrue, completefalse, records0, items0, stable_replaytrue, displayrevision1.
That harness version did not emit error_category, so the execution cause is not
established. It did not proceed to resume. No acceptance pass is claimed.

The harness now emits stable error_category and capture reason on completed
attempts. One diagnostic rerun admitted the same image, then failed during
model discovery with docker_control_failed before model prompting. No further
retry was made; no container or daemon reset was attempted.

Earlier successful fresh/resume evidence at b3a3fcef remains earlier-revision
acceptance only. Current supporting tests49 Activity+39capture/catalogue pass.
Reviewer initial code verdictREVISE, corrections recheckpending: focused same-
session request was quota-refused until15:00Berlin2026-11-11. Specification
review incomplete. No Activity cancellation, Claude/OpenCode execution, host-loss
or daemon-wide cleanup evidence is claimed.
