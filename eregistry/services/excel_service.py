from __future__ import annotations

import calendar
import os
import tempfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import Employee, PayrollEntry, PayrollMonth


PEACH = "F8CBAD"
LIGHT_PEACH = "FCE4D6"
THIN = Side(style="thin", color="000000")


class ExcelSyncError(RuntimeError):
    pass


class ExcelService:
    def __init__(self, db, organisation, organisation_folder: Path):
        self.db = db
        self.organisation = organisation
        self.organisation_folder = organisation_folder

    @property
    def workbook_path(self) -> Path:
        safe = "".join(c for c in self.organisation.name if c.isalnum() or c in " -_").strip()
        return self.organisation_folder / f"{safe}_eRegistry.xlsx"

    def sync(self) -> Path:
        with self.db.session() as session:
            employees = list(
                session.scalars(
                    select(Employee)
                    .options(
                        selectinload(Employee.work_experiences),
                        selectinload(Employee.education_records),
                        selectinload(Employee.nominees),
                        selectinload(Employee.family_members),
                    )
                    .order_by(Employee.name)
                ).unique()
            )
            months = list(
                session.scalars(
                    select(PayrollMonth)
                    .options(selectinload(PayrollMonth.entries).selectinload(PayrollEntry.employee))
                    .order_by(PayrollMonth.year.desc(), PayrollMonth.month.desc())
                ).unique()
            )
        wb = Workbook()
        wb.remove(wb.active)
        if months:
            for month in months:
                self._salary_sheet(wb, month)
        else:
            self._salary_template(wb, employees)
        self._employees_sheet(wb, employees)
        self._relation_sheets(wb, employees)
        self.organisation_folder.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(suffix=".xlsx", dir=self.organisation_folder)
        os.close(fd)
        temp = Path(temp_name)
        try:
            wb.save(temp)
            os.replace(temp, self.workbook_path)
        except PermissionError as exc:
            temp.unlink(missing_ok=True)
            raise ExcelSyncError(
                f"Close '{self.workbook_path.name}' in Excel and try again."
            ) from exc
        return self.workbook_path

    def _salary_template(self, wb: Workbook, employees: list[Employee]) -> None:
        ws = wb.create_sheet("Salary Template")
        self._salary_header(ws, "MONTH / YEAR")
        for idx, employee in enumerate(employees, 5):
            self._salary_row(ws, idx, employee, None)
        self._finish_salary_sheet(ws, len(employees) + 4)

    def _salary_sheet(self, wb: Workbook, month: PayrollMonth) -> None:
        title = f"{calendar.month_name[month.month]} {month.year}"
        ws = wb.create_sheet(f"{calendar.month_abbr[month.month]} {month.year}")
        self._salary_header(ws, title.upper())
        entries = [e for e in month.entries if e.included]
        entries.sort(key=lambda e: (e.employee.name or "").casefold())
        for idx, entry in enumerate(entries, 5):
            self._salary_row(ws, idx, entry.employee, entry)
        self._finish_salary_sheet(ws, len(entries) + 4)

    def _salary_header(self, ws, period: str) -> None:
        ws.sheet_view.showGridLines = False
        ws.merge_cells("A1:X1")
        ws["A1"] = self.organisation.name.upper()
        ws["A1"].font = Font(name="Cambria", size=18, bold=True)
        ws["A1"].alignment = Alignment(horizontal="center")
        ws.merge_cells("A2:X2")
        ws["A2"] = f"SALARY SHEET FOR THE MONTH OF {period}"
        ws["A2"].font = Font(name="Cambria", size=16, bold=True)
        ws["A2"].alignment = Alignment(horizontal="center")
        ws.merge_cells("A3:A4")
        ws["A3"] = "S.No."
        ws.merge_cells("B3:B4")
        ws["B3"] = "Designation"
        ws.merge_cells("C3:C4")
        ws["C3"] = "Name"
        ws.merge_cells("D3:D4")
        ws["D3"] = "Reg No."
        ws.merge_cells("E3:F3")
        ws["E3"] = "BANK DETAILS"
        ws["E4"] = "Bank Name"
        ws["F4"] = "Account Number"
        ws.merge_cells("G3:G4")
        ws["G3"] = "IFSC Code"
        ws.merge_cells("H3:H4")
        ws["H3"] = "Working Days"
        ws.merge_cells("I3:I4")
        ws["I3"] = "OT/PH"
        ws.merge_cells("J3:J4")
        ws["J3"] = "Wages Per Day"
        ws.merge_cells("K3:M3")
        ws["K3"] = "ADDITIONS"
        ws["K4"] = "Working Day Wages (Rs.)"
        ws["L4"] = "OT/PH Wages"
        ws["M4"] = "Bonus"
        ws.merge_cells("N3:N4")
        ws["N3"] = "Gross Salary"
        ws.merge_cells("O3:R3")
        ws["O3"] = "DEDUCTIONS"
        ws["O4"] = "EPF @12%"
        ws["P4"] = "ESIC @0.75%"
        ws["Q4"] = "Advance"
        ws["R4"] = "Total Deduction"
        ws.merge_cells("S3:S4")
        ws["S3"] = "Net Salary"
        ws.merge_cells("T3:T4")
        ws["T3"] = "Signature"
        ws.merge_cells("U3:U4")
        ws["U3"] = "Mobile No."
        ws.merge_cells("V3:V4")
        ws["V3"] = "Aadhaar No."
        ws.merge_cells("W3:W4")
        ws["W3"] = "UAN No."
        ws.merge_cells("X3:X4")
        ws["X3"] = "ESIC No."
        for row in ws.iter_rows(min_row=3, max_row=4, min_col=1, max_col=24):
            for cell in row:
                cell.fill = PatternFill("solid", fgColor=PEACH)
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
        ws.row_dimensions[3].height = 30
        ws.row_dimensions[4].height = 40

    def _salary_row(self, ws, row: int, employee: Employee, entry: PayrollEntry | None) -> None:
        values = [
            row - 4,
            employee.designation,
            employee.name,
            employee.registration_number,
            employee.bank_name,
            employee.bank_account_number,
            employee.ifsc_code,
            entry.working_days if entry else "",
            f"{entry.ot_hours:g}h / {entry.ph_days:g}d"
            if entry and (entry.ot_hours or entry.ph_days)
            else "",
            entry.wages_per_day if entry else "",
            entry.working_day_wages if entry else "",
            entry.ot_ph_wages if entry else "",
            entry.bonus if entry else "",
            entry.gross_salary if entry else "",
            entry.epf_deduction if entry else "",
            entry.esic_deduction if entry else "",
            entry.advance if entry else "",
            entry.total_deduction if entry else "",
            entry.net_salary if entry else "",
            "",
            employee.contact_number,
            employee.aadhaar_number,
            employee.uan_number,
            employee.esic_number,
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row, col, value if value is not None else "")
            cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
            cell.alignment = Alignment(
                vertical="center", horizontal="right" if col in range(8, 20) else "left"
            )
            if col in range(10, 20) and isinstance(value, (int, float)):
                cell.number_format = "#,##0.00" if col == 10 else "#,##0"

    def _finish_salary_sheet(self, ws, last_row: int) -> None:
        widths = [
            7,
            16,
            28,
            14,
            24,
            22,
            16,
            13,
            12,
            15,
            18,
            15,
            12,
            15,
            13,
            14,
            12,
            17,
            15,
            16,
            16,
            18,
            17,
            16,
        ]
        for idx, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(idx)].width = width
        ws.freeze_panes = "A5"
        ws.auto_filter.ref = f"A4:X{max(5, last_row)}"
        ws.print_title_rows = "1:4"
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    def _employees_sheet(self, wb: Workbook, employees: list[Employee]) -> None:
        ws = wb.create_sheet("Registration Details")
        columns = [
            "Employee ID",
            "Registration No.",
            "Registration Date",
            "Current Designation",
            "Status",
            "Name",
            "Father's / Husband's Name",
            "Date of Birth",
            "Appointment Date",
            "Age Years",
            "Age Months",
            "Mother's Name",
            "Mother's Age",
            "Place of Birth",
            "Gender",
            "Marital Status",
            "Nationality",
            "Blood Group",
            "Identification Mark 1",
            "Identification Mark 2",
            "Armed Forces Experience",
            "Armed Forces Years",
            "Armed Forces Rank",
            "Gunman Details",
            "Gun License No.",
            "Issuing Authority",
            "License Valid To",
            "Weapon Type",
            "Aadhaar No.",
            "Driving License No.",
            "Other Certification",
            "Languages Known",
            "Permanent Address",
            "Communication Address",
            "PAN No.",
            "Bank Name",
            "Branch Name",
            "Account No.",
            "IFSC",
            "EPFO Registered",
            "ESIC Registered",
            "UAN No.",
            "ESIC No.",
            "Contact No.",
            "Alternate Contact No.",
            "Exit Date",
            "Exit Reason",
            "Photo Path",
        ]
        self._simple_header(ws, columns)
        attrs = [
            "id",
            "registration_number",
            "registration_date",
            "designation",
            "status",
            "name",
            "father_husband_name",
            "date_of_birth",
            "appointment_date",
            "age_years",
            "age_months",
            "mother_name",
            "mother_age",
            "place_of_birth",
            "gender",
            "marital_status",
            "nationality",
            "blood_group",
            "identification_mark_1",
            "identification_mark_2",
            "armed_forces_experience",
            "armed_forces_years",
            "armed_forces_rank",
            "gunman_details",
            "gun_license_number",
            "gun_issuing_authority",
            "gun_license_valid_to",
            "weapon_type",
            "aadhaar_number",
            "driving_license_number",
            "other_certification",
            "languages_known",
            "permanent_address",
            "communication_address",
            "pan_number",
            "bank_name",
            "bank_branch",
            "bank_account_number",
            "ifsc_code",
            "epfo_registered",
            "esic_registered",
            "uan_number",
            "esic_number",
            "contact_number",
            "alternate_contact_number",
            "exit_date",
            "exit_reason",
            "photo_path",
        ]
        for employee in employees:
            ws.append(
                [
                    getattr(employee, attr) if getattr(employee, attr) is not None else ""
                    for attr in attrs
                ]
            )
        self._finish_detail_sheet(ws)

    def _relation_sheets(self, wb: Workbook, employees: list[Employee]) -> None:
        specs = [
            (
                "Work Experience",
                "work_experiences",
                [
                    "Employer Name & Address",
                    "Rank/Post",
                    "From",
                    "To",
                    "Salary/Month",
                    "Nature of Work",
                    "Reason for Leaving",
                ],
                [
                    "employer_name_address",
                    "rank_post",
                    "date_from",
                    "date_to",
                    "salary_per_month",
                    "nature_of_work",
                    "reason_for_leaving",
                ],
            ),
            (
                "Education",
                "education_records",
                [
                    "Qualification",
                    "Subject",
                    "Year of Passing",
                    "Board/College/University",
                    "Division/Result",
                    "Remarks",
                ],
                [
                    "qualification",
                    "subject",
                    "year_of_passing",
                    "board_college_university",
                    "division_result",
                    "remarks",
                ],
            ),
            (
                "Nominees",
                "nominees",
                ["Name", "Relation", "Address", "Mobile No."],
                ["name", "relation", "address", "mobile_number"],
            ),
            (
                "Family",
                "family_members",
                [
                    "Name",
                    "Date of Birth",
                    "Relation",
                    "Residing With Employee",
                    "Gender",
                    "Aadhaar No.",
                ],
                [
                    "name",
                    "date_of_birth",
                    "relation",
                    "residing_with_employee",
                    "gender",
                    "aadhaar_number",
                ],
            ),
        ]
        for sheet_name, relation, headers, attrs in specs:
            ws = wb.create_sheet(sheet_name)
            self._simple_header(ws, ["Employee ID", "Registration No.", "Employee Name", *headers])
            for employee in employees:
                for child in getattr(employee, relation):
                    ws.append(
                        [
                            employee.id,
                            employee.registration_number or "",
                            employee.name,
                            *[
                                getattr(child, attr) if getattr(child, attr) is not None else ""
                                for attr in attrs
                            ],
                        ]
                    )
            self._finish_detail_sheet(ws)

    @staticmethod
    def _simple_header(ws, headers):
        ws.append(headers)
        for cell in ws[1]:
            cell.fill = PatternFill("solid", fgColor=PEACH)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    @staticmethod
    def _finish_detail_sheet(ws):
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for column in ws.columns:
            letter = get_column_letter(column[0].column)
            width = min(max(len(str(cell.value or "")) for cell in column) + 2, 45)
            ws.column_dimensions[letter].width = max(12, width)
            for cell in column:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
