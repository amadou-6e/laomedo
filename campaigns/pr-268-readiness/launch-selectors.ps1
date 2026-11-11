# Isolated PR-selector QA only: no Agent nodes, execution, grants or GitHub writes.
param([ValidateSet('App','PR')][string]$Service)
$ErrorActionPreference='Stop'
$source='C:/CodeWorkspace/laomedo/.tools/worktrees/pr-268'
$qa=Join-Path $env:TEMP 'laomedo-graph-20261107/readiness/selectors-20261111'
New-Item -ItemType Directory -Force -Path $qa,(Join-Path $qa 'registry') | Out-Null
Get-ChildItem Env: | Where-Object { $_.Name -match '^(LANGFLOW_|LFX_|LAOMEDO_)' } | ForEach-Object { [Environment]::SetEnvironmentVariable($_.Name,$null,'Process') }
$env:PYTHONPATH=Join-Path $source 'src'
$env:LANGFLOW_CONFIG_DIR=Join-Path $qa 'langflow'
$env:LFX_CONFIG_DIR=$env:LANGFLOW_CONFIG_DIR
$env:LANGFLOW_DATABASE_URL='sqlite:///'+(Join-Path $qa 'langflow/flow.db').Replace('\','/')
$env:LANGFLOW_DO_NOT_TRACK='true'
$env:LANGFLOW_AUTO_LOGIN='true'
$env:LANGFLOW_FRONTEND_PATH=Join-Path $env:TEMP 'laomedo-graph-20261107/readiness/pr268-upstream/src/frontend/build'
$env:LANGFLOW_COMPONENTS_PATH=Join-Path $source 'components'
$env:LAOMEDO_COMPONENT_DIR=Join-Path $source 'components/laomedo'
$env:LAOMEDO_SKILL_STORE=Join-Path $qa 'registry'
$env:LAOMEDO_AGENT_ACTIVITY_DB=Join-Path $qa 'activity.sqlite'
$env:LAOMEDO_GITHUB_PR_URL='http://127.0.0.1:8786'
$env:LAOMEDO_GITHUB_PR_TOKEN_FILE=Join-Path $qa 'api.token'
Set-Location -LiteralPath $qa
if ($Service -eq 'PR') {
 & C:/CodeWorkspace/laomedo/.venv/Scripts/python.exe -m laomedo.github.interface.pull_requests.cli --repository amadou-6e/laomedo --github-token-file C:/CodeWorkspace/laomedo/.env --github-token-key GH_LAOMEDO --api-token-file $env:LAOMEDO_GITHUB_PR_TOKEN_FILE --mediation-store (Join-Path $qa 'mediation.sqlite') --forbidden-agent-mount C:/CodeWorkspace/laomedo/docs/vision-and-goals --port 8786
} else {
 & C:/CodeWorkspace/laomedo/.venv/Scripts/python.exe -c "import uvicorn; from laomedo.integrations.langflow.viewer import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=7861,access_log=False)"
}
exit $LASTEXITCODE
