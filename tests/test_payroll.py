from eregistry.services.payroll_service import calculate_entry


def test_salary_calculation_matches_reference_rules():
    result = calculate_entry(
        {
            "working_days": 31,
            "wages_per_day": 424.34,
            "ot_ph_wages": 0,
            "bonus": 0,
            "epf_deduction": 1579,
            "esic_deduction": 99,
            "advance": 0,
            "client_billing_rate": 500,
        }
    )
    assert result["working_day_wages"] == 13155
    assert result["gross_salary"] == 13155
    assert result["total_deduction"] == 1678
    assert result["net_salary"] == 11477
    assert result["billed_revenue"] == 15500


def test_confirmed_override_is_preserved():
    result = calculate_entry(
        {"working_days": 10, "wages_per_day": 100, "working_day_wages": 950}, {"working_day_wages"}
    )
    assert result["working_day_wages"] == 950
