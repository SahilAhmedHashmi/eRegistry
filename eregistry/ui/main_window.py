from __future__ import annotations

import calendar
import json
import os
import shutil
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..app_state import AppContext
from ..catalog import Organisation
from ..constants import DEFAULT_KPI_WEIGHTS, LABOUR_CATEGORIES
from ..database import DatabaseManager, organisation_db_key
from ..models import AppSetting, AuditLog, RateCard
from ..services.analytics_service import AnalyticsService
from ..services.backup_service import BackupService
from ..services.employee_service import EmployeeService
from ..services.excel_service import ExcelSyncError
from ..services.import_service import ExcelImportService, TARGET_FIELDS
from ..services.report_service import AnalyticsReportService
from .dialogs import OrganisationDialog
from .employee_wizard import EmployeeWizard


def money(value) -> str:
    return f"₹{float(value or 0):,.0f}"


def item(value="", editable=False) -> QTableWidgetItem:
    result = QTableWidgetItem("" if value is None else str(value))
    if not editable:
        result.setFlags(result.flags() & ~Qt.ItemIsEditable)
    return result


class MetricCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        self.title = QLabel(title)
        self.title.setStyleSheet("color:#64748b")
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size:22pt;font-weight:700")
        layout.addWidget(self.title)
        layout.addWidget(self.value)


class StatusDialog(QDialog):
    def __init__(self, employee, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change employee status")
        form = QFormLayout(self)
        self.status = QComboBox()
        self.status.addItems(["Active", "Inactive"])
        self.status.setCurrentText(employee.status)
        self.exit_date = QDateEdit(QDate.currentDate())
        self.exit_date.setCalendarPopup(True)
        self.exit_date.setDisplayFormat("dd-MM-yyyy")
        self.reason = QTextEdit(employee.exit_reason or "")
        self.reason.setMaximumHeight(80)
        form.addRow("Status", self.status)
        form.addRow("Exit date", self.exit_date)
        form.addRow("Exit reason", self.reason)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self):
        value = self.exit_date.date()
        return (
            self.status.currentText(),
            date(value.year(), value.month(), value.day()),
            self.reason.toPlainText().strip(),
        )


class TransferDialog(QDialog):
    def __init__(
        self,
        organisations: list[Organisation],
        current: Organisation,
        registration: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Copy employee to another organisation")
        form = QFormLayout(self)
        self.organisation = QComboBox()
        for org in organisations:
            if org.id != current.id:
                self.organisation.addItem(org.name, org.id)
        self.registration = QLineEdit(registration or "")
        form.addRow("Destination", self.organisation)
        form.addRow("Registration No. in destination", self.registration)
        note = QLabel(
            "The original record stays in this organisation. Duplicate identifiers in the destination are blocked."
        )
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class RateCardsDialog(QDialog):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("Default wage and billing rates")
        self.resize(650, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Defaults apply when a new salary month is created. Employee and monthly values can override them."
            )
        )
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Category / Designation", "Daily Wage", "Client Billing Rate"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        with context.db.session() as session:
            cards = list(session.query(RateCard).order_by(RateCard.designation))
        if not cards:
            cards = [
                RateCard(designation=x, daily_wage=0, client_billing_rate=0)
                for x in LABOUR_CATEGORIES
            ]
        for card in cards:
            self._add(card.designation, card.daily_wage, card.client_billing_rate)
        row = QHBoxLayout()
        add = QPushButton("Add category")
        add.clicked.connect(lambda: self._add("", 0, 0))
        row.addWidget(add)
        row.addStretch()
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add(self, name, wage, billing):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, value in enumerate((name, wage, billing)):
            self.table.setItem(r, c, QTableWidgetItem(str(value or "")))

    def _save(self):
        try:
            for r in range(self.table.rowCount()):
                name = self.table.item(r, 0).text().strip()
                if name:
                    self.context.payroll.save_rate_card(
                        name,
                        float(self.table.item(r, 1).text() or 0),
                        float(self.table.item(r, 2).text() or 0),
                    )
        except Exception as exc:
            QMessageBox.warning(self, "Invalid rate", str(exc))
            return
        self.accept()


