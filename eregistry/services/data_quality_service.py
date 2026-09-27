from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import Employee, PayrollEntry, PayrollMonth


@dataclass(frozen=True)
class DataQualityIssue:
    severity: str
    category: str
    employee_id: int | None
    employee_name: str
    registration_number: str
    entity_type: str
    entity_id: int | None
    source: str
    field: str
    message: str


def _text(value) -> str:
    return str(value or "").strip()


def _numeric_identifier(value) -> str:
    return re.sub(r"[\s-]+", "", _text(value)).upper()


def _registration_identifier(value) -> str:
    return re.sub(r"\s+", "", _text(value)).upper()


def _digits(value) -> str:
    return re.sub(r"\D", "", _text(value))


def _money(value) -> float:
    return float(
        Decimal(str(value or 0)).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


class DataQualityService:
    """Read-only checks for the current organisation database."""

    IDENTIFIERS = (
        ("registration_number", "Registration No.", _registration_identifier),
        ("aadhaar_number", "Aadhaar", _numeric_identifier),
        ("uan_number", "UAN", _numeric_identifier),
        ("esic_number", "ESIC", _numeric_identifier),
    )

    def __init__(self, db):
        self.db = db

    def scan(self) -> list[DataQualityIssue]:
        with self.db.session() as session:
            employees = list(
                session.scalars(
                    select(Employee).order_by(Employee.name)
                )
            )
            months = list(
                session.scalars(
                    select(PayrollMonth)
                    .options(
                        selectinload(PayrollMonth.entries).selectinload(
                            PayrollEntry.employee
                        )
                    )
                    .order_by(PayrollMonth.year.desc(), PayrollMonth.month.desc())
                ).unique()
            )

        issues: list[DataQualityIssue] = []
        issues.extend(self._duplicate_issues(employees))
        for employee in employees:
            issues.extend(self._employee_issues(employee))
        for month in months:
            issues.extend(self._payroll_issues(month))

        severity_order = {"Error": 0, "Warning": 1, "Info": 2}
        return sorted(
            issues,
            key=lambda issue: (
                severity_order.get(issue.severity, 9),
                issue.employee_name.casefold(),
                issue.category,
                issue.field,
            ),
        )

    @staticmethod
    def _employee_issue(employee, severity, category, field, message):
        return DataQualityIssue(
            severity=severity,
            category=category,
            employee_id=employee.id,
            employee_name=employee.name or "",
            registration_number=employee.registration_number or "",
            entity_type="employee",
            entity_id=employee.id,
            source="Employee Register",
            field=field,
            message=message,
        )

    @staticmethod
    def _payroll_issue(entry, month, severity, category, field, message):
        employee = entry.employee
        return DataQualityIssue(
            severity=severity,
            category=category,
            employee_id=employee.id if employee else None,
            employee_name=employee.name if employee else "Unknown employee",
            registration_number=(employee.registration_number or "") if employee else "",
            entity_type="payroll_entry",
            entity_id=entry.id,
            source=f"Salary {month.year}-{month.month:02d}",
            field=field,
            message=message,
        )

    def _duplicate_issues(self, employees):
        issues = []
        for field, label, normalise in self.IDENTIFIERS:
            groups = defaultdict(list)
            for employee in employees:
                value = normalise(getattr(employee, field, None))
                if value:
                    groups[value].append(employee)
            for value, matches in groups.items():
                if len(matches) < 2:
                    continue
                names = ", ".join(
                    f"{employee.name} ({employee.registration_number or 'no Reg No.'})"
                    for employee in matches
                )
                for employee in matches:
                    issues.append(
                        self._employee_issue(
                            employee,
                            "Error",
                            "Duplicate identifier",
                            field,
                            f"Duplicate {label} {value}. Matching records: {names}.",
                        )
                    )
        return issues

    def _employee_issues(self, employee):
        issue = lambda severity, category, field, message: self._employee_issue(
            employee, severity, category, field, message
        )
        issues = []

        required = (
            ("name", "Name"),
            ("registration_number", "Registration number"),
            ("designation", "Designation/skill category"),
            ("contact_number", "Contact number"),
        )
        for field, label in required:
            if not _text(getattr(employee, field, None)):
                issues.append(
                    issue(
                        "Error" if field in {"name", "contact_number"} else "Warning",
                        "Missing information",
                        field,
                        f"{label} is missing.",
                    )
                )

        recommended = (
            ("date_of_birth", "Date of birth"),
            ("aadhaar_number", "Aadhaar number"),
            ("permanent_address", "Permanent address"),
        )
        for field, label in recommended:
            if not getattr(employee, field, None):
                issues.append(
                    issue(
                        "Info",
                        "Missing information",
                        field,
                        f"{label} has not been recorded.",
                    )
                )

        aadhaar = _numeric_identifier(employee.aadhaar_number)
        if aadhaar and not re.fullmatch(r"\d{12}", aadhaar):
            issues.append(
                issue("Error", "Invalid format", "aadhaar_number", "Aadhaar must contain exactly 12 digits.")
            )

        uan = _numeric_identifier(employee.uan_number)
        if uan and not re.fullmatch(r"\d{12}", uan):
            issues.append(
                issue("Error", "Invalid format", "uan_number", "UAN must contain exactly 12 digits.")
            )

        esic = _numeric_identifier(employee.esic_number)
        if esic and not re.fullmatch(r"\d{10}", esic):
            issues.append(
                issue("Warning", "Invalid format", "esic_number", "ESIC insurance number normally contains 10 digits.")
            )

        pan = _text(employee.pan_number).upper()
        if pan and not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", pan):
            issues.append(
                issue("Warning", "Invalid format", "pan_number", "PAN should use the format AAAAA9999A.")
            )

        ifsc = _text(employee.ifsc_code).upper()
        if ifsc and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", ifsc):
            issues.append(
                issue("Warning", "Invalid format", "ifsc_code", "IFSC should contain four letters, 0, and six letters or digits.")
            )

        for field, label in (
            ("contact_number", "Contact number"),
            ("alternate_contact_number", "Alternate contact number"),
        ):
            value = _text(getattr(employee, field, ""))
            digits = _digits(value)
            valid = len(digits) == 10 or (len(digits) == 12 and digits.startswith("91"))
            if value and not valid:
                issues.append(
                    issue("Warning", "Invalid format", field, f"{label} should contain a 10-digit Indian mobile number.")
                )

        today = date.today()
        if employee.date_of_birth and employee.date_of_birth > today:
            issues.append(
                issue("Error", "Date inconsistency", "date_of_birth", "Date of birth is in the future.")
            )
        if employee.appointment_date and employee.date_of_birth and employee.appointment_date < employee.date_of_birth:
            issues.append(
                issue("Error", "Date inconsistency", "appointment_date", "Appointment date is earlier than date of birth.")
            )
        if employee.registration_date and employee.registration_date > today:
            issues.append(
                issue("Warning", "Date inconsistency", "registration_date", "Registration date is in the future.")
            )

        if employee.epfo_registered and not uan:
            issues.append(
                issue("Error", "Statutory inconsistency", "uan_number", "EPFO is marked Yes, but UAN is missing.")
            )
        if uan and not employee.epfo_registered:
            issues.append(
                issue("Warning", "Statutory inconsistency", "epfo_registered", "A UAN is recorded, but EPFO is marked No.")
            )
        if employee.esic_registered and not esic:
            issues.append(
                issue("Error", "Statutory inconsistency", "esic_number", "ESIC is marked Yes, but ESIC number is missing.")
            )
        if esic and not employee.esic_registered:
            issues.append(
                issue("Warning", "Statutory inconsistency", "esic_registered", "An ESIC number is recorded, but ESIC is marked No.")
            )

        if employee.status == "Inactive":
            if not employee.exit_date:
                issues.append(
                    issue("Warning", "Status inconsistency", "exit_date", "Inactive employee has no exit date.")
                )
            if not _text(employee.exit_reason):
                issues.append(
                    issue("Info", "Status inconsistency", "exit_reason", "Inactive employee has no exit reason.")
                )
        elif employee.exit_date or _text(employee.exit_reason):
            issues.append(
                issue("Warning", "Status inconsistency", "status", "Active employee still has exit information.")
            )

        return issues

    def _payroll_issues(self, month):
        issues = []
        numeric_fields = (
            "working_days",
            "ot_hours",
            "ph_days",
            "wages_per_day",
            "working_day_wages",
            "ot_ph_wages",
            "bonus",
            "gross_salary",
            "epf_deduction",
            "esic_deduction",
            "advance",
            "total_deduction",
            "net_salary",
            "client_billing_rate",
            "billed_revenue",
        )

        for entry in month.entries:
            if not entry.included:
                continue
            add = lambda severity, category, field, message: issues.append(
                self._payroll_issue(entry, month, severity, category, field, message)
            )

            for field in numeric_fields:
                if float(getattr(entry, field, 0) or 0) < 0:
                    add("Error", "Payroll value", field, f"{field.replace('_', ' ').title()} cannot be negative.")

            if entry.working_days > 31:
                add("Error", "Payroll value", "working_days", "Working days cannot exceed 31.")
            if entry.ph_days > 31:
                add("Error", "Payroll value", "ph_days", "Public-holiday days cannot exceed 31.")
            if entry.ot_hours > 100:
                add("Warning", "Payroll value", "ot_hours", "Overtime exceeds 100 hours; verify this value.")
            if entry.performance_rating is not None and not 1 <= entry.performance_rating <= 5:
                add("Error", "Performance", "performance_rating", "Performance rating must be between 1 and 5.")
            if month.status == "Completed" and entry.performance_rating is None:
                add("Info", "Performance", "performance_rating", "Completed salary month has no performance rating.")

            overrides = {
                value.strip()
                for value in _text(entry.override_fields).split(",")
                if value.strip()
            }
            expected = {
                "working_day_wages": _money(entry.working_days * entry.wages_per_day),
                "gross_salary": _money(entry.working_day_wages + entry.ot_ph_wages + entry.bonus),
                "total_deduction": _money(entry.epf_deduction + entry.esic_deduction + entry.advance),
                "net_salary": _money(entry.gross_salary - entry.total_deduction),
                "billed_revenue": _money(entry.working_days * entry.client_billing_rate),
            }
            for field, expected_value in expected.items():
                if field in overrides:
                    continue
                actual = float(getattr(entry, field, 0) or 0)
                if abs(actual - expected_value) > 0.01:
                    add(
                        "Error",
                        "Calculation mismatch",
                        field,
                        f"Stored value {actual:,.2f} does not match calculated value {expected_value:,.2f}.",
                    )

            if entry.total_deduction > entry.gross_salary:
                add("Warning", "Payroll value", "total_deduction", "Total deduction exceeds gross salary.")
            if entry.employee and entry.employee.status == "Inactive":
                add("Warning", "Status inconsistency", "employee_id", "Inactive employee is included in this salary month.")

        return issues