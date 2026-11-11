"""Explicit supported-route OpenCode acceptance with temporary private auth."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, build_opener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--cancel-only", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.implementation / "src"))
    from claude_activity_acceptance import observe
    from laomedo.agents.agents.opencode.auth.utils import console_provider
    from laomedo.agents.agents.opencode.auth.transport import NoRedirect
    from laomedo.agents.agents.opencode.runtime import OpenCodeAgentRuntime
    from laomedo.agents.agents.opencode.agent import OpenCodeAgent
    from laomedo.agents.agents.base.utils import _json
    from laomedo.agents.activity.store import ActivityStore
    from laomedo.host.runner.http.server import RunnerServer
    from laomedo.host.private_state.utils import prepare_private_directory
    from laomedo.host.private_state.models import DirectoryPermissionPolicy
    from laomedo.host.private_state.windows import WindowsDirectorySecurity
    from laomedo.agents.errors import RunnerError

    def supported_config(url, headers):
        with build_opener(NoRedirect()).open(
            Request(url, headers=headers), timeout=30
        ) as response:
            remote = json.load(response)
        provider = remote["config"]["provider"]["opencode-go"]
        native = provider["models"]
        provider["models"] = {
            name: value
            for name, value in native.items()
            if value.get("provider", {}).get("npm", "@ai-sdk/openai-compatible")
            in {"@ai-sdk/openai", "@ai-sdk/openai-compatible", "@ai-sdk/anthropic"}
        }
        print(
            json.dumps(
                {
                    "stage": "routing_selection",
                    "available_models": len(native),
                    "supported_models": len(provider["models"]),
                }
            ),
            flush=True,
        )
        return remote

    server = http = None
    with tempfile.TemporaryDirectory(
        prefix="laomedo-opencode-acceptance-"
    ) as directory:
        root = Path(directory)
        profile = root / "profile"
        system = WindowsDirectorySecurity().system_directory()
        policy = DirectoryPermissionPolicy(
            whoami=system / "whoami.exe",
            icacls=system / "icacls.exe",
            environment=dict(os.environ),
            deadline=time.monotonic() + 60,
        )
        prepare_private_directory(profile, policy=policy)
        try:
            credential, org, routing, validity = console_provider(
                Path.home() / ".local/share/opencode/opencode.db",
                fetch=supported_config,
                include_routing=True,
                include_expiry=True,
            )
            _json(profile / "auth.json", {"opencode-go": credential})
            _json(
                profile / "auth-validity.json",
                dict(
                    validity,
                    credential_sha256=hashlib.sha256(
                        credential["key"].encode()
                    ).hexdigest(),
                ),
            )
            _json(
                profile / "provider-options.json",
                {
                    "provider": {
                        "opencode-go": dict(
                            routing, options={"headers": {"x-opencode-org-id": org}}
                        )
                    }
                },
            )
            del credential, org, validity
            source = root / "repository/source"
            source.mkdir(parents=True)
            subprocess.run(["git", "init", "--quiet", str(source.parent)], check=True)
            (source / "task.txt").write_text("Acceptance marker: amber-277.\n")

            def transport_factory(workspace, evidence):
                return OpenCodeAgentRuntime(workspace, evidence, profile=profile)

            agent = OpenCodeAgent(
                root / "runner",
                root / "registry",
                source,
                transport_factory=transport_factory,
            )
            ready = agent.readiness()
            print(
                json.dumps(
                    {
                        "stage": "readiness",
                        "provider": "opencode",
                        "ready": ready.ready,
                        "reason": ready.reason,
                        "scope": ready.scope,
                    }
                ),
                flush=True,
            )
            catalog = agent.model_catalog(refresh=True)
            models = catalog["models"]
            candidates = [
                value for value in models if value["id"].startswith("opencode-go/")
            ]
            selected = next(
                (value for value in candidates if "claude-haiku" in value["id"]),
                candidates[0],
            )
            model = selected["id"]
            print(
                json.dumps(
                    {
                        "stage": "discovery",
                        "model_count": len(models),
                        "selected_model": model,
                        "effort": "default",
                    }
                ),
                flush=True,
            )
            server = RunnerServer(agent, port=0)
            http = threading.Thread(target=server.serve_forever, daemon=True)
            http.start()
            store = ActivityStore(root / "application.db")
            fresh = observe(agent, server, store, "fresh", model, "default")
            resumed = (
                fresh
                if args.cancel_only
                else observe(agent, server, store, "resume", model, "default", fresh)
            )

            def active_worker():
                for backend in list(agent.active_backends.values()):
                    if getattr(backend, "_cancelled", None) is None:
                        continue
                    broker = backend.broker
                    with broker.lock:
                        receipts = list(broker.allocated_receipts)
                    for receipt in receipts:
                        if not receipt.exists() or not receipt.stem.startswith(
                            "laomedo-oc-worker-"
                        ):
                            continue
                        inspected = subprocess.run(
                            [
                                "docker",
                                "inspect",
                                "--format",
                                "{{.State.Running}}",
                                receipt.stem,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if (
                            inspected.returncode == 0
                            and inspected.stdout.strip() == "true"
                        ):
                            return True
                return False

            observe(
                agent,
                server,
                store,
                "cancel",
                model,
                "default",
                resumed,
                cancel_ready=active_worker,
            )
        except RunnerError as error:
            print(
                json.dumps(
                    {"stage": "blocked", "provider": "opencode", "code": error.code}
                ),
                flush=True,
            )
            raise RuntimeError("opencode_acceptance_blocked") from None
        finally:
            if server:
                server.shutdown()
                http.join(timeout=5)
                server.server_close()
    print(
        json.dumps(
            {"stage": "temporary_profile_cleanup", "removed": not root.exists()}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
