"""Export a private RSH TEST employee roster for HR-approved biometric mappings.

Odoo shell usage:
    exec(open("/path/export_rsh_test_mapping_template.py", encoding="utf-8").read(),
         {"env": env, "__name__": "__main__"})

This script:
- Refuses non-test_RSH databases.
- Never reads or exports employee PINs or badge/barcode values.
- Writes no Odoo database records.
- Creates one owner-only CSV (mode 0600); never overwrites an existing CSV.
- Leaves biometric device user IDs blank for HR/device-administrator verification.
"""
import csv
import os
from pathlib import Path


HEADERS = (
    "test_employee_id",
    "employee_name",
    "department",
    "zk_room_1_user_id",
    "hik_room_2_user_id",
    "approved_by",
    "approval_status",
)


def export_rsh_mapping_template(env, output_path=None):
    if env.cr.dbname != "test_RSH":
        raise RuntimeError("REFUSED: mapping template export is test_RSH only")

    devices = env["asg.biometric.device"].sudo().search(
        [("external_id", "in", ("zk_room_1", "hik_room_2")),
         ("active", "=", True)]
    )
    by_external = {d.external_id: d for d in devices}
    if len(devices) != 2 or set(by_external) != {"zk_room_1", "hik_room_2"}:
        raise RuntimeError("Expected exactly two active biometric devices in RSH Test")
    if by_external["zk_room_1"].company_id.id != by_external["hik_room_2"].company_id.id:
        raise RuntimeError("Test biometric devices are assigned to different companies")
    company = by_external["zk_room_1"].company_id

    employees = env["hr.employee"].sudo().search(
        [("active", "=", True), ("company_id", "=", company.id)],
        order="id",
    )
    if not employees:
        raise RuntimeError("No active employees found for the RSH test company")

    if output_path is None:
        output_path = (
            Path.home() / ".local" / "share" / "raidat-biometric"
            / "rsh_test_mapping_template.csv"
        )
    path = Path(output_path)
    if path.is_symlink():
        raise RuntimeError("REFUSED: output file is a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        path.parent.chmod(0o700)

    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=HEADERS)
            writer.writeheader()
            for employee in employees:
                writer.writerow({
                    "test_employee_id": employee.id,
                    "employee_name": employee.name or "",
                    "department": employee.department_id.display_name if employee.department_id else "",
                    "zk_room_1_user_id": "",
                    "hik_room_2_user_id": "",
                    "approved_by": "",
                    "approval_status": "PENDING",
                })
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    print("RSH TEST mapping template exported:", path)
    print("Employees in test company:", len(employees))
    print("All biometric user IDs blank: must be verified against the actual devices")
    print("Employee PINs and badges NOT exported; no mappings were created")
    print("Private CSV mode: 0600, private directory: 0700")
    return path


if __name__ == "__main__":
    if "env" not in globals():
        raise RuntimeError("Run inside Odoo shell, not standalone")
    export_rsh_mapping_template(globals()["env"])
