"""Scoped real-provider acceptance; no credentials or raw native output in evidence."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--native-model-metadata", action="store_true")
    parser.add_argument("--session-login", action="store_true")
    parser.add_argument("--resume-cancel", action="store_true")
    parser.add_argument("--open-session", action="store_true")
    parser.add_argument("--max-prompts", type=int, default=1, choices=(1, 2, 3))
    args = parser.parse_args()
    sys.path.insert(0, str(args.implementation / "src"))
    from laomedo.agents.agents.codex.agent import CodexAgent
    from laomedo.agents.errors import RunnerError

    if args.native_model_metadata:
        observe_native_models()

    with tempfile.TemporaryDirectory(prefix="laomedo-docker-acceptance-") as temporary:
        root = Path(temporary)
        repository = root / "repository"
        source = repository / "source"
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
        (source / "task.txt").write_text("Docker acceptance marker: amber-277.\n")
        lease = root / "lease"
        environment = dict(os.environ, PYTHONPATH=str(args.implementation / "src"))
        log = (root / "supervisor.log").open("wb")
        supervisor = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "laomedo.host.leases.service_cli",
                "serve",
                "--state",
                str(lease),
            ],
            env=environment,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + 20
            while not (lease / "service.json").exists():
                if supervisor.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("lease_service_start_failed")
                time.sleep(0.1)
            options = session_login() if args.session_login else {}
            agent = CodexAgent(
                root / "runner",
                root / "registry",
                source,
                lease_service=lease,
                **options,
            )
            print(
                json.dumps(
                    {
                        "stage": "admission",
                        "provider": "codex",
                        "image_id": agent.image_id,
                    }
                ),
                flush=True,
            )
            catalog = agent.model_catalog(refresh=True)
            models = catalog["models"]
            print(
                json.dumps(
                    {
                        "stage": "discovery",
                        "provider": "codex",
                        "model_count": len(models),
                    }
                ),
                flush=True,
            )
            if args.native_model_metadata:
                typed = agent.catalog.list_models()
                print(
                    json.dumps(
                        {
                            "stage": "typed_catalog",
                            "default_model_id": typed.default_model_id,
                            "models": [model.model_dump() for model in typed.models],
                            "wire_fields": sorted(catalog),
                        }
                    ),
                    flush=True,
                )
            if not args.execute and not args.open_session:
                return
            selected = next((m for m in models if "gpt-5" in m["id"]), models[0])
            model = selected["id"]
            efforts = selected.get("efforts", [])
            effort = (
                "low" if "low" in efforts else (efforts[0] if efforts else "default")
            )
            if args.open_session:
                asyncio.run(check_session(agent, model, effort))
                return
            first = agent.start(
                {
                    "task": "Read task.txt and reply with only the acceptance marker. Do not edit files or delegate.",
                    "model": model,
                    "effort": effort,
                }
            )
            print(
                json.dumps(
                    {
                        "stage": "fresh",
                        "status": first["status"],
                        "error": first.get("error_category"),
                        "answer_ok": "amber-277" in (first.get("answer") or ""),
                        "model": model,
                    }
                ),
                flush=True,
            )
            if first["status"] != "completed" or args.max_prompts < 2:
                return
            if args.resume_cancel:
                resume_then_cancel(agent, first, model, effort)
                return
            second = agent.resume(
                first["run_id"],
                "What marker did you just read? Reply with only that marker. Do not use tools or delegate.",
                expected_post_run_hash=first["post_run_hash"],
                expected_thread_id=first["thread_id"],
                model=model,
                effort=effort,
            )
            print(
                json.dumps(
                    {
                        "stage": "resume",
                        "status": second["status"],
                        "error": second.get("error_category"),
                        "thread_preserved": second.get("thread_id")
                        == first["thread_id"],
                        "answer_ok": "amber-277" in (second.get("answer") or ""),
                    }
                ),
                flush=True,
            )
            if args.max_prompts < 3 or second["status"] != "completed":
                return
            resume_then_cancel(agent, second, model, effort)
        except RunnerError as error:
            print(
                json.dumps(
                    {"stage": "blocked", "provider": "codex", "code": error.code}
                ),
                flush=True,
            )
        finally:
            supervisor.terminate()
            supervisor.wait(timeout=15)
            log.close()


def observe_native_models():
    """Record only allowlisted public model fields; never session or login data."""
    from laomedo.agents.agents.codex.runtime import CodexAgentRuntime

    original = CodexAgentRuntime.extension

    async def observe(self, method, params, **kwargs):
        result = await original(self, method, params, **kwargs)
        if method == "laomedo/codexModels":
            print(
                json.dumps(
                    {
                        "stage": "native_catalog_metadata",
                        "models": [
                            {
                                key: item[key]
                                for key in (
                                    "id",
                                    "displayName",
                                    "defaultReasoningEffort",
                                    "isDefault",
                                )
                                if key in item
                            }
                            for item in result["data"]
                        ],
                    }
                ),
                flush=True,
            )
        return result

    CodexAgentRuntime.extension = observe


def resume_then_cancel(agent, first, model, effort):
    """Resume the completed native session and cancel its active second turn."""
    from laomedo.agents.agents.codex.runtime import CodexAgentRuntime

    results, errors = [], []
    prompt_started = threading.Event()
    original_prompt = CodexAgentRuntime.prompt

    async def observe_prompt(self, *args, **kwargs):
        prompt_started.set()
        return await original_prompt(self, *args, **kwargs)

    CodexAgentRuntime.prompt = observe_prompt

    def resume():
        try:
            results.append(
                agent.resume(
                    first["run_id"],
                    "Use the shell to sleep for 45 seconds, then repeat the marker from our previous turn. Do not edit files or delegate.",
                    expected_post_run_hash=first["post_run_hash"],
                    expected_thread_id=first["thread_id"],
                    model=model,
                    effort=effort,
                )
            )
        except Exception as error:
            errors.append(type(error).__name__)

    worker = threading.Thread(target=resume)
    worker.start()
    started = prompt_started.wait(timeout=60)
    if started:
        time.sleep(3)
    requested = agent.cancel(first["run_id"])
    worker.join(timeout=120)
    if worker.is_alive():
        raise RuntimeError("resumed_turn_did_not_settle_after_cancellation")
    CodexAgentRuntime.prompt = original_prompt
    current = agent.status(first["run_id"])
    print(
        json.dumps(
            {
                "stage": "resumed_turn_cancellation",
                "prompt_started": started,
                "status": current["status"],
                "thread_preserved": current.get("thread_id") == first["thread_id"],
                "requested": requested.get("cancel_requested"),
                "confirmed": current.get("cancel_confirmed"),
                "error": current.get("error_category"),
                "worker_errors": errors,
            }
        ),
        flush=True,
    )


def session_login():
    """Borrow only the explicitly authorized host access token for this process."""
    from pydantic import SecretStr
    from laomedo.agents.errors import RunnerError

    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    try:
        stored = json.loads((home / "auth.json").read_text(encoding="utf-8"))
        native = stored.get("tokens") or {}
        access = native["access_token"]
        account = native["account_id"]
        if (
            not isinstance(access, str)
            or not access
            or not isinstance(account, str)
            or not account
        ):
            raise ValueError()
    except (OSError, ValueError, TypeError, KeyError):
        raise RunnerError("session_access_credential_unavailable") from None
    return {
        "split_executor": True,
        "split_access_token": SecretStr(access),
        "split_provider_config": (
            'model_provider="session_chatgpt"',
            'model_providers.session_chatgpt.name="Authorized host session"',
            'model_providers.session_chatgpt.base_url="https://chatgpt.com/backend-api/codex"',
            'model_providers.session_chatgpt.env_key="ACCESS_TOKEN"',
            'model_providers.session_chatgpt.wire_api="responses"',
            "model_providers.session_chatgpt.requires_openai_auth=false",
            "model_providers.session_chatgpt.supports_websockets=false",
            'model_providers.session_chatgpt.http_headers={"ChatGPT-Account-Id"='
            + json.dumps(account)
            + "}",
        ),
    }


async def check_session(agent, model, effort):
    from laomedo.agents.agents.base.acp.session import AcpSession
    from laomedo.agents.errors import RunnerError

    original = AcpSession._request

    async def observed(self, request, method, seconds):
        try:
            return await original(self, request, method, seconds)
        except RunnerError as error:
            cause = error.__context__
            print(
                json.dumps(
                    {
                        "stage": "rpc_failure",
                        "method": method,
                        "code": error.code,
                        "cause_type": type(cause).__name__,
                        "rpc_code": getattr(cause, "code", None),
                        "diagnostic_terms": [
                            term
                            for term in (
                                "auth",
                                "login",
                                "permission denied",
                                "read-only",
                                "no such file",
                                "spawn",
                                "invalid",
                                "model",
                                "sandbox",
                                "config",
                                "thread/start",
                                "unsupported",
                                "deserialize",
                                "environment",
                                "token",
                            )
                            if term in str(cause).lower()
                        ],
                    }
                ),
                flush=True,
            )
            raise

    AcpSession._request = observed
    record = agent._prepare(
        {"task": "No prompt: session setup only.", "model": model, "effort": effort}
    )
    root = agent._run_dir(record["run_id"])
    runtime = agent._open_server(root, lifetime_seconds=120)
    try:
        await runtime.initialize()
        print(json.dumps({"stage": "session_initialize", "ok": True}), flush=True)
        await runtime.open(record, resume=False)
        print(json.dumps({"stage": "session_open", "ok": True}), flush=True)
    finally:
        await runtime.shutdown()


if __name__ == "__main__":
    main()
