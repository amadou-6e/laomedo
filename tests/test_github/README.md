# GitHub controls

`test_issues` and `test_pull_requests` own normalization, selection, operations,
feedback and context. Their `test_graph` packages exercise actual components and
the supported bounded feedback scheduler with internal provider doubles.
`test_interface` owns loopback authentication, parsing, error projection and the
publisher boundary. `test_transport` owns Git and REST delivery. `test_browser`
holds the existing internal browser controls, never real integration acceptance.

Every test-bearing folder begins `test_`. Helpers have descriptive names:
feature `utils.py` creates fresh `IssueCase`/`PullRequestCase` values in the
corresponding `models.py`; `provider.py` implements a deterministic opener;
`response.py` owns its JSON response. No test borrows another TestCase's setup.
Each caller owns a fresh temporary directory and its cleanup. The case keeps
the exact clock/binding identities used by its gateway closures; these trusted
test factory values are constructed without copying them. No public payload
admission uses that internal factory shortcut.

Run from the implementation checkout, against an installed package:

```powershell
python -m unittest discover -s tests/test_github -t tests -v
python -m unittest discover -s tests/test_host/test_mediation -t tests -v
```

Core discovery includes these packages. Graph modules skip only when `lfx` is
absent; an installed runtime's import or test failure is a failure. Install the
declared Langflow/LFX environment to run those cases. Browser controls require
their explicit task-owned test setup and Playwright; their fake manifest gate
prevents confusing them with real GitHub acceptance. No default test dispatches
a paid model or writes to a real GitHub repository.

The former root gateway/transport/HTTP/context/feedback suites retain their
distinct assertions. Provider and setup extraction consolidates infrastructure,
not authorization, conflict, pagination, timeout, replay or cleanup cases. The
old saved fixture export is replaced by JSON roundtrip/handle assertions against
the current internal builder; its original bytes are preserved on `exp`.

EXP44/45 Issue publication and EXP108 account-broker tests are archived with
their prototypes at `exp` revision `714db418`. They are not production
capabilities. Actual production guarantees remain covered by:

| Boundary | Owning regression |
| --- | --- |
| Confirmed/unknown effects and no redispatch | Issue/PR gateway and PR feedback tests |
| Exact selected identity, authorization and changed content | Issue/PR gateway, REST and interface tests |
| Grant binding, stale generation, reviewed payload and replay | `test_host/test_mediation/test_store.py` |
| Actual file/environment token lookup and generation rotation | deferred host `test_host_token_connection.py` |
| Synthetic account OAuth broker and prototype IF12 crash protocol | preserved on `exp`; no production parity claimed |

The old Issue campaign's model-receipt orchestration tests are preserved on
`exp` too; native Agent receipt validation stays Agent-owned. Agent campaigns
remain deferred. Their exact inventoried imports may be adapted by the existing
`support.retained` loader; GitHub production tests never import campaigns or
fetch `exp`.
