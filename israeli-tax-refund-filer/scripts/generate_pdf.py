#!/usr/bin/env python3
"""Generate a pre-filled Form 135 PDF from calculation results.

Usage: python3 generate_pdf.py <calculation_result.json> [--output form-135.pdf]
"""

import json
import sys

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
except ImportError:
    print("ERROR: reportlab not installed. Run: pip install reportlab", file=sys.stderr)
    sys.exit(1)

try:
    from bidi.algorithm import get_display
except ImportError:
    print("ERROR: python-bidi not installed. Run: pip install python-bidi", file=sys.stderr)
    sys.exit(1)


def fmt(n: float) -> str:
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.2f}"


def register_hebrew_font():
    """Try to register a Hebrew-capable font."""
    import os
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Hebrew.ttc",
        "/System/Library/Fonts/ArialHB.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("HebrewFont", path, subfontIndex=0))
                return "HebrewFont"
            except Exception:
                continue
    return "Helvetica"


def generate_pdf(calc: dict, output_path: str):
    """Generate a Form 135 summary PDF."""
    font_name = register_hebrew_font()
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4

    def bidi(text):
        return get_display(text)

    def draw_rtl(x, y, text, size=10):
        c.setFont(font_name, size)
        c.drawRightString(x, y, bidi(text))

    def draw_ltr(x, y, text, size=10):
        c.setFont(font_name, size)
        c.drawString(x, y, text)

    year = calc["tax_year"]
    summary = calc["summary"]
    person = calc.get("person") or {}
    nz = calc["nekudot_zikui"]
    dc = calc["donations_credit"]
    pc = calc["pension_credit"]

    y = height - 30*mm
    draw_rtl(width - 20*mm, y, f"טופס 135 — דוח שנתי מקוצר — שנת {year}", 16)
    y -= 10*mm

    draw_rtl(width - 20*mm, y, "פרטים אישיים", 12)
    y -= 7*mm
    draw_rtl(width - 20*mm, y, f"ת.ז.: {person.get('id', '________')}")
    y -= 6*mm
    draw_rtl(width - 20*mm, y, f"שם: {person.get('name', '________')}")
    y -= 10*mm

    draw_rtl(width - 20*mm, y, "הכנסות", 12)
    y -= 7*mm
    income = calc["income"]
    draw_rtl(width - 20*mm, y, f"שכר ברוטו שנתי: {fmt(income['gross_salary'])} ₪")
    y -= 6*mm
    draw_rtl(width - 20*mm, y, f"מס שנוכה במקור: {fmt(summary['total_tax_withheld'])} ₪")
    y -= 6*mm
    draw_rtl(width - 20*mm, y, f"מעסיקים: {', '.join(income['employers'])}")
    y -= 10*mm

    draw_rtl(width - 20*mm, y, "נקודות זיכוי", 12)
    y -= 7*mm
    for item in nz["breakdown"]:
        draw_rtl(width - 20*mm, y, f"{item['category']}: {item['points']} נקודות")
        y -= 5*mm
    draw_rtl(width - 20*mm, y, f"סה״כ: {nz['total_points']} נקודות = {fmt(nz['total_nis'])} ₪")
    y -= 10*mm

    draw_rtl(width - 20*mm, y, "תרומות מוכרות (סעיף 46)", 12)
    y -= 7*mm
    for d in dc["qualifying_donations"]:
        draw_rtl(width - 20*mm, y, f"{d.get('institution', '?')}: {fmt(d['amount'])} ₪")
        y -= 5*mm
    draw_rtl(width - 20*mm, y, f"זיכוי תרומות: {fmt(dc['credit'])} ₪")
    y -= 10*mm

    draw_rtl(width - 20*mm, y, "פנסיה (סעיף 45א)", 12)
    y -= 7*mm
    draw_rtl(width - 20*mm, y, f"הפקדת עובד: {fmt(pc['total_pension_employee'])} ₪")
    y -= 5*mm
    draw_rtl(width - 20*mm, y, f"זיכוי פנסיה: {fmt(pc['credit'])} ₪")
    y -= 10*mm

    cg = calc["capital_gains"]
    if cg["transactions"]:
        draw_rtl(width - 20*mm, y, "רווח הון", 12)
        y -= 7*mm
        draw_rtl(width - 20*mm, y, f"רווח/הפסד נטו: {fmt(cg['net_gain_loss'])} ₪")
        y -= 5*mm
        draw_rtl(width - 20*mm, y, f"מס רווח הון: {fmt(cg['tax'])} ₪")
        y -= 10*mm

    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(20*mm, y + 3*mm, width - 20*mm, y + 3*mm)
    y -= 2*mm
    draw_rtl(width - 20*mm, y, "שורה תחתונה", 14)
    y -= 8*mm
    draw_rtl(width - 20*mm, y, f"חבות מס נטו: {fmt(summary['net_tax_liability'])} ₪")
    y -= 6*mm
    draw_rtl(width - 20*mm, y, f"מס שנוכה במקור: {fmt(summary['total_tax_withheld'])} ₪")
    y -= 8*mm

    if summary["is_refund"]:
        c.setFillColor(colors.darkgreen)
        draw_rtl(width - 20*mm, y, f"החזר מס צפוי: {fmt(summary['refund_or_owed'])} ₪ ✓", 14)
    else:
        c.setFillColor(colors.red)
        draw_rtl(width - 20*mm, y, f"יתרה לתשלום: {fmt(abs(summary['refund_or_owed']))} ₪", 14)

    c.save()
    print(f"PDF written to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_pdf.py <calculation_result.json> [--output form-135.pdf]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        calc = json.load(f)

    output = "form-135-filled.pdf"
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]

    generate_pdf(calc, output)
