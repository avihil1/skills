#!/usr/bin/env python3
"""Generate a Markdown tax refund report from calculation results.

Usage: python3 generate_report.py <calculation_result.json> [--output report.md]

If --output is omitted, prints to stdout.
"""

import json
import sys
from pathlib import Path


def fmt(n: float) -> str:
    """Format number as NIS with commas."""
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.2f}"


def generate_report(calc: dict) -> str:
    """Generate the full Markdown report."""
    lines = []
    year = calc["tax_year"]
    summary = calc["summary"]

    lines.append(f"# דוח החזר מס — שנת {year}")
    lines.append("")
    lines.append(f"**תאריך הפקה:** {__import__('datetime').date.today().isoformat()}")
    lines.append("")

    # 1. Document Inventory
    lines.append("## 1. מסמכים שנסרקו")
    lines.append("")
    lines.append("| # | קובץ | סוג | סטטוס | הערה |")
    lines.append("|---|-------|------|--------|------|")
    for i, f in enumerate(calc["files_inventory"], 1):
        status_map = {"used": "נקרא", "manual": "ידני", "skipped": "דולג"}
        status_he = status_map.get(f["status"], f["status"])
        type_map = {"form_106": "טופס 106", "donation": "קבלת תרומה", "brokerage": "דוח ברוקר", "pension": "פנסיה", "insurance": "ביטוח", "unknown": "לא מזוהה"}
        lines.append(f"| {i} | {f['path']} | {type_map.get(f['type'], f['type'])} | {status_he} | {f.get('reason', '')} |")
    lines.append("")

    # 2. Personal Details
    lines.append("## 2. פרטים אישיים")
    lines.append("")
    person = calc.get("person") or {}
    lines.append(f"- **ת.ז.:** {person.get('id', 'לא זוהה')}")
    lines.append(f"- **שם:** {person.get('name', 'לא זוהה')}")
    spouse = calc.get("spouse")
    if spouse:
        lines.append(f"- **בן/בת זוג ת.ז.:** {spouse.get('id', '')}")
        lines.append(f"- **שם בן/בת זוג:** {spouse.get('name', '')}")
    lines.append("")

    # 3. Income Summary
    lines.append("## 3. סיכום הכנסות")
    lines.append("")
    income = calc["income"]
    lines.append(f"**מספר טפסי 106:** {income['form_106_count']}")
    lines.append(f"**מעסיקים:** {', '.join(income['employers']) if income['employers'] else 'לא זוהה'}")
    lines.append("")
    lines.append("| פריט | סכום (₪) |")
    lines.append("|------|----------|")
    lines.append(f"| שכר ברוטו | {fmt(income['gross_salary'])} |")
    lines.append(f"| מס שנוכה במקור | {fmt(summary['total_tax_withheld'])} |")
    lines.append("")

    # 4. Donations
    lines.append("## 4. תרומות (סעיף 46)")
    lines.append("")
    dc = calc["donations_credit"]
    if dc["qualifying_donations"]:
        lines.append("| # | מוסד | סעיף 46 | סכום (₪) | תאריך | קובץ |")
        lines.append("|---|------|---------|----------|--------|------|")
        for i, d in enumerate(dc["qualifying_donations"], 1):
            lines.append(f"| {i} | {d.get('institution', '?')} | {d.get('section_46_number', '✓')} | {fmt(d['amount'])} | {d.get('date', '?')} | {d.get('file', '')} |")
        lines.append("")
    if dc["non_qualifying_donations"]:
        lines.append("**תרומות שלא מוכרות לסעיף 46:**")
        for d in dc["non_qualifying_donations"]:
            lines.append(f"- {d.get('institution', '?')}: {fmt(d['amount'])} ₪ ({d.get('file', '')})")
        lines.append("")

    lines.append("| פריט | סכום (₪) |")
    lines.append("|------|----------|")
    lines.append(f"| סה״כ תרומות מוכרות | {fmt(dc['total_qualifying_amount'])} |")
    lines.append(f"| רצפת מינימום | {fmt(dc['floor_applied'])} |")
    lines.append(f"| תקרה (30% מההכנסה) | {fmt(dc['ceiling_applied'])} |")
    lines.append(f"| סכום מזכה | {fmt(dc['eligible_amount'])} |")
    lines.append(f"| **זיכוי (35%)** | **{fmt(dc['credit'])}** |")
    if dc["excess_carried_forward"] > 0:
        lines.append(f"| עודף להעברה קדימה | {fmt(dc['excess_carried_forward'])} |")
    lines.append("")

    # 5. Pension
    lines.append("## 5. הפקדות פנסיוניות (סעיף 45א)")
    lines.append("")
    pc = calc["pension_credit"]
    lines.append("| פריט | סכום (₪) |")
    lines.append("|------|----------|")
    lines.append(f"| הפקדת עובד | {fmt(pc['total_pension_employee'])} |")
    lines.append(f"| תקרה ({pc['ceiling_pct']*100:.0f}% מהשכר) | {fmt(pc['ceiling_amount'])} |")
    lines.append(f"| סכום מזכה | {fmt(pc['qualifying_amount'])} |")
    lines.append(f"| **זיכוי (35%)** | **{fmt(pc['credit'])}** |")
    lines.append("")

    # 5b. Insurance
    ic = calc.get("insurance_credit")
    if ic and ic.get("policies"):
        lines.append("## 5b. ביטוח חיים/סיכון (סעיף 45)")
        lines.append("")
        lines.append("| פוליסה | מבטח | מבוטח | סכום (₪) |")
        lines.append("|--------|------|-------|----------|")
        for p in ic["policies"]:
            lines.append(f"| {p.get('type', 'ביטוח')} | {p.get('insurer', '?')} | {p.get('person_name', '?')} | {fmt(p['amount'])} |")
        lines.append("")
        lines.append(f"**זיכוי (25%):** {fmt(ic['credit'])} ₪")
        lines.append("")

    # 6. Capital Gains
    cg = calc["capital_gains"]
    if cg["transactions"]:
        lines.append("## 6. רווח הון מניירות ערך")
        lines.append("")
        lines.append("| נייר ערך | תאריך קנייה | תאריך מכירה | מחיר קנייה (₪) | מחיר מכירה (₪) | רווח/הפסד (₪) |")
        lines.append("|----------|-------------|-------------|----------------|----------------|---------------|")
        for t in cg["transactions"]:
            lines.append(f"| {t['security']} | {t['buy_date']} | {t['sell_date']} | {fmt(t['buy_price'])} | {fmt(t['sell_price'])} | {fmt(t['gain_loss'])} |")
        lines.append("")
        lines.append(f"**רווח/הפסד נטו:** {fmt(cg['net_gain_loss'])} ₪")
        lines.append(f"**מס רווח הון:** {fmt(cg['tax'])} ₪")
        if cg["carry_forward_loss"] > 0:
            lines.append(f"**הפסד להעברה:** {fmt(cg['carry_forward_loss'])} ₪")
        lines.append("")

    # 7. Nekudot Zikui
    lines.append("## 7. נקודות זיכוי")
    lines.append("")
    nz = calc["nekudot_zikui"]
    lines.append("| קטגוריה | נקודות |")
    lines.append("|---------|--------|")
    for item in nz["breakdown"]:
        lines.append(f"| {item['category']} | {item['points']} |")
    lines.append(f"| **סה״כ** | **{nz['total_points']}** |")
    lines.append("")
    lines.append(f"**ערך נקודה:** {fmt(nz['point_value'])} ₪")
    lines.append(f"**סה״כ זיכוי נקודות:** {fmt(nz['total_nis'])} ₪")
    lines.append("")

    # 8. Tax Calculation
    lines.append("## 8. חישוב מס")
    lines.append("")
    lines.append("### מדרגות מס")
    lines.append("")
    lines.append("| מדרגה | טווח הכנסה (₪) | שיעור | הכנסה במדרגה (₪) | מס (₪) |")
    lines.append("|-------|----------------|-------|-------------------|--------|")
    for b in calc["income_tax"]["brackets"]:
        lines.append(f"| {b['rate']*100:.0f}% | {fmt(b['from'])} - {fmt(b['to'])} | {b['rate']*100:.0f}% | {fmt(b['income_in_bracket'])} | {fmt(b['tax'])} |")
    lines.append(f"| | | **סה״כ** | | **{fmt(calc['income_tax']['total_tax'])}** |")
    lines.append("")

    if calc.get("surtax"):
        st = calc["surtax"]
        lines.append(f"### מס יסף")
        lines.append(f"- סף: {fmt(st['threshold'])} ₪")
        lines.append(f"- חריגה: {fmt(st['excess'])} ₪")
        lines.append(f"- שיעור: {st['rate']*100:.0f}%")
        lines.append(f"- **מס יסף: {fmt(st['amount'])} ₪**")
        lines.append("")

    # 9. Bottom Line
    lines.append("## 9. שורה תחתונה")
    lines.append("")
    lines.append("| פריט | סכום (₪) |")
    lines.append("|------|----------|")
    lines.append(f"| מס ברוטו (מדרגות + יסף + רווח הון) | {fmt(summary['gross_tax'])} |")
    lines.append(f"| זיכויים שהוחלו ע\"י המעסיק (נקודות + 45א) | -{fmt(summary.get('employer_credits', nz['total_nis'] + pc['credit']))} |")
    lines.append(f"| זיכוי תרומות (סעיף 46) | -{fmt(dc['credit'])} |")
    ic = calc.get("insurance_credit")
    if ic and ic["credit"] > 0:
        lines.append(f"| זיכוי ביטוח חיים (סעיף 45) | -{fmt(ic['credit'])} |")
    lines.append(f"| **חבות מס נטו** | **{fmt(summary['net_tax_liability'])}** |")
    lines.append(f"| מס שנוכה במקור | {fmt(summary['total_tax_withheld'])} |")
    lines.append("")

    if summary["is_refund"]:
        lines.append(f"### **החזר מס צפוי: {fmt(summary['refund_or_owed'])} ₪** ✅")
    else:
        lines.append(f"### **יתרה לתשלום: {fmt(abs(summary['refund_or_owed']))} ₪** ⚠️")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_report.py <calculation_result.json> [--output report.md]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        calc = json.load(f)

    report = generate_report(calc)

    output_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report written to {output_path}", file=sys.stderr)
    else:
        print(report)
