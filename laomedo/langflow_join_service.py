"""Opt-in host service for a saved-flow Langflow Playground join.

This command does not launch Langflow or the Codex runner. Supply private token
files and a private run store outside Git; it never prints token contents.
"""

import argparse
from pathlib import Path

from .langflow_join import LangflowJoinController
from .langflow_join_http import RunnerHTTPTransport, serve_langflow_join
from .work_graph.grants import _private_path
from .work_graph.local_launch import LangflowLocalClient
from .workflow_run_store import LaunchError, WorkflowRunStore


def _token_file(path):
    source = _private_path(path)
    if not source.is_file():
        raise LaunchError("join_token_file_unavailable")
    try:
        value = source.read_text(encoding="utf-8").strip()
    except OSError:
        raise LaunchError("join_token_file_unavailable") from None
    if not value:
        raise LaunchError("join_token_file_empty")
    return value


def build_service(*, store_path, bridge_token_file, runner_token_file,
                  langflow_url, runner_url, port):
    store = _private_path(store_path)
    bridge_source = _private_path(bridge_token_file)
    runner_source = _private_path(runner_token_file)
    if len({store, bridge_source, runner_source}) != 3:
        raise LaunchError("join_private_paths_must_differ")
    bridge_token = _token_file(bridge_source)
    runner_token = _token_file(runner_source)
    client = LangflowLocalClient(langflow_url)
    controller = LangflowJoinController(
        WorkflowRunStore(store), RunnerHTTPTransport(runner_url, runner_token),
        client.fetch)
    return serve_langflow_join(controller, bridge_token, port=port)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--bridge-token-file", required=True, type=Path)
    parser.add_argument("--runner-token-file", required=True, type=Path)
    parser.add_argument("--langflow-url", required=True)
    parser.add_argument("--runner-url", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args(argv)
    server = build_service(
        store_path=args.store, bridge_token_file=args.bridge_token_file,
        runner_token_file=args.runner_token_file,
        langflow_url=args.langflow_url, runner_url=args.runner_url,
        port=args.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
