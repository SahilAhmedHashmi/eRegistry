from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..models import Education, Employee, FamilyMember, Nominee, WorkExperience


REPEATING_MODELS = {
    "work_experiences": WorkExperience,
    "education_records": Education,
    "nominees": Nominee,
    "family_members": FamilyMember,
}


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def clean_identifier(value: Any) -> str | None:
    value = re.sub(
        r"\s+",
        "",
        str(value or "").strip(),
    ).upper()
    return value or None


def clean_numeric_identifier(value: Any) -> str | None:
    value = re.sub(
        r"[\s-]+",
        "",
        str(value or "").strip(),
    ).upper()
    return value or None


def calculate_age(dob: date | None, appointment: date | None) -> tuple[int | None, int | None]:
    if not dob or not appointment or appointment < dob:
        return None, None
    months = (appointment.year - dob.year) * 12 + appointment.month - dob.month
    if appointment.day < dob.day:
        months -= 1
    return months // 12, months % 12


class DuplicateEmployeeError(ValueError):
    FIELD_LABELS = {
        "registration_number": "Registration number",
        "aadhaar_number": "Aadhaar number",
        "uan_number": "UAN number",
        "esic_number": "ESIC number",
    }

    def __init__(
        self,
        field: str,
        employee: Employee,
    ):
        label = self.FIELD_LABELS.get(
            field,
            field.replace("_", " ").title(),
        )
        registration = (
            employee.registration_number
            or "Not set"
        )
        super().__init__(
            f"{label} already belongs to "
            f"{employee.name} "
            f"(Registration No. {registration})."
        )
        self.field = field
        self.employee = employee


class EmployeeService:
    def __init__(self, db, organisation_folder: Path):
        self.db = db
        self.organisation_folder = organisation_folder

    def _query(self):
        return select(Employee).options(
            selectinload(Employee.work_experiences),
            selectinload(Employee.education_records),
            selectinload(Employee.nominees),
            selectinload(Employee.family_members),
        )

    def list(self, search: str = "", status: str = "All") -> list[Employee]:
        with self.db.session() as session:
            stmt = self._query().order_by(Employee.name)
            if search.strip():
                term = f"%{search.strip()}%"
                stmt = stmt.where(
                    or_(
                        Employee.name.ilike(term),
                        Employee.registration_number.ilike(term),
                        Employee.aadhaar_number.ilike(term),
                        Employee.uan_number.ilike(term),
                    )
                )
            if status != "All":
                stmt = stmt.where(Employee.status == status)
            return list(session.scalars(stmt).unique())

    def get(self, employee_id: int) -> Employee | None:
        with self.db.session() as session:
            return session.scalars(self._query().where(Employee.id == employee_id)).first()

    def _check_duplicate(
        self, session, field: str, value: str | None, exclude_id: int | None = None
    ):
        if not value:
            return
        column = getattr(Employee, field)
        stmt = select(Employee).where(column == value)
        if exclude_id:
            stmt = stmt.where(Employee.id != exclude_id)
        existing = session.scalars(stmt).first()
        if existing:
            raise DuplicateEmployeeError(field, existing)

    def save(self, values: dict[str, Any], employee_id: int | None = None) -> Employee:
        values = dict(values)
        name = clean_text(values.get("name"))
        if not name:
            raise ValueError("Employee name is required.")
        values["name"] = name
        values["registration_number"] = clean_identifier(
            values.get("registration_number")
        )
        for field in (
            "aadhaar_number",
            "uan_number",
            "esic_number",
        ):
            values[field] = clean_numeric_identifier(
                values.get(field)
            )
        if not values.get("age_manual_override"):
            values["age_years"], values["age_months"] = calculate_age(
                values.get("date_of_birth"), values.get("appointment_date")
            )
        repeating = {name: values.pop(name, []) for name in REPEATING_MODELS}
        source_photo = values.pop("photo_source", "")
        with self.db.session() as session:
            for field in (
                "registration_number",
                "aadhaar_number",
                "uan_number",
                "esic_number",
            ):
                self._check_duplicate(session, field, values.get(field), employee_id)
            employee = session.get(Employee, employee_id) if employee_id else Employee()
            if employee is None:
                raise ValueError("Employee record no longer exists.")
            for key, value in values.items():
                if hasattr(employee, key):
                    setattr(employee, key, value)
            session.add(employee)
            session.flush()
            if source_photo:
                photos = self.organisation_folder / "photos"
                photos.mkdir(exist_ok=True)
                suffix = Path(source_photo).suffix.lower() or ".jpg"
                target = photos / f"employee_{employee.id}{suffix}"
                if Path(source_photo).resolve() != target.resolve():
                    shutil.copy2(source_photo, target)
                employee.photo_path = str(target.relative_to(self.organisation_folder))
            for relation_name, model in REPEATING_MODELS.items():
                getattr(employee, relation_name).clear()
                for row in repeating[relation_name]:
                    if any(str(v or "").strip() for v in row.values()):
                        getattr(employee, relation_name).append(model(**row))
            action = "employee.edit" if employee_id else "employee.create"
            session.flush()
            self._audit(
                session,
                action,
                employee.id,
                f"{employee.name} ({employee.registration_number or 'no registration number'})",
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError(
                    "A unique identifier is already in use in this organisation."
                ) from exc
            return employee

    def delete(self, employee_id: int) -> None:
        with self.db.session() as session:
            employee = session.get(Employee, employee_id)
            if not employee:
                return
            description = f"Permanently deleted {employee.name} ({employee.registration_number or 'no registration number'})"
            photo = self.organisation_folder / employee.photo_path if employee.photo_path else None
            session.delete(employee)
            self._audit(session, "employee.delete", employee_id, description)
            session.commit()
            if photo and photo.exists():
                photo.unlink(missing_ok=True)

    def set_status(self, employee_id: int, status: str, exit_date=None, exit_reason="") -> None:
        with self.db.session() as session:
            employee = session.get(Employee, employee_id)
            if not employee:
                raise ValueError("Employee not found.")
            employee.status = status
            employee.exit_date = exit_date if status == "Inactive" else None
            employee.exit_reason = exit_reason if status == "Inactive" else ""
            self._audit(session, "employee.status", employee_id, f"Status changed to {status}")
            session.commit()

    def copy_to(
        self,
        employee_id: int,
        destination_service: "EmployeeService",
        registration_number: str | None,
    ) -> Employee:
        employee = self.get(employee_id)
        if not employee:
            raise ValueError("Employee not found.")
        scalar_columns = [
            c.name
            for c in Employee.__table__.columns
            if c.name not in {"id", "created_at", "updated_at"}
        ]
        values = {name: getattr(employee, name) for name in scalar_columns}
        values["registration_number"] = registration_number
        if employee.photo_path:
            values["photo_source"] = str(self.organisation_folder / employee.photo_path)
        for relation_name, model in REPEATING_MODELS.items():
            rows = []
            for row in getattr(employee, relation_name):
                rows.append(
                    {
                        c.name: getattr(row, c.name)
                        for c in model.__table__.columns
                        if c.name not in {"id", "employee_id"}
                    }
                )
            values[relation_name] = rows
        copied = destination_service.save(values)
        with self.db.session() as session:
            self._audit(
                session,
                "employee.transfer",
                employee_id,
                f"Copied {employee.name} to another organisation",
            )
            session.commit()
        return copied

    @staticmethod
    def _audit(session, action: str, entity_id: int | str, description: str):
        from ..models import AuditLog

        session.add(
            AuditLog(
                action=action,
                entity_type="employee",
                entity_id=str(entity_id),
                description=description,
            )
        )
