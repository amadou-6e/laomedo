import importlib.util
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "exp18" / "preflight.py"
spec = importlib.util.spec_from_file_location("exp18_preflight", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.image_id = "sha256:" + "a" * 64
        self.tmpfs = {"/tmp": "rw,nosuid,nodev,size=16m"}
        self.source = str(Path(__file__).resolve())
        self.mounts = {"/skills": ("bind", self.source, False),
                       "/draft": ("bind", self.source, True)}
        host = deepcopy(module.HOST_CONFIG_BASELINE)
        host["NetworkMode"] = "exp18-private"
        host["SecurityOpt"] = ["no-new-privileges:true"]
        for mount in host["Mounts"]:
            mount["Source"] = self.source
        self.inspect = {
            "Image": self.image_id,
            "HostConfig": host,
            "Config": {"User": "10001:10001"},
            "Mounts": [
                {"Destination": target, "Type": "bind", "Source": self.source,
                 "RW": writable, "Propagation": "rprivate"}
                for target, (_, _, writable) in self.mounts.items()
            ],
        }

    def test_exact_grant_accepted(self):
        self.assertEqual(module.validate_inspect(self.inspect, self.mounts,
                                                 "exp18-private", self.image_id,
                                                 self.tmpfs), [])

    def test_writable_skill_mount_and_extra_mount_rejected(self):
        self.inspect["Mounts"][0]["RW"] = True
        self.inspect["Mounts"].append({"Destination": "/host", "Type": "bind",
                                        "Source": self.source, "RW": False,
                                        "Propagation": "rprivate"})
        errors = self.validate()
        self.assertIn("mount_mismatch:/skills", errors)
        self.assertIn("mount_set_mismatch", errors)

    def test_missing_protection_rejected(self):
        self.inspect["HostConfig"]["ReadonlyRootfs"] = False
        self.inspect["HostConfig"]["SecurityOpt"] = []
        self.inspect["HostConfig"]["Privileged"] = True
        errors = self.validate()
        self.assertIn("root_not_read_only", errors)
        self.assertIn("security_options_mismatch", errors)
        self.assertIn("privileged_or_unknown", errors)

    def validate(self):
        return module.validate_inspect(self.inspect, self.mounts, "exp18-private",
                                       self.image_id, self.tmpfs)

    def test_each_real_downgrade_is_rejected(self):
        mutations = (
            ("cap_add", "CapAdd", ["SYS_ADMIN"], "capabilities_added"),
            ("nnp_false", "SecurityOpt", ["no-new-privileges:false"],
             "security_options_mismatch"),
            ("seccomp_unconfined", "SecurityOpt",
             ["no-new-privileges:true", "seccomp=unconfined"],
             "security_options_mismatch"),
            ("apparmor_unconfined", "SecurityOpt",
             ["no-new-privileges:true", "apparmor=unconfined"],
             "security_options_mismatch"),
            ("host_pid", "PidMode", "host", "pidmode_mismatch"),
            ("device", "Devices", [{"PathOnHost": "/dev/fuse"}],
             "devices_present"),
            ("extra_tmpfs", "Tmpfs", {**self.tmpfs, "/data": "exec"},
             "tmpfs_mismatch"),
        )
        baseline = deepcopy(self.inspect)
        for label, field, value, code in mutations:
            with self.subTest(label=label):
                self.inspect = deepcopy(baseline)
                self.inspect["HostConfig"][field] = value
                self.assertIn(code, self.validate())

    def test_namespace_device_request_tmpfs_mount_and_image_mismatch(self):
        baseline = deepcopy(self.inspect)
        for field, value, code in (
            ("IpcMode", "host", "ipcmode_mismatch"),
            ("UTSMode", "host", "utsmode_mismatch"),
            ("UsernsMode", "host", "usernsmode_mismatch"),
            ("DeviceRequests", [{"Capabilities": [["gpu"]]}],
             "device_requests_present"),
        ):
            with self.subTest(field=field):
                self.inspect = deepcopy(baseline)
                self.inspect["HostConfig"][field] = value
                self.assertIn(code, self.validate())
        self.inspect = deepcopy(baseline)
        self.inspect["Image"] = "sha256:" + "b" * 64
        self.assertIn("image_id_mismatch", self.validate())
        self.inspect = deepcopy(baseline)
        self.inspect["Mounts"].append({"Destination": "/data", "Type": "tmpfs"})
        self.assertIn("tmpfs_mount_set_mismatch", self.validate())

    def test_systempaths_unconfined_real_inspect_shape_is_rejected(self):
        # Docker records this downgrade by emptying both path lists, even when
        # SecurityOpt contains no "systempaths" entry.
        self.inspect["HostConfig"]["MaskedPaths"] = []
        self.inspect["HostConfig"]["ReadonlyPaths"] = []
        self.assertNotIn("systempaths=unconfined",
                         self.inspect["HostConfig"]["SecurityOpt"])
        errors = self.validate()
        self.assertIn("masked_paths_mismatch", errors)
        self.assertIn("readonly_paths_mismatch", errors)

    def test_full_host_config_projection_rejects_unlisted_downgrades(self):
        baseline = deepcopy(self.inspect)
        cases = (
            ("CgroupnsMode", "host"), ("GroupAdd", ["0"]),
            ("Sysctls", {"net.ipv4.ip_forward": "1"}),
            ("ExtraHosts", ["example:127.0.0.1"]),
            ("Ulimits", [{"Name": "nofile", "Soft": 1024, "Hard": 1024}]),
            ("OomKillDisable", True), ("MemorySwap", -1),
            ("new_field", "unsafe"),
        )
        for field, value in cases:
            with self.subTest(field=field):
                self.inspect = deepcopy(baseline)
                self.inspect["HostConfig"][field] = value
                self.assertIn("hostconfig_mismatch:" + field, self.validate())
        self.inspect = deepcopy(baseline)
        self.inspect["HostConfig"]["ReadonlyPaths"] = []
        self.assertIn("readonly_paths_mismatch", self.validate())
        self.inspect = deepcopy(baseline)
        self.inspect["Mounts"][0]["Propagation"] = "rshared"
        self.assertIn("mount_mismatch:/skills", self.validate())

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
