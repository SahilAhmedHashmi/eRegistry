from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import AuditLog, Employee, PayrollEntry, PayrollMonth, RateCard


def money(value: float | int | str | None) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_entry(values: dict, overrides: set[str] | None = None) -> dict:
    overrides = overrides or set()
    result = dict(values)
    if "working_day_wages" not in overrides:
        result["working_day_wages"] = money(
            float(result.get("working_days", 0)) * float(result.get("wages_per_day", 0))
        )
    if "gross_salary" not in overrides:
        result["gross_salary"] = money(
            float(result.get("working_day_wages", 0))
            + float(result.get("ot_ph_wages", 0))
            + float(result.get("bonus", 0))
        )
    if "total_deduction" not in overrides:
        result["total_deduction"] = money(
            float(result.get("epf_deduction", 0))
            + float(result.get("esic_deduction", 0))
            + float(result.get("advance", 0))
        )
    if "net_salary" not in overrides:
        result["net_salary"] = money(
            float(result.get("gross_salary", 0)) - float(result.get("total_deduction", 0))
        )
    result["billed_revenue"] = money(
        float(result.get("working_days", 0)) * float(result.get("client_billing_rate", 0))
    )
    return result


class PayrollService:
    def __init__(self, db):
        self.db = db

    def list_months(self) -> list[PayrollMonth]:
        with self.db.session() as session:
            return list(
                session.scalars(
                    select(PayrollMonth).order_by(
                        PayrollMonth.year.desc(), PayrollMonth.month.desc()
                    )
                )
            )

    def get_or_create_month(self, year: int, month: int) -> PayrollMonth:
        with self.db.session() as session:
            payroll = session.scalars(
                select(PayrollMonth).where(PayrollMonth.year == year, PayrollMonth.month == month)
            ).first()
            if payroll:
                return payroll
            payroll = PayrollMonth(year=year, month=month)
            session.add(payroll)
            session.flush()
            employees = list(
                session.scalars(
                    select(Employee).where(Employee.status == "Active").order_by(Employee.name)
                )
            )
            rates = {r.designation.casefold(): r for r in session.scalars(select(RateCard))}
            for employee in employees:
                card = rates.get((employee.designation or "").casefold())
                payroll.entries.append(
                    PayrollEntry(
                        employee_id=employee.id,
                        wages_per_day=employee.daily_wage_override
                        if employee.daily_wage_override is not None
                        else (card.daily_wage if card else 0),
                        client_billing_rate=card.client_billing_rate if card else 0,
                    )
                )
            session.add(
                AuditLog(
                    action="payroll.create",
                    entity_type="payroll_month",
                    entity_id=str(payroll.id),
                    description=f"Created payroll for {year}-{month:02d}",
                )
            )
            session.commit()
            return payroll

    def get_month(self, payroll_id: int) -> PayrollMonth | None:
        with self.db.session() as session:
            return session.scalars(
                select(PayrollMonth)
                .options(selectinload(PayrollMonth.entries).selectinload(PayrollEntry.employee))
                .where(PayrollMonth.id == payroll_id)
            ).first()

    def save_entry(
        self, entry_id: int, values: dict, override_fields: set[str] | None = None
    ) -> PayrollEntry:
        override_fields = override_fields or set()
        calculated = calculate_entry(values, override_fields)
        with self.db.session() as session:
            entry = session.get(PayrollEntry, entry_id)
            if not entry:
                raise ValueError("Payroll entry not found.")
            month = session.get(PayrollMonth, entry.payroll_month_id)
            if month.status == "Completed":
                raise ValueError("This salary month is locked. Reopen it before editing.")
            for key, value in calculated.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)
            entry.override_fields = ",".join(sorted(override_fields))
            if override_fields:
                session.add(
                    AuditLog(
                        action="salary.override",
                        entity_type="payroll_entry",
                        entity_id=str(entry.id),
                        description=f"Manual overrides: {entry.override_fields}",
                    )
                )
            session.commit()
            return entry

    def update_month_metadata(
        self,
        payroll_id: int,
        rating: int | None,
        notes: str,
        employer: float,
        statutory: float,
        operational: float,
    ):
        with self.db.session() as session:
            month = session.get(PayrollMonth, payroll_id)
            if not month:
                raise ValueError("Payroll month not found.")
            month.client_satisfaction_rating = rating
            month.client_satisfaction_notes = notes
            month.employer_costs = employer
            month.statutory_costs = statutory
            month.operational_costs = operational
            session.commit()

    def complete(self, payroll_id: int) -> None:
        with self.db.session() as session:
            month = session.get(PayrollMonth, payroll_id)
            month.status = "Completed"
            month.completed_at = datetime.utcnow()
            session.add(
                AuditLog(
                    action="payroll.complete",
                    entity_type="payroll_month",
                    entity_id=str(month.id),
                    description=f"Completed payroll {month.year}-{month.month:02d}",
                )
            )
            session.commit()

    def reopen(self, payroll_id: int) -> None:
        with self.db.session() as session:
            month = session.get(PayrollMonth, payroll_id)
            month.status = "Draft"
            session.add(
                AuditLog(
                    action="payroll.reopen",
                    entity_type="payroll_month",
                    entity_id=str(month.id),
                    description=f"Reopened completed payroll {month.year}-{month.month:02d}",
                )
            )
            session.commit()

    def save_rate_card(self, designation: str, daily_wage: float, billing_rate: float):
        with self.db.session() as session:
            card = session.scalars(
                select(RateCard).where(RateCard.designation == designation)
            ).first()
            if not card:
                card = RateCard(designation=designation)
                session.add(card)
            card.daily_wage = daily_wage
            card.client_billing_rate = billing_rate
            session.commit()
