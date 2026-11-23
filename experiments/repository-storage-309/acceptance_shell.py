"""Bounded live selected-file checks through the preview's normal profile login."""

from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor
from uuid import uuid4


class StorageAcceptance:
    """Use existing saved provider accounts; never export or copy credentials."""

    def __init__(self):
        self.base = "http://127.0.0.1:55753"
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self.opener.addheaders = [("Origin", self.base)]
        self.marker = "repository-pilot-" + uuid4().hex[:12]

    def request(self, path, body=None):
        request = Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with self.opener.open(request, timeout=150) as response:
            return json.load(response)

    def login(self):
        profiles = self.request("/api/v1/laomedo/profiles")["profiles"]
        profile = next(row for row in profiles if row["name"].lower() == "amadou")
        pin = next(
            line.split("=", 1)[1].strip().strip("\"'")
            for line in Path("C:/CodeWorkspace/laomedo/.env")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.startswith("LAOMEDO_PIN=")
        )
        self.opener.open(
            self.base + "/api/v1/login",
            data=urlencode({"username": profile["name"], "password": pin}).encode(),
        ).close()

    def wait(self, identifier):
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            result = self.request(
                "/api/v1/laomedo/assistant/conversations/" + identifier
            )
            if result["conversation"]["active_message_id"] is None:
                return result
            time.sleep(1)
        raise RuntimeError("acceptance_turn_did_not_settle")

    def message(self, identifier, text):
        self.request(
            "/api/v1/laomedo/assistant/conversations/" + identifier + "/messages",
            {"client_message_id": str(uuid4()), "text": text},
        )
        result = self.wait(identifier)
        message = result["messages"][-1]
        if message["state"] != "completed" or message.get("error_code"):
            raise RuntimeError(
                "turn_" + message["state"] + ":" + str(message.get("error_code"))
            )
        return result

    def run(self):
        self.login()
        prefix = "/api/v1/laomedo/assistant"
        state = self.request(prefix + "/storage")
        repository = next(
            row
            for row in state["repositories"]
            if row["name"] == "Repository storage validation"
        )
        checkout = Path(repository["path"])
        expected_root = (
            Path(os.environ["LOCALAPPDATA"])
            / "Laomedo/acceptance/assistant-saved-293-01a1ba85/project-storage/checkouts"
        )
        if not checkout.resolve().is_relative_to(expected_root.resolve()):
            raise RuntimeError("wrong_acceptance_checkout")
        location = {"repository_id": repository["id"], "path": "agent-files"}
        if state["agent_files"] not in (None, location):
            raise RuntimeError("preserve_existing_storage_selection")
        self.request(prefix + "/storage/agent-files", location)
        (checkout / "agent-files" / "acceptance-seed.md").write_text(
            self.marker, encoding="utf-8"
        )
        graph = next(
            row
            for row in state["workflows"]
            if row["id"] == "d6e24c04-1cb3-4f05-b9a6-bb0732dd0b73"
        )
        if graph["id"] not in state["graphs"]:
            self.request(
                prefix + "/storage/graphs/" + graph["id"] + "/save",
                {
                    "location": {
                        "repository_id": repository["id"],
                        "path": "graphs/validation.json",
                    },
                    "expected_graph_revision": graph["revision"],
                    "expected_file_hash": None,
                },
            )
        connections = self.request(prefix + "/connections")["connections"]
        results = []
        for provider in ("codex", "claude", "opencode"):
            try:
                connection = next(
                    row
                    for row in connections
                    if row["provider"] == provider and row["lifecycle"] == "connected"
                )
                query = urlencode(
                    {
                        "provider": provider,
                        "connection_id": connection["connection_id"],
                        "connection_generation": connection["generation"],
                    }
                )
                models = self.request(prefix + "/models?" + query)["models"]
                candidates = [
                    row
                    for row in models
                    if provider != "opencode" or row["id"].startswith("opencode-go/")
                ]
                model = (candidates or models)[0]
                effort = "low" if "low" in model["efforts"] else model["efforts"][0]
                conversation = self.request(
                    prefix + "/conversations",
                    {
                        "provider": provider,
                        "connection_id": connection["connection_id"],
                        "connection_generation": connection["generation"],
                        "model": model["id"],
                        "effort": effort,
                    },
                )
                identifier = (
                    conversation.get("id") or conversation["conversation"]["id"]
                )
                expected = self.marker + "-" + provider
                task = (
                    "Use your normal shell tool, not MCP file tools. Read project/agent-files/acceptance-seed.md and project/graphs/"
                    + graph["id"]
                    + ".json. Write the seed text followed by '-"
                    + provider
                    + "' into project/agent-files/"
                    + provider
                    + "-acceptance.md. Do not change any other files, workflows, or settings. Reply only with the written text."
                )
                first = self.message(identifier, task)
                target = checkout / "agent-files" / (provider + "-acceptance.md")
                if target.read_text(encoding="utf-8").strip() != expected:
                    raise RuntimeError("fresh_shell_write_not_persisted")
                self.message(
                    identifier,
                    "Using your normal shell tool, append '-resumed' to project/agent-files/"
                    + provider
                    + "-acceptance.md. Do not change any other files. Reply only with the complete new content.",
                )
                if target.read_text(encoding="utf-8").strip() != expected + "-resumed":
                    raise RuntimeError("resumed_shell_write_not_persisted")
                results.append(
                    {
                        "provider": provider,
                        "fresh": "passed",
                        "resume": "passed",
                        "conversation": identifier,
                    }
                )
            except Exception as error:
                # No response bodies, account identities or provider credentials in evidence.
                results.append(
                    {
                        "provider": provider,
                        "result": "blocked",
                        "reason": (
                            str(error)
                            if isinstance(error, RuntimeError)
                            else type(error).__name__
                        ),
                    }
                )
            print(json.dumps(results[-1]), flush=True)


if __name__ == "__main__":
    StorageAcceptance().run()
