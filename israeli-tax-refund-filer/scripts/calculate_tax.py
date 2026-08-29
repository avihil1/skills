#!/usr/bin/env python3
"""Calculate Israeli tax refund based on parsed documents.

Usage: python3 calculate_tax.py <parsed_data.json> <personal_details.json>

personal_details.json format:
{
  "gender": "male" | "female",
  "children": [{"age": 3}, {"age": 7}, {"age": 15}],
  "single_parent": false,
  "oleh_year": null | 1 | 2 | 3,
  "degree": null | "ba" | "ma" | "vocational",
  "degree_graduation_year": null | 2023,
  "disability_100": false,
  "reserve_days": 0
}

Outputs JSON to stdout with full calculation breakdown.
"""

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent / "references"


def load_tax_year_data(year: str) -> dict:
    """Load tax parameters for the given year."""
    tax_years_path = SCRIPT_DIR / "tax_years.json"
    with open(tax_years_path) as f:
        all_data = json.load(f)

    if year not in all_data:
        available = [k for k in all_data if k.isdigit()]
        raise ValueError(f"Tax year {year} not found. Available: {available}")

    data = all_data[year]
    data["nekudot_zikui"] = all_data["nekudot_zikui"]
    return data


def calculate_nekudot_zikui(personal: dict, tax_data: dict, tax_year: int) -> dict:
    """Calculate total nekudot zikui points and NIS value."""
    nz = tax_data["nekudot_zikui"]
    point_value = tax_data["credit_point_value"]
    breakdown = []

    gender = personal.get("gender", "male")
    if gender == "female":
        points = nz["resident_female"]
        breakdown.append({"category": "תושבת ישראל", "points": points})
    else:
        points = nz["resident_male"]
        breakdown.append({"category": "תושב ישראל", "points": points})

    total_points = points

    for child in personal.get("children", []):
        age = child.get("age", 0)
        if age == 0:
            p = nz["child_born_this_year"]
            breakdown.append({"category": f"ילד שנולד השנה", "points": p})
        elif 1 <= age <= 5:
            p = nz["child_1_to_5"]
            breakdown.append({"category": f"ילד גיל {age}", "points": p})
        elif 6 <= age <= 17:
            p = nz["child_6_to_17"]
            breakdown.append({"category": f"ילד גיל {age}", "points": p})
        elif age == 18:
            p = nz["child_18"]
            breakdown.append({"category": f"ילד גיל 18", "points": p})
        else:
            continue
        total_points += p

    if personal.get("single_parent"):
        p = nz["single_parent"]
        breakdown.append({"category": "הורה יחיד", "points": p})
        total_points += p

    oleh_year = personal.get("oleh_year")
    if oleh_year == 1:
        p = nz["oleh_year_1"]
        breakdown.append({"category": "עולה חדש - שנה 1", "points": p})
        total_points += p
    elif oleh_year == 2:
        p = nz["oleh_year_2"]
        breakdown.append({"category": "עולה חדש - שנה 2", "points": p})
        total_points += p
    elif oleh_year == 3:
        p = nz["oleh_year_3"]
        breakdown.append({"category": "עולה חדש - שנה 3", "points": p})
        total_points += p

    degree = personal.get("degree")
    grad_year = personal.get("degree_graduation_year")
    if degree and grad_year:
        years_since = tax_year - grad_year
        if degree == "ba" or degree == "vocational":
            if grad_year >= 2023 and 0 <= years_since <= 2:
                p = nz["ba_degree"]
                breakdown.append({"category": f"תואר ראשון/מקצועי", "points": p})
                total_points += p
            elif 2014 <= grad_year < 2023 and years_since == 0:
                p = nz["ba_degree"]
                breakdown.append({"category": f"תואר ראשון/מקצועי", "points": p})
                total_points += p
        elif degree == "ma":
            if grad_year >= 2023 and 0 <= years_since <= 1:
                p = nz["ma_degree"]
                breakdown.append({"category": "תואר שני", "points": p})
                total_points += p
            elif 2014 <= grad_year < 2023 and years_since == 0:
                p = nz["ma_degree"]
                breakdown.append({"category": "תואר שני", "points": p})
                total_points += p

    if personal.get("disability_100"):
        p = nz["disability_100"]
        breakdown.append({"category": "נכות 100%", "points": p})
        total_points += p

    # Section 39b reserve credit: Amendment 283 applies from 2026 tax year (for 2025 service onward)
    reserve_days = personal.get("reserve_days", 0)
    if reserve_days > 0 and tax_year >= 2026:
        if reserve_days >= 60:
            p = nz["reserve_60_days"]
            breakdown.append({"category": f"מילואים ({reserve_days} ימים)", "points": p})
            total_points += p
        elif reserve_days >= 45:
            p = nz["reserve_45_days"]
            breakdown.append({"category": f"מילואים ({reserve_days} ימים)", "points": p})
            total_points += p
        elif reserve_days >= 20:
            p = nz["reserve_20_days"]
            breakdown.append({"category": f"מילואים ({reserve_days} ימים)", "points": p})
            total_points += p

    nis_value = total_points * point_value

    return {
        "breakdown": breakdown,
        "total_points": total_points,
        "point_value": point_value,
        "total_nis": nis_value,
    }


