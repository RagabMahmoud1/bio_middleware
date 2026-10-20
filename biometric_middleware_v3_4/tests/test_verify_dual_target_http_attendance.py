"""Verifier tests: synthetic HTTP event keys and Live fail-closed gate."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
def load(name):
    spec=importlib.util.spec_from_file_location(name,SCRIPTS/(name+".py"))
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

verifier=load("verify_dual_target_http_attendance")
runner=load("run_dual_target_http_synthetic_e2e")

class E2EVerificationGuards(unittest.TestCase):
    def test_exact_sql_and_orm_hash_keys_match(self):
        data={
            ev["source_event_id"].rsplit("_",2)[-2]+"_"+ev["source_event_id"].rsplit("_",2)[-1]:ev["event_key"]
            for ev in runner.events()
        }
        self.assertEqual(data,verifier.EXPECTED_KEYS)
    def test_refuses_live_without_accessing_any_model(self):
        class Env:
            cr=SimpleNamespace(dbname="RSH")
            def __getitem__(self,key):
                raise AssertionError("must never access production models")
        with self.assertRaisesRegex(RuntimeError,"only ERP and RSH Test"):
            verifier.verify_and_process(Env())

if __name__=="__main__":
    unittest.main()
