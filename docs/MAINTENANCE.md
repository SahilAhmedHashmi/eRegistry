# Maintenance and release guide

## Ownership

All application source, schemas, tests, build recipes, and documentation are included. There is no obfuscation or generated core business logic. The included MIT license permits use, modification, private or public redistribution, and sublicensing. Replace it before distribution if your organisation prefers a proprietary licensing policy.

## Safe change workflow

1. Create a Git repository and commit the initial source.
2. Create a feature branch for each patch.
3. Change service-layer rules first, then adapt the UI.
4. Add or update tests for every calculation/schema change.
5. Run `pytest` and manually inspect a generated registration PDF and organisation workbook.
6. Update the version in `eregistry/__init__.py`, `pyproject.toml`, and `packaging/eRegistry.iss`.
7. Build on a clean Windows machine and test both installer and portable distributions.
8. Code-sign the installer and executable before external distribution when you obtain a signing certificate.

The included `.github/workflows/windows-release.yml` provides a reproducible Windows build. Pin third-party action revisions to commit hashes if your release policy requires supply-chain immutability.

## Database upgrades

Version 1.0 creates tables with SQLAlchemy. Before changing any existing column in a deployed release, introduce Alembic migrations rather than deleting/recreating databases. Always test migrations against backup copies and preserve SQLCipher connection setup. Never log database keys, the in-memory master key, passwords, or recovery keys.

## Adding a payroll field

Update, in order: `models.PayrollEntry`, the payroll UI mapping, `PayrollService.calculate_entry` if calculated, Excel header/row generation, reports/analytics, import/export tests, and documentation. A new field also needs a migration once users have production data.

## Adding a registration field

Update `models.Employee` or its repeating child model, `EmployeeWizard`, `EmployeeService`, Excel registration details, registration PDF, imports if applicable, tests, and a migration.

## Releases and updates

The current installer replaces program files but does not touch the user-selected data folder. Before shipping an update, test opening an old encrypted database and restoring an old backup. Publish checksums with releases. Keep portable and installed editions at the same version and never silently change calculation rules.

## Recommended future work

- Add Alembic before the first schema-changing production patch.
- Add Windows Authenticode signing and an optional user-approved update checker.
- Add a configurable full-time-equivalent working-day target per month for sharper attendance analytics.
- Add client invoices and payment receipt tracking if revenue should move beyond calculated billed revenue.
- Add chart widgets after enough completed monthly history exists; retain tabular exports as the auditable source.
- Add field-level validation profiles for Aadhaar, PAN, IFSC, UAN, and ESIC once the organisation confirms its accepted legacy formats.
