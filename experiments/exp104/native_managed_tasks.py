"""Ownership-checked S12 task fixture; no task starts on import."""
from pathlib import Path
import json
import time

from experiments.exp104.probe_managed_startup import powershell, processes, quote

CHECKOUT = Path(__file__).resolve().parents[2]
SERVICES = ("host-services", "bundle-verifier")
DESCRIPTION = "Laomedo managed per-user host process v1"


def expected_arguments(service, configuration):
    if service not in SERVICES:
        raise ValueError("unknown_service")
    if any(char in str(configuration) for char in ('"', '\r', '\n', '\0')):
        raise ValueError("unsafe_configuration_path")
    return '-m laomedo.managed_service --service ' + service + ' --configuration "' + str(configuration) + '"'


def register(root, python, owned):
    """Record exact candidate before registration; never replace an existing task."""
    for service in SERVICES:
        configuration = (root / (service + ".json")).resolve()
        expected_arguments(service, configuration)
        if not configuration.is_file():
            raise ValueError("configuration_missing")
        task = powershell("'Laomedo-' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value + '-' + " + quote(service))
        if not task.startswith("Laomedo-S-1-") or not task.endswith("-" + service):
            raise ValueError("task_identity_invalid")
        powershell("if (Get-ScheduledTask -TaskPath '\\' -TaskName " + quote(task) +
                   " -ErrorAction SilentlyContinue) { throw 'task_already_exists' }")
        # Preserve candidate even if the installer result is lost.
        owned[service] = {"name": task, "configuration": configuration,
                          "python": Path(python).resolve()}
        registered = powershell("& " + quote(CHECKOUT / "scripts/Install-LaomedoUserTask.ps1") +
            " -Service " + quote(service) + " -Python " + quote(python) +
            " -Checkout " + quote(CHECKOUT) + " -Configuration " + quote(configuration))
        if registered != task:
            raise RuntimeError("task_registration_unknown")
        powershell("Start-ScheduledTask -TaskPath '\\' -TaskName " + quote(task))


def evidence(service, item):
    arguments = expected_arguments(service, item["configuration"])
    return json.loads(powershell("$t = Get-ScheduledTask -TaskPath '\\' -TaskName " + quote(item["name"]) +
        "; @{ limited = ($t.Principal.RunLevel -eq 'Limited'); "
        "interactive = ($t.Principal.LogonType -eq 'Interactive'); "
        "ignore_new = ($t.Settings.MultipleInstances -eq 'IgnoreNew'); "
        "ownership_matches = ($t.Description -eq " + quote(DESCRIPTION) +
        " -and @($t.Actions).Count -eq 1 -and $t.Actions.Execute -eq " + quote(item["python"]) +
        " -and $t.Actions.Arguments -eq " + quote(arguments) +
        " -and $t.Actions.WorkingDirectory -eq " + quote(CHECKOUT) +
        ") } | ConvertTo-Json -Compress"))


def cleanup(owned):
    """Remove only saved action identity; no directory or wildcard deletion."""
    result = {}
    for service, item in owned.items():
        try:
            if service not in SERVICES:
                raise ValueError("unknown_service")
            arguments = expected_arguments(service, item["configuration"])
            powershell("$t = Get-ScheduledTask -TaskPath '\\' -TaskName " + quote(item["name"]) +
                " -ErrorAction SilentlyContinue; if ($t) { "
                "if ($t.Description -ne " + quote(DESCRIPTION) +
                " -or @($t.Actions).Count -ne 1 -or $t.Actions.Execute -ne " + quote(item["python"]) +
                " -or $t.Actions.Arguments -ne " + quote(arguments) +
                " -or $t.Actions.WorkingDirectory -ne " + quote(CHECKOUT) +
                ") { throw 'task_ownership_changed' }; "
                "Stop-ScheduledTask -TaskPath '\\' -TaskName " + quote(item["name"]) +
                "; Unregister-ScheduledTask -TaskPath '\\' -TaskName " + quote(item["name"]) +
                " -Confirm:$false }; if (Get-ScheduledTask -TaskPath '\\' -TaskName " +
                quote(item["name"]) + " -ErrorAction SilentlyContinue) { throw 'task_remains' }")
            deadline = time.monotonic() + 10
            while processes(item["configuration"]) and time.monotonic() < deadline:
                time.sleep(.1)
            result[service] = not processes(item["configuration"])
        except Exception:
            result[service] = False
    return result
