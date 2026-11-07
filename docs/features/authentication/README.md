# Local application sign-in

The native Windows application reuses Langflow's login page, user database,
password verification and access/refresh cookies. `tools/start_normal_login.ps1`
prepares an isolated normal-login deployment; it does not replace authentication
or implement private GitHub sessions. Owner: [#258](https://github.com/amadou-6e/laomedo/issues/258),
parent [#251](https://github.com/amadou-6e/laomedo/issues/251),
[canonical draft](https://github.com/amadou-6e/specs/pull/411).

## Boundaries and commands

The launcher owns child-process configuration only. `Prepare` admits an empty
non-Git runtime and fixes its loopback origin. `Check` verifies effective upstream
settings. `Bootstrap` delegates account creation and hidden password entry to the
existing upstream CLI. `Serve` delegates the app to Laomedo's existing factory.
No account is created by Prepare, Check or Serve. Runtime/config/database/key
state is separate from an existing preview. Inherited Laomedo/Langflow settings
are removed for the child and restored in the calling process.

Use Python 3.12 with Laomedo and the pinned Langflow runtime installed, and a
matching built frontend. From the repository root, in PowerShell:

```powershell
$login = @{
    PythonExe = (Resolve-Path '.venv/Scripts/python.exe').Path
    FrontendPath = 'C:/path/to/matching/upstream/src/frontend/build'
    RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'Laomedo/normal-login')
    Port = 17864
}
./tools/start_normal_login.ps1 @login -Mode Prepare
./tools/start_normal_login.ps1 @login -Mode Check
./tools/start_normal_login.ps1 @login -Mode Bootstrap
./tools/start_normal_login.ps1 @login -Mode Serve
```

The bootstrap terminal prompts for an administrator name and hidden password.
Choose them yourself; do not pass passwords on the command line or paste them
into chat. Initial bootstrap needs a new database; subsequent administrator
creation follows upstream authorization and is not automated here. Use existing
administrator user management to create/activate a non-default owner, then sign
in as that owner. Public signup remains disabled. Private owner binding and
server-revocable private sessions belong to #259, not this launcher.

Open `http://127.0.0.1:17864` in a separate browser profile with no imported data.
Different ports do not isolate cookies. Keep this profile and runtime directory
for browser/app restart checks. Stop only this foreground server with Ctrl+C;
re-run Serve against the same directory to restore its database/signing key.
Never reuse another application's runtime. HTTP loopback is local-only and does
not claim TLS or protection against malicious processes under the same OS user.

## Acceptance record

Implementation is in progress. No actual login, browser persistence, crash or
owner workflow acceptance is claimed yet. Verify correct/incorrect login,
refresh, logout, expired login, browser/profile and app restart, human takeover,
concurrent-profile support/constraints and crash recovery with the real app.
Record exact revision/environment, results, cleanup and gaps. Upstream logout
currently deletes cookies; it is not server-side JWT revocation. That gap is
owned by #259. No runner/model request or GitHub credential is needed for #258.
