import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "exp18" / "preflight.py"
spec = importlib.util.spec_from_file_location("exp18_preflight", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.source = str(Path(__file__).resolve())
        self.mounts = {"/skills": ("bind", self.source, False),
                       "/draft": ("bind", self.source, True)}
        self.inspect = {
            "HostConfig": {"ReadonlyRootfs": True, "CapDrop": ["ALL"],
                           "SecurityOpt": ["no-new-privileges:true"],
                           "PidsLimit": 128, "Memory": 1024 ** 3,
                           "NetworkMode": "exp18-private", "Privileged": False},
            "Config": {"User": "10001:10001"},
            "Mounts": [
                {"Destination": target, "Type": "bind", "Source": self.source,
                 "RW": writable} for target, (_, _, writable) in self.mounts.items()
            ],
        }

    def test_exact_grant_accepted(self):
        self.assertEqual(module.validate_inspect(self.inspect, self.mounts,
                                                 "exp18-private"), [])

    def test_writable_skill_mount_and_extra_mount_rejected(self):
        self.inspect["Mounts"][0]["RW"] = True
        self.inspect["Mounts"].append({"Destination": "/host", "Type": "bind",
                                        "Source": self.source, "RW": False})
        errors = module.validate_inspect(self.inspect, self.mounts, "exp18-private")
        self.assertIn("mount_mismatch:/skills", errors)
        self.assertIn("mount_set_mismatch", errors)

    def test_missing_protection_rejected(self):
        self.inspect["HostConfig"]["ReadonlyRootfs"] = False
        self.inspect["HostConfig"]["SecurityOpt"] = []
        self.inspect["HostConfig"]["Privileged"] = True
        errors = module.validate_inspect(self.inspect, self.mounts, "exp18-private")
        self.assertIn("root_not_read_only", errors)
        self.assertIn("new_privileges_allowed", errors)
        self.assertIn("privileged_or_unknown", errors)

    def test_fixture_roots_must_be_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            roots = {name: base / name for name in ("checkout", "effective_skill",
                     "canonical_skill", "host", "runner_store", "credential_standin")}
            for path in roots.values():
                path.mkdir()
            self.assertEqual(module.validate_host_roots(roots), [])
            roots["canonical_skill"] = roots["checkout"]
            self.assertTrue(any(error.startswith("overlapping_roots:") for error
                                in module.validate_host_roots(roots)))


if __name__ == "__main__":
    unittest.main()
