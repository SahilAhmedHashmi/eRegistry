from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _v(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d-%m-%Y")
    return str(value)


class RegistrationPdfService:
    def __init__(self, organisation_folder: Path, organisation_name: str):
        self.organisation_folder = organisation_folder
        self.organisation_name = organisation_name
        self.styles = getSampleStyleSheet()
        self.small = ParagraphStyle("small", parent=self.styles["Normal"], fontSize=8, leading=10)
        self.center = ParagraphStyle(
            "center", parent=self.styles["Heading2"], alignment=TA_CENTER, fontSize=15
        )

    def generate(self, employee, output: Path | None = None) -> Path:
        output = output or (
            self.organisation_folder
            / "pdfs"
            / f"Registration_{employee.registration_number or employee.id}.pdf"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output),
            pagesize=A4,
            leftMargin=13 * mm,
            rightMargin=13 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
        )
        story = [Paragraph("<u>REGISTRATION FORM</u>", self.center), Spacer(1, 3 * mm)]
        photo = "Photo"
        if employee.photo_path:
            path = self.organisation_folder / employee.photo_path
            if path.exists():
                photo = Image(str(path), width=25 * mm, height=30 * mm)
        meta = Table(
            [
                [
                    Paragraph(
                        f"<b>Registration No.</b> {_v(employee.registration_number)}", self.small
                    ),
                    Paragraph(f"<b>Date:</b> {_v(employee.registration_date)}", self.small),
                    photo,
                ]
            ],
            colWidths=[95 * mm, 50 * mm, 28 * mm],
            rowHeights=[32 * mm],
        )
        meta.setStyle(
            TableStyle(
                [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (2, 0), (2, 0), 0.8, colors.black)]
            )
        )
        story.append(meta)
        fields = [
            ("1. Name of the Applicant", employee.name),
            ("2. Applicant Father's / Husband's Name", employee.father_husband_name),
            ("3. Date of Birth", _v(employee.date_of_birth)),
            ("   Appointment Date", _v(employee.appointment_date)),
            (
                "   Age at the time of appointment",
                f"{_v(employee.age_years)} years {_v(employee.age_months)} months",
            ),
            ("4. Mother", f"{employee.mother_name}    Age: {_v(employee.mother_age)}"),
            ("5. Place of birth", employee.place_of_birth),
            ("6. Gender", employee.gender),
            ("7. Marital Status", employee.marital_status),
            ("8. Nationality", employee.nationality),
            ("9. Blood Group", employee.blood_group),
            ("10. Identification marks (a)", employee.identification_mark_1),
            ("     (b)", employee.identification_mark_2),
        ]
        story.append(self._field_table(fields))
        story.append(Paragraph("<b>11. Work Experience</b>", self.small))
        story.append(
            self._table(
                [
                    "Sl No.",
                    "Employer Name & Address",
                    "Rank/Post",
                    "From",
                    "To",
                    "Salary/month",
                    "Nature/type of work",
                    "Reason for leaving",
                ],
                [
                    [
                        i + 1,
                        x.employer_name_address,
                        x.rank_post,
                        _v(x.date_from),
                        _v(x.date_to),
                        _v(x.salary_per_month),
                        x.nature_of_work,
                        x.reason_for_leaving,
                    ]
                    for i, x in enumerate(employee.work_experiences)
                ]
                or [["", "", "", "", "", "", "", ""]],
                [9, 34, 20, 16, 16, 20, 32, 31],
            )
        )
        more = [
            (
                "12. Experience in Armed Forces/PME",
                f"{employee.armed_forces_experience}; Years: {employee.armed_forces_years}; Rank: {employee.armed_forces_rank}",
            ),
            (
                "Gun Man / License",
                f"{employee.gunman_details}; No: {employee.gun_license_number}; Authority: {employee.gun_issuing_authority}; Valid to: {_v(employee.gun_license_valid_to)}; Weapon: {employee.weapon_type}",
            ),
            (
                "13. Aadhaar No.",
                f"{_v(employee.aadhaar_number)}    Driving License: {employee.driving_license_number}",
            ),
        ]
        story.append(self._field_table(more))
        story.append(Paragraph("<b>14. Educational Qualification</b>", self.small))
        story.append(
            self._table(
                [
                    "Sl No.",
                    "Qualification",
                    "Subject",
                    "Year",
                    "Board/College/University",
                    "Division/Result",
                    "Remarks",
                ],
                [
                    [
                        i + 1,
                        x.qualification,
                        x.subject,
                        x.year_of_passing,
                        x.board_college_university,
                        x.division_result,
                        x.remarks,
                    ]
                    for i, x in enumerate(employee.education_records)
                ]
                or [["", "", "", "", "", "", ""]],
                [11, 26, 24, 17, 42, 29, 30],
            )
        )
        story.append(
            self._field_table(
                [
                    ("15. Any other certification", employee.other_certification),
                    ("16. Languages Known", employee.languages_known),
                ]
            )
        )
        story.append(Paragraph("<b>17. Nominee Details</b>", self.small))
        story.append(
            self._table(
                ["Name", "Relation", "Address", "Mobile No."],
                [[x.name, x.relation, x.address, x.mobile_number] for x in employee.nominees]
                or [["", "", "", ""]],
                [45, 28, 72, 38],
            )
        )
        story.append(PageBreak())
        story.append(Paragraph("<b>18. Family Details</b>", self.small))
        story.append(
            self._table(
                [
                    "Name",
                    "Date of Birth",
                    "Relation with employee",
                    "Residing with him/her",
                    "M/F",
                    "Aadhaar No.",
                ],
                [
                    [
                        x.name,
                        _v(x.date_of_birth),
                        x.relation,
                        "Yes" if x.residing_with_employee else "No",
                        x.gender,
                        x.aadhaar_number,
                    ]
                    for x in employee.family_members
                ]
                or [["", "", "", "", "", ""]],
                [42, 27, 36, 34, 16, 35],
            )
        )
        story.append(Spacer(1, 4 * mm))
        story.append(
            self._field_table(
                [
                    ("19. Permanent Address", employee.permanent_address),
                    ("20. Communication Address", employee.communication_address),
                    ("21. PAN No.", employee.pan_number),
                    (
                        "22. Bank Details",
                        f"Bank: {employee.bank_name}; Branch: {employee.bank_branch}; Account: {employee.bank_account_number}; IFSC: {employee.ifsc_code}",
                    ),
                    (
                        "23. Registered with EPFO & ESIC",
                        f"EPFO: {'Yes' if employee.epfo_registered else 'No'}; ESIC: {'Yes' if employee.esic_registered else 'No'}; UAN: {_v(employee.uan_number)}; ESIC No.: {_v(employee.esic_number)}",
                    ),
                    ("24. Contact Number", employee.contact_number),
                    ("25. Alternate Contact No.", employee.alternate_contact_number),
                ],
                row_height=13 * mm,
            )
        )
        story.extend(
            [
                Spacer(1, 5 * mm),
                Paragraph("<u><b>DECLARATION</b></u>", self.center),
                Paragraph(
                    "I hereby declare that the information given in this application is true and correct to the best of my knowledge and belief. If any information proves false or incorrect, I shall be responsible for the consequences.",
                    self.small,
                ),
                Spacer(1, 22 * mm),
                Table(
                    [["Applicant Signature", "Authorised Signature"]],
                    colWidths=[90 * mm, 90 * mm],
                    style=[
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                    ],
                ),
            ]
        )
        doc.build(story)
        return output

    def _field_table(self, fields, row_height=None):
        data = [
            [Paragraph(f"<b>{label}</b>", self.small), Paragraph(_v(value), self.small)]
            for label, value in fields
        ]
        table = Table(
            data,
            colWidths=[62 * mm, 120 * mm],
            rowHeights=[row_height] * len(data) if row_height else None,
        )
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (1, 0), (1, -1), 0.35, colors.grey),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return table

    def _table(self, headers, rows, widths):
        data = [[Paragraph(f"<b>{h}</b>", self.small) for h in headers]]
        data += [[Paragraph(_v(v), self.small) for v in row] for row in rows]
        table = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ]
            )
        )
        return table
