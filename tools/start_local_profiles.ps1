# Native isolated local profiles. PIN entry happens only in the browser.
[CmdletBinding()]
param(
    [ValidateSet('Prepare', 'Check', 'Serve')]
    [string]$Mode = 'Check',
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [Parameter(Mandatory=$true)][string]$FrontendPath,
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [ValidateRange(1024,65535)][int]$Port = 17866
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'This setup supports native Windows only.' }
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = (Resolve-Path -LiteralPath $PythonExe).Path
$frontend = (Resolve-Path -LiteralPath $FrontendPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'index.html') -PathType Leaf)) {
    throw 'Frontend build is missing index.html. Build the matching frontend first.'
}
if (-not [IO.Path]::IsPathRooted($RuntimeRoot)) { throw 'RuntimeRoot must be absolute.' }
$runtime = [IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\','/')
# Never put login state in any Git checkout, including an ancestor worktree.
$ancestor = $runtime
while ($ancestor) {
    if (Test-Path -LiteralPath $ancestor) {
        $item = Get-Item -LiteralPath $ancestor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'RuntimeRoot and its ancestors must not be symbolic links or junctions.'
        }
    }
    if (Test-Path -LiteralPath (Join-Path $ancestor '.git')) {
        throw 'RuntimeRoot must be outside Git checkouts.'
    }
    $parent = [IO.Directory]::GetParent($ancestor)
    if ($null -eq $parent) { break }
    $ancestor = $parent.FullName
}
$marker = Join-Path $runtime 'local-profiles.json'
if (Test-Path -LiteralPath $runtime) {
    if (-not (Test-Path -LiteralPath $marker) -and
        @(Get-ChildItem -LiteralPath $runtime -Force).Count -gt 0) {
        throw 'Refusing an existing non-empty runtime without a local-profile marker.'
    }
}
if (Test-Path -LiteralPath $marker) {
    $existing = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
    if ($existing.purpose -ne 'laomedo-local-profiles' -or $existing.version -ne 1 -or
        $existing.port -ne $Port) { throw 'Runtime marker or fixed origin does not match.' }
}
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
if (-not (Test-Path -LiteralPath $marker)) {
    @{purpose='laomedo-local-profiles';version=1;port=$Port} |
        ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
}
foreach ($folder in @('langflow','registry')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $runtime $folder) | Out-Null
}
if ($Mode -in @('Check','Serve')) {
    $probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    $probe.ExclusiveAddressUse = $true
    try { $probe.Start() } catch { throw 'Port is already in use. Choose a fresh runtime and free port; do not stop unrelated services.' } finally { $probe.Stop() }
}
if ($Mode -eq 'Prepare') { Write-Output 'Isolated runtime prepared; no account or server created.'; exit 0 }
# Changes affect this launcher/child only, and are restored even on failure.
$saved = @{}
$names = @(Get-ChildItem Env: | Where-Object { $_.Name -match '^(LANGFLOW_|LFX_|LAOMEDO_)' } |
    ForEach-Object { $_.Name }) + @('PYTHONPATH')
foreach ($name in $names) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $null, 'Process')
}
$config = @{
    LANGFLOW_CONFIG_DIR=(Join-Path $runtime 'langflow')
    LFX_CONFIG_DIR=(Join-Path $runtime 'langflow')
    LANGFLOW_DATABASE_URL=('sqlite:///' + (Join-Path $runtime 'langflow/flow.db').Replace('\','/'))
    LANGFLOW_AUTO_LOGIN='false'
    LANGFLOW_SKIP_AUTH_AUTO_LOGIN='false'
    LANGFLOW_ENABLE_SIGNUP='false'
    LANGFLOW_NEW_USER_IS_ACTIVE='true'
    LANGFLOW_ENABLE_SUPERUSER_CLI='false'
    LANGFLOW_API_KEY_SOURCE='db'
    LANGFLOW_EXTERNAL_AUTH_ENABLED='false'
    LANGFLOW_FRONTEND_PATH=$frontend
    LANGFLOW_COMPONENTS_PATH=(Join-Path $repoRoot 'components')
    LAOMEDO_COMPONENT_DIR=(Join-Path $repoRoot 'components/laomedo')
    LAOMEDO_SKILL_STORE=(Join-Path $runtime 'registry')
    LAOMEDO_AGENT_ACTIVITY_DB=(Join-Path $runtime 'activity.db')
    LANGFLOW_DO_NOT_TRACK='true'
    LANGFLOW_CORS_ORIGINS=('["http://127.0.0.1:' + $Port + '"]')
    LANGFLOW_CORS_ALLOW_CREDENTIALS='true'
    LAOMEDO_LOCAL_PROFILE_PORT=[string]$Port
    LAOMEDO_LOCAL_PROFILE_RUNTIME=$runtime
    PYTHONPATH=(Join-Path $repoRoot 'src')
}
$originalLocation = Get-Location
try {
    foreach ($name in $config.Keys) {
        [Environment]::SetEnvironmentVariable($name, $config[$name], 'Process')
    }
    # Avoid loading an unrelated checkout's .env through upstream startup.
    Set-Location -LiteralPath $runtime
        $bootstrap = @"
import os
from langflow.services.deps import get_settings_service
settings = get_settings_service().auth_settings
if settings.AUTO_LOGIN or settings.skip_auth_auto_login or settings.ENABLE_SIGNUP:
    raise SystemExit('Normal login requires auto-login, bypass and public signup disabled.')
from laomedo.integrations.langflow.local_profiles.admission import ProfileRuntimeAdmission
from laomedo.integrations.langflow.local_profiles.settings import LocalProfileSettings
ProfileRuntimeAdmission(LocalProfileSettings().runtime_root).verify_settings(get_settings_service())
print('Effective settings: local profiles require PIN login; generic signup disabled.', flush=True)
"@
        if ($Mode -eq 'Serve') {
            $bootstrap += @"

import laomedo
import uvicorn
laomedo.__path__.append(os.environ['LAOMEDO_COMPONENT_DIR'])
from laomedo.integrations.langflow.local_profiles.settings import LocalProfileSettings
from laomedo.integrations.langflow.local_profiles.runtime import LocalProfileRuntime
from laomedo.integrations.langflow.viewer import create_app
app = create_app(profile_runtime=LocalProfileRuntime(LocalProfileSettings().runtime_root))
uvicorn.run(app, host='127.0.0.1', port=int(os.environ['LAOMEDO_LOCAL_PROFILE_PORT']), access_log=False)
"@
        }
        $bootstrap | & $pythonPath -
    if ($LASTEXITCODE -ne 0) { throw 'Upstream normal-login command failed. No success is claimed.' }
} finally {
    Set-Location -LiteralPath $originalLocation.Path
    foreach ($name in $config.Keys) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') }
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
