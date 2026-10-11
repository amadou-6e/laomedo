import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.exp93.real_stage_support import IDENTITY, reserve, validate


def good():
    return {"identity":IDENTITY,"boundary_observed":True,"loss":{
        "command_started":1.,"kill_completed":2.,"revoked":7.,"denied":8.,
        "cleanup_finished":7.1,"container_absent_observed":7.2,
        "denial_status":403,"denial_error":"grant_unavailable",
        "attempts_before_denial":0,"attempts_after_denial":0,
        "a_container_absent":True,"b_owned_alive":True,"b_read_status":200,"b_read_count":1},
        "provider_writes":0,"local_turns":1,"shared_used":14,"shared_cap":16,
        "restart_status":"interrupted","restart_identity_retained":True,
        "sentinel_checked_after":61.1,"sentinel_present":False,
        "cleanup":{"grants":True,"a":True,"b":True,"workers":True,"tasks":True,"stages":True}}


class RealStageChecks(unittest.TestCase):
    def test_positive_and_mutations(self):
        validate(good())
        mutations = [("boundary_observed",False),("identity","old"),("provider_writes",1),
            ("local_turns",2),("shared_used",13),("shared_cap",12),
            ("restart_status","completed"),("restart_identity_retained",False),
            ("sentinel_checked_after",3),("sentinel_present",True)]
        for key,value in mutations:
            with self.subTest(key=key),self.assertRaises(ValueError):
                row=good();row[key]=value;validate(row)
        for key,value in [("revoked",90),("revoked",float("nan")),("denial_status",200),
                ("cleanup_finished",90),("container_absent_observed",90),
                ("denial_error","other"),("attempts_after_denial",1),
                ("a_container_absent",False),("b_owned_alive",False),
                ("b_read_status",403),("b_read_count",0)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                row=good();row["loss"][key]=value;validate(row)
        with self.assertRaises(ValueError):
            row=good();row["cleanup"]["grants"]=False;validate(row)

    def test_budget_extension_preserves_prior_entries_and_refuses_repeat(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/"ledger.json"
            prior=[{"id":str(n),"result":"historic"} for n in range(13)]
            path.write_text(json.dumps({"cap":16,"attempts":prior}))
            reserve(path,Path(name)/"state")
            value=json.loads(path.read_bytes())
            self.assertEqual(value["cap"],16)
            self.assertEqual(value["attempts"][:13],prior)
            self.assertEqual(len(value["attempts"]),14)
            self.assertEqual(value["attempts"][-1]["case_kind"],IDENTITY)
            with self.assertRaises(ValueError):
                reserve(path,Path(name)/"other")
            self.assertEqual(json.loads(path.read_bytes()),value)

    def test_wrong_budget_refused_without_change(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/"ledger.json"
            path.write_text(json.dumps({"cap":12,"attempts":[]}))
            original=path.read_bytes()
            with self.assertRaises(ValueError):
                reserve(path,Path(name)/"state")
            self.assertEqual(path.read_bytes(),original)

    def test_s1_original_capture_is_preserved(self):
        from hashlib import sha256
        source=Path(__file__).with_name("real-stage-s1-observation.json").read_bytes()
        self.assertEqual(sha256(source).hexdigest(),"73f7b83a358f038768c97fe73274dfdbedb75fe7fc403c4d5e351c74c3f63d40")
        row=json.loads(source)
        self.assertEqual(row["result"],"incomplete")
        self.assertEqual(row["shared_used"],13)
        self.assertEqual(row["provider_writes"],0)
        self.assertEqual(row["local_turns"],1)

    def test_cleanup_wait_requires_service_result_and_independent_absence(self):
        from experiments.exp93 import real_stage_probe as probe
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            (root/"deadline").write_text("100")
            target=root/"host/lease/leases/t/result.json"
            target.parent.mkdir(parents=True)
            selected={"token":"t","name":"n","run_id":"r"}
            target.write_text(json.dumps({"cleanup_verified":True,"cleanup_finished_at_monotonic":5}))
            with patch.object(probe.time,"monotonic",return_value=6),patch.object(probe,"inspect_exact",return_value=("absent",None)):
                self.assertEqual(probe.wait_cleanup(root,selected,1),(5,6))
            with patch.object(probe.time,"monotonic",return_value=6),patch.object(probe,"inspect_exact",return_value=("owned","x")),self.assertRaises(ValueError):
                probe.wait_cleanup(root,selected,1)
            target.write_text(json.dumps({"cleanup_verified":True,"cleanup_finished_at_monotonic":90}))
            with patch.object(probe.time,"monotonic",return_value=6),self.assertRaises(ValueError):
                probe.wait_cleanup(root,selected,1)

    def test_cleanup_order_and_dispatched_missing_state(self):
        from experiments.exp93 import real_stage_probe as probe
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/"start-gate").touch();(root/"stages").mkdir()
            def remove(*args):
                self.assertFalse((root/"b-stop").exists())
                return True,"absent"
            def stages(*args):
                self.assertFalse((root/"b-stop").exists())
                return True,[]
            with patch.object(probe,"identities",return_value={"name":"n","run_id":"r","token":"t"}),patch.object(probe,"cleanup_exact",side_effect=remove),patch.object(probe,"stage_cleanup",side_effect=stages),patch.object(probe.tasks,"cleanup",return_value={}):
                result=probe.cleanup(root,{}, {})
            self.assertTrue((root/"b-stop").exists());self.assertFalse(result["grants"])
            with patch.object(probe,"identities",return_value={}),patch.object(probe,"stage_cleanup",return_value=(True,[])),patch.object(probe.tasks,"cleanup",return_value={}):
                result=probe.cleanup(root,{}, {})
            self.assertFalse(result["a"]);self.assertFalse(result["b"])


if __name__=="__main__":
    unittest.main()
