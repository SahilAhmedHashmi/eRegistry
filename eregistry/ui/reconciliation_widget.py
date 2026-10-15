from __future__ import annotations

import calendar
from collections import Counter
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..services.reconciliation_service import (
    FIELD_LABELS,
    ReconciliationResult,
    ReconciliationService,
    _suggest_mapping,
)
from .table_utils import configure_resizable_columns


class ColumnMappingDialog(QDialog):
    def __init__(self, path: Path, inspection, parent=None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle("Confirm salary-sheet columns")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Confirm how the organisation's worksheet columns map to the five "
            "temporary reconciliation fields. No workbook values will be changed."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        self.sheet = QComboBox()
        self.sheet.addItems(inspection.sheet_names)
        self.sheet.setCurrentText(inspection.sheet_name)
        self.header_row = QSpinBox()
        self.header_row.setRange(1, 1000)
        self.header_row.setValue(inspection.header_row)
        form.addRow("Worksheet", self.sheet)
        form.addRow("Header row", self.header_row)
        self.fields = {}
        for field, label in FIELD_LABELS.items():
            combo = QComboBox()
            self.fields[field] = combo
            form.addRow(label, combo)
        layout.addLayout(form)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.sheet.currentTextChanged.connect(self._reload_headers)
        self.header_row.valueChanged.connect(self._reload_headers)
        self._set_headers(inspection.headers, inspection.suggested_mapping)

    def _reload_headers(self, *_):
        try:
            headers = ReconciliationService.read_headers(
                self.path,
                self.sheet.currentText(),
                self.header_row.value(),
            )
        except Exception as exc:
            self.preview.setText(str(exc))
            return
        self._set_headers(headers, _suggest_mapping(headers))

    def _set_headers(self, headers: list[str], suggested: dict[str, int]):
        for field, combo in self.fields.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— Select a column —", None)
            for index, header in enumerate(headers):
                column = self._excel_column(index + 1)
                combo.addItem(f"{column} — {header or '(blank)'}", index)
            wanted = suggested.get(field)
            if wanted is not None:
                index = combo.findData(wanted)
                combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
        readable = ", ".join(value or "(blank)" for value in headers)
        self.preview.setText(f"Detected headers: {readable or 'None'}")

    @staticmethod
    def _excel_column(number: int) -> str:
        result = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _accept(self):
        mapping = self.mapping()
        if len(mapping) != len(FIELD_LABELS):
            QMessageBox.warning(self, "Incomplete mapping", "Select all five required columns.")
            return
        if len(set(mapping.values())) != len(mapping):
            QMessageBox.warning(
                self,
                "Duplicate mapping",
                "Each reconciliation field must use a different Excel column.",
            )
            return
        self.accept()

    def mapping(self) -> dict[str, int]:
        return {
            field: combo.currentData()
            for field, combo in self.fields.items()
            if combo.currentData() is not None
        }


class ReconciliationWidget(QWidget):
    FILTERS = [
        "All results",
        "Confirmed match",
        "Salary mismatch",
        "Working-days mismatch",
        "Identity issue",
        "Missing employee",
        "Duplicate",
        "Invalid value",
    ]

    HEADERS = [
        "Status",
        "Source Row",
        "Reported PF/UAN",
        "eRegistry UAN",
        "Reported Employee Name",
        "eRegistry Employee Name",
        "Reported Working Days",
        "eRegistry Working Days",
        "Wage/Day",
        "Reported Expected Salary",
        "Calculated Expected Salary",
        "Expected Difference",
        "Reported Actual Salary",
        "Calculated From Reported Days",
        "eRegistry Working Wages",
        "Actual Difference",
        "Formula Difference",
        "Explanation",
    ]

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.results: list[ReconciliationResult] = []
        self.visible_results: list[ReconciliationResult] = []
        self.source_path: Path | None = None
        self.reconciled_month = None

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.month = QComboBox()
        self.month.setMinimumWidth(220)
        load = QPushButton("Load organisation sheet")
        load.clicked.connect(self._load_workbook)
        clear = QPushButton("Clear comparison")
        clear.setProperty("secondary", True)
        clear.clicked.connect(self.clear)
        self.export = QPushButton("Export reconciliation Excel")
        self.export.clicked.connect(self._export_report)
        self.export.setEnabled(False)
        self.filter = QComboBox()
        self.filter.addItems(self.FILTERS)
        self.filter.currentTextChanged.connect(self._render)
        controls.addWidget(QLabel("Salary month:"))
        controls.addWidget(self.month)
        controls.addWidget(load)
        controls.addWidget(clear)
        controls.addWidget(QLabel("Show:"))
        controls.addWidget(self.filter)
        controls.addStretch()
        controls.addWidget(self.export)
        layout.addLayout(controls)

        self.summary = QLabel(
            "Select a salary month and load the organisation's .xlsx workbook. "
            "Both sources remain unchanged."
        )
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        configure_resizable_columns(
            self.table,
            [150, 90, 160, 160, 220, 220, 150, 150, 120, 180, 190, 160,
             180, 210, 190, 150, 160, 520],
        )
        layout.addWidget(self.table)

    def refresh_months(self):
        current = self.month.currentData()
        self.month.blockSignals(True)
        self.month.clear()
        if self.context.payroll:
            for month in self.context.payroll.list_months():
                self.month.addItem(
                    f"{calendar.month_name[month.month]} {month.year} — {month.status}",
                    month.id,
                )
        if current is not None:
            index = self.month.findData(current)
            if index >= 0:
                self.month.setCurrentIndex(index)
        self.month.blockSignals(False)
        self.clear()

    def clear(self):
        self.results = []
        self.visible_results = []
        self.source_path = None
        self.reconciled_month = None
        self.table.setRowCount(0)
        self.export.setEnabled(False)
        self.summary.setText(
            "Select a salary month and load the organisation's .xlsx workbook. "
            "Both sources remain unchanged."
        )

    def _load_workbook(self):
        payroll_id = self.month.currentData()
        if payroll_id is None:
            QMessageBox.information(
                self,
                "No salary month",
                "Create or select an eRegistry salary month before reconciliation.",
            )
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select organisation salary sheet",
            "",
            "Excel Workbook (*.xlsx *.xlsm)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            inspection = ReconciliationService.inspect_workbook(path)
            dialog = ColumnMappingDialog(path, inspection, self)
            if dialog.exec() != QDialog.Accepted:
                return
            rows = ReconciliationService.load_rows(
                path,
                dialog.sheet.currentText(),
                dialog.header_row.value(),
                dialog.mapping(),
            )
            month, results = ReconciliationService(self.context.db).reconcile(
                int(payroll_id), rows
            )
        except Exception as exc:
            QMessageBox.critical(self, "Reconciliation failed", str(exc))
            return

        self.source_path = path
        self.reconciled_month = month
        self.results = results
        self.export.setEnabled(True)
        self._update_summary()
        self._render()

    def _update_summary(self):
        counts = Counter(result.status for result in self.results)
        confirmed = counts.get("Confirmed match", 0)
        problems = len(self.results) - confirmed
        self.summary.setText(
            f"{len(self.results)} comparison row(s): {confirmed} confirmed match(es), "
            f"{problems} row(s) requiring review. Source: {self.source_path.name}. "
            "The encrypted database and source workbook were not modified."
        )

    def _matches_filter(self, result: ReconciliationResult) -> bool:
        selected = self.filter.currentText()
        if selected == "All results":
            return True
        if selected == "Identity issue":
            return result.status in {
                "Name conflict",
                "Identifier conflict",
                "Possible name match",
                "Ambiguous",
            }
        if selected == "Missing employee":
            return result.status in {"External only", "eRegistry only"}
        return result.status == selected

    def _render(self, *_):
        self.visible_results = [result for result in self.results if self._matches_filter(result)]
        self.table.setRowCount(0)
        colours = {
            "Confirmed match": QColor("#bbf7d0"),
            "Salary mismatch": QColor("#fde68a"),
            "Working-days mismatch": QColor("#fde68a"),
            "Possible name match": QColor("#bfdbfe"),
            "Name conflict": QColor("#fecaca"),
            "Identifier conflict": QColor("#fecaca"),
            "Ambiguous": QColor("#fecaca"),
            "External only": QColor("#fecaca"),
            "eRegistry only": QColor("#fecaca"),
            "Duplicate": QColor("#fecaca"),
            "Invalid value": QColor("#fecaca"),
        }
        for result in self.visible_results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                result.status,
                result.source_row or "",
                result.reported_pf_number,
                result.eregistry_uan,
                result.reported_name,
                result.eregistry_name,
                self._number(result.reported_working_days),
                self._number(result.eregistry_working_days),
                self._money(result.wages_per_day),
                self._money(result.reported_expected_salary),
                self._money(result.calculated_expected_salary),
                self._signed_money(result.expected_difference),
                self._money(result.reported_actual_salary),
                self._money(result.calculated_from_reported_days),
                self._money(result.eregistry_working_wages),
                self._signed_money(result.actual_difference),
                self._signed_money(result.formula_difference),
                result.explanation,
            ]
            colour = colours.get(result.status, QColor("white"))
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                cell.setBackground(QBrush(colour))
                self.table.setItem(row, column, cell)

    @staticmethod
    def _number(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:g}"

    @staticmethod
    def _money(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"₹{value:,.0f}"

    @staticmethod
    def _signed_money(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"₹{value:+,.0f}"

    def _export_report(self):
        if not self.results or self.reconciled_month is None or self.source_path is None:
            return
        organisation = self.context.organisation
        default_name = (
            f"{organisation.name}_{self.reconciled_month.year}-"
            f"{self.reconciled_month.month:02d}_Reconciliation.xlsx"
        )
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export reconciliation report",
            str(self.context.root / "reports" / default_name),
            "Excel Workbook (*.xlsx)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.casefold() != ".xlsx":
            path = path.with_suffix(".xlsx")
        try:
            ReconciliationService.export_report(
                path,
                organisation.name,
                self.reconciled_month,
                self.source_path.name,
                self.results,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
