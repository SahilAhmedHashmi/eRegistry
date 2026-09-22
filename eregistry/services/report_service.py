from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


class AnalyticsReportService:
    def __init__(self, organisation_name: str, analytics):
        self.organisation_name = organisation_name
        self.analytics = analytics

    def export_pdf(self, path: Path) -> Path:
        summary = self.analytics.summary()
        trends = self.analytics.payroll_trends()
        categories = self.analytics.category_financials()
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(
            str(path),
            pagesize=landscape(A4),
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )
        story = [
            Paragraph(f"eRegistry Management Report — {self.organisation_name}", styles["Title"]),
            Spacer(1, 5 * mm),
        ]
        cards = [
            [
                "Total Employees",
                summary["total_employees"],
                "Active",
                summary["active_employees"],
                "Recent Registrations",
                summary["recent_registrations"],
            ],
            [
                "Salary Expenditure",
                f"₹{summary['salary_expenditure']:,.0f}",
                "Revenue",
                f"₹{summary['revenue']:,.0f}",
                "Profit Margin",
                f"{summary['profit_margin']:.1f}%",
            ],
            [
                "Overtime Hours",
                f"{summary['overtime_hours']:,.1f}",
                "Incomplete Records",
                summary["incomplete_records"],
                "EPFO / ESIC",
                f"{summary['epfo_registered']} / {summary['esic_registered']}",
            ],
        ]
        story.append(self._table(cards))
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph("Monthly trends", styles["Heading2"]))
        story.append(
            self._table(
                [
                    ["Month", "Salary", "Revenue", "Profit", "OT Hours", "Client Rating"],
                    *[
                        [
                            r["label"],
                            f"₹{r['salary']:,.0f}",
                            f"₹{r['revenue']:,.0f}",
                            f"₹{r['profit']:,.0f}",
                            f"{r['overtime']:.1f}",
                            r["client_satisfaction"] or "—",
                        ]
                        for r in trends
                    ],
                ]
            )
        )
        story.append(PageBreak())
        story.append(Paragraph("Skill-category financial performance", styles["Heading2"]))
        story.append(
            self._table(
                [
                    ["Category", "Salary", "Revenue", "Contribution"],
                    *[
                        [
                            r["category"],
                            f"₹{r['salary']:,.0f}",
                            f"₹{r['revenue']:,.0f}",
                            f"₹{r['profit']:,.0f}",
                        ]
                        for r in categories
                    ],
                ]
            )
        )
        doc.build(story)
        return path

    def export_excel(self, path: Path) -> Path:
        wb = Workbook()
        ws = wb.active
        ws.title = "KPI Summary"
        summary = self.analytics.summary()
        ws.append(["KPI", "Value"])
        for key, value in summary.items():
            if isinstance(value, dict):
                continue
            ws.append([key.replace("_", " ").title(), value])
        self._header(ws)
        trends = wb.create_sheet("Monthly Trends")
        trends.append(
            ["Month", "Salary", "Revenue", "Profit", "Overtime Hours", "Client Satisfaction"]
        )
        for row in self.analytics.payroll_trends():
            trends.append(
                [
                    row["label"],
                    row["salary"],
                    row["revenue"],
                    row["profit"],
                    row["overtime"],
                    row["client_satisfaction"],
                ]
            )
        self._header(trends)
        categories = wb.create_sheet("Skill Categories")
        categories.append(["Category", "Salary Expenditure", "Revenue", "Contribution"])
        for row in self.analytics.category_financials():
            categories.append([row["category"], row["salary"], row["revenue"], row["profit"]])
        self._header(categories)
        wb.save(path)
        return path

    @staticmethod
    def _header(ws):
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="F8CBAD")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(
                max(len(str(c.value or "")) for c in col) + 3, 40
            )

    @staticmethod
    def _table(data):
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8CBAD")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table
