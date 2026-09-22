from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import func, select

from ..constants import DEFAULT_KPI_WEIGHTS, DEFAULT_OT_HEALTHY_CAP
from ..models import Employee, PayrollEntry, PayrollMonth


class AnalyticsService:
    def __init__(self, db):
        self.db = db

    def summary(self) -> dict:
        with self.db.session() as session:
            employees = list(session.scalars(select(Employee)))
            months = list(session.scalars(select(PayrollMonth)))
            entries = list(session.scalars(select(PayrollEntry)))
        active = [e for e in employees if e.status == "Active"]
        completed = [m for m in months if m.status == "Completed"]
        gross = sum(e.gross_salary for e in entries)
        revenue = sum(e.billed_revenue for e in entries)
        extra_costs = sum(
            m.employer_costs + m.statutory_costs + m.operational_costs for m in completed
        )
        profit = revenue - gross - extra_costs
        categories = Counter((e.designation or "Unspecified") for e in active)
        gender = Counter((e.gender or "Unspecified") for e in active)
        incomplete = sum(self._is_incomplete(e) for e in active)
        return {
            "total_employees": len(employees),
            "active_employees": len(active),
            "recent_registrations": sum(
                1
                for e in employees
                if e.registration_date and (date.today() - e.registration_date).days <= 30
            ),
            "categories": dict(categories),
            "gender": dict(gender),
            "epfo_registered": sum(bool(e.epfo_registered) for e in active),
            "esic_registered": sum(bool(e.esic_registered) for e in active),
            "incomplete_records": incomplete,
            "salary_expenditure": gross,
            "revenue": revenue,
            "profit": profit,
            "profit_margin": (profit / revenue * 100) if revenue else 0,
            "overtime_hours": sum(e.ot_hours for e in entries),
        }

    @staticmethod
    def _is_incomplete(e: Employee) -> bool:
        fields = (
            e.contact_number,
            e.aadhaar_number,
            e.bank_account_number,
            e.ifsc_code,
            e.permanent_address,
        )
        return not all(fields)

    def payroll_trends(self) -> list[dict]:
        with self.db.session() as session:
            months = list(
                session.scalars(
                    select(PayrollMonth).order_by(PayrollMonth.year, PayrollMonth.month)
                )
            )
            output = []
            for month in months:
                entries = list(
                    session.scalars(
                        select(PayrollEntry).where(
                            PayrollEntry.payroll_month_id == month.id,
                            PayrollEntry.included.is_(True),
                        )
                    )
                )
                salary = sum(e.gross_salary for e in entries)
                revenue = sum(e.billed_revenue for e in entries)
                cost = (
                    salary + month.employer_costs + month.statutory_costs + month.operational_costs
                )
                output.append(
                    {
                        "label": f"{month.year}-{month.month:02d}",
                        "salary": salary,
                        "revenue": revenue,
                        "profit": revenue - cost,
                        "overtime": sum(e.ot_hours for e in entries),
                        "client_satisfaction": month.client_satisfaction_rating,
                    }
                )
            return output

    def category_financials(self) -> list[dict]:
        with self.db.session() as session:
            rows = session.execute(
                select(
                    Employee.designation,
                    func.sum(PayrollEntry.gross_salary),
                    func.sum(PayrollEntry.billed_revenue),
                )
                .join(PayrollEntry, PayrollEntry.employee_id == Employee.id)
                .where(PayrollEntry.included.is_(True))
                .group_by(Employee.designation)
            ).all()
        return [
            {
                "category": r[0] or "Unspecified",
                "salary": float(r[1] or 0),
                "revenue": float(r[2] or 0),
                "profit": float((r[2] or 0) - (r[1] or 0)),
            }
            for r in rows
        ]

    def retention(self) -> list[dict]:
        with self.db.session() as session:
            employees = list(session.scalars(select(Employee)))
            months = list(
                session.scalars(
                    select(PayrollMonth).order_by(PayrollMonth.year, PayrollMonth.month)
                )
            )
        output = []
        for m in months:
            start = date(m.year, m.month, 1)
            if m.month == 12:
                end = date(m.year + 1, 1, 1)
            else:
                end = date(m.year, m.month + 1, 1)
            at_start = [
                e
                for e in employees
                if e.appointment_date
                and e.appointment_date < start
                and (not e.exit_date or e.exit_date >= start)
            ]
            retained = [e for e in at_start if not e.exit_date or e.exit_date >= end]
            output.append(
                {
                    "label": f"{m.year}-{m.month:02d}",
                    "retention": (len(retained) / len(at_start) * 100) if at_start else 0,
                }
            )
        return output

    def redeployability(
        self,
        required_category: str,
        weights: dict | None = None,
        healthy_ot_cap: float = DEFAULT_OT_HEALTHY_CAP,
    ) -> list[dict]:
        weights = weights or DEFAULT_KPI_WEIGHTS
        with self.db.session() as session:
            employees = list(session.scalars(select(Employee).where(Employee.status == "Active")))
            months = list(
                session.scalars(
                    select(PayrollMonth)
                    .where(PayrollMonth.status == "Completed")
                    .order_by(PayrollMonth.year.desc(), PayrollMonth.month.desc())
                    .limit(3)
                )
            )
            month_ids = [m.id for m in months]
            entries = (
                list(
                    session.scalars(
                        select(PayrollEntry).where(PayrollEntry.payroll_month_id.in_(month_ids))
                    )
                )
                if month_ids
                else []
            )
        by_employee = defaultdict(list)
        for entry in entries:
            by_employee[entry.employee_id].append(entry)
        results = []
        for employee in employees:
            history = by_employee[employee.id]
            if not history:
                continue
            ratings = [e.performance_rating for e in history if e.performance_rating]
            performance = (sum(ratings) / len(ratings) / 5 * 100) if ratings else 0
            attendance_values = []
            for e in history:
                # Uses a 31-day ceiling because the source payroll sheet records calendar-day wages.
                attendance_values.append(min(e.working_days / 31 * 100, 100))
            attendance = sum(attendance_values) / len(attendance_values)
            skill_fit = (
                100
                if (employee.designation or "").casefold() == required_category.casefold()
                else 0
            )
            avg_ot = sum(e.ot_hours for e in history) / len(history)
            overtime = min(avg_ot / healthy_ot_cap * 100, 100) if healthy_ot_cap else 0
            score = (
                performance * weights["performance"]
                + attendance * weights["attendance"]
                + skill_fit * weights["skill_fit"]
                + overtime * weights["overtime"]
            )
            results.append(
                {
                    "employee_id": employee.id,
                    "name": employee.name,
                    "designation": employee.designation,
                    "score": round(score, 1),
                    "performance": round(performance, 1),
                    "attendance": round(attendance, 1),
                    "skill_fit": skill_fit,
                    "overtime": round(overtime, 1),
                    "months": len(history),
                    "limited_history": len(history) < 3,
                    "high_overtime": avg_ot > healthy_ot_cap,
                }
            )
        return sorted(results, key=lambda row: row["score"], reverse=True)
