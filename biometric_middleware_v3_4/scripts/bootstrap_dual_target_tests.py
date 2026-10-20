"""One-time isolated synthetic dual-target setup; Odoo TEST DBs ONLY.

Run inside Odoo shell for db 'test' (ERP Test) and 'test_RSH' (RSH Test),
separately. No real employee or device record is changed. All codes and device
external IDs are synthetic and must never appear in Production.

Two synthetic devices + one SHARED identity per DB, an ERP-only identity in
ERP Test, and an RSH-only identity in RSH Test.

IMPORTANT: intentionally disables only the Test DB's First/Last daily cron
during deterministic E2E, without editing cron definitions or Live databases.
"""
import os
from pathlib import Path
import secrets

PREFIX = "RAIDAT_DUAL_E2E_20261020"
SYNTH_DEVICE_IDS = ("raidat_dual_e2e_zk", "raidat_dual_e2e_hik")
SYNTH_CODES = {
    "shared": PREFIX + "_SHARED",
    "erp_only": PREFIX + "_ERP_ONLY",
    "rsh_only": PREFIX + "_RSH_ONLY",
}
TOKEN_FILE = Path("/odoo16/.config/raidat-biometric/erp-test-token")


def setup(env):
    db = env.cr.dbname
    if db not in ("test", "test_RSH"):
        raise RuntimeError("REFUSED: dual test bootstrap can run only on test or test_RSH")

    Module = env["ir.module.module"].sudo()
    required = ("hr_attendance", "rm_hr_attendance_sheet",
                "rgb_biometric_attendance_bridge",
                "rgb_biometric_first_last_attendance")
    missing = [m for m in required if not Module.search([
        ("name", "=", m), ("state", "=", "installed")], limit=1)]
    if missing:
        raise RuntimeError("REFUSED: missing TEST modules: " + ", ".join(missing))

    Device = env["asg.biometric.device"].sudo()
    Mapping = env["asg.biometric.employee.mapping"].sudo()
    Employee = env["hr.employee"].sudo()
    Parameter = env["ir.config_parameter"].sudo()

    if db == "test_RSH":
        real_devices = Device.search([
            ("external_id", "in", ["zk_room_1", "hik_room_2"]),
            ("active", "=", True)
        ])
        if len(real_devices) != 2 or len(real_devices.mapped("company_id")) != 1:
            raise RuntimeError("REFUSED: expected RSH Test device baseline")
        company = real_devices[0].company_id
    else:
        company = env.company

    # Do not overwrite any pre-existing device, mapping, or employee from other tests.
    if Device.with_context(active_test=False).search([
        ("external_id", "in", list(SYNTH_DEVICE_IDS))
    ]):
        raise RuntimeError("REFUSED: dual E2E synthetic devices already exist")
    if Employee.with_context(active_test=False).search([
        ("name", "=like", PREFIX + "%")
    ]):
        raise RuntimeError("REFUSED: dual E2E synthetic employees already exist")

    token = Parameter.get_param("asg_biometric.api_token")
    generate_token = (db == "test" and not token)
    if db == "test_RSH" and (not token or len(token) < 32):
        raise RuntimeError("REFUSED: RSH TEST token not ready")
    if db == "test" and token and len(token) < 32:
        raise RuntimeError("REFUSED: unexpected short ERP TEST token")
    if db == "test" and token and not TOKEN_FILE.exists():
        raise RuntimeError("REFUSED: existing ERP TEST API token lacks private local file")
    if generate_token and TOKEN_FILE.exists():
        raise RuntimeError("REFUSED: stale private ERP TEST token file")
    if generate_token:
        token = secrets.token_urlsafe(48)

    # We require installed First/Last cron to prevent global triggers on test records.
    daily_cron = env.ref(
        "rgb_biometric_first_last_attendance.ir_cron_daily_first_last",
        raise_if_not_found=False
    )
    if not daily_cron:
        raise RuntimeError("REFUSED: cannot identify TEST daily cron")

    subjects = ["shared", "erp_only"] if db == "test" else ["shared", "rsh_only"]
    employees = {}
    for subject in subjects:
        employees[subject] = Employee.create({
            "name": PREFIX + "_" + subject.upper() + "_" + ("ERP" if db == "test" else "RSH"),
            "company_id": company.id,
            "active": True,
        })
    devices = Device.create([
        {"external_id": SYNTH_DEVICE_IDS[0],
         "name": PREFIX + "_ZK", "device_type": "zkteco",
         "company_id": company.id, "processing_strategy": "raw_only",
         "active": True},
        {"external_id": SYNTH_DEVICE_IDS[1],
         "name": PREFIX + "_HIK", "device_type": "hikvision",
         "company_id": company.id, "processing_strategy": "raw_only",
         "active": True},
    ])
    records = []
    for d in devices:
        records.append({
            "device_id": d.id,
            "employee_id": employees["shared"].id,
            "external_user_id": SYNTH_CODES["shared"], "active": True,
        })
    only = "erp_only" if db == "test" else "rsh_only"
    records.append({
        "device_id": devices[0].id,
        "employee_id": employees[only].id,
        "external_user_id": SYNTH_CODES[only], "active": True,
    })
    Mapping.create(records)
    if daily_cron.active:
        daily_cron.write({"active": False})
    if generate_token:
        Parameter.set_param("asg_biometric.api_token", token)
        TOKEN_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        TOKEN_FILE.parent.chmod(0o700)
        fd = os.open(TOKEN_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(token + "\n")
        except BaseException:
            TOKEN_FILE.unlink(missing_ok=True)
            env.cr.rollback()
            raise
    try:
        env.cr.commit()
    except BaseException:
        if generate_token:
            TOKEN_FILE.unlink(missing_ok=True)
        raise
    print("SYNTH TEST BOOTSTRAP: PASS")
    print("TEST DATABASE:", db)
    print("Synthetic devices created: 2")
    print("Synthetic employee mappings created:", len(records))
    print("Private ERP TEST API token:", "generated and file saved" if generate_token else
          ("already configured" if db == "test" else "existing RSH token unchanged"))
    print("TEST ONLY daily First/Last cron: disabled for deterministic tests")
    print("No Production, real employee, or real device configurations modified")


if __name__ == "__main__":
    if "env" not in globals():
        raise RuntimeError("Run inside Odoo shell with env")
    setup(globals()["env"])
