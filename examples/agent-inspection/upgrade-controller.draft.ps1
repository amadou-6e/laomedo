$ErrorActionPreference='Stop'
$root='C:\CodeWorkspace\agentviz'
$source=Join-Path $root 'work-issue-graph.local'
$state='C:\Users\amado\AppData\Local\Temp\laomedo-issue-operation-input-20261013-a'
$tokenFile='C:\Users\amado\AppData\Local\Temp\laomedo-langflow-demo-20261012-c\runner\api-token'
$manifest=Get-Content (Join-Path $root 'claude-review.local/native-prompt-services.json') -Raw | ConvertFrom-Json
if($manifest.state -ne $state){throw 'controller_state_mismatch'}
$revision=(& git -C $source rev-parse HEAD).Trim()
if((& git -C $source status --porcelain)){throw 'source_not_clean'}
$process=Get-CimInstance Win32_Process -Filter "ProcessId=$($manifest.controller_pid)"
if(!$process -or $process.Name -ne 'uv.exe' -or !$process.CommandLine.Contains('graph_demo.py') -or !$process.CommandLine.Contains($state)){throw 'controller_process_identity_mismatch'}
$records=Get-ChildItem -LiteralPath (Join-Path $state 'runner/runs') -Filter record.json -Recurse
if(!$records){throw 'terminal_record_missing'}
foreach($f in $records){
 $r=Get-Content -LiteralPath $f.FullName -Raw | ConvertFrom-Json
 if($r.status -notin @('completed','failed','cancelled','interrupted','unknown') -or !$r.attempt_finished){throw 'unfinished_run_refuses_upgrade'}
 $containers=& docker ps -aq --filter "label=laomedo.run_id=$($r.run_id)"
 if($LASTEXITCODE -ne 0 -or $containers){throw 'owned_container_refuses_upgrade'}
}
$ledger=Join-Path $state 'runner/turn-ledger.json'
$protected=@($ledger,(Join-Path $state 'config.json'))+@($records.FullName)
foreach($name in @('binding.json','update-receipt.json','close-receipt.json')){if(Test-Path (Join-Path $state $name)){$protected+=Join-Path $state $name}}
$hashes=@{};foreach($f in $protected){$hashes[$f]=(Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash}
# Refuse any active saved graph before stopping this one dedicated process tree.
$login=Invoke-RestMethod 'http://127.0.0.1:7864/api/v1/auto_login'
$headers=@{Authorization='Bearer '+$login.access_token}
$flows=Invoke-RestMethod 'http://127.0.0.1:7864/api/v1/flows/' -Headers $headers
foreach($flow in $flows){$pending=Invoke-RestMethod ("http://127.0.0.1:7864/api/v2/workflows/pending?flow_id="+$flow.id) -Headers $headers;if($pending){throw 'pending_graph_refuses_upgrade'}}
& taskkill.exe /PID $manifest.controller_pid /T /F | Out-Null
if($LASTEXITCODE -ne 0){throw 'controller_stop_failed'}
$args=@('run','--no-project','--offline','--python','3.12','--with','PyJWT[crypto]==2.15.1','--with','truststore==0.10.4','python','examples/github-issue/graph_demo.py','--state',$state,'--token-file',$tokenFile)
$new=Start-Process uv -ArgumentList $args -WorkingDirectory $source -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'claude-review.local/agent-inspection-controller.stdout') -RedirectStandardError (Join-Path $root 'claude-review.local/agent-inspection-controller.stderr')
$token=(Get-Content -LiteralPath $tokenFile -Raw).Trim();$ready=$false
for($i=0;$i -lt 30;$i++){
 try{$history=Invoke-RestMethod 'http://127.0.0.1:8784/v1/inspection/runs' -Headers @{Authorization='Bearer '+$token};if($history.schema_version -eq 'laomedo.agent-history.v1'){$ready=$true;break}}catch{};Start-Sleep -Seconds 1
}
if(!$ready){throw 'controller_inspection_startup_failed'}
foreach($f in $protected){if((Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash -ne $hashes[$f]){throw 'campaign_state_changed'}}
if(!(Get-Process -Id 39780 -ErrorAction SilentlyContinue)){throw 'independent_lease_service_missing'}
@{source=$revision;controller_pid=$new.Id;state=$state;turn_cap=3;preserved_used=1;lease_reused=$true} | ConvertTo-Json | Set-Content (Join-Path $root 'claude-review.local/agent-inspection-controller-services.json') -Encoding utf8
Write-Output 'Controller inspection enabled; campaign evidence/ledger unchanged; independent lease retained; zero model turns.'
