# Architecture

## Design goals

eRegistry is deliberately a local desktop application. PySide6 supplies the Windows UI; SQLAlchemy maps the data model; SQLCipher encrypts each organisation database; openpyxl builds Excel views; ReportLab produces printable PDFs. Business rules live in services, not UI event handlers, so future interfaces and reports can reuse them.

## Source layout

| Path | Responsibility |
|---|---|
| `eregistry/main.py` | Setup/login lifecycle, global theme, inactivity lock, logout |
| `eregistry/ui/` | Windows screens, guided registration, mapping dialogs |
| `eregistry/models.py` | Database schema |
| `eregistry/services/employee_service.py` | Validation, CRUD, transfers, activity log |
| `eregistry/services/payroll_service.py` | Salary calculations, overrides, month locking |
| `eregistry/services/excel_service.py` | Exact salary layout and linked detail sheets |
| `eregistry/services/pdf_service.py` | Two-page registration form and continuation pages |
| `eregistry/services/analytics_service.py` | KPIs, retention, trends, redeployment |
| `eregistry/security.py` | Password/recovery key derivation and master-key wrapping |
| `eregistry/database.py` | SQLCipher connections and per-organisation keys |
| `packaging/` | PyInstaller portable build and Inno Setup installer |

## Storage model

The bootstrap pointer lives in the user's normal Windows application configuration directory. The selected data folder contains `auth.json`, `organisations.json`, `organisations/<organisation>/eregistry.db`, photos, PDFs, unencrypted Excel workbooks, reports, and backups.

`auth.json` stores salts and AES-GCM wrapped master-key material—not the password or recovery key. Scrypt derives wrapping keys. A unique database key is derived from the master key and organisation ID. The encrypted SQLCipher database is authoritative.

Organisation names and locations in `organisations.json` are not encrypted. This enables organisation discovery before a database opens; employee/payroll records remain encrypted.

## Calculations

```text
working wages = working days × wages/day
gross salary = working wages + OT/PH wages + bonus
total deduction = EPF + ESIC + advance
net salary = gross salary − total deduction
billed revenue = working days × client billing rate
profit = revenue − gross salary − employer/statutory/operational costs
```

Currency results use half-up rounding to whole rupees to reproduce the supplied payroll workbook. Confirmed manual changes to calculated salary columns are retained and audited.

Redeployability defaults to performance 40%, attendance 30%, exact skill fit 20%, and moderate overtime 10%. The last three completed months available are used. A new employee is evaluated on available months and labelled as limited history rather than penalised for missing months. Overtime contribution is capped; unusually high overtime is flagged.