def calculate_income_tax(taxable_income: float, brackets: list) -> dict:
    """Calculate income tax using progressive brackets."""
    bracket_breakdown = []
    total_tax = 0
    remaining = taxable_income

    for bracket in brackets:
        bracket_from = bracket["from"]
        bracket_to = bracket["to"]
        rate = bracket["rate"]

        if remaining <= 0:
            break

        bracket_width = bracket_to - bracket_from + 1
        taxable_in_bracket = min(remaining, bracket_width)
        tax_in_bracket = taxable_in_bracket * rate

        bracket_breakdown.append({
            "from": bracket_from,
            "to": bracket_to,
            "rate": rate,
            "income_in_bracket": taxable_in_bracket,
            "tax": round(tax_in_bracket, 2),
        })

        total_tax += tax_in_bracket
        remaining -= taxable_in_bracket

    # Income above the highest bracket keeps being taxed at the top marginal rate.
    # Without this it fell off the table untaxed.
    if remaining > 0 and brackets:
        top = brackets[-1]
        tax_above = remaining * top["rate"]
        bracket_breakdown.append({
            "from": top["to"] + 1,
            "to": None,
            "rate": top["rate"],
            "income_in_bracket": remaining,
            "tax": round(tax_above, 2),
        })
        total_tax += tax_above

    return {
        "brackets": bracket_breakdown,
        "total_tax": round(total_tax, 2),
    }


def _selftest():
    """Top-rate continuation: income past the last bracket must still be taxed."""
    b = [{"from": 0, "to": 100, "rate": 0.1}, {"from": 101, "to": 200, "rate": 0.5}]
    assert calculate_income_tax(150, b)["total_tax"] == 34.6, "101*.1 + 49*.5"
    r = calculate_income_tax(300, b)                                 # 99 above the table
    assert r["total_tax"] == 109.6, r["total_tax"]                   # 10.1 + 50 + 99*.5
    assert r["brackets"][-1]["income_in_bracket"] == 99
    print("selftest ok")


