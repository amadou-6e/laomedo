import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.exp93.real_stage_support import IDENTITY; from experiments.exp93.real_stage_support import reserve; from experiments.exp93.real_stage_support import validate


def good():
    return {"identity":IDENTITY,"boundary_observed":True,"loss":{
        "command_started":1.,"kill_completed":2.,"revoked":7.,"denied":8.,
        "container_absent_observed":7.2,"original_container_id":"exact-id","prekill_running":True,
        "service_cleanup_state":"never_observed",
        "absence_checks":{"original_id":"absent","reserved_name":"absent","label_ids":[]},
        "denial_status":403,"denial_error":"grant_unavailable",
        "attempts_before_denial":0,"attempts_after_denial":0,
        "a_container_absent":True,"b_owned_alive":True,"b_read_status":200,"b_read_count":1},
        "provider_writes":0,"local_turns":1,"shared_used":15,"shared_cap":16,"delayed_absence_verified":True,
        "restart_status":"interrupted","restart_identity_retained":True,
        "sentinel_checked_after":61.1,"sentinel_present":False,
        "cleanup":{"grants":True,"a":True,"b":True,"workers":True,"tasks":True,"stages":True}}


class RealStageChecks(unittest.TestCase):
    def test_positive_and_mutations(self):
        validate(good())
        mutations = [("boundary_observed",False),("identity","old"),("provider_writes",1),
            ("local_turns",2),("shared_used",14),("shared_cap",12),("delayed_absence_verified",False),
            ("restart_status","completed"),("restart_identity_retained",False),
            ("sentinel_checked_after",3),("sentinel_present",True)]
        for key,value in mutations:
            with self.subTest(key=key),self.assertRaises(ValueError):
                row=good();row[key]=value;validate(row)
        for key,value in [("revoked",90),("revoked",float("nan")),("denial_status",200),
                ("container_absent_observed",90),("service_cleanup_state","unknown"),
                ("service_cleanup_state","cleanup_error"),("prekill_running",False),
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
            prior=[{"id":str(n),"result":"historic"} for n in range(14)]
            path.write_text(json.dumps({"cap":16,"attempts":prior}))
            reserve(path,Path(name)/"state")
            value=json.loads(path.read_bytes())
            self.assertEqual(value["cap"],16)
            self.assertEqual(value["attempts"][:14],prior)
            self.assertEqual(len(value["attempts"]),15)
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

    def test_s2_incomplete_capture_is_not_relabeled(self):
        from hashlib import sha256
        source=Path(__file__).with_name("real-stage-s2-observation.json").read_bytes()
        self.assertEqual(sha256(source).hexdigest(),"2d03481c1c8318e84b1a4a47923c94cf5c1ec88a2acfec14530c8785b47d301e")
        row=json.loads(source)
        self.assertEqual(row["result"],"incomplete")
        self.assertEqual(row["shared_used"],14)
        self.assertEqual(row["failure_code"],"service_cleanup_unverified_or_late")

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

    def test_original_id_name_and_labels_all_required(self):
        import subprocess
        from experiments.exp93 import real_stage_probe as probe
        selected={"name":"n","run_id":"r","token":"t"}
        entry={"Id":"id","Name":"/n","Config":{"Labels":{
            "laomedo.run_id":"r","laomedo.launch_token":"t"}},"State":{"Running":True}}
        def listing(value):
            return subprocess.CompletedProcess([],0,value,"")
        with patch.object(probe,"inspect_target",side_effect=[None,None]),patch.object(probe.subprocess,"run",return_value=listing("")):
            self.assertEqual(probe.exact_container_state(selected,"id"),(True,False,
                {"original_id":"absent","reserved_name":"absent","label_ids":[]}))
        with patch.object(probe,"inspect_target",side_effect=[entry,None]),patch.object(probe.subprocess,"run",return_value=listing("id\n")):
            self.assertFalse(probe.exact_container_state(selected,"id")[0])
        with patch.object(probe,"inspect_target",side_effect=[None,None]),patch.object(probe.subprocess,"run",return_value=listing("replacement\n")),self.assertRaises(ValueError):
            probe.exact_container_state(selected,"id")
        wrong=copy.deepcopy(entry);wrong["Id"]="replacement"
        with patch.object(probe,"inspect_target",side_effect=[None,wrong]),self.assertRaises(ValueError):
            probe.exact_container_state(selected,"id")
        stopped=copy.deepcopy(entry);stopped["State"]["Running"]=False
        with patch.object(probe,"inspect_target",side_effect=[stopped,stopped]),patch.object(probe.subprocess,"run",return_value=listing("id\n")):
            self.assertFalse(probe.exact_container_state(selected,"id")[1])

    def test_daemon_unknown_never_becomes_absence(self):
        import subprocess
        from experiments.exp93 import real_stage_probe as probe
        with patch.object(probe.subprocess,"run",return_value=subprocess.CompletedProcess([],1,"","daemon unavailable")),self.assertRaisesRegex(ValueError,"docker_inspection_unknown"):
            probe.inspect_target("id")
        with patch.object(probe.subprocess,"run",return_value=subprocess.CompletedProcess([],1,"","No such object: id")):
            self.assertIsNone(probe.inspect_target("id"))

    def test_service_diagnostic_never_fabricates_removal(self):
        from experiments.exp93 import real_stage_probe as probe
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/"deadline").write_text("100")
            result=root/"host/lease/leases/t/result.json";result.parent.mkdir(parents=True)
            selected={"name":"n","run_id":"r","token":"t"}
            checks={"original_id":"absent","reserved_name":"absent","label_ids":[]}
            result.write_text(json.dumps({"state":"never_observed","cleanup_verified":False}))
            row={"loss":{}}
            with patch.object(probe.time,"monotonic",return_value=6),patch.object(probe,"exact_container_state",return_value=(True,False,checks)):
                probe.wait_exact_absence(root,selected,"id",1,row)
            self.assertEqual(row["loss"]["service_cleanup_state"],"never_observed")
            self.assertFalse(row["loss"]["service_cleanup_verified"])
            self.assertEqual(row["loss"]["container_absent_observed"],6)
            for danger in ("conflict","unknown","late_owned","cleanup_error"):
                result.write_text(json.dumps({"state":danger}))
                with patch.object(probe.time,"monotonic",return_value=6),patch.object(probe,"exact_container_state",return_value=(True,False,checks)),self.assertRaisesRegex(ValueError,"danger_signal"):
                    probe.wait_exact_absence(root,selected,"id",1,{"loss":{}})


if __name__=="__main__":
    unittest.main()
