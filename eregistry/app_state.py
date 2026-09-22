from __future__ import annotations

from pathlib import Path

from .catalog import Organisation, OrganisationCatalog
from .database import DatabaseManager, organisation_db_key
from .services.analytics_service import AnalyticsService
from .services.employee_service import EmployeeService
from .services.excel_service import ExcelService
from .services.payroll_service import PayrollService
from .services.pdf_service import RegistrationPdfService


class AppContext:
    def __init__(self, root: Path, master_key: bytes):
        self.root = root
        self.master_key = master_key
        self.catalog = OrganisationCatalog(root)
        self.organisation: Organisation | None = None
        self.db: DatabaseManager | None = None
        self.employees: EmployeeService | None = None
        self.payroll: PayrollService | None = None
        self.analytics: AnalyticsService | None = None
        self.excel: ExcelService | None = None
        self.pdf: RegistrationPdfService | None = None

    def open_organisation(self, organisation: Organisation) -> None:
        if self.db:
            self.db.close()
        folder = self.catalog.folder_for(organisation)
        db = DatabaseManager(
            folder / "eregistry.db", organisation_db_key(self.master_key, organisation.id)
        )
        db.initialize(
            {
                "external_id": organisation.id,
                "name": organisation.name,
                "address": organisation.address,
                "contact_person": organisation.contact_person,
                "phone": organisation.phone,
                "email": organisation.email,
            }
        )
        self.organisation = organisation
        self.db = db
        self.employees = EmployeeService(db, folder)
        self.payroll = PayrollService(db)
        self.analytics = AnalyticsService(db)
        self.excel = ExcelService(db, organisation, folder)
        self.pdf = RegistrationPdfService(folder, organisation.name)

    def create_organisation(self, **values) -> Organisation:
        org = self.catalog.create(**values)
        self.open_organisation(org)
        self.excel.sync()
        return org

    def close(self) -> None:
        if self.db:
            self.db.close()
        self.master_key = b""
