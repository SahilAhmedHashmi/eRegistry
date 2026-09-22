# eRegistry

eRegistry is an offline, single-user Windows desktop application for labour registration, organisation-specific encrypted records, monthly payroll, linked Excel registers, registration-form PDFs, backups, analytics, and redeployment ranking.

The project is complete, unobfuscated source code under the included MIT license. It has no subscription, cloud service, telemetry, remote login, or vendor-controlled update dependency. You can inspect, change, build, sign, and distribute your own releases.

## Main capabilities

- Separate encrypted SQLCipher database for every client/worksite organisation.
- Password at every new session, logout, 15-minute inactivity lock, and printable recovery key.
- Guided registration form matching the supplied two-page paper form, including cropped photos and unlimited repeating details.
- Duplicate blocking for nonblank registration number, Aadhaar, and UAN inside each organisation.
- Manual employee copy between organisations with a registration-number choice.
- Faithful registration PDF with blank applicant/authorised signature areas.
- Automatically rebuilt, unprotected Excel workbook after each data change. Salary sheets appear first; complete registration and repeating-detail sheets follow.
- Monthly payroll with manual days, OT hours, PH days, manual OT/PH/EPF/ESIC amounts, default and override rates, automatic calculations, confirmed overrides, and completion locking.
- Active/inactive history, performance reviews, client satisfaction, costs, KPI reports, and transparent three-month redeployability scoring.
- Guided Excel import, audit log, manual full backup, safe restore, and weekly backup reminder.
- English UI with light and dark themes.

## Run from source on Windows

Install 64-bit Python 3.12. Then double-click `scripts\run_dev.bat`, or use PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m eregistry
```

At first start, choose the main eRegistry data folder and create the password. Save the displayed recovery key somewhere separate from the computer.

## Tests

```powershell
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Tests cover password recovery, SQLCipher file encryption, duplicate protection, reference payroll calculations, exact workbook sheet ordering/content, and backup restore safety.

## Build the portable app and installer

1. Install Python 3.12 x64.
2. For the installer, install Inno Setup 6 and ensure `iscc.exe` is in `PATH`.
3. Run `scripts\build_portable.bat` for `dist\eRegistry\`.
4. Run `scripts\build_installer.bat` for `dist\installer\eRegistry-Setup-1.0.0.exe`.

The portable version is the entire `dist\eRegistry` folder, not just its EXE. Zip that folder for distribution.

Alternatively, place this source in GitHub and run **Build Windows release** under Actions (or push a `v*` tag). The included workflow tests the code and uploads both a portable ZIP and installer EXE as build artifacts. No application data or credentials are sent to that workflow.

## Important data behaviour

- Encrypted databases are the source of truth. Excel files are convenient read-only-by-policy views/exports; editing them never changes eRegistry.
- Excel files are intentionally unencrypted and stored under the selected main data folder.
- If Excel has an organisation workbook open during a save, Windows can prevent replacement. eRegistry reports this and retains database changes; close Excel and use **Sync Excel now**.
- Unsaved registration input survives the inactivity lock because the wizard stays open. Explicitly cancelling the wizard or closing the application discards it, as specified.
- Restore replaces current data only after creating a timestamped safety backup in the data folder's `backups` directory.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/MAINTENANCE.md](docs/MAINTENANCE.md), and [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) before modifying or releasing the application.
