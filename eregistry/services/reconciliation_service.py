from __future__ import annotations

import calendar
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import PayrollEntry, PayrollMonth


FIELD_LABELS = {
    "pf_number": "PF No.",
    "employee_name": "Employee Name",
    "expected_salary": "Expected Salary",
    "actual_salary": "Actual Salary",
    "working_days": "Working Days",
}

HEADER_ALIASES = {
    "pf_number": {
        "pf", "pf no", "pf number", "pf account no", "pf account number",
        "uan", "uan no", "uan number", "uan pf no", "uan pf number",
    },
    "employee_name": {"name", "employee", "employee name", "worker name"},
    "expected_salary": {
        "expected salary", "expected wages", "full salary", "full month salary",
    },
    "actual_salary": {
        "actual salary", "actual wages", "earned salary", "salary earned",
    },
    "working_days": {"days", "days worked", "working days", "worked days"},
}


class ReconciliationError(ValueError):
    pass


@dataclass(frozen=True)
class WorkbookInspection:
    sheet_names: list[str]
    sheet_name: str
    header_row: int
    headers: list[str]
    suggested_mapping: dict[str, int]


@dataclass(frozen=True)
class ExternalSalaryRow:
    source_row: int
    pf_number: str
    employee_name: str
    expected_salary: Decimal | None
    actual_salary: Decimal | None
    working_days: Decimal | None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    source_row: int | None
    reported_pf_number: str
    eregistry_uan: str
    reported_name: str
    eregistry_name: str
    reported_working_days: Decimal | None
    eregistry_working_days: Decimal | None
    wages_per_day: Decimal | None
    reported_expected_salary: Decimal | None
    calculated_expected_salary: Decimal | None
    expected_difference: Decimal | None
    reported_actual_salary: Decimal | None
    calculated_from_reported_days: Decimal | None
    eregistry_working_wages: Decimal | None
    actual_difference: Decimal | None
    formula_difference: Decimal | None
    explanation: str


def _header_key(value) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalise_pf(value) -> str:
    return re.sub(r"[\s-]+", "", _cell_text(value)).upper()


def normalise_name(value) -> str:
    text = _cell_text(value).casefold()
    simplified = "".join(
        character if character.isalnum() else " " for character in text
    )
    return " ".join(simplified.split())


def parse_decimal(value, label: str) -> tuple[Decimal | None, str | None]:
    if value is None or _cell_text(value) == "":
        return None, None
    if isinstance(value, bool):
        return None, f"{label} is not a valid number."
    text = _cell_text(value).replace(",", "").replace("₹", "").strip()
    try:
        return Decimal(text), None
    except InvalidOperation:
        return None, f"{label} is not a valid number: {_cell_text(value)!r}."


