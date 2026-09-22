from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class OrganisationProfile(Base):
    __tablename__ = "organisation_profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(250))
    address: Mapped[str] = mapped_column(Text, default="")
    contact_person: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(200), default="")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("registration_number", name="uq_employee_registration"),
        UniqueConstraint("aadhaar_number", name="uq_employee_aadhaar"),
        UniqueConstraint("uan_number", name="uq_employee_uan"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_number: Mapped[str | None] = mapped_column(String(80))
    registration_date: Mapped[date | None] = mapped_column(Date)
    designation: Mapped[str] = mapped_column(String(120), default="")
    photo_path: Mapped[str] = mapped_column(String(500), default="")
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    father_husband_name: Mapped[str] = mapped_column(String(250), default="")
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    appointment_date: Mapped[date | None] = mapped_column(Date)
    age_years: Mapped[int | None] = mapped_column(Integer)
    age_months: Mapped[int | None] = mapped_column(Integer)
    age_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    mother_name: Mapped[str] = mapped_column(String(250), default="")
    mother_age: Mapped[int | None] = mapped_column(Integer)
    place_of_birth: Mapped[str] = mapped_column(String(250), default="")
    gender: Mapped[str] = mapped_column(String(50), default="")
    marital_status: Mapped[str] = mapped_column(String(50), default="")
    nationality: Mapped[str] = mapped_column(String(100), default="Indian")
    blood_group: Mapped[str] = mapped_column(String(20), default="")
    identification_mark_1: Mapped[str] = mapped_column(String(300), default="")
    identification_mark_2: Mapped[str] = mapped_column(String(300), default="")
    armed_forces_experience: Mapped[str] = mapped_column(String(300), default="")
    armed_forces_years: Mapped[str] = mapped_column(String(30), default="")
    armed_forces_rank: Mapped[str] = mapped_column(String(120), default="")
    gunman_details: Mapped[str] = mapped_column(String(200), default="")
    gun_license_number: Mapped[str] = mapped_column(String(100), default="")
    gun_issuing_authority: Mapped[str] = mapped_column(String(200), default="")
    gun_license_valid_to: Mapped[date | None] = mapped_column(Date)
    weapon_type: Mapped[str] = mapped_column(String(120), default="")
    aadhaar_number: Mapped[str | None] = mapped_column(String(20))
    driving_license_number: Mapped[str] = mapped_column(String(100), default="")
    other_certification: Mapped[str] = mapped_column(Text, default="")
    languages_known: Mapped[str] = mapped_column(String(400), default="")
    permanent_address: Mapped[str] = mapped_column(Text, default="")
    communication_address: Mapped[str] = mapped_column(Text, default="")
    pan_number: Mapped[str] = mapped_column(String(20), default="")
    bank_name: Mapped[str] = mapped_column(String(200), default="")
    bank_branch: Mapped[str] = mapped_column(String(200), default="")
    bank_account_number: Mapped[str] = mapped_column(String(50), default="")
    ifsc_code: Mapped[str] = mapped_column(String(20), default="")
    epfo_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    esic_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    uan_number: Mapped[str | None] = mapped_column(String(30))
    esic_number: Mapped[str | None] = mapped_column(String(30))
    contact_number: Mapped[str] = mapped_column(String(20), default="")
    alternate_contact_number: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(20), default="Active")
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_reason: Mapped[str] = mapped_column(Text, default="")
    daily_wage_override: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    work_experiences: Mapped[list[WorkExperience]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    education_records: Mapped[list[Education]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    nominees: Mapped[list[Nominee]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    family_members: Mapped[list[FamilyMember]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class WorkExperience(Base):
    __tablename__ = "work_experience"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    employer_name_address: Mapped[str] = mapped_column(Text, default="")
    rank_post: Mapped[str] = mapped_column(String(150), default="")
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    salary_per_month: Mapped[float | None] = mapped_column(Float)
    nature_of_work: Mapped[str] = mapped_column(Text, default="")
    reason_for_leaving: Mapped[str] = mapped_column(Text, default="")
    employee: Mapped[Employee] = relationship(back_populates="work_experiences")


class Education(Base):
    __tablename__ = "education"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    qualification: Mapped[str] = mapped_column(String(150), default="")
    subject: Mapped[str] = mapped_column(String(150), default="")
    year_of_passing: Mapped[str] = mapped_column(String(10), default="")
    board_college_university: Mapped[str] = mapped_column(String(250), default="")
    division_result: Mapped[str] = mapped_column(String(100), default="")
    remarks: Mapped[str] = mapped_column(String(250), default="")
    employee: Mapped[Employee] = relationship(back_populates="education_records")


class Nominee(Base):
    __tablename__ = "nominees"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(250), default="")
    relation: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    mobile_number: Mapped[str] = mapped_column(String(20), default="")
    employee: Mapped[Employee] = relationship(back_populates="nominees")


class FamilyMember(Base):
    __tablename__ = "family_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(250), default="")
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    relation: Mapped[str] = mapped_column(String(100), default="")
    residing_with_employee: Mapped[bool | None] = mapped_column(Boolean)
    gender: Mapped[str] = mapped_column(String(30), default="")
    aadhaar_number: Mapped[str] = mapped_column(String(20), default="")
    employee: Mapped[Employee] = relationship(back_populates="family_members")


class RateCard(Base):
    __tablename__ = "rate_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    designation: Mapped[str] = mapped_column(String(120), unique=True)
    daily_wage: Mapped[float] = mapped_column(Float, default=0)
    client_billing_rate: Mapped[float] = mapped_column(Float, default=0)


class PayrollMonth(Base):
    __tablename__ = "payroll_months"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_payroll_month"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="Draft")
    client_satisfaction_rating: Mapped[int | None] = mapped_column(Integer)
    client_satisfaction_notes: Mapped[str] = mapped_column(Text, default="")
    employer_costs: Mapped[float] = mapped_column(Float, default=0)
    statutory_costs: Mapped[float] = mapped_column(Float, default=0)
    operational_costs: Mapped[float] = mapped_column(Float, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    entries: Mapped[list[PayrollEntry]] = relationship(
        back_populates="payroll_month", cascade="all, delete-orphan"
    )


class PayrollEntry(Base):
    __tablename__ = "payroll_entries"
    __table_args__ = (
        UniqueConstraint("payroll_month_id", "employee_id", name="uq_month_employee"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payroll_month_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_months.id", ondelete="CASCADE")
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    included: Mapped[bool] = mapped_column(Boolean, default=True)
    working_days: Mapped[float] = mapped_column(Float, default=0)
    ot_hours: Mapped[float] = mapped_column(Float, default=0)
    ph_days: Mapped[float] = mapped_column(Float, default=0)
    wages_per_day: Mapped[float] = mapped_column(Float, default=0)
    working_day_wages: Mapped[float] = mapped_column(Float, default=0)
    ot_ph_wages: Mapped[float] = mapped_column(Float, default=0)
    bonus: Mapped[float] = mapped_column(Float, default=0)
    gross_salary: Mapped[float] = mapped_column(Float, default=0)
    epf_deduction: Mapped[float] = mapped_column(Float, default=0)
    esic_deduction: Mapped[float] = mapped_column(Float, default=0)
    advance: Mapped[float] = mapped_column(Float, default=0)
    total_deduction: Mapped[float] = mapped_column(Float, default=0)
    net_salary: Mapped[float] = mapped_column(Float, default=0)
    client_billing_rate: Mapped[float] = mapped_column(Float, default=0)
    billed_revenue: Mapped[float] = mapped_column(Float, default=0)
    performance_rating: Mapped[int | None] = mapped_column(Integer)
    performance_notes: Mapped[str] = mapped_column(Text, default="")
    override_fields: Mapped[str] = mapped_column(Text, default="")
    payroll_month: Mapped[PayrollMonth] = relationship(back_populates="entries")
    employee: Mapped[Employee] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(80), default="")
    entity_id: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class AppSetting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
