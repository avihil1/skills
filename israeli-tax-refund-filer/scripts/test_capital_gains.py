#!/usr/bin/env python3
"""Self-check for the capital-gains and surtax logic.

Anchored on a real 2025 return whose numbers were verified against the Tax
Authority's own חישוב (frmResult.aspx): salary 855,764, three §102 sales with a
nominal gain of 136,563 and a real gain of 125,612 after the inflationary split.
The portal's figures were CG tax 31,403 and surtax 7,794.

Run: python3 scripts/test_capital_gains.py
"""
from calculate_tax import calculate_capital_gains, load_tax_year_data

TD = load_tax_year_data("2025")
SALARY = 855_764
NOMINAL = 136_563
REAL = 125_612


def surtax(taxable_income, capital_income):
    """Mirror of the surtax block in calculate_refund."""
    base = taxable_income + capital_income
    thr = TD["surtax_threshold"]
    if base <= thr:
        return 0.0
    tier1 = (base - thr) * TD["surtax_rate_active"]
    tier2 = max(0, capital_income - thr) * TD.get("surtax_rate_capital_extra", 0)
    return tier1 + tier2


def demo():
    # --- the 2% tier keys on capital income ALONE, not on the combined excess ---
    s = surtax(SALARY, REAL)
    assert abs(s - 7_794.39) < 0.5, f"surtax {s} != portal 7,794"
    # the old bug applied 2% to min(capital, excess), inventing ~2,731 of tax
    assert abs(s - (SALARY + REAL - TD["surtax_threshold"]) * 0.03) < 0.01, "tier2 must be 0 here"

    # it must still fire when capital income genuinely clears the threshold
    big = 900_000
    s_big = surtax(0, big)
    expected = (big - TD["surtax_threshold"]) * (
        TD["surtax_rate_active"] + TD["surtax_rate_capital_extra"])
    assert abs(s_big - expected) < 0.01, f"{s_big} != {expected}"

    # --- real gain is what gets taxed, and nominal input is flagged ---
    nominal = calculate_capital_gains([{"gain_loss": NOMINAL}], TD)
    assert nominal["basis"] == "nominal" and nominal["note"], "nominal must be flagged"
    assert abs(nominal["tax"] - NOMINAL * 0.25) < 0.01

    real = calculate_capital_gains(
        [{"gain_loss": NOMINAL, "real_gain": REAL}], TD)
    assert real["basis"] == "real" and real["note"] is None
    assert abs(real["tax"] - 31_403) < 1, f"{real['tax']} != portal 31,403"
    assert real["net_gain_loss"] == NOMINAL, "nominal gain still reported"

    # a loss carries forward and is never taxed
    loss = calculate_capital_gains([{"gain_loss": -5_000}], TD)
    assert loss["tax"] == 0 and loss["carry_forward_loss"] == 5_000

    print("ok: surtax tier2 gated on capital income alone; real gain taxed, "
          "nominal flagged as an upper bound")


if __name__ == "__main__":
    demo()