def round_rupee(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _suggest_mapping(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, header in enumerate(headers):
        key = _header_key(header)
        for field, aliases in HEADER_ALIASES.items():
            if field not in mapping and key in aliases:
                mapping[field] = index
    return mapping


class ReconciliationService:
    """Read-only comparison between a payroll month and an external workbook."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def inspect_workbook(path: Path) -> WorkbookInspection:
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            best = None
            for worksheet in workbook.worksheets:
                for row_number, row in enumerate(
                    worksheet.iter_rows(min_row=1, max_row=30, values_only=True), 1
                ):
                    headers = [_cell_text(value) for value in row]
                    while headers and not headers[-1]:
                        headers.pop()
                    mapping = _suggest_mapping(headers)
                    score = len(mapping)
                    candidate = (score, worksheet.title, row_number, headers, mapping)
                    if best is None or candidate[0] > best[0]:
                        best = candidate
            if best is None:
                raise ReconciliationError("The workbook does not contain any readable rows.")
            _, sheet_name, header_row, headers, mapping = best
            return WorkbookInspection(
                sheet_names=list(workbook.sheetnames),
                sheet_name=sheet_name,
                header_row=header_row,
                headers=headers,
                suggested_mapping=mapping,
            )
        finally:
            workbook.close()

    @staticmethod
    def read_headers(path: Path, sheet_name: str, header_row: int) -> list[str]:
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            if sheet_name not in workbook.sheetnames:
                raise ReconciliationError(f"Worksheet {sheet_name!r} was not found.")
            worksheet = workbook[sheet_name]
            row = next(
                worksheet.iter_rows(
                    min_row=header_row,
                    max_row=header_row,
                    values_only=True,
                ),
                (),
            )
            headers = [_cell_text(value) for value in row]
            while headers and not headers[-1]:
                headers.pop()
            return headers
        finally:
            workbook.close()

    @staticmethod
    def load_rows(
        path: Path,
        sheet_name: str,
        header_row: int,
        mapping: dict[str, int],
    ) -> list[ExternalSalaryRow]:
        missing = [field for field in FIELD_LABELS if field not in mapping]
        if missing:
            labels = ", ".join(FIELD_LABELS[field] for field in missing)
            raise ReconciliationError(f"Map all required columns before continuing: {labels}.")
        if len(set(mapping.values())) != len(mapping):
            raise ReconciliationError(
                "Each reconciliation field must use a different Excel column."
            )

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            if sheet_name not in workbook.sheetnames:
                raise ReconciliationError(f"Worksheet {sheet_name!r} was not found.")
            worksheet = workbook[sheet_name]
            results = []
            for row_number, row in enumerate(
                worksheet.iter_rows(min_row=header_row + 1, values_only=True),
                header_row + 1,
            ):
                values = {
                    field: row[index] if index < len(row) else None
                    for field, index in mapping.items()
                }
                if not any(_cell_text(value) for value in values.values()):
                    continue
                errors = []
                expected, error = parse_decimal(values["expected_salary"], "Expected Salary")
                if error:
                    errors.append(error)
                elif expected is None:
                    errors.append("Expected Salary is missing.")
                actual, error = parse_decimal(values["actual_salary"], "Actual Salary")
                if error:
                    errors.append(error)
                elif actual is None:
                    errors.append("Actual Salary is missing.")
                days, error = parse_decimal(values["working_days"], "Working Days")
                if error:
                    errors.append(error)
                elif days is None:
                    errors.append("Working Days is missing.")
                if days is not None and days < 0:
                    errors.append("Working Days cannot be negative.")
                if not _cell_text(values["employee_name"]):
                    errors.append("Employee Name is missing.")
                if not _cell_text(values["pf_number"]):
                    errors.append("PF/UAN is missing.")
                results.append(
                    ExternalSalaryRow(
                        source_row=row_number,
                        pf_number=_cell_text(values["pf_number"]),
                        employee_name=_cell_text(values["employee_name"]),
                        expected_salary=expected,
                        actual_salary=actual,
                        working_days=days,
                        errors=tuple(errors),
                    )
                )
            if not results:
                raise ReconciliationError(
                    "No salary rows were found below the selected header row."
                )
            return results
        finally:
            workbook.close()

    def reconcile(
        self,
        payroll_id: int,
        external_rows: list[ExternalSalaryRow],
    ) -> tuple[PayrollMonth, list[ReconciliationResult]]:
        with self.db.session() as session:
            month = session.scalars(
                select(PayrollMonth)
                .options(selectinload(PayrollMonth.entries).selectinload(PayrollEntry.employee))
                .where(PayrollMonth.id == payroll_id)
            ).first()
            if month is None:
                raise ReconciliationError("The selected salary month no longer exists.")
            internal_entries = [entry for entry in month.entries if entry.included]
            # Convert ORM-backed data before the read-only session closes.
            internal = [
                {
                    "entry_id": entry.id,
                    "employee_id": entry.employee.id,
                    "name": entry.employee.name or "",
                    "uan": entry.employee.uan_number or "",
                    "working_days": Decimal(str(entry.working_days or 0)),
                    "wages_per_day": Decimal(str(entry.wages_per_day or 0)),
                    "working_wages": Decimal(str(entry.working_day_wages or 0)),
                }
                for entry in internal_entries
            ]

        by_pf = defaultdict(list)
        by_name = defaultdict(list)
        for row in internal:
            if normalise_pf(row["uan"]):
                by_pf[normalise_pf(row["uan"])].append(row)
            if normalise_name(row["name"]):
                by_name[normalise_name(row["name"])].append(row)

        external_pf_counts = Counter(
            normalise_pf(row.pf_number) for row in external_rows if normalise_pf(row.pf_number)
        )
        internal_pf_counts = Counter(
            normalise_pf(row["uan"]) for row in internal if normalise_pf(row["uan"])
        )

        matched_employee_ids: set[int] = set()
        results = []
        days_in_month = calendar.monthrange(month.year, month.month)[1]

        for external in external_rows:
            pf_key = normalise_pf(external.pf_number)
            name_key = normalise_name(external.employee_name)
            candidate = None
            status = "External only"
            explanations = list(external.errors)

            if pf_key and (external_pf_counts[pf_key] > 1 or internal_pf_counts[pf_key] > 1):
                pf_candidates = by_pf.get(pf_key, [])
                candidate = pf_candidates[0] if len(pf_candidates) == 1 else None
                status = "Duplicate"
                explanations.append("PF/UAN occurs more than once in a comparison source.")
            else:
                pf_candidates = by_pf.get(pf_key, []) if pf_key else []
                if len(pf_candidates) == 1:
                    candidate = pf_candidates[0]
                    if name_key and name_key == normalise_name(candidate["name"]):
                        status = "Confirmed match"
                    else:
                        status = "Name conflict"
                        explanations.append("PF/UAN matches, but the employee names differ.")
                elif len(pf_candidates) > 1:
                    status = "Ambiguous"
                    explanations.append("PF/UAN matches more than one eRegistry employee.")
                else:
                    name_candidates = by_name.get(name_key, []) if name_key else []
                    if len(name_candidates) == 1:
                        candidate = name_candidates[0]
                        if pf_key:
                            status = "Identifier conflict"
                            explanations.append("Employee name matches, but PF/UAN differs.")
                        else:
                            status = "Possible name match"
                            explanations.append("PF/UAN is missing; matched by one unique name.")
                    elif len(name_candidates) > 1:
                        status = "Ambiguous"
                        explanations.append(
                            "Employee name matches more than one eRegistry employee."
                        )
                    else:
                        explanations.append("No eRegistry employee matches this PF/UAN or name.")

            if pf_key and not re.fullmatch(r"\d{12}", pf_key):
                explanations.append("Reported PF/UAN is not a 12-digit number.")
                if status == "Confirmed match":
                    status = "Identifier conflict"

            result = self._comparison_result(
                status,
                explanations,
                external,
                candidate,
                days_in_month,
            )
            results.append(result)
            if candidate is not None:
                matched_employee_ids.add(candidate["employee_id"])

        for row in internal:
            if row["employee_id"] in matched_employee_ids:
                continue
            results.append(
                ReconciliationResult(
                    status="eRegistry only",
                    source_row=None,
                    reported_pf_number="",
                    eregistry_uan=row["uan"],
                    reported_name="",
                    eregistry_name=row["name"],
                    reported_working_days=None,
                    eregistry_working_days=row["working_days"],
                    wages_per_day=row["wages_per_day"],
                    reported_expected_salary=None,
                    calculated_expected_salary=round_rupee(
                        Decimal(days_in_month) * row["wages_per_day"]
                    ),
                    expected_difference=None,
                    reported_actual_salary=None,
                    calculated_from_reported_days=None,
                    eregistry_working_wages=round_rupee(row["working_wages"]),
                    actual_difference=None,
                    formula_difference=None,
                    explanation=(
                        "Employee is in eRegistry salary month but absent from "
                        "the organisation sheet."
                    ),
                )
            )

        return month, results

    @staticmethod
    def _comparison_result(status, explanations, external, internal, days_in_month):
        if internal is None:
            return ReconciliationResult(
                status=status,
                source_row=external.source_row,
                reported_pf_number=external.pf_number,
                eregistry_uan="",
                reported_name=external.employee_name,
                eregistry_name="",
                reported_working_days=external.working_days,
                eregistry_working_days=None,
                wages_per_day=None,
                reported_expected_salary=external.expected_salary,
                calculated_expected_salary=None,
                expected_difference=None,
                reported_actual_salary=external.actual_salary,
                calculated_from_reported_days=None,
                eregistry_working_wages=None,
                actual_difference=None,
                formula_difference=None,
                explanation=" ".join(explanations),
            )

        wage = internal["wages_per_day"]
        calculated_expected = round_rupee(Decimal(days_in_month) * wage)
        reported_expected = round_rupee(external.expected_salary)
        expected_difference = (
            reported_expected - calculated_expected
            if reported_expected is not None
            else None
        )
        calculated_actual = (
            round_rupee(external.working_days * wage)
            if external.working_days is not None
            else None
        )
        reported_actual = round_rupee(external.actual_salary)
        internal_wages = round_rupee(internal["working_wages"])
        actual_difference = (
            reported_actual - internal_wages if reported_actual is not None else None
        )
        formula_difference = (
            reported_actual - calculated_actual
            if reported_actual is not None and calculated_actual is not None
            else None
        )

        day_difference = (
            external.working_days - internal["working_days"]
            if external.working_days is not None
            else None
        )
        if external.working_days is not None and external.working_days > days_in_month:
            explanations.append(
                f"Reported working days exceed the {days_in_month} calendar days in the month."
            )
        if day_difference not in (None, Decimal("0")):
            explanations.append(
                f"Working days differ by {day_difference:+g} day(s)."
            )
        if expected_difference not in (None, Decimal("0")):
            explanations.append(
                f"Expected salary differs by ₹{expected_difference:+,.0f}."
            )
        if formula_difference not in (None, Decimal("0")):
            explanations.append(
                "Reported actual salary differs from reported-days calculation "
                f"by ₹{formula_difference:+,.0f}."
            )
        if actual_difference not in (None, Decimal("0")):
            explanations.append(
                "Reported actual salary differs from eRegistry working wages "
                f"by ₹{actual_difference:+,.0f}."
            )

        if external.errors and status == "Confirmed match":
            status = "Invalid value"
        elif status == "Confirmed match":
            if day_difference not in (None, Decimal("0")):
                status = "Working-days mismatch"
            elif any(
                difference not in (None, Decimal("0"))
                for difference in (expected_difference, actual_difference, formula_difference)
            ):
                status = "Salary mismatch"

        if not explanations and status == "Confirmed match":
            explanations.append("Identity, working days and rounded salary values match.")

        return ReconciliationResult(
            status=status,
            source_row=external.source_row,
            reported_pf_number=external.pf_number,
            eregistry_uan=internal["uan"],
            reported_name=external.employee_name,
            eregistry_name=internal["name"],
            reported_working_days=external.working_days,
            eregistry_working_days=internal["working_days"],
            wages_per_day=wage,
            reported_expected_salary=reported_expected,
            calculated_expected_salary=calculated_expected,
            expected_difference=expected_difference,
            reported_actual_salary=reported_actual,
            calculated_from_reported_days=calculated_actual,
            eregistry_working_wages=internal_wages,
            actual_difference=actual_difference,
            formula_difference=formula_difference,
            explanation=" ".join(explanations),
        )

    @staticmethod
    def export_report(
        path: Path,
        organisation_name: str,
        month: PayrollMonth,
        source_name: str,
        results: list[ReconciliationResult],
    ) -> Path:
        workbook = Workbook()
        summary = workbook.active
        summary.title = "Summary"
        summary.append(["Salary Reconciliation Report"])
        summary.append(["Organisation", organisation_name])
        summary.append(["Salary month", f"{calendar.month_name[month.month]} {month.year}"])
        summary.append(["External workbook", source_name])
        summary.append([])
        summary.append(["Status", "Rows"])
        for status, count in sorted(Counter(row.status for row in results).items()):
            summary.append([status, count])
        summary.column_dimensions["A"].width = 32
        summary.column_dimensions["B"].width = 42
        summary["A1"].font = Font(size=16, bold=True)

        details = workbook.create_sheet("Comparison")
        headers = [
            "Status", "Source Row", "Reported PF/UAN", "eRegistry UAN",
            "Reported Employee Name", "eRegistry Employee Name",
            "Reported Working Days", "eRegistry Working Days", "Wage Per Day",
            "Reported Expected Salary", "Calculated Expected Salary", "Expected Difference",
            "Reported Actual Salary", "Calculated From Reported Days",
            "eRegistry Working Wages", "Actual Difference", "Formula Difference", "Explanation",
        ]
        details.append(headers)
        for cell in details[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="F8CBAD")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for result in results:
            details.append([
                result.status,
                result.source_row,
                result.reported_pf_number,
                result.eregistry_uan,
                result.reported_name,
                result.eregistry_name,
                (
                    float(result.reported_working_days)
                    if result.reported_working_days is not None
                    else None
                ),
                (
                    float(result.eregistry_working_days)
                    if result.eregistry_working_days is not None
                    else None
                ),
                float(result.wages_per_day) if result.wages_per_day is not None else None,
                (
                    float(result.reported_expected_salary)
                    if result.reported_expected_salary is not None
                    else None
                ),
                (
                    float(result.calculated_expected_salary)
                    if result.calculated_expected_salary is not None
                    else None
                ),
                (
                    float(result.expected_difference)
                    if result.expected_difference is not None
                    else None
                ),
                (
                    float(result.reported_actual_salary)
                    if result.reported_actual_salary is not None
                    else None
                ),
                (
                    float(result.calculated_from_reported_days)
                    if result.calculated_from_reported_days is not None
                    else None
                ),
                (
                    float(result.eregistry_working_wages)
                    if result.eregistry_working_wages is not None
                    else None
                ),
                float(result.actual_difference) if result.actual_difference is not None else None,
                float(result.formula_difference) if result.formula_difference is not None else None,
                result.explanation,
            ])
        for column in range(7, 18):
            for cell in details.iter_cols(min_col=column, max_col=column, min_row=2):
                for value_cell in cell:
                    value_cell.number_format = "#,##0.00"
        widths = [22, 12, 20, 20, 28, 28, 18, 18, 15, 22, 24, 20, 22, 25, 22, 18, 18, 70]
        for index, width in enumerate(widths, 1):
            details.column_dimensions[get_column_letter(index)].width = width
        details.freeze_panes = "A2"
        details.auto_filter.ref = details.dimensions
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(path)
        return path
