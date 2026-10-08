"""Credential-free Codex command/exec network check for Phase C.

The host endpoint returns only a fixed marker. No model turn or mediator
capability is used. The printed result includes only the exit code and marker.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import tempfile
import threading

from laomedo.local_runner import AppServer, _docker_prefix


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"PHASE-C-NETWORK-READY")

    def log_message(self, *_):
        pass


def main():
    host = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    host_thread = threading.Thread(target=host.serve_forever, daemon=True)
    host_thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="laomedo-phase-c-network-") as directory:
            root = Path(directory)
            for name in ("workspace", "canonical", "store", "evidence"):
                (root / name).mkdir()
            command = ["docker", *_docker_prefix(
                root / "workspace", root / "canonical", root / "store")]
            server = AppServer(command, root / "evidence")
            try:
                initialized = server.request("initialize", {"clientInfo": {
                    "name": "laomedo_phase_c_network", "title": "Phase C Network Check",
                    "version": "0.1.0"}})
                if "result" not in initialized:
                    raise RuntimeError("initialize_rejected")
                server.notify("initialized", {})
                script = ("fetch('http://host.docker.internal:" + str(host.server_port) +
                          "/health', {signal: AbortSignal.timeout(3000)})"
                          ".then(async r => { console.log(r.status === 200 && "
                          "(await r.text()) === 'PHASE-C-NETWORK-READY' ? 'READY' : "
                          "'WRONG_RESPONSE') })"
                          ".catch(() => { console.log('DENIED'); process.exitCode = 2 })")
                response = server.request("command/exec", {
                    "command": ["node", "-e", script], "cwd": "/draft",
                    "timeoutMs": 10000}, timeout=20)
                result = response.get("result") or {}
                output = str(result.get("stdout", ""))
                print(json.dumps({"exit_code": result.get("exitCode"),
                                  "ready": "READY" in output,
                                  "denied": "DENIED" in output}))
            finally:
                server.close()
    finally:
        host.shutdown()
        host.server_close()
        host_thread.join(timeout=5)


if __name__ == "__main__":
    main()
