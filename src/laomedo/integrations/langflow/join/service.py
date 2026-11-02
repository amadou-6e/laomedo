"""Opt-in host service for a saved-flow Langflow Playground join.

This command does not launch Langflow or the Codex runner. Supply private token
files and a private run store outside Git; it never prints token contents.
"""

from pathlib import Path
import argparse
import laomedo.work_graph.runs.errors as _workflow_errors
import laomedo.work_graph.runs.store as _workflow_store
import laomedo.integrations.langflow.join.controller as _join_controller
import laomedo.integrations.langflow.join.server as _join_server
import laomedo.integrations.langflow.join.transport as _join_transport
import laomedo.work_graph.client as _work_graph_client
import laomedo.work_graph.grant_utils as _work_graph_grant_utils


def _token_file(path):
    source = _work_graph_grant_utils._private_path(path)
    if not source.is_file():
        raise _workflow_errors.LaunchError("join_token_file_unavailable")
    try:
        value = source.read_text(encoding="utf-8").strip()
    except OSError:
        raise _workflow_errors.LaunchError("join_token_file_unavailable") from None
    if not value:
        raise _workflow_errors.LaunchError("join_token_file_empty")
    return value


def build_service(
    *,
    store_path,
    bridge_token_file,
    runner_token_file,
    langflow_url,
    runner_url,
    port,
    provider="codex",
):
    store = _work_graph_grant_utils._private_path(store_path)
    bridge_source = _work_graph_grant_utils._private_path(bridge_token_file)
    runner_source = _work_graph_grant_utils._private_path(runner_token_file)
    if len({store, bridge_source, runner_source}) != 3:
        raise _workflow_errors.LaunchError("join_private_paths_must_differ")
    bridge_token = _token_file(bridge_source)
    runner_token = _token_file(runner_source)
    client = _work_graph_client.LangflowLocalClient(langflow_url)
    controller = _join_controller.LangflowJoinController(
        _workflow_store.WorkflowRunStore(store),
        _join_transport.RunnerHTTPTransport(
            runner_url, runner_token, provider=provider
        ),
        client.fetch,
    )
    return _join_server.JoinServer(controller, bridge_token, port=port)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--bridge-token-file", required=True, type=Path)
    parser.add_argument("--runner-token-file", required=True, type=Path)
    parser.add_argument("--langflow-url", required=True)
    parser.add_argument("--runner-url", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--provider", choices=["codex", "claude"], default="codex")
    args = parser.parse_args(argv)
    server = build_service(
        store_path=args.store,
        bridge_token_file=args.bridge_token_file,
        runner_token_file=args.runner_token_file,
        langflow_url=args.langflow_url,
        runner_url=args.runner_url,
        port=args.port,
        provider=args.provider,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
