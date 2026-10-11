import copy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.exp93.real_stage_support import IDENTITY, reserve, validate


def good():
    return {"identity":IDENTITY,"boundary_observed":True,"loss":{
        "command_started":1.,"kill_completed":2.,"revoked":7.,"denied":8.,
        "denial_status":403,"denial_error":"grant_unavailable",
        "attempts_before_denial":0,"attempts_after_denial":0,
        "a_container_absent":True,"b_owned_alive":True,"b_read_status":200,"b_read_count":1},
        "provider_writes":0,"local_turns":1,"shared_used":13,"shared_cap":16,
        "restart_status":"interrupted","restart_identity_retained":True,
        "sentinel_checked_after":61.1,"sentinel_present":False,
        "cleanup":{"grants":True,"a":True,"b":True,"workers":True,"tasks":True,"stages":True}}


class RealStageChecks(unittest.TestCase):
    def test_positive_and_mutations(self):
        validate(good())
        mutations = [("boundary_observed",False),("identity","old"),("provider_writes",1),
            ("local_turns",2),("shared_used",12),("shared_cap",12),
            ("restart_status","completed"),("restart_identity_retained",False),
            ("sentinel_checked_after",3),("sentinel_present",True)]
        for key,value in mutations:
            with self.subTest(key=key),self.assertRaises(ValueError):
                row=good();row[key]=value;validate(row)
        for key,value in [("revoked",90),("revoked",float("nan")),("denial_status",200),
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
            prior=[{"id":str(n),"result":"historic"} for n in range(12)]
            path.write_text(json.dumps({"cap":12,"attempts":prior}))
            reserve(path,Path(name)/"state")
            value=json.loads(path.read_bytes())
            self.assertEqual(value["cap"],16)
            self.assertEqual(value["attempts"][:12],prior)
            self.assertEqual(len(value["attempts"]),13)
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


if __name__=="__main__":
    unittest.main()
