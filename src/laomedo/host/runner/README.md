# Local runner control

`RunnerService` in `service.py` owns host-configured API startup and cancellation.
Graph data cannot supply process commands, credentials or filesystem paths.
`routes.py` exposes authenticated controls; `http/` serves the separate Agent API.

| Object and method | Contract |
| --- | --- |
| `RunnerService.status(url=None)` | Check runner identity and Docker readiness without starting work. |
| `RunnerService.start(url=None)` | Admit one local API startup after a fresh successful Docker check. |
| `RunnerService.cancel_start(startup_id)` | Stop the exact startup attempt; do not stop an already-ready service. |
| `DockerReadiness` in `models.py` | Immutable reason and monotonic completion time for one Docker check. |
| `Settings` in `settings.py` | Read the trusted service-file location at point of use. |

Status checks remain nonblocking when another Docker check is running. Start
waits at most the Docker-check timeout for that existing check and consumes its
new result, rather than launching another check or dropping the requested action.
A stale, failed or unfinished check never authorizes startup. Neither startup nor
recovery reruns a graph or submits a model request.

`startup.py` coordinates cancellation with publishing the listener. Stable failure
codes are explained by the shared error catalogue; private startup logs and
configuration never become browser responses.
