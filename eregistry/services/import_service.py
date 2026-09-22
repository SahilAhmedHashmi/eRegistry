from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from .employee_service import DuplicateEmployeeError


TARGET_FIELDS = {
    "Name": "name",
    "Registration Number": "registration_number",
    "Current Designation": "designation",
    "Mobile Number": "contact_number",
    "Aadhaar Number": "aadhaar_number",
    "UAN Number": "uan_number",
    "ESIC Number": "esic_number",
    "Bank Name": "bank_name",
    "Bank Branch": "bank_branch",
    "Account Number": "bank_account_number",
    "IFSC Code": "ifsc_code",
    "PAN Number": "pan_number",
    "Permanent Address": "permanent_address",
    "Communication Address": "communication_address",
    "Gender": "gender",
    "Date of Birth": "date_of_birth",
    "Appointment Date": "appointment_date",
}


def parse_date(value):
    if value is None or value == "":
        return None
    if hasattr(value, "date"):
        return value.date()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            pass
    return None


class ExcelImportService:
    def __init__(self, employee_service):
        self.employee_service = employee_service

    def inspect(self, path: Path, sheet_name: str | None = None):
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet_name] if sheet_name else wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
        headers = [str(x or "").strip() for x in rows[0]] if rows else []
        return wb.sheetnames, ws.title, headers, rows[1:6]

    def import_rows(
        self, path: Path, sheet_name: str, mapping: dict[str, str], conflict_resolver=None
    ):
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet_name]
        rows = ws.iter_rows(values_only=True)
        headers = [str(x or "").strip() for x in next(rows)]
        index = {name: idx for idx, name in enumerate(headers)}
        result = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
        for number, row in enumerate(rows, 2):
            values = {}
            for target_label, source_header in mapping.items():
                if source_header and source_header in index:
                    field = TARGET_FIELDS[target_label]
                    value = row[index[source_header]]
                    values[field] = (
                        parse_date(value)
                        if field in {"date_of_birth", "appointment_date"}
                        else value
                    )
            if not str(values.get("name") or "").strip():
                result["skipped"] += 1
                continue
            try:
                self.employee_service.save(values)
                result["created"] += 1
            except DuplicateEmployeeError as exc:
                decision = conflict_resolver(exc.employee, values) if conflict_resolver else "skip"
                if decision == "update":
                    self.employee_service.save(values, exc.employee.id)
                    result["updated"] += 1
                else:
                    result["skipped"] += 1
            except Exception as exc:
                result["errors"].append(f"Row {number}: {exc}")
        return result
