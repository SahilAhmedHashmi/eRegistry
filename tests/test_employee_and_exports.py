from pathlib import Path

import pytest
from openpyxl import load_workbook

from eregistry.app_state import AppContext
from eregistry.security import AuthStore
from eregistry.services.employee_service import DuplicateEmployeeError


@pytest.fixture()
def context(tmp_path: Path):
    master, _ = AuthStore(tmp_path / "auth.json").setup("test password")
    ctx = AppContext(tmp_path, master)
    ctx.create_organisation(name="Assam Administrative Staff College")
    yield ctx
    ctx.close()


def test_duplicate_identifiers_are_blocked(context):
    context.employees.save({"name": "First", "aadhaar_number": "1234 5678 9012"})
    with pytest.raises(DuplicateEmployeeError):
        context.employees.save({"name": "Second", "aadhaar_number": "123456789012"})


def test_excel_has_salary_first_and_linked_detail_sheets(context):
    context.employees.save(
        {
            "name": "Hira Basfor",
            "registration_number": "180",
            "designation": "Semi-skilled",
            "bank_name": "SBI-KIOSK BANKING",
            "bank_account_number": "38835535072",
            "work_experiences": [
                {"employer_name_address": "Previous employer", "rank_post": "Worker"}
            ],
        }
    )
    payroll = context.payroll.get_or_create_month(2026, 5)
    entry = context.payroll.get_month(payroll.id).entries[0]
    context.payroll.save_entry(entry.id, {"working_days": 31, "wages_per_day": 424.34})
    path = context.excel.sync()
    workbook = load_workbook(path, data_only=True)
    assert workbook.sheetnames[:2] == ["May 2026", "Registration Details"]
    assert workbook["May 2026"]["A1"].value == "ASSAM ADMINISTRATIVE STAFF COLLEGE"
    assert workbook["May 2026"]["K5"].value == 13155
    assert {"Work Experience", "Education", "Nominees", "Family"}.issubset(workbook.sheetnames)


def test_database_is_not_plain_sqlite(context):
    database = context.catalog.folder_for(context.organisation) / "eregistry.db"
    header = database.read_bytes()[:16]
    assert header != b"SQLite format 3\x00"
