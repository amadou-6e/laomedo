# EXP-06: UI disconnect versus backend death

This zero-model test runs two synthetic custom-component flows through pinned
Langflow 1.12.3. `stage_component.py` reserves a Laomedo launch record before
its waiting callback. `start.py` sweeps incomplete records before each server
start. `probe.py` first closes a client connection and reopens the saved flow,
then hard-kills and restarts the disposable backend.

The [observation](observation.json) shows that the UI-disconnected run completed
after release, while the backend-killed run became `crashed` with incomplete
evidence and one dispatch attempt. The callback for the killed run was not
released. The stage lives inside the backend container, so this does not test
an independently surviving agent container or push-capable grant. That is
EXP-07's separate boundary.

Only the disposable container `laomedo-exp06-20261002` and named volume of the
same name were used. The volume held temporary auto-login state and was removed
after evidence capture. The Laomedo package and fixtures were mounted read-only.
