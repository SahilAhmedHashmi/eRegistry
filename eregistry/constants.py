from __future__ import annotations

APP_NAME = "eRegistry"
APP_VERSION = "1.0.0"
DEFAULT_KPI_WEIGHTS = {
    "performance": 0.40,
    "attendance": 0.30,
    "skill_fit": 0.20,
    "overtime": 0.10,
}
DEFAULT_OT_HEALTHY_CAP = 32.0
SESSION_TIMEOUT_MINUTES = 15
LABOUR_CATEGORIES = ["Skilled", "Semi-skilled", "Unskilled"]
GENDERS = ["Male", "Female", "Other", "Prefer not to say"]
MARITAL_STATUSES = ["Unmarried", "Married", "Other"]

SALARY_HEADERS = [
    "S.No.",
    "Designation",
    "Name",
    "Reg No.",
    "Bank Name",
    "Account Number",
    "IFSC Code",
    "Working Days",
    "OT/PH",
    "Wages Per Day",
    "Working Day Wages",
    "OT/PH Wages",
    "Bonus",
    "Gross Salary",
    "EPF @12%",
    "ESIC @0.75%",
    "Advance",
    "Total Deduction",
    "Net Salary",
    "Signature",
    "Mobile No.",
    "Aadhaar No.",
    "UAN No.",
    "ESIC No.",
]