def calculate_donations_credit(donations: list, taxable_income: float, tax_data: dict) -> dict:
    """Calculate Section 46 donation credit."""
    qualifying = [d for d in donations if d.get("section_46")]
    total_qualifying = sum(d["amount"] for d in qualifying)
    non_qualifying = [d for d in donations if not d.get("section_46")]

    floor = tax_data["donation_floor"]
    ceiling = taxable_income * tax_data["donation_ceiling_pct"]

    # The floor is a minimum-donation THRESHOLD, not a deductible: clear it and the
    # whole amount qualifies. Subtracting it understated the credit.
    eligible = total_qualifying if total_qualifying >= floor else 0
    eligible = min(eligible, ceiling)
    credit = eligible * tax_data["donation_credit_rate"]
    excess = max(0, (total_qualifying if total_qualifying >= floor else 0) - ceiling)

    return {
        "qualifying_donations": qualifying,
        "non_qualifying_donations": non_qualifying,
        "total_qualifying_amount": total_qualifying,
        "floor_applied": floor,
        "ceiling_applied": round(ceiling, 2),
        "eligible_amount": round(eligible, 2),
        "credit_rate": tax_data["donation_credit_rate"],
        "credit": round(credit, 2),
        "excess_carried_forward": round(excess, 2),
    }


def calculate_pension_credit(aggregated_106: dict, tax_data: dict) -> dict:
    """Calculate Section 45A pension credit."""
    total_pension_employee = aggregated_106.get("total_pension_employee", 0)
    # The 7% cap runs on the capped "משכורת מזכה", NOT on full salary. Using full
    # salary inflated the credit ~4x for high earners.
    monthly_cap = tax_data.get("mashkoret_mezaka_monthly")
    gross_salary = (monthly_cap * 12) if monthly_cap else aggregated_106.get("total_gross_salary", 0)

    ceiling = gross_salary * tax_data["pension_45a_employee_ceiling_pct"]
    qualifying = min(total_pension_employee, ceiling)
    credit = qualifying * tax_data["pension_45a_credit_rate"]

    return {
        "total_pension_employee": total_pension_employee,
        "salary_for_ceiling": gross_salary,
        "ceiling_pct": tax_data["pension_45a_employee_ceiling_pct"],
        "ceiling_amount": round(ceiling, 2),
        "qualifying_amount": round(qualifying, 2),
        "credit_rate": tax_data["pension_45a_credit_rate"],
        "credit": round(credit, 2),
    }


def calculate_insurance_credit(insurance: list, primary_id: str) -> dict:
    """Calculate Section 45 life insurance credit for private policies claimed by primary filer."""
    claimable = [i for i in insurance if i.get("claimed_by") == primary_id]
    total_premiums = sum(i["amount"] for i in claimable)
    credit_rate = 0.25
    credit = total_premiums * credit_rate

    return {
        "policies": claimable,
        "total_premiums": round(total_premiums, 2),
        "credit_rate": credit_rate,
        "credit": round(credit, 2),
    }


def calculate_capital_gains(brokerage: list, tax_data: dict) -> dict:
    """Calculate capital gains tax from brokerage transactions."""
    if not brokerage:
        return {"transactions": [], "net_gain_loss": 0, "tax": 0, "carry_forward_loss": 0}

    net = sum(t["gain_loss"] for t in brokerage)
    if net > 0:
        tax = net * tax_data["capital_gains_rate"]
        carry_forward = 0
    else:
        tax = 0
        carry_forward = abs(net)

    return {
        "transactions": brokerage,
        "net_gain_loss": round(net, 2),
        "tax": round(tax, 2),
        "carry_forward_loss": round(carry_forward, 2),
    }


