"""Idempotent, TEST-ONLY Odoo shell bootstrap for Raidat RSH biometrics.

Usage from an Odoo shell connected to test_RSH:
    exec(open("/path/to/bootstrap_rsh_test_odoo.py", encoding="utf-8").read(), {"env": env, "__name__": "__main__"})
Requires Odoo's shell-provided `env` variable.
Does not create employee mappings or process attendance.
Never prints the API token.
"""
import os
import secrets
from pathlib import Path


def bootstrap_rsh_test(env):
    expected_db = "test_RSH"
    actual_db = env.cr.dbname
    if actual_db != expected_db:
        raise RuntimeError(
            "REFUSED: this script may run only on test_RSH, not " + actual_db
        )

    required_modules = [
        "hr_attendance",
        "rm_hr_attendance_sheet",
        "rgb_biometric_attendance_bridge",
        "rgb_biometric_first_last_attendance",
    ]
    Module = env["ir.module.module"].sudo()
    missing = [
        module for module in required_modules
        if not Module.search([("name", "=", module), ("state", "=", "installed")], limit=1)
    ]
    if missing:
        raise RuntimeError("Install required modules on TEST first: " + ", ".join(missing))

    Company = env["res.company"].sudo()
    companies = Company.search([("name", "ilike", "RAIDAT AL SHARQ FACTORY")])
    if len(companies) != 1:
        raise RuntimeError(
            "Expected precisely one RSH factory company; found %s" % len(companies)
        )
    company = companies[0]

    Devices = env["asg.biometric.device"].sudo()
    descriptors = [
        ("zk_room_1", "ZKTeco MB1000 Room 1", "zkteco"),
        ("hik_room_2", "Hikvision DS-K1T502DBFWX-C Room 2", "hikvision"),
    ]
    new_devices = []
    for external_id, name, dtype in descriptors:
        existing = Devices.search([("external_id", "=", external_id)], limit=2)
        if len(existing) > 1:
            raise RuntimeError("Ambiguous device ID " + external_id)
        if existing:
            device = existing[0]
            if device.company_id.id != company.id or device.device_type != dtype:
                raise RuntimeError("Conflicting test device configuration: " + external_id)
            if device.processing_strategy != "raw_only" or not device.active:
                raise RuntimeError("Review existing test device before continuing: " + external_id)
        else:
            new_devices.append({
                "external_id": external_id,
                "name": name,
                "device_type": dtype,
                "processing_strategy": "raw_only",
                "company_id": company.id,
                "active": True,
            })

    Param = env["ir.config_parameter"].sudo()
    timezone = Param.get_param("asg_biometric_first_last.timezone")
    if timezone not in (None, "", "Asia/Riyadh"):
        raise RuntimeError("Unexpected test timezone; manual review required")

    old_token = Param.get_param("asg_biometric.api_token")
    # The generated token must be retained outside Git in a private file, for
    # copying to the isolated TEST middleware configuration. Do not paste it to chat.
    token_path = Path.home() / ".config" / "raidat-biometric" / "rsh-test-token"
    token_created = False
    token = None
    if not old_token:
        if token_path.exists():
            raise RuntimeError("Existing token file with missing Odoo config; manual review")
        token = secrets.token_urlsafe(48)

    if new_devices:
        Devices.create(new_devices)
    if timezone != "Asia/Riyadh":
        Param.set_param("asg_biometric_first_last.timezone", "Asia/Riyadh")
    if token:
        Param.set_param("asg_biometric.api_token", token)

    # Odoo shell transactions may otherwise roll back at exit.
    if token:
        token_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            token_path.parent.chmod(0o700)
        fd = os.open(str(token_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(token + "\n")
        except BaseException:
            token_path.unlink(missing_ok=True)
            raise
        token_created = True

    try:
        env.cr.commit()
    except BaseException:
        if token_created:
            token_path.unlink(missing_ok=True)
        raise

    print("RSH TEST prepared successfully, database=test_RSH")
    print("Company:", company.name)
    print("Created devices:", [d["external_id"] for d in new_devices])
    print("Timezone: Asia/Riyadh")
    print("API token:", "generated and stored privately" if token_created else "already configured")
    if token_created:
        print("Private token file:", token_path)
    print("Employee mappings: NOT CREATED — require approved device employee IDs.")
    print("Daily First/Last cron: UNCHANGED — activate after successful Test Cases.")


if __name__ == "__main__":
    if "env" not in globals():
        raise RuntimeError("Run from Odoo shell with env; do not run standalone")
    bootstrap_rsh_test(globals()["env"])