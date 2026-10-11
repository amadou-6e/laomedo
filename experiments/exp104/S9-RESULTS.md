# EXP-104 S9: pre-write process identity failure

S9 identity `exp104-s9-20261008-01` was invoked once at source
`9da801c743d25a8c39260251bcc5407e3340f893` after a positive independent
pre-run review. It stopped with `host_service_identity_mismatch` before setup
grants, Docker runners or provider mutations. S9 is consumed; it must not be
rerun.

The private observation reports `inconclusive_or_failed`, zero events and
zero model turns. The state contains no `provider-attempts.jsonl`; the
mediator and lease service published the same Python PID. The probe's strict
comparison to `subprocess.Popen.pid` failed. No S9 setup branch was pushed by
this execution path. The private state remains under the single-use S9 name
for audit and is not copied into the repository because it also contains host
service state.

A harmless local control reproduced the root cause: on this Windows virtual
environment, `Popen.pid` named the Python launcher, while `os.getpid()` in the
child named a different process. Relaxing the check would leave runner-loss
ownership ambiguous. Amendment 26 freezes a new S10 identity and a direct
base-interpreter launch with the reviewed source and venv imports explicitly
bound. S9's positive review is not approval for S10.
