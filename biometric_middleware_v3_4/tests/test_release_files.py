import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent.parent
ODOO_MODULE = (
    PROJECTS
    / "erp-raidatalsharq"
    / "rgb_biometric_attendance_bridge"
)


class ReleaseFilesTests(unittest.TestCase):
    def test_example_config_is_valid_yaml(self):
        with (ROOT / "config.example.yaml").open(
            "r",
            encoding="utf-8",
        ) as stream:
            cfg = yaml.safe_load(stream)
        self.assertIn("app", cfg)
        self.assertIn("odoo", cfg)
        self.assertIn("devices", cfg)

    def test_required_release_scripts_exist(self):
        required = [
            "install_service.ps1",
            "uninstall_service.ps1",
            "service_status.ps1",
            "deploy_stable.ps1",
            "backup_runtime.ps1",
            "RELEASE_3_5_0.md",
        ]
        for name in required:
            self.assertTrue((ROOT / name).exists(), name)

    def test_odoo_xml_files_are_well_formed(self):
        files = [
            ODOO_MODULE / "views" / "biometric_device_views.xml",
            ODOO_MODULE / "views" / "biometric_event_views.xml",
            ODOO_MODULE / "views" / "biometric_mapping_views.xml",
            ODOO_MODULE / "views" / "menu.xml",
            ODOO_MODULE / "data" / "cron.xml",
        ]
        for path in files:
            ET.parse(path)


if __name__ == "__main__":
    unittest.main()