class RedeploymentWeightsDialog(QDialog):
    def __init__(self, weights: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Redeployability weights")
        form = QFormLayout(self)
        self.inputs = {}
        labels = {
            "performance": "Recent performance",
            "attendance": "Attendance consistency",
            "skill_fit": "Skill/category fit",
            "overtime": "Moderate overtime",
        }
        for key, label in labels.items():
            box = QSpinBox()
            box.setRange(0, 100)
            box.setSuffix("%")
            box.setValue(round(weights[key] * 100))
            self.inputs[key] = box
            form.addRow(label, box)
        form.addRow(QLabel("Weights must total 100%. The score shows every component."))
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _submit(self):
        if sum(box.value() for box in self.inputs.values()) != 100:
            QMessageBox.warning(
                self,
                "Weights must total 100%",
                "Adjust the four weights so their total is exactly 100%.",
            )
            return
        self.accept()

    def values(self):
        return {key: box.value() / 100 for key, box in self.inputs.items()}


class RegistrationOutputDialog(QDialog):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle("Registration form ready")
        layout = QVBoxLayout(self)
        label = QLabel(f"The registration PDF is ready.\n\n{path}")
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)
        row = QHBoxLayout()
        preview = QPushButton("Preview")
        save = QPushButton("Save a copy…")
        print_button = QPushButton("Print")
        close = QPushButton("Close")
        preview.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        save.clicked.connect(self._save_copy)
        print_button.clicked.connect(self._print)
        close.clicked.connect(self.accept)
        for button in (preview, save, print_button, close):
            row.addWidget(button)
        layout.addLayout(row)

    def _save_copy(self):
        destination, _ = QFileDialog.getSaveFileName(
            self, "Save registration PDF", self.path.name, "PDF (*.pdf)"
        )
        if destination:
            shutil.copy2(self.path, destination)
            QMessageBox.information(self, "PDF saved", f"Saved to:\n{destination}")

    def _print(self):
        if os.name != "nt":
            QMessageBox.information(
                self,
                "Printing on Windows",
                "The packaged Windows application sends this PDF to the default PDF print handler.",
            )
            return
        try:
            os.startfile(str(self.path), "print")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Unable to print",
                f"Windows could not send the PDF to the printer. Preview it and print from the PDF viewer instead.\n\n{exc}",
            )


