[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][ValidateSet('host-services','bundle-verifier')][string]$Service,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Checkout,
    [Parameter(Mandatory)][string]$Configuration
)
$ErrorActionPreference = 'Stop'
# Only a configuration-file reference is stored in Task Scheduler. No token,
# grant or provider environment value is accepted as an action argument.
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
$checkoutPath = (Resolve-Path -LiteralPath $Checkout).Path
$configPath = (Resolve-Path -LiteralPath $Configuration).Path
foreach ($value in @($pythonPath, $checkoutPath, $configPath)) {
    if ($value.Contains('"') -or $value.Contains("`n") -or $value.Contains("`r")) {
        throw 'Task path contains unsafe characters'
    }
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$taskName = 'Laomedo-' + $identity.User.Value + '-' + $Service
$description = 'Laomedo managed per-user host process v1'
$existing = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue
if ($existing) { throw 'Task already exists; inspect and explicitly remove it before replacement' }
$arguments = '-m laomedo.managed_service --service ' + $Service + ' --configuration "' + $configPath + '"'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $checkoutPath
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
if ($PSCmdlet.ShouldProcess($taskName, 'Register independent per-user Laomedo task (does not start it)')) {
    Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $action -Principal $principal -Trigger $trigger -Settings $settings -Description $description | Out-Null
    Write-Output $taskName
}
