import importlib.util
from pathlib import Path
import sys
import unittest


PATH = (Path(__file__).resolve().parents[1] / "experiments" / "exp18" /
        "model_egress_proxy.py")
spec = importlib.util.spec_from_file_location("exp18_model_egress", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.insert(0, str(PATH.parent))
preflight_spec = importlib.util.spec_from_file_location(
    "exp18_model_egress_preflight", PATH.parent / "probe_model_egress_create.py")
preflight = importlib.util.module_from_spec(preflight_spec)
preflight_spec.loader.exec_module(preflight)


class ModelEgressTests(unittest.TestCase):
    def test_only_fixed_connect_authority_is_accepted(self):
        request = (b"CONNECT api.openai.com:443 HTTP/1.1\r\n"
                   b"Host: api.openai.com:443\r\n\r\nTLS")
        self.assertEqual(module.parse_connect(request), b"TLS")
        for target in (b"host.docker.internal:8767", b"api.openai.com:80",
                       b"example.com:443", b"127.0.0.1:2375"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                module.parse_connect(request.replace(b"api.openai.com:443", target))
        with self.assertRaises(ValueError):
            module.parse_connect(b"GET http://api.openai.com/ HTTP/1.1\r\n\r\n")

    def test_proxy_refuses_credentials_and_request_body_headers(self):
        base = b"CONNECT api.openai.com:443 HTTP/1.1\r\n"
        for extra in (b"Proxy-Authorization: Basic fixture\r\n",
                      b"Content-Length: 1\r\n",
                      b"Transfer-Encoding: chunked\r\n",
                      b"Host: host.docker.internal:8767\r\n"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                module.parse_connect(base + extra + b"\r\n")

    def test_create_preflight_refuses_weakened_sidecar_config(self):
        host = {"PidsLimit": 64, "Memory": 128 * 1024 * 1024,
                "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0}}
        item = {"HostConfig": host, "Config": {"WorkingDir": "", "Cmd": None,
                                              "Env": ["PATH=/bin"]}}
        self.assertEqual(preflight.extra_errors(item, ["PATH=/bin"]), [])
        for key, value in (("Tmpfs", {"/tmp": "rw"}),
                           ("Devices", [{"PathOnHost": "/dev/fuse"}]),
                           ("PidMode", "host"), ("PidsLimit", 0)):
            with self.subTest(key=key):
                weakened = {"HostConfig": {**host, key: value},
                            "Config": item["Config"]}
                self.assertTrue(preflight.extra_errors(weakened, ["PATH=/bin"]))
        self.assertIn("sidecar_environment_mismatch",
                      preflight.extra_errors(item, ["PATH=/bin", "TOKEN=x"]))


if __name__ == "__main__":
    unittest.main()
