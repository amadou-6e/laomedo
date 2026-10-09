import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


path = Path(__file__).resolve().parents[1] / "experiments/exp104/probe_managed_startup.py"
spec = importlib.util.spec_from_file_location("managed_startup_probe", path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProcessObservationTests(unittest.TestCase):
    def test_empty_and_real_pids(self):
        self.assertEqual(probe.parse_processes("[]"), [])
        self.assertEqual(probe.parse_processes("[2,1]"), [1, 2])

    def test_null_scalar_invalid_id_cannot_prove_readiness(self):
        for encoded in ("[null]", "1", "null", "[true]", "[0]", '"1"'):
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                probe.parse_processes(encoded)

    def test_query_excludes_itself_and_filters_python(self):
        with patch.object(probe, "powershell", return_value="[]") as call:
            self.assertEqual(probe.processes("synthetic-config.json"), [])
        command = call.call_args.args[0]
        self.assertIn("$_.ProcessId -ne $PID", command)
        self.assertIn("$_.Name -eq 'python.exe'", command)
        self.assertIn("ForEach-Object { [int]$_.ProcessId }", command)