def calculate_refund(parsed_data: dict, personal: dict) -> dict:
    """Main calculation: compute full tax refund."""
    year = parsed_data["tax_year"]
    tax_data = load_tax_year_data(year)

    agg = parsed_data.get("aggregated_106", {})
    primary_id = parsed_data["persons"]["primary"]["id"] if parsed_data["persons"]["primary"] else "unknown"
    primary_agg = agg.get(primary_id, {
        "total_gross_salary": 0, "total_tax_withheld": 0,
        "total_bituach_leumi": 0, "total_health_tax": 0,
        "total_pension_employee": 0, "total_pension_employer": 0,
        "employers": [],
    })

    taxable_income = primary_agg["total_gross_salary"]

    income_tax = calculate_income_tax(taxable_income, tax_data["brackets"])

    capital_gains = calculate_capital_gains(parsed_data.get("brokerage", []), tax_data)

    # Surtax base is ALL taxable income, salary + capital. From 2025 a second tier
    # adds 2% on the capital-source portion sitting above the same threshold.
    surtax = 0
    surtax_details = None
    capital_income = max(0, capital_gains["net_gain_loss"])
    surtax_base = taxable_income + capital_income
    threshold = tax_data["surtax_threshold"]
    if surtax_base > threshold:
        excess = surtax_base - threshold
        tier1 = excess * tax_data["surtax_rate_active"]
        capital_above = min(capital_income, excess)
        tier2 = capital_above * tax_data.get("surtax_rate_capital_extra", 0)
        surtax = tier1 + tier2
        surtax_details = {
            "threshold": threshold,
            "excess": round(excess, 2),
            "rate": tax_data["surtax_rate_active"],
            "tier1_amount": round(tier1, 2),
            "capital_above_threshold": round(capital_above, 2),
            "capital_extra_rate": tax_data.get("surtax_rate_capital_extra", 0),
            "tier2_amount": round(tier2, 2),
            "amount": round(surtax, 2),
        }

    nekudot = calculate_nekudot_zikui(personal, tax_data, int(year))

    donations_credit = calculate_donations_credit(
        parsed_data.get("donations", []), taxable_income, tax_data
    )

    pension_credit = calculate_pension_credit(primary_agg, tax_data)

    insurance_credit = calculate_insurance_credit(
        parsed_data.get("insurance", []), primary_id
    )

    gross_tax = income_tax["total_tax"] + surtax + capital_gains["tax"]

    # Use employer-applied credits as baseline (nekudot + pension/45A already in withholding).
    # Only add credits NOT applied by employer: donations and private insurance.
    employer_credits = primary_agg.get("total_nekudot_zikui_employer_nis", 0)
    employer_other_credits = 0
    for f106 in parsed_data.get("form_106", []):
        if f106.get("person_id") == primary_id:
            employer_other_credits += f106.get("section_45a_credit", 0)

    employer_total_credits = employer_credits + employer_other_credits
    additional_credits = donations_credit["credit"] + insurance_credit["credit"]
    total_credits = employer_total_credits + additional_credits
    net_tax = max(0, gross_tax - total_credits)

    total_withheld = primary_agg["total_tax_withheld"]
    refund = total_withheld - net_tax

    return {
        "tax_year": year,
        "person": parsed_data["persons"]["primary"],
        "spouse": parsed_data["persons"]["spouse"],
        "income": {
            "gross_salary": primary_agg["total_gross_salary"],
            "employers": primary_agg["employers"],
            "form_106_count": len([f for f in parsed_data["form_106"] if f["person_id"] == primary_id]),
        },
        "income_tax": income_tax,
        "surtax": surtax_details,
        "nekudot_zikui": nekudot,
        "donations_credit": donations_credit,
        "pension_credit": pension_credit,
        "insurance_credit": insurance_credit,
        "capital_gains": capital_gains,
        "summary": {
            "gross_tax": round(gross_tax, 2),
            "employer_credits": round(employer_total_credits, 2),
            "additional_credits": round(additional_credits, 2),
            "total_credits": round(total_credits, 2),
            "net_tax_liability": round(net_tax, 2),
            "total_tax_withheld": round(total_withheld, 2),
            "refund_or_owed": round(refund, 2),
            "is_refund": refund > 0,
        },
        "files_inventory": parsed_data["files"],
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 calculate_tax.py <parsed_data.json> <personal_details.json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        parsed = json.load(f)
    with open(sys.argv[2]) as f:
        personal = json.load(f)

    result = calculate_refund(parsed, personal)
    print(json.dumps(result, ensure_ascii=False, indent=2))
