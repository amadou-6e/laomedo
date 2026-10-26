import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
from unittest import TestCase, main, mock
from urllib import error, request


MODULE_PATH = (Path(__file__).resolve().parents[1] / "experiments" / "exp18" /
               "runner_probe_sidecar.py")
spec = importlib.util.spec_from_file_location("exp18_runner_probe_sidecar", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SidecarTests(TestCase):
    def test_fixed_unauthenticated_request_only(self):
        response = mock.Mock(status=401)
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with mock.patch.object(module.http.client, "HTTPConnection",
                               return_value=connection) as constructor:
            self.assertEqual(module.probe_runner(), 401)
        constructor.assert_called_once_with("host.docker.internal", 8767, timeout=3)
        connection.request.assert_called_once_with(
            "GET", "/v1/runs/00000000-0000-0000-0000-000000000000")
        connection.close.assert_called_once()

    def test_server_rejects_stage_controlled_route_and_body(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with mock.patch.object(module, "probe_runner", return_value=401) as probe:
                with self.assertRaises(error.HTTPError) as denied:
                    request.urlopen(base + module.PROBE_PATH,
                                    timeout=2)
                self.assertEqual(denied.exception.code, 401)
                probe.assert_called_once_with()
                for path, method, data, expected in (
                    (module.PROBE_PATH + "?url=http://example", "GET", None, 404),
                    (module.PROBE_PATH, "POST", b"secret", 405),
                    (module.PROBE_PATH, "GET", b"secret", 404),
                ):
                    with self.subTest(path=path, method=method):
                        req = request.Request(base + path, method=method, data=data,
                                              headers={"Authorization": "secret"})
                        with self.assertRaises(error.HTTPError) as rejected:
                            request.urlopen(req, timeout=2)
                        self.assertEqual(rejected.exception.code, expected)
                self.assertEqual(probe.call_count, 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
