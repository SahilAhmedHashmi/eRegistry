# Data dictionary

## Registration

The employee record covers registration number/date, category/designation, photograph, applicant and parent details, birth/appointment dates, calculated or manually overridden age, mother's details, birthplace, gender, marital status, nationality, blood group, identification marks, armed-forces/PME and gun-license details, Aadhaar, driving licence, certifications, languages, permanent/communication addresses, PAN, bank/branch/account/IFSC, EPFO/ESIC flags, UAN, ESIC number, contact numbers, active/inactive status, exit date/reason, and optional employee daily-wage override.

Work experience, education, nominees, and family members are one-to-many tables. The digital form allows additional rows; the PDF flows excess rows onto continuation pages through ReportLab's table pagination.

## Salary

Each organisation has unique Year + Month records. Entries link employees and include: inclusion flag, working days, separate OT hours and PH days, daily wage, working wages, manual OT/PH wages, bonus, gross salary, manual EPF/ESIC, advance, total deduction, net salary, client billing rate, billed revenue, 1–5 performance rating, notes, and recorded override fields.

The Excel salary sheet combines OT hours and PH days into the supplied `OT/PH` display column while retaining separate source values in the encrypted database.

## KPI definitions

| KPI | Definition |
|---|---|
| Daily labour rate | Wages per day by skill/category or employee/month override |
| Client billing rate | Daily client rate by organisation/category or employee/month override |
| Deployment rate | Active/deployed workforce compared with the relevant workforce pool |
| Salary expenditure | Sum of included gross salary entries |
| Revenue | Sum of included billed revenue entries |
| Profit margin | `(revenue - salaries - configured costs) / revenue × 100` |
| Retention | Employees present at period end divided by employees present at period start |
| Overtime | Separate recorded OT hours; PH days remain distinct internally |
| Performance | Manual 1–5 monthly score plus notes and attendance context |
| Client satisfaction | Manual monthly 1–5 organisation score plus notes |
| Data completeness | Active records missing contact, Aadhaar, bank account, IFSC, or permanent address |
| Skill contribution | Salary, revenue, and contribution grouped by category; highest revenue category is highlighted |
| Redeployability | Transparent weighted performance, attendance, skill-fit, and capped overtime score |

