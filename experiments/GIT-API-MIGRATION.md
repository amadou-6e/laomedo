# Historical Git experiment constraint

The following one-shot experiments depended on removed private Git process or
credential-environment helpers. They now stop explicitly at the first retired helper call, before that Git
operation. Pure metadata imports used by current verifier tests remain available.
The experiment-only refusal helper performs no Git or credential work.
Historical evidence remains unchanged. They are not current launcher examples or
acceptance proof. Before rerunning, migrate to `laomedo.git` with explicit context
and credential models, revalidate their external effect authorization, and update
their historical assumptions. No compatibility runner is installed.

Current regression controls still use the EXP-104 dry-run preflight, clean-source
check and host/Agent process environment functions. Those specific functions have
been migrated to the shared Git objects or the separate service-process environment
owner. Other retired helper calls in these historical workflows still refuse;
passing their internal controls does not validate rerunning a historical campaign.

- `experiments/exp100/probe_native_capture.py`
- `experiments/exp100/probe_paired.py`
- `experiments/exp104/live_probe.py`
- `experiments/exp104/native_localrunner_probe.py`
- `experiments/exp104/native_localrunner_worker.py`
- `experiments/exp104/native_managed_probe.py`
- `experiments/exp104/native_managed_worker.py`
- `experiments/exp104/probe_active_delivery.py`
- `experiments/exp104/probe_verifier_crash.py`
- `experiments/exp104/s11_probe.py`
- `experiments/exp139/prepare.py`
- `experiments/exp139/prepare_amend08.py`
- `experiments/exp93/real_stage_probe.py`
