# Internal GitHub browser controls

These controls use a deterministic host double and require an explicit test
manifest. They are regression tools, not a real GitHub demonstration or acceptance
evidence. Real workflow validation uses the configured actual GitHub service and
the maintained `examples/github` builder instead.

From the implementation checkout, with the installed app/LFX and Playwright
environments, start the loopback test backend in its own terminal:

```powershell
python tests/test_github/test_issues/test_browser/serve.py --manifest C:/Private/issue-backend.json
```

Configure the disposable task app with the URL and token-file settings from that
manifest; do not use a personal app/profile. The backend records only its own
temporary state. Prepare the Issue flow in that task app:

```powershell
Copy-Item C:/Private/issue-backend.json C:/Private/issue-browser.json
python tests/test_github/test_issues/test_browser/prepare.py --manifest C:/Private/issue-browser.json --base http://127.0.0.1:APP_PORT --action read
node tests/test_github/test_issues/test_browser/selection.cjs C:/Private/issue-browser.json
```

Use `--action modify` or `close` only for the corresponding internal operation
controls. `operation.cjs`, `stale.cjs` and
`viewer.cjs` exercise the named states using their explicit fixture manifest.
The `.cjs` controls need `@playwright/test` and the installed Edge channel.
Supply private absolute manifest paths and the actual task app port. Stop only
the test backend and app you started; retain any failed-control evidence, and
never commit token files, browser profiles or runtime manifests.

`--help` works for both Python scripts directly and outside the checkout. It
starts no listener and creates no provider/model activity; `test_entrypoints.py`
protects this startup contract.
