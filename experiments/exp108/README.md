# EXP-108: synthetic GitHub account connection

This experiment implements and tests a **disposable reference broker**, not
Laomedo's production login or secret store. It exercises the merged
[connection contract at specs `9c287ec`](https://github.com/amadou-6e/specs/blob/9c287ec/projects/laomedo/subsystems/agent-execution/contract/github-account-connection.md)
for [issue #108](https://github.com/amadou-6e/laomedo/issues/108).

## Frozen sequence and result

1. Protocol `1c1797e` was committed before probe source `1502ffb`.
2. The first run produced `observation.json`. It passed 22 controls, but did
   not exercise a browser callback's wrong repository or a code presented
   against another *valid* state. It is historical, **not** the complete pass.
3. Amendments `d557cd4` and `e491e8e` were committed before revised probe
   `371af10` and its single recorded run. `observation-v2.json` passed all 24
   controls. Both observations were committed at `81d4a6d`.

The v2 fake provider received 26 synthetic requests, including 4 accepted
writes. No request went to GitHub, no model turn ran, and no real credential
was loaded. The broker refused wrong owner, session, state, code/state pair,
account, repository, token class, expired token, insufficient scope,
cross-user selection, old connection generation, disconnected connection,
and a provider-revoked token. A second connection kept working after the
first was replaced. A broker restart retained the selected connection and
pending callback. Stage payloads and the sanitized provider journal contained
no token; fake ambient `GH_TOKEN`, Git helper settings and a `gh` shim were
not used.

Evidence SHA-256 (LF checkout bytes, `experiments/** text eol=lf`):

| Committed file at `81d4a6d` | SHA-256 |
| --- | --- |
| `observation.json` | `6ae2e418007297ebecc8b65a28421310f28be02ec9a0d33260ff621e028231b2` |
| `observation-v2.json` | `85d971b43c9cfed93cdbb31b3246beb59608d699f1aa385e5a4cdf1003c24c7f` |

The observed code at `371af10` has SHA-256
`cbb291caa97a832bf8ae0882304ad8bac8695525288408752a77e74f6d3a3c60`
for `probe.py` and
`599f4bc8e04177c04254d2320567f59bdc0432e781190580aa4d2ffc499fe52a`
for `connection.py`.

Run the repeatable controls without replacing the observations:

```powershell
python -m unittest discover -s experiments/exp108 -p test_probe.py -v
python experiments/exp108/probe.py
```

`--record` refuses to overwrite the committed v2 observation. The temporary
SQLite database contains only synthetic tokens; it is deleted at process
exit. This is not evidence for deployed browser login, OS-backed token
custody, a real GitHub permission check, runner-loss revocation, or full
`git`/`gh` parity. In particular, the fake endpoint's code/state behavior is
a test fixture, not a claim about GitHub. #100 and #104 retain the live
mediator and grant obligations.
