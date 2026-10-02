"""Inspect the real private provider connection without submitting a model turn."""

import json

import acceptance as a


RUN_ID = "15b19d98-9e3e-40ca-8ab1-30fc4c911cd1"


def main():
    root = a.STATE / "runs-state/runs" / RUN_ID
    backend = a.factory(root / "workspace", root)
    try:
        health = backend.call("GET", "/global/health")
        catalog = backend.call("GET", "/provider")
        connected = "opencode-go" in catalog.get("connected", [])
        provider = next((entry for entry in catalog.get("all", [])
                         if entry.get("id") == "opencode-go"), {})
        model = "gpt-6-luna" in provider.get("models", {})
    finally:
        backend.close()
    placeholder = a.profile() / "sessions/auth.json"
    empty = not placeholder.exists() or placeholder.stat().st_size == 0
    result = {"controller_healthy": health.get("healthy") is True,
              "provider_connected": connected, "model_available": model,
              "session_auth_placeholder_empty": empty, "model_turns_submitted": 0}
    print(json.dumps(result))
    if not all(result[name] for name in
               ("controller_healthy", "provider_connected", "model_available",
                "session_auth_placeholder_empty")):
        raise RuntimeError("real_provider_preflight_incomplete")


if __name__ == "__main__":
    main()
