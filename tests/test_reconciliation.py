from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from eregistry.app_state import AppContext
from eregistry.security import AuthStore
from eregistry.services.reconciliation_service import (
    ExternalSalaryRow,
    ReconciliationService,
)


@pytest.fixture()
def reconciliation_context(tmp_path: Path):
    master, _ = AuthStore(tmp_path / "auth.json").setup("test password")
    context = AppContext(tmp_path, master)
    context.create_organisation(name="Reconciliation Test Organisation")
    employee = context.employees.save(
        {
            "name": "Anita Das",
            "registration_number": "REG-001",
            "designation": "Skilled",
            "contact_number": "9876543210",
            "uan_number": "100000000001",
        }
    )
    payroll = context.payroll.get_or_create_month(2026, 5)
    entry = context.payroll.get_month(payroll.id).entries[0]
    context.payroll.save_entry(
        entry.id,
        {
            "working_days": 27,
            "wages_per_day": 500,
        },
    )
    yield context, payroll.id, employee.id
    context.close()


def test_reconciliation_matches_identity_days_and_salary(reconciliation_context):
    context, payroll_id, _ = reconciliation_context
    external = [
        ExternalSalaryRow(
            source_row=2,
            pf_number="1000-0000-0001",
            employee_name="  anita   das ",
            expected_salary=Decimal("15500"),
            actual_salary=Decimal("13500"),
            working_days=Decimal("27"),
        )
    ]

    month, results = ReconciliationService(context.db).reconcile(payroll_id, external)

    assert (month.year, month.month) == (2026, 5)
    assert len(results) == 1
    result = results[0]
    assert result.status == "Confirmed match"
    assert result.calculated_expected_salary == Decimal("15500")
    assert result.calculated_from_reported_days == Decimal("13500")
    assert result.actual_difference == Decimal("0")
    assert result.formula_difference == Decimal("0")


def test_reconciliation_flags_day_difference_without_writing_database(
    reconciliation_context,
):
    context, payroll_id, _ = reconciliation_context
    before = context.payroll.get_month(payroll_id).entries[0]
    before_values = (before.working_days, before.working_day_wages)
    external = [
        ExternalSalaryRow(
            source_row=2,
            pf_number="100000000001",
            employee_name="Anita Das",
            expected_salary=Decimal("15500"),
            actual_salary=Decimal("13000"),
            working_days=Decimal("26"),
        )
    ]

    _, results = ReconciliationService(context.db).reconcile(payroll_id, external)

    assert results[0].status == "Working-days mismatch"
    assert results[0].actual_difference == Decimal("-500")
    assert results[0].formula_difference == Decimal("0")
    after = context.payroll.get_month(payroll_id).entries[0]
    assert (after.working_days, after.working_day_wages) == before_values


def test_workbook_headers_are_detected_and_rows_are_read(tmp_path: Path):
    path = tmp_path / "organisation-salary.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "May"
    sheet.append(["Organisation salary statement"])
    sheet.append(["PF No.", "Employee Name", "Expected Salary", "Actual Salary", "Days Worked"])
    sheet.append(["100000000001", "Anita Das", 15500, 13500, 27])
    workbook.save(path)

    inspection = ReconciliationService.inspect_workbook(path)
    rows = ReconciliationService.load_rows(
        path,
        inspection.sheet_name,
        inspection.header_row,
        inspection.suggested_mapping,
    )

    assert inspection.sheet_name == "May"
    assert inspection.header_row == 2
    assert len(inspection.suggested_mapping) == 5
    assert rows[0].pf_number == "100000000001"
    assert rows[0].employee_name == "Anita Das"
    assert rows[0].working_days == Decimal("27")
