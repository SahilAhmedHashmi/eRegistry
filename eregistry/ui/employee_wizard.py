from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QRect, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from ..constants import GENDERS, LABOUR_CATEGORIES, MARITAL_STATUSES
from ..services.employee_service import calculate_age


def to_date(widget: QDateEdit):
    value = widget.date()
    if value == widget.minimumDate():
        return None
    return date(value.year(), value.month(), value.day())


def set_date(widget: QDateEdit, value):
    if value:
        widget.setDate(QDate(value.year, value.month, value.day))
    else:
        widget.setDate(widget.minimumDate())


def date_edit() -> QDateEdit:
    widget = QDateEdit()
    widget.setCalendarPopup(True)
    widget.setDisplayFormat("dd-MM-yyyy")
    widget.setMinimumDate(QDate(1900, 1, 1))
    widget.setSpecialValueText("Not set")
    widget.setDate(widget.minimumDate())
    return widget


class CropLabel(QLabel):
    selection_changed = Signal()

    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self.original = pixmap
        self.setPixmap(pixmap.scaled(700, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setFixedSize(self.pixmap().size())
        self.origin = None
        self.selection = QRect()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.selection = QRect(self.origin, self.origin)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.origin is not None:
            self.selection = QRect(self.origin, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.origin = None
            self.selection_changed.emit()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.selection.isNull():
            painter = QPainter(self)
            painter.setPen(QPen(Qt.red, 2))
            painter.drawRect(self.selection)

    def cropped(self) -> QPixmap:
        shown = self.pixmap()
        rect = (
            self.selection
            if not self.selection.isNull()
            else QRect(0, 0, shown.width(), shown.height())
        )
        sx = self.original.width() / shown.width()
        sy = self.original.height() / shown.height()
        source = QRect(
            int(rect.x() * sx), int(rect.y() * sy), int(rect.width() * sx), int(rect.height() * sy)
        )
        return self.original.copy(source)


class CropDialog(QDialog):
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crop employee photograph")
        self.result_path = ""
        pixmap = QPixmap(image_path)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Drag a rectangle around the photograph, then click Use Crop."))
        self.image = CropLabel(pixmap)
        layout.addWidget(self.image, alignment=Qt.AlignCenter)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Use Crop")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_to(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.image.cropped().scaled(
            600, 720, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        ).save(str(path), "JPG", 92)
        self.result_path = str(path)


class RowsEditor(QGroupBox):
    def __init__(self, title: str, headers: list[str], parent=None):
        super().__init__(title, parent)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(150)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton("Add another")
        remove = QPushButton("Remove selected")
        remove.setProperty("secondary", True)
        add.clicked.connect(self.add_row)
        remove.clicked.connect(self.remove_row)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        self.add_row()

    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col in range(self.table.columnCount()):
            self.table.setItem(row, col, QTableWidgetItem(""))

    def remove_row(self):
        if self.table.rowCount() > 1:
            self.table.removeRow(max(0, self.table.currentRow()))

    def rows(self, keys: list[str]) -> list[dict]:
        return [
            {
                key: (self.table.item(r, c).text().strip() if self.table.item(r, c) else "")
                for c, key in enumerate(keys)
            }
            for r in range(self.table.rowCount())
        ]

    def load(self, items, attrs):
        self.table.setRowCount(0)
        for item in items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, attr in enumerate(attrs):
                value = getattr(item, attr, "")
                self.table.setItem(row, col, QTableWidgetItem(str(value or "")))
        if not items:
            self.add_row()


class EmployeeWizard(QWizard):
    def __init__(self, context, employee=None, parent=None):
        super().__init__(parent)
        self.context = context
        self.employee = employee
        self.saved_employee = None
        self.photo_source = ""
        self.setWindowTitle("Edit Registration" if employee else "New Employee Registration")
        self.setMinimumSize(1050, 720)
        self.setWizardStyle(QWizard.ModernStyle)
        self.addPage(self._identity_page())
        self.addPage(self._experience_page())
        self.addPage(self._education_page())
        self.addPage(self._family_page())
        self.addPage(self._contact_page())
        self.currentIdChanged.connect(self._refresh_summary)
        if employee:
            self._load(employee)

    def _identity_page(self):
        page = QWizardPage()
        page.setTitle("Identity and appointment")
        page.setSubTitle("Enter the applicant's core information and photograph.")
        grid = QGridLayout(page)
        self.reg = QLineEdit()
        self.reg_date = date_edit()
        self.reg_date.setDate(QDate.currentDate())
        self.designation = QComboBox()
        self.designation.setEditable(True)
        self.designation.addItems([*LABOUR_CATEGORIES, "Custom"])
        self.name = QLineEdit()
        self.father = QLineEdit()
        self.dob = date_edit()
        self.appointment = date_edit()
        self.age_years = QSpinBox()
        self.age_years.setRange(0, 120)
        self.age_months = QSpinBox()
        self.age_months.setRange(0, 11)
        self.age_override = QCheckBox("Manually override calculated age")
        self.mother = QLineEdit()
        self.mother_age = QSpinBox()
        self.mother_age.setRange(0, 120)
        self.birth_place = QLineEdit()
        self.gender = QComboBox()
        self.gender.addItems(["", *GENDERS])
        self.marital = QComboBox()
        self.marital.addItems(["", *MARITAL_STATUSES])
        self.nationality = QLineEdit("Indian")
        self.blood = QLineEdit()
        self.mark1 = QLineEdit()
        self.mark2 = QLineEdit()
        self.photo_label = QLabel("No photo selected")
        self.photo_label.setFixedSize(150, 180)
        self.photo_label.setAlignment(Qt.AlignCenter)
        self.photo_label.setStyleSheet("border: 1px dashed #888")
        photo_btn = QPushButton("Browse and crop…")
        photo_btn.clicked.connect(self._choose_photo)
        fields = [
            ("Registration No.", self.reg),
            ("Registration Date", self.reg_date),
            ("Current Category / Designation", self.designation),
            ("Applicant Name*", self.name),
            ("Father's / Husband's Name", self.father),
            ("Date of Birth", self.dob),
            ("Appointment Date", self.appointment),
        ]
        form = QFormLayout()
        for label, widget in fields:
            form.addRow(label, widget)
        age_row = QHBoxLayout()
        age_row.addWidget(QLabel("Years"))
        age_row.addWidget(self.age_years)
        age_row.addWidget(QLabel("Months"))
        age_row.addWidget(self.age_months)
        form.addRow("Age at appointment", age_row)
        form.addRow("", self.age_override)
        form.addRow("Mother's Name", self.mother)
        form.addRow("Mother's Age", self.mother_age)
        form.addRow("Place of Birth", self.birth_place)
        form.addRow("Gender", self.gender)
        form.addRow("Marital Status", self.marital)
        form.addRow("Nationality", self.nationality)
        form.addRow("Blood Group", self.blood)
        form.addRow("Identification Mark (a)", self.mark1)
        form.addRow("Identification Mark (b)", self.mark2)
        grid.addLayout(form, 0, 0)
        side = QVBoxLayout()
        side.addWidget(self.photo_label)
        side.addWidget(photo_btn)
        side.addStretch()
        grid.addLayout(side, 0, 1)
        self.dob.dateChanged.connect(self._calculate_age)
        self.appointment.dateChanged.connect(self._calculate_age)
        self.age_override.toggled.connect(self._age_mode)
        return page

    def _experience_page(self):
        page = QWizardPage()
        page.setTitle("Work experience and service details")
        page.setSubTitle("Use Add another for additional previous employers.")
        layout = QVBoxLayout(page)
        self.work = RowsEditor(
            "Work Experience",
            [
                "Employer Name & Address",
                "Rank/Post",
                "From (DD-MM-YYYY)",
                "To",
                "Salary/Month",
                "Nature of Work",
                "Reason for Leaving",
            ],
        )
        layout.addWidget(self.work)
        form = QFormLayout()
        self.armed = QLineEdit()
        self.armed_years = QLineEdit()
        self.armed_rank = QLineEdit()
        self.gunman = QLineEdit()
        self.gun_license = QLineEdit()
        self.gun_authority = QLineEdit()
        self.gun_valid = date_edit()
        self.weapon = QLineEdit()
        form.addRow("Armed Forces/PME Experience", self.armed)
        form.addRow("Years", self.armed_years)
        form.addRow("Rank", self.armed_rank)
        form.addRow("Gun Man details", self.gunman)
        form.addRow("Gun License No.", self.gun_license)
        form.addRow("Issuing Authority", self.gun_authority)
        form.addRow("License Valid To", self.gun_valid)
        form.addRow("Weapon/Gun Type", self.weapon)
        layout.addLayout(form)
        return page

    def _education_page(self):
        page = QWizardPage()
        page.setTitle("Education and certifications")
        page.setSubTitle("Record qualifications and languages known.")
        layout = QVBoxLayout(page)
        self.education = RowsEditor(
            "Educational Qualification",
            [
                "Qualification",
                "Subject",
                "Year of Passing",
                "Board/College/University",
                "Division/Result",
                "Remarks",
            ],
        )
        layout.addWidget(self.education)
        form = QFormLayout()
        self.certification = QTextEdit()
        self.certification.setMaximumHeight(70)
        self.languages = QLineEdit()
        form.addRow("Any other certification", self.certification)
        form.addRow("Languages Known", self.languages)
        layout.addLayout(form)
        return page

    def _family_page(self):
        page = QWizardPage()
        page.setTitle("Nominee and family details")
        page.setSubTitle("Use Add another when more rows are needed.")
        layout = QVBoxLayout(page)
        self.nominees = RowsEditor("Nominee Details", ["Name", "Relation", "Address", "Mobile No."])
        self.family = RowsEditor(
            "Family Details",
            [
                "Name",
                "Date of Birth",
                "Relation",
                "Residing With? (Yes/No)",
                "Gender",
                "Aadhaar No.",
            ],
        )
        layout.addWidget(self.nominees)
        layout.addWidget(self.family)
        return page

    def _contact_page(self):
        page = QWizardPage()
        page.setTitle("Address, banking and statutory details")
        page.setSubTitle("Review carefully before saving the completed registration.")
        grid = QGridLayout(page)
        form = QFormLayout()
        self.permanent = QTextEdit()
        self.permanent.setMaximumHeight(70)
        self.communication = QTextEdit()
        self.communication.setMaximumHeight(70)
        self.same_address = QCheckBox("Same as permanent address")
        self.same_address.toggled.connect(self._same_address)
        self.pan = QLineEdit()
        self.bank = QLineEdit()
        self.branch = QLineEdit()
        self.account = QLineEdit()
        self.ifsc = QLineEdit()
        self.aadhaar = QLineEdit()
        self.driving = QLineEdit()
        self.epfo = QCheckBox("Registered with EPFO")
        self.esic_registered = QCheckBox("Registered with ESIC")
        self.uan = QLineEdit()
        self.esic_no = QLineEdit()
        self.contact = QLineEdit()
        self.alternate = QLineEdit()
        form.addRow("Permanent Address", self.permanent)
        form.addRow("", self.same_address)
        form.addRow("Communication Address", self.communication)
        form.addRow("PAN No.", self.pan)
        form.addRow("Aadhaar No.", self.aadhaar)
        form.addRow("Driving License No.", self.driving)
        form.addRow("Bank Name", self.bank)
        form.addRow("Branch Name", self.branch)
        form.addRow("Account No.", self.account)
        form.addRow("IFSC", self.ifsc)
        form.addRow("", self.epfo)
        form.addRow("UAN No.", self.uan)
        form.addRow("", self.esic_registered)
        form.addRow("ESIC No.", self.esic_no)
        form.addRow("Contact Number", self.contact)
        form.addRow("Alternate Contact No.", self.alternate)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("padding: 12px; border: 1px solid #aaa; border-radius: 6px")
        grid.addLayout(form, 0, 0)
        grid.addWidget(self.summary, 0, 1)
        return page

    def _choose_photo(self):
        source, _ = QFileDialog.getOpenFileName(
            self, "Select employee photograph", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if not source:
            return
        dialog = CropDialog(source, self)
        if dialog.exec() == QDialog.Accepted:
            temp = self.context.root / ".photo-crop.jpg"
            dialog.save_to(temp)
            self.photo_source = str(temp)
            self.photo_label.setPixmap(
                QPixmap(str(temp)).scaled(
                    self.photo_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )

    def _calculate_age(self):
        if self.age_override.isChecked():
            return
        years, months = calculate_age(to_date(self.dob), to_date(self.appointment))
        self.age_years.setValue(years or 0)
        self.age_months.setValue(months or 0)

    def _age_mode(self, manual):
        self.age_years.setEnabled(manual)
        self.age_months.setEnabled(manual)
        if not manual:
            self._calculate_age()

    def _same_address(self, checked):
        if checked:
            self.communication.setPlainText(self.permanent.toPlainText())
            self.communication.setEnabled(False)
        else:
            self.communication.setEnabled(True)

    def _refresh_summary(self):
        if hasattr(self, "summary"):
            self.summary.setText(
                f"<b>Ready to save</b><br><br>Name: {self.name.text() or '—'}<br>Registration: {self.reg.text() or '—'}<br>Designation: {self.designation.currentText() or '—'}<br><br>Only the employee name is mandatory. Optional identifiers are format-checked and duplicates are blocked."
            )

    @staticmethod
    def _parsed_date(value: str):
        value = value.strip()
        if not value:
            return None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                from datetime import datetime

                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
        return None

    @staticmethod
    def _float(value: str):
        try:
            return float(value.replace(",", "")) if value else None
        except ValueError:
            return None

    def values(self):
        work = self.work.rows(
            [
                "employer_name_address",
                "rank_post",
                "date_from",
                "date_to",
                "salary_per_month",
                "nature_of_work",
                "reason_for_leaving",
            ]
        )
        for row in work:
            row["date_from"] = self._parsed_date(row["date_from"])
            row["date_to"] = self._parsed_date(row["date_to"])
            row["salary_per_month"] = self._float(row["salary_per_month"])
        family = self.family.rows(
            [
                "name",
                "date_of_birth",
                "relation",
                "residing_with_employee",
                "gender",
                "aadhaar_number",
            ]
        )
        for row in family:
            row["date_of_birth"] = self._parsed_date(row["date_of_birth"])
            raw = str(row["residing_with_employee"]).strip().casefold()
            row["residing_with_employee"] = (
                True if raw in {"yes", "y", "true", "1"} else False if raw else None
            )
        return {
            "registration_number": self.reg.text(),
            "registration_date": to_date(self.reg_date),
            "designation": self.designation.currentText(),
            "name": self.name.text(),
            "father_husband_name": self.father.text(),
            "date_of_birth": to_date(self.dob),
            "appointment_date": to_date(self.appointment),
            "age_years": self.age_years.value(),
            "age_months": self.age_months.value(),
            "age_manual_override": self.age_override.isChecked(),
            "mother_name": self.mother.text(),
            "mother_age": self.mother_age.value() or None,
            "place_of_birth": self.birth_place.text(),
            "gender": self.gender.currentText(),
            "marital_status": self.marital.currentText(),
            "nationality": self.nationality.text(),
            "blood_group": self.blood.text(),
            "identification_mark_1": self.mark1.text(),
            "identification_mark_2": self.mark2.text(),
            "armed_forces_experience": self.armed.text(),
            "armed_forces_years": self.armed_years.text(),
            "armed_forces_rank": self.armed_rank.text(),
            "gunman_details": self.gunman.text(),
            "gun_license_number": self.gun_license.text(),
            "gun_issuing_authority": self.gun_authority.text(),
            "gun_license_valid_to": to_date(self.gun_valid),
            "weapon_type": self.weapon.text(),
            "aadhaar_number": self.aadhaar.text(),
            "driving_license_number": self.driving.text(),
            "other_certification": self.certification.toPlainText(),
            "languages_known": self.languages.text(),
            "permanent_address": self.permanent.toPlainText(),
            "communication_address": self.communication.toPlainText(),
            "pan_number": self.pan.text(),
            "bank_name": self.bank.text(),
            "bank_branch": self.branch.text(),
            "bank_account_number": self.account.text(),
            "ifsc_code": self.ifsc.text(),
            "epfo_registered": self.epfo.isChecked(),
            "esic_registered": self.esic_registered.isChecked(),
            "uan_number": self.uan.text(),
            "esic_number": self.esic_no.text(),
            "contact_number": self.contact.text(),
            "alternate_contact_number": self.alternate.text(),
            "photo_source": self.photo_source,
            "work_experiences": work,
            "education_records": self.education.rows(
                [
                    "qualification",
                    "subject",
                    "year_of_passing",
                    "board_college_university",
                    "division_result",
                    "remarks",
                ]
            ),
            "nominees": self.nominees.rows(["name", "relation", "address", "mobile_number"]),
            "family_members": family,
        }

    def accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Required field", "Applicant Name is required.")
            self.setCurrentId(0)
            return
        try:
            self.saved_employee = self.context.employees.save(
                self.values(), self.employee.id if self.employee else None
            )
            self.context.excel.sync()
        except Exception as exc:
            QMessageBox.critical(self, "Unable to save registration", str(exc))
            return
        if self.photo_source and Path(self.photo_source).name == ".photo-crop.jpg":
            Path(self.photo_source).unlink(missing_ok=True)
        super().accept()

    def reject(self):
        answer = QMessageBox.question(
            self,
            "Discard incomplete registration?",
            "Closing now will permanently discard all unsaved information in this registration.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            super().reject()

    def _load(self, e):
        self.reg.setText(e.registration_number or "")
        set_date(self.reg_date, e.registration_date)
        self.designation.setCurrentText(e.designation or "")
        self.name.setText(e.name)
        self.father.setText(e.father_husband_name)
        set_date(self.dob, e.date_of_birth)
        set_date(self.appointment, e.appointment_date)
        self.age_override.setChecked(e.age_manual_override)
        self.age_years.setValue(e.age_years or 0)
        self.age_months.setValue(e.age_months or 0)
        self.mother.setText(e.mother_name)
        self.mother_age.setValue(e.mother_age or 0)
        self.birth_place.setText(e.place_of_birth)
        self.gender.setCurrentText(e.gender)
        self.marital.setCurrentText(e.marital_status)
        self.nationality.setText(e.nationality)
        self.blood.setText(e.blood_group)
        self.mark1.setText(e.identification_mark_1)
        self.mark2.setText(e.identification_mark_2)
        self.armed.setText(e.armed_forces_experience)
        self.armed_years.setText(e.armed_forces_years)
        self.armed_rank.setText(e.armed_forces_rank)
        self.gunman.setText(e.gunman_details)
        self.gun_license.setText(e.gun_license_number)
        self.gun_authority.setText(e.gun_issuing_authority)
        set_date(self.gun_valid, e.gun_license_valid_to)
        self.weapon.setText(e.weapon_type)
        self.certification.setPlainText(e.other_certification)
        self.languages.setText(e.languages_known)
        self.permanent.setPlainText(e.permanent_address)
        self.communication.setPlainText(e.communication_address)
        self.pan.setText(e.pan_number)
        self.aadhaar.setText(e.aadhaar_number or "")
        self.driving.setText(e.driving_license_number)
        self.bank.setText(e.bank_name)
        self.branch.setText(e.bank_branch)
        self.account.setText(e.bank_account_number)
        self.ifsc.setText(e.ifsc_code)
        self.epfo.setChecked(e.epfo_registered)
        self.esic_registered.setChecked(e.esic_registered)
        self.uan.setText(e.uan_number or "")
        self.esic_no.setText(e.esic_number or "")
        self.contact.setText(e.contact_number)
        self.alternate.setText(e.alternate_contact_number)
        self.work.load(
            e.work_experiences,
            [
                "employer_name_address",
                "rank_post",
                "date_from",
                "date_to",
                "salary_per_month",
                "nature_of_work",
                "reason_for_leaving",
            ],
        )
        self.education.load(
            e.education_records,
            [
                "qualification",
                "subject",
                "year_of_passing",
                "board_college_university",
                "division_result",
                "remarks",
            ],
        )
        self.nominees.load(e.nominees, ["name", "relation", "address", "mobile_number"])
        self.family.load(
            e.family_members,
            [
                "name",
                "date_of_birth",
                "relation",
                "residing_with_employee",
                "gender",
                "aadhaar_number",
            ],
        )
        if e.photo_path:
            path = self.context.catalog.folder_for(self.context.organisation) / e.photo_path
            if path.exists():
                self.photo_label.setPixmap(
                    QPixmap(str(path)).scaled(
                        self.photo_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                )
