"""Guards for dual-target synthetic setup; no real Odoo API used."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

FILE=Path(__file__).resolve().parents[1]/"scripts"/"bootstrap_dual_target_tests.py"
spec=importlib.util.spec_from_file_location("raidat_dual_bootstrap",FILE)
script=importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

class DualBootstrapGuards(unittest.TestCase):
    def test_refuses_live_before_any_model_access(self):
        class NoModelEnv:
            cr=SimpleNamespace(dbname="rsh")
            def __getitem__(self,name):
                raise AssertionError("Should not even access live models")
        with self.assertRaisesRegex(RuntimeError,"only on test or test_RSH"):
            script.setup(NoModelEnv())

    def test_test_id_prefixes_distinct_from_real_devices(self):
        self.assertEqual(len(script.SYNTH_DEVICE_IDS),2)
        self.assertTrue(all(n.startswith("raidat_dual_e2e_") for n in script.SYNTH_DEVICE_IDS))
        self.assertFalse(set(script.SYNTH_DEVICE_IDS)&{"zk_room_1","hik_room_2"})
        self.assertEqual(len(set(script.SYNTH_CODES.values())),3)

    def test_token_file_separate_from_rsh_test_secret(self):
        self.assertEqual(script.TOKEN_FILE.name,"erp-test-token")
        self.assertNotEqual(script.TOKEN_FILE.name,"rsh-test-token")

if __name__=="__main__":
    unittest.main()
