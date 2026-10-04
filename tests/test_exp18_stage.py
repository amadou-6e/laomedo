import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parents[1] / "experiments" / "exp18"
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("exp18_probe_stage", HERE / "probe_stage.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StagePreflightTests(unittest.TestCase):
    def sidecar(self):
        return {
            "Image": module.SIDE_ID,
            "Mounts": [],
            "HostConfig": {
                "NetworkMode": "isolated", "Binds": None, "Mounts": [],
                "PortBindings": {}, "PublishAllPorts": False,
                "ReadonlyRootfs": True, "CapDrop": ["ALL"], "CapAdd": None,
                "Privileged": False, "SecurityOpt": ["no-new-privileges"],
                "Devices": [], "DeviceRequests": [],
            },
            "NetworkSettings": {
                "Networks": {"isolated": {}, "bridge": {}}, "Ports": {},
            },
            "Config": {
                "Volumes": None, "User": "10001:10001",
                "Entrypoint": ["python", "-B", "-u", "/app/probe.py"],
            },
        }

    def test_only_inspected_two_network_restricted_sidecar_passes(self):
        item = self.sidecar()
        self.assertEqual(module.sidecar_evidence(item, "isolated")["errors"], [])
        item["NetworkSettings"]["Networks"]["third"] = {}
        self.assertIn("sidecar_network_set_mismatch",
                      module.sidecar_evidence(item, "isolated")["errors"])
        del item["NetworkSettings"]["Networks"]["third"]
        item["HostConfig"]["PortBindings"] = {"8098/tcp": [{"HostPort": "8098"}]}
        self.assertIn("sidecar_published_port",
                      module.sidecar_evidence(item, "isolated")["errors"])
        item["HostConfig"]["PortBindings"] = {}
        item["Mounts"] = [{"Destination": "/host"}]
        self.assertIn("sidecar_mount_present",
                      module.sidecar_evidence(item, "isolated")["errors"])

    def test_stage_config_changes_fail_before_start(self):
        env = ["PATH=/bin", "HOME=/home/runner", "CANARY_GRANT=fixture"]
        item = {"Config": {"Env": env, "Cmd": ["sh", "-c", "sleep 45"],
                           "Entrypoint": ["docker-entrypoint.sh"],
                           "WorkingDir": "/draft"}}
        fake = mock.Mock(stdout=json.dumps(env[:2]))
        with mock.patch.object(module, "docker", return_value=fake):
            self.assertEqual(module.config_errors(item, "fixture")[0], [])
            item["Config"]["Cmd"] = ["sh", "-c", "other"]
            item["Config"]["Env"].append("UNREVIEWED=1")
            self.assertEqual(set(module.config_errors(item, "fixture")[0]),
                             {"config_command_mismatch", "config_env_names_mismatch"})


if __name__ == "__main__":
    unittest.main()