class ImportDialog(QDialog):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.service = ExcelImportService(context.employees)
        self.path = None
        self.setWindowTitle("Guided Excel import")
        self.resize(760, 620)
        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        self.source = QLineEdit()
        self.source.setReadOnly(True)
        browse = QPushButton("Choose workbook…")
        browse.clicked.connect(self._browse)
        source_row.addWidget(self.source)
        source_row.addWidget(browse)
        layout.addLayout(source_row)
        self.sheet = QComboBox()
        self.sheet.currentTextChanged.connect(self._load_sheet)
        layout.addWidget(self.sheet)
        layout.addWidget(
            QLabel("Map each eRegistry field to a source column. Only Name is required.")
        )
        self.mapping = QTableWidget(len(TARGET_FIELDS), 2)
        self.mapping.setHorizontalHeaderLabels(["eRegistry field", "Excel column"])
        self.mapping.horizontalHeader().setStretchLastSection(True)
        for r, label in enumerate(TARGET_FIELDS):
            self.mapping.setItem(r, 0, item(label))
            self.mapping.setCellWidget(r, 1, QComboBox())
        layout.addWidget(self.mapping)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Import")
        buttons.accepted.connect(self._run)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Import employees", "", "Excel workbooks (*.xlsx *.xlsm)"
        )
        if not name:
            return
        self.path = Path(name)
        self.source.setText(name)
        try:
            sheets, selected, _, _ = self.service.inspect(self.path)
        except Exception as exc:
            QMessageBox.critical(self, "Cannot read workbook", str(exc))
            return
        self.sheet.blockSignals(True)
        self.sheet.clear()
        self.sheet.addItems(sheets)
        self.sheet.setCurrentText(selected)
        self.sheet.blockSignals(False)
        self._load_sheet(selected)

    def _load_sheet(self, sheet):
        if not self.path or not sheet:
            return
        try:
            _, _, headers, _ = self.service.inspect(self.path, sheet)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot read sheet", str(exc))
            return
        for r, label in enumerate(TARGET_FIELDS):
            combo = self.mapping.cellWidget(r, 1)
            combo.clear()
            combo.addItem("")
            combo.addItems(headers)
            candidates = {
                label.casefold(),
                label.replace("Number", "No.").casefold(),
                label.replace("Current ", "").casefold(),
            }
            for h in headers:
                if h.casefold() in candidates:
                    combo.setCurrentText(h)
                    break

    def _run(self):
        if not self.path:
            QMessageBox.warning(self, "Choose a workbook", "Choose an Excel workbook first.")
            return
        mapping = {
            self.mapping.item(r, 0).text(): self.mapping.cellWidget(r, 1).currentText()
            for r in range(self.mapping.rowCount())
        }
        if not mapping.get("Name"):
            QMessageBox.warning(
                self, "Name mapping required", "Map the Name field before importing."
            )
            return

        def conflict(existing, values):
            answer = QMessageBox.question(
                self,
                "Existing employee",
                f"{existing.name} matches this row. Update the existing record?\n\nChoose No to skip this row.",
                QMessageBox.Yes | QMessageBox.No,
            )
            return "update" if answer == QMessageBox.Yes else "skip"

        result = self.service.import_rows(self.path, self.sheet.currentText(), mapping, conflict)
        try:
            self.context.excel.sync()
        except ExcelSyncError as exc:
            QMessageBox.warning(self, "Imported; Excel sync pending", str(exc))
        QMessageBox.information(
            self,
            "Import complete",
            f"Created: {result['created']}\nUpdated: {result['updated']}\nSkipped: {result['skipped']}\nErrors: {len(result['errors'])}"
            + (("\n\n" + "\n".join(result["errors"][:8])) if result["errors"] else ""),
        )
        self.accept()


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self.settings = QSettings(str(context.root / "settings.ini"), QSettings.IniFormat)
        self.current_payroll_id = None
        self.setWindowTitle("eRegistry — Offline Labour Management")
        self.resize(1440, 880)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        header = QHBoxLayout()
        brand = QLabel("eRegistry")
        brand.setStyleSheet("font-size:22pt;font-weight:800")
        self.org_combo = QComboBox()
        self.org_combo.setMinimumWidth(300)
        self.org_combo.currentIndexChanged.connect(self._switch_organisation)
        create_org = QPushButton("New organisation")
        create_org.clicked.connect(self._new_organisation)
        self.theme = QComboBox()
        self.theme.addItems(["Light", "Dark"])
        self.theme.setCurrentText(self.settings.value("theme", "Light"))
        self.theme.currentTextChanged.connect(self._theme_changed)
        logout = QPushButton("Log out")
        logout.setProperty("secondary", True)
        logout.clicked.connect(self.logout_requested)
        header.addWidget(brand)
        header.addStretch()
        header.addWidget(QLabel("Organisation:"))
        header.addWidget(self.org_combo)
        header.addWidget(create_org)
        header.addWidget(self.theme)
        header.addWidget(logout)
        outer.addLayout(header)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        self._build_dashboard()
        self._build_employees()
        self._build_payroll()
        self._build_analytics()
        self._build_tools()
        self._reload_organisations()

    def _build_dashboard(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Dashboard scope:"))
        self.dashboard_scope = QComboBox()
        self.dashboard_scope.addItems(["Current organisation", "All organisations"])
        self.dashboard_scope.currentTextChanged.connect(self._refresh_dashboard)
        scope_row.addWidget(self.dashboard_scope)
        scope_row.addStretch()
        layout.addLayout(scope_row)
        grid = QGridLayout()
        self.cards = {}
        labels = [
            ("total_employees", "Employees"),
            ("active_employees", "Active"),
            ("recent_registrations", "Registered in 30 days"),
            ("salary_expenditure", "Salary expenditure"),
            ("revenue", "Client revenue"),
            ("profit_margin", "Profit margin"),
            ("overtime_hours", "Overtime hours"),
            ("incomplete_records", "Incomplete records"),
        ]
        for i, (key, title) in enumerate(labels):
            card = MetricCard(title)
            self.cards[key] = card
            grid.addWidget(card, i // 4, i % 4)
        layout.addLayout(grid)
        self.dashboard_details = QLabel()
        self.dashboard_details.setWordWrap(True)
        self.dashboard_details.setAlignment(Qt.AlignTop)
        self.dashboard_details.setStyleSheet("font-size:11pt;padding:16px")
        layout.addWidget(self.dashboard_details)
        layout.addStretch()
        self.tabs.addTab(page, "Dashboard")

    def _build_employees(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, registration no., Aadhaar or UAN…")
        self.search.textChanged.connect(self.refresh_employees)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Active", "Inactive"])
        self.status_filter.currentTextChanged.connect(self.refresh_employees)
        new = QPushButton("New registration")
        new.clicked.connect(self._new_employee)
        edit = QPushButton("Edit")
        edit.clicked.connect(self._edit_employee)
        status = QPushButton("Active / Inactive")
        status.clicked.connect(self._status_employee)
        transfer = QPushButton("Copy to organisation")
        transfer.clicked.connect(self._transfer_employee)
        pdf = QPushButton("Registration PDF")
        pdf.clicked.connect(self._pdf_employee)
        delete = QPushButton("Delete")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_employee)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.status_filter)
        tools.addWidget(new)
        tools.addWidget(edit)
        tools.addWidget(status)
        tools.addWidget(transfer)
        tools.addWidget(pdf)
        tools.addWidget(delete)
        layout.addLayout(tools)
        self.employee_table = QTableWidget(0, 9)
        self.employee_table.setHorizontalHeaderLabels(
            ["ID", "Reg No.", "Name", "Designation", "Status", "Mobile", "Aadhaar", "UAN", "ESIC"]
        )
        self.employee_table.setColumnHidden(0, True)
        self.employee_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.employee_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.employee_table.doubleClicked.connect(self._edit_employee)
        self.employee_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.employee_table)
        self.tabs.addTab(page, "Employees")

    def _build_payroll(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        tools = QHBoxLayout()
        self.payroll_month = QComboBox()
        self.payroll_month.currentIndexChanged.connect(self._load_payroll)
        create = QPushButton("Create / open month")
        create.clicked.connect(self._create_payroll)
        save = QPushButton("Save entries")
        save.clicked.connect(self._save_payroll)
        self.payroll_lock = QPushButton("Complete and lock")
        self.payroll_lock.clicked.connect(self._toggle_payroll_lock)
        rates = QPushButton("Default rates")
        rates.clicked.connect(
            lambda: RateCardsDialog(self.context, self).exec()
            if self.context.organisation
            else None
        )
        tools.addWidget(self.payroll_month)
        tools.addWidget(create)
        tools.addWidget(save)
        tools.addWidget(self.payroll_lock)
        tools.addWidget(rates)
        tools.addStretch()
        layout.addLayout(tools)
        headers = [
            "Entry ID",
            "Include",
            "Employee",
            "Working Days",
            "OT Hours",
            "PH Days",
            "Wage/Day",
            "Working Wages*",
            "OT/PH Wages",
            "Bonus",
            "Gross*",
            "EPF",
            "ESIC",
            "Advance",
            "Total Deduction*",
            "Net*",
            "Billing Rate",
            "Revenue",
            "Rating 1–5",
            "Performance Notes",
        ]
        self.payroll_table = QTableWidget(0, len(headers))
        self.payroll_table.setHorizontalHeaderLabels(headers)
        self.payroll_table.setColumnHidden(0, True)
        self.payroll_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.payroll_table)
        meta = QHBoxLayout()
        self.client_rating = QSpinBox()
        self.client_rating.setRange(0, 5)
        self.client_notes = QLineEdit()
        self.employer_cost = QDoubleSpinBox()
        self.statutory_cost = QDoubleSpinBox()
        self.operational_cost = QDoubleSpinBox()
        for box in (self.employer_cost, self.statutory_cost, self.operational_cost):
            box.setRange(0, 1_000_000_000)
            box.setDecimals(2)
        meta.addWidget(QLabel("Client rating"))
        meta.addWidget(self.client_rating)
        meta.addWidget(QLabel("Notes"))
        meta.addWidget(self.client_notes, 1)
        meta.addWidget(QLabel("Employer costs"))
        meta.addWidget(self.employer_cost)
        meta.addWidget(QLabel("Statutory"))
        meta.addWidget(self.statutory_cost)
        meta.addWidget(QLabel("Operational"))
        meta.addWidget(self.operational_cost)
        layout.addLayout(meta)
        layout.addWidget(
            QLabel(
                "*Calculated automatically. Editing a calculated value requests confirmation and records a salary override in the audit log."
            )
        )
        self.tabs.addTab(page, "Monthly Salary")

    def _build_analytics(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        top = QHBoxLayout()
        self.required_category = QComboBox()
        self.required_category.setEditable(True)
        self.required_category.addItems(LABOUR_CATEGORIES)
        rank = QPushButton("Rank redeployment candidates")
        rank.clicked.connect(self._rank_redeployment)
        weights = QPushButton("Configure weights")
        weights.clicked.connect(self._configure_redeployment_weights)
        pdf = QPushButton("Export KPI PDF")
        pdf.clicked.connect(lambda: self._export_report("pdf"))
        excel = QPushButton("Export KPI Excel")
        excel.clicked.connect(lambda: self._export_report("xlsx"))
        top.addWidget(QLabel("Destination required category:"))
        top.addWidget(self.required_category)
        top.addWidget(rank)
        top.addWidget(weights)
        top.addStretch()
        top.addWidget(pdf)
        top.addWidget(excel)
        layout.addLayout(top)
        self.analytics_note = QLabel(
            "Scores use the last three completed months available. New employees are assessed on available history and marked Limited history."
        )
        self.analytics_note.setWordWrap(True)
        layout.addWidget(self.analytics_note)
        self.redeploy_table = QTableWidget(0, 10)
        self.redeploy_table.setHorizontalHeaderLabels(
            [
                "Rank",
                "Employee",
                "Category",
                "Score",
                "Performance",
                "Attendance",
                "Skill Fit",
                "Overtime",
                "Months",
                "Flags",
            ]
        )
        self.redeploy_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.redeploy_table)
        self.tabs.addTab(page, "Analytics & Redeployment")

    def _build_tools(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        actions = [
            ("Open automatically updated Excel workbook", self._open_excel),
            ("Sync Excel now", self._sync_excel),
            ("Import employees from Excel", self._import_excel),
            ("Create complete backup", self._backup),
            ("Restore backup (safety copy first)", self._restore),
            (
                "Open data folder",
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.context.root))),
            ),
            ("View activity log", self._audit_log),
        ]
        for title, callback in actions:
            button = QPushButton(title)
            button.clicked.connect(callback)
            layout.addWidget(button)
        layout.addStretch()
        self.tabs.addTab(page, "Tools & Backup")

    def _reload_organisations(self, select_id=None):
        self.org_combo.blockSignals(True)
        self.org_combo.clear()
        for org in self.context.catalog.list():
            self.org_combo.addItem(org.name, org.id)
        self.org_combo.blockSignals(False)
        if self.org_combo.count() == 0:
            self._new_organisation()
            return
        if select_id:
            index = self.org_combo.findData(select_id)
            self.org_combo.setCurrentIndex(max(0, index))
        self._switch_organisation(self.org_combo.currentIndex())

    def _new_organisation(self):
        dialog = OrganisationDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            org = self.context.create_organisation(**dialog.values)
        except Exception as exc:
            QMessageBox.critical(self, "Cannot create organisation", str(exc))
            return
        self._reload_organisations(org.id)

    def _switch_organisation(self, index):
        if index < 0:
            return
        oid = self.org_combo.itemData(index)
        org = next((x for x in self.context.catalog.list() if x.id == oid), None)
        if not org:
            return
        try:
            self.context.open_organisation(org)
        except Exception as exc:
            QMessageBox.critical(self, "Cannot open organisation", str(exc))
            return
        self.refresh_all()

    def refresh_all(self):
        self.refresh_employees()
        self._refresh_dashboard()
        self._refresh_months()

    def refresh_employees(self):
        if not self.context.employees:
            return
        rows = self.context.employees.list(self.search.text(), self.status_filter.currentText())
        self.employee_table.setRowCount(0)
        for employee in rows:
            r = self.employee_table.rowCount()
            self.employee_table.insertRow(r)
            for c, value in enumerate(
                (
                    employee.id,
                    employee.registration_number,
                    employee.name,
                    employee.designation,
                    employee.status,
                    employee.contact_number,
                    employee.aadhaar_number,
                    employee.uan_number,
                    employee.esic_number,
                )
            ):
                self.employee_table.setItem(r, c, item(value))
        self.employee_table.resizeColumnsToContents()

    def _selected_employee(self):
        row = self.employee_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select an employee", "Select an employee row first.")
            return None
        return self.context.employees.get(int(self.employee_table.item(row, 0).text()))

    def _new_employee(self):
        if EmployeeWizard(self.context, parent=self).exec() == QDialog.Accepted:
            self.refresh_all()

    def _edit_employee(self):
        employee = self._selected_employee()
        if employee and EmployeeWizard(self.context, employee, self).exec() == QDialog.Accepted:
            self.refresh_all()

    def _status_employee(self):
        employee = self._selected_employee()
        if not employee:
            return
        dialog = StatusDialog(employee, self)
        if dialog.exec() != QDialog.Accepted:
            return
        status, exit_date, reason = dialog.values()
        self.context.employees.set_status(employee.id, status, exit_date, reason)
        self._sync_excel(silent=True)
        self.refresh_all()

    def _delete_employee(self):
        employee = self._selected_employee()
        if not employee:
            return
        if (
            QMessageBox.warning(
                self,
                "Permanently delete?",
                f"Delete {employee.name} permanently? This cannot be undone except by restoring a backup.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        try:
            self.context.employees.delete(employee.id)
            self.context.excel.sync()
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))
            return
        self.refresh_all()

    def _transfer_employee(self):
        employee = self._selected_employee()
        organisations = self.context.catalog.list()
        if not employee:
            return
        if len(organisations) < 2:
            QMessageBox.information(self, "No destination", "Create another organisation first.")
            return
        dialog = TransferDialog(
            organisations, self.context.organisation, employee.registration_number or "", self
        )
        if dialog.exec() != QDialog.Accepted:
            return
        destination = next(x for x in organisations if x.id == dialog.organisation.currentData())
        folder = self.context.catalog.folder_for(destination)
        db = DatabaseManager(
            folder / "eregistry.db", organisation_db_key(self.context.master_key, destination.id)
        )
        try:
            db.initialize(
                {
                    "external_id": destination.id,
                    "name": destination.name,
                    "address": destination.address,
                    "contact_person": destination.contact_person,
                    "phone": destination.phone,
                    "email": destination.email,
                }
            )
            service = EmployeeService(db, folder)
            self.context.employees.copy_to(
                employee.id, service, dialog.registration.text().strip() or None
            )
            from ..services.excel_service import ExcelService

            ExcelService(db, destination, folder).sync()
        except Exception as exc:
            QMessageBox.critical(self, "Copy failed", str(exc))
            return
        finally:
            db.close()
        QMessageBox.information(
            self,
            "Employee copied",
            f"{employee.name} was copied to {destination.name}. The original remains unchanged.",
        )

    def _pdf_employee(self):
        employee = self._selected_employee()
        if not employee:
            return
        try:
            path = self.context.pdf.generate(employee)
        except Exception as exc:
            QMessageBox.critical(self, "PDF failed", str(exc))
            return
        RegistrationOutputDialog(path, self).exec()

    def _refresh_dashboard(self):
        if not self.context.analytics:
            return
        all_organisations = self.dashboard_scope.currentText() == "All organisations"
        if all_organisations:
            s, financials = self._all_organisation_summary()
        else:
            s = self.context.analytics.summary()
            financials = self.context.analytics.category_financials()
        for key, card in self.cards.items():
            value = s[key]
            if key in {"salary_expenditure", "revenue"}:
                value = money(value)
            elif key == "profit_margin":
                value = f"{value:.1f}%"
            elif key == "overtime_hours":
                value = f"{value:,.1f} h"
            card.value.setText(str(value))
        categories = (
            ", ".join(f"{k}: {v}" for k, v in sorted(s["categories"].items())) or "No employees yet"
        )
        gender = ", ".join(f"{k}: {v}" for k, v in sorted(s["gender"].items())) or "No data"
        best = max(financials, key=lambda x: x["revenue"], default=None)
        extra = (
            f"<br><b>Highest-revenue skill category:</b> {best['category']} ({money(best['revenue'])})"
            if best
            else ""
        )
        self.dashboard_details.setText(
            f"<b>Scope:</b> {'All organisations' if all_organisations else self.context.organisation.name}<br><br>"
            f"<b>Employees by skill/designation:</b> {categories}<br><br><b>Gender breakdown:</b> {gender}<br><br>"
            f"<b>EPFO registered:</b> {s['epfo_registered']} &nbsp;&nbsp; <b>ESIC registered:</b> {s['esic_registered']}{extra}"
        )

    def _all_organisation_summary(self):
        totals = {
            "total_employees": 0,
            "active_employees": 0,
            "recent_registrations": 0,
            "salary_expenditure": 0.0,
            "revenue": 0.0,
            "profit": 0.0,
            "overtime_hours": 0.0,
            "incomplete_records": 0,
            "epfo_registered": 0,
            "esic_registered": 0,
        }
        categories = Counter()
        gender = Counter()
        category_financials = {}
        for organisation in self.context.catalog.list():
            temporary = None
            if organisation.id == self.context.organisation.id:
                analytics = self.context.analytics
            else:
                folder = self.context.catalog.folder_for(organisation)
                temporary = DatabaseManager(
                    folder / "eregistry.db",
                    organisation_db_key(self.context.master_key, organisation.id),
                )
                temporary.initialize(
                    {
                        "external_id": organisation.id,
                        "name": organisation.name,
                        "address": organisation.address,
                        "contact_person": organisation.contact_person,
                        "phone": organisation.phone,
                        "email": organisation.email,
                    }
                )
                analytics = AnalyticsService(temporary)
            summary = analytics.summary()
            for key in totals:
                totals[key] += summary[key]
            categories.update(summary["categories"])
            gender.update(summary["gender"])
            for row in analytics.category_financials():
                combined = category_financials.setdefault(
                    row["category"],
                    {"category": row["category"], "salary": 0.0, "revenue": 0.0, "profit": 0.0},
                )
                for key in ("salary", "revenue", "profit"):
                    combined[key] += row[key]
            if temporary:
                temporary.close()
        totals["categories"] = dict(categories)
        totals["gender"] = dict(gender)
        totals["profit_margin"] = (
            totals["profit"] / totals["revenue"] * 100 if totals["revenue"] else 0
        )
        return totals, list(category_financials.values())

    def _refresh_months(self):
        self.payroll_month.blockSignals(True)
        self.payroll_month.clear()
        for month in self.context.payroll.list_months():
            self.payroll_month.addItem(
                f"{calendar.month_name[month.month]} {month.year} — {month.status}", month.id
            )
        self.payroll_month.blockSignals(False)
        self._load_payroll(self.payroll_month.currentIndex())

    def _create_payroll(self):
        year, ok = QInputDialog.getInt(self, "Salary year", "Year", datetime.now().year, 2000, 2200)
        if not ok:
            return
        month, ok = QInputDialog.getItem(
            self,
            "Salary month",
            "Month",
            list(calendar.month_name)[1:],
            datetime.now().month - 1,
            False,
        )
        if not ok:
            return
        payroll = self.context.payroll.get_or_create_month(
            year, list(calendar.month_name).index(month)
        )
        self._sync_excel(silent=True)
        self._refresh_months()
        index = self.payroll_month.findData(payroll.id)
        self.payroll_month.setCurrentIndex(index)

    def _load_payroll(self, index):
        self.payroll_table.setRowCount(0)
        self.current_payroll_id = self.payroll_month.itemData(index) if index >= 0 else None
        if not self.current_payroll_id:
            return
        month = self.context.payroll.get_month(self.current_payroll_id)
        editable = month.status != "Completed"
        self.payroll_lock.setText("Complete and lock" if editable else "Reopen for editing")
        for entry in month.entries:
            r = self.payroll_table.rowCount()
            self.payroll_table.insertRow(r)
            values = [
                entry.id,
                entry.included,
                entry.employee.name,
                entry.working_days,
                entry.ot_hours,
                entry.ph_days,
                entry.wages_per_day,
                entry.working_day_wages,
                entry.ot_ph_wages,
                entry.bonus,
                entry.gross_salary,
                entry.epf_deduction,
                entry.esic_deduction,
                entry.advance,
                entry.total_deduction,
                entry.net_salary,
                entry.client_billing_rate,
                entry.billed_revenue,
                entry.performance_rating or "",
                entry.performance_notes,
            ]
            self.payroll_table.setItem(r, 0, item(entry.id))
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked if entry.included else Qt.Unchecked)
            self.payroll_table.setItem(r, 1, check)
            for c in range(2, len(values)):
                self.payroll_table.setItem(r, c, item(values[c], editable and c not in {2, 17}))
        self.payroll_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
            if editable
            else QAbstractItemView.NoEditTriggers
        )
        self.client_rating.setValue(month.client_satisfaction_rating or 0)
        self.client_notes.setText(month.client_satisfaction_notes or "")
        self.employer_cost.setValue(month.employer_costs)
        self.statutory_cost.setValue(month.statutory_costs)
        self.operational_cost.setValue(month.operational_costs)

    def _save_payroll(self):
        if not self.current_payroll_id:
            return
        month = self.context.payroll.get_month(self.current_payroll_id)
        if month.status == "Completed":
            QMessageBox.warning(self, "Month locked", "Reopen this month before editing.")
            return
        calculated_columns = {
            7: "working_day_wages",
            10: "gross_salary",
            14: "total_deduction",
            15: "net_salary",
        }
        override_needed = False
        prepared = []
        fields = {
            3: "working_days",
            4: "ot_hours",
            5: "ph_days",
            6: "wages_per_day",
            7: "working_day_wages",
            8: "ot_ph_wages",
            9: "bonus",
            10: "gross_salary",
            11: "epf_deduction",
            12: "esic_deduction",
            13: "advance",
            14: "total_deduction",
            15: "net_salary",
            16: "client_billing_rate",
            18: "performance_rating",
            19: "performance_notes",
        }
        try:
            for r in range(self.payroll_table.rowCount()):
                values = {"included": self.payroll_table.item(r, 1).checkState() == Qt.Checked}
                overrides = set()
                for c, field in fields.items():
                    raw = self.payroll_table.item(r, c).text().strip()
                    if field == "performance_notes":
                        values[field] = raw
                    elif field == "performance_rating":
                        values[field] = int(raw) if raw else None
                    else:
                        values[field] = float(raw.replace(",", "") or 0)
                base = {**values}
                from ..services.payroll_service import calculate_entry

                automatic = calculate_entry(base)
                for c, field in calculated_columns.items():
                    if abs(values[field] - automatic[field]) > 0.001:
                        overrides.add(field)
                        override_needed = True
                prepared.append((int(self.payroll_table.item(r, 0).text()), values, overrides))
        except ValueError as exc:
            QMessageBox.warning(
                self, "Invalid salary value", f"Use numbers in salary fields. {exc}"
            )
            return
        if (
            override_needed
            and QMessageBox.question(
                self,
                "Confirm salary override",
                "One or more calculated values were changed manually. Save and record these overrides in the activity log?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        try:
            for entry_id, values, overrides in prepared:
                self.context.payroll.save_entry(entry_id, values, overrides)
            self.context.payroll.update_month_metadata(
                self.current_payroll_id,
                self.client_rating.value() or None,
                self.client_notes.text(),
                self.employer_cost.value(),
                self.statutory_cost.value(),
                self.operational_cost.value(),
            )
            self.context.excel.sync()
        except Exception as exc:
            QMessageBox.critical(self, "Salary save failed", str(exc))
            return
        self._load_payroll(self.payroll_month.currentIndex())
        self._refresh_dashboard()
        QMessageBox.information(
            self,
            "Salary saved",
            "The encrypted database and organisation Excel workbook are updated.",
        )

    def _toggle_payroll_lock(self):
        if not self.current_payroll_id:
            return
        month = self.context.payroll.get_month(self.current_payroll_id)
        if month.status == "Completed":
            if (
                QMessageBox.question(
                    self,
                    "Reopen completed month?",
                    "Reopening allows changes and is recorded in the activity log. Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                != QMessageBox.Yes
            ):
                return
            self.context.payroll.reopen(month.id)
        else:
            if (
                QMessageBox.question(
                    self,
                    "Complete and lock month?",
                    "Save your entries first. Lock this salary sheet against further editing?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                != QMessageBox.Yes
            ):
                return
            self.context.payroll.complete(month.id)
        self._sync_excel(silent=True)
        self._refresh_months()
        self._refresh_dashboard()

    def _rank_redeployment(self):
        rows = self.context.analytics.redeployability(
            self.required_category.currentText(), self._redeployment_weights()
        )
        self.redeploy_table.setRowCount(0)
        for rank, row in enumerate(rows, 1):
            r = self.redeploy_table.rowCount()
            self.redeploy_table.insertRow(r)
            flags = ", ".join(
                x
                for x in (
                    "Limited history" if row["limited_history"] else "",
                    "High overtime" if row["high_overtime"] else "",
                )
                if x
            )
            for c, value in enumerate(
                (
                    rank,
                    row["name"],
                    row["designation"],
                    row["score"],
                    row["performance"],
                    row["attendance"],
                    row["skill_fit"],
                    row["overtime"],
                    row["months"],
                    flags,
                )
            ):
                self.redeploy_table.setItem(r, c, item(value))
        self.redeploy_table.resizeColumnsToContents()

    def _redeployment_weights(self):
        with self.context.db.session() as session:
            setting = session.get(AppSetting, "redeployment_weights")
            if not setting:
                return dict(DEFAULT_KPI_WEIGHTS)
            try:
                values = json.loads(setting.value)
                if (
                    set(values) == set(DEFAULT_KPI_WEIGHTS)
                    and abs(sum(values.values()) - 1) < 0.001
                ):
                    return values
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        return dict(DEFAULT_KPI_WEIGHTS)

    def _configure_redeployment_weights(self):
        dialog = RedeploymentWeightsDialog(self._redeployment_weights(), self)
        if dialog.exec() != QDialog.Accepted:
            return
        with self.context.db.session() as session:
            setting = session.get(AppSetting, "redeployment_weights") or AppSetting(
                key="redeployment_weights"
            )
            setting.value = json.dumps(dialog.values(), sort_keys=True)
            session.add(setting)
            session.commit()
        self._rank_redeployment()

    def _export_report(self, kind):
        if not self.context.organisation:
            return
        suffix = ".pdf" if kind == "pdf" else ".xlsx"
        name = f"{self.context.organisation.name}_KPI_Report{suffix}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export KPI report",
            str(self.context.root / "reports" / name),
            "PDF (*.pdf)" if kind == "pdf" else "Excel (*.xlsx)",
        )
        if not path:
            return
        report = AnalyticsReportService(self.context.organisation.name, self.context.analytics)
        try:
            report.export_pdf(Path(path)) if kind == "pdf" else report.export_excel(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _sync_excel(self, checked=False, silent=False):
        if not self.context.excel:
            return
        try:
            path = self.context.excel.sync()
        except Exception as exc:
            QMessageBox.warning(self, "Excel sync failed", str(exc))
            return
        if not silent:
            QMessageBox.information(self, "Excel updated", f"Workbook updated:\n{path}")

    def _open_excel(self):
        self._sync_excel(silent=True)
        if self.context.excel:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.context.excel.workbook_path)))

    def _import_excel(self):
        if ImportDialog(self.context, self).exec() == QDialog.Accepted:
            self.refresh_all()

    def _backup(self):
        default = (
            self.context.root / "backups" / f"eRegistry_{datetime.now():%Y%m%d_%H%M}.eregbackup"
        )
        name, _ = QFileDialog.getSaveFileName(
            self, "Create eRegistry backup", str(default), "eRegistry Backup (*.eregbackup)"
        )
        if not name:
            return
        try:
            path = BackupService(self.context.root).create(Path(name))
        except Exception as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))
            return
        self.settings.setValue("last_backup", datetime.now().isoformat())
        QMessageBox.information(self, "Backup complete", f"Complete backup saved to:\n{path}")

    def _restore(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Restore eRegistry backup", "", "eRegistry Backup (*.eregbackup);;All files (*)"
        )
        if not name:
            return
        if (
            QMessageBox.warning(
                self,
                "Replace current data?",
                "Restore replaces all current eRegistry data. A safety backup will be made first. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        try:
            self.context.db.close()
            safety = BackupService(self.context.root).restore(Path(name))
            self.context.catalog = __import__(
                "eregistry.catalog", fromlist=["OrganisationCatalog"]
            ).OrganisationCatalog(self.context.root)
        except Exception as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        QMessageBox.information(
            self, "Restore complete", f"Data restored. Safety backup:\n{safety}"
        )
        self._reload_organisations()
        with self.context.db.session() as session:
            session.add(
                AuditLog(
                    action="backup.restore",
                    entity_type="application",
                    description=f"Restored {Path(name).name}; safety copy {safety.name}",
                )
            )
            session.commit()

    def _audit_log(self):
        with self.context.db.session() as session:
            logs = list(session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(500))
        dialog = QDialog(self)
        dialog.setWindowTitle("Activity log")
        dialog.resize(900, 600)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["When", "Action", "Record", "Description"])
        table.horizontalHeader().setStretchLastSection(True)
        for log in logs:
            r = table.rowCount()
            table.insertRow(r)
            for c, value in enumerate(
                (
                    log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    log.action,
                    f"{log.entity_type} {log.entity_id}",
                    log.description,
                )
            ):
                table.setItem(r, c, item(value))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _theme_changed(self, value):
        self.settings.setValue("theme", value)
        from .theme import DARK, LIGHT

        self.window().setStyleSheet(DARK if value == "Dark" else LIGHT)

    def maybe_weekly_backup_reminder(self):
        raw = self.settings.value("last_backup", "")
        try:
            last = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            last = None
        if not last or (datetime.now() - last).days >= 7:
            QMessageBox.information(
                self,
                "Weekly backup reminder",
                "It has been at least one week since the last recorded backup. Use Tools & Backup → Create complete backup when convenient.",
            )
