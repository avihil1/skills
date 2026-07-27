#!/usr/bin/env python3
"""Parse tax documents from a local folder.

Usage: python3 parse_documents.py <folder_path> [--year YYYY]

Outputs JSON to stdout with structure:
{
  "files": [{"path": "...", "type": "form_106|donation|brokerage|pension|unknown", "status": "used|skipped", "reason": "..."}],
  "form_106": [{"person_id": "...", "employer": "...", "gross_salary": ..., "tax_withheld": ..., ...}],
  "donations": [{"institution": "...", "amount": ..., "date": "...", "section_46": true, "file": "..."}],
  "brokerage": [{"security": "...", "buy_date": "...", "sell_date": "...", "buy_price": ..., "sell_price": ..., "gain_loss": ...}],
  "persons": {"primary": {"id": "...", "name": "..."}, "spouse": {"id": "...", "name": "..."} | null}
}
"""

import json
import os
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)


def try_fix_encoding(text: str) -> str:
    """Fix garbled Hebrew text encoded as Latin-1 instead of CP1255."""
    high_latin = sum(1 for c in text if '\x80' <= c <= '\xff')
    hebrew = sum(1 for c in text if '֐' <= c <= '׿')
    if high_latin > hebrew and high_latin > 20:
        try:
            fixed = text.encode('latin-1').decode('cp1255')
            return fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return text


def reverse_hebrew_words(text: str) -> str:
    """Reverse visual-order Hebrew text to logical order."""
    hebrew = sum(1 for c in text if '֐' <= c <= '׿')
    if hebrew < 10:
        return text
    lines = text.split('\n')
    result = []
    for line in lines:
        words = line.split()
        reversed_words = [w[::-1] if any('֐' <= c <= '׿' for c in w) else w for w in words]
        result.append(' '.join(reversed_words))
    return '\n'.join(result)


def normalize_text(raw_text: str) -> str:
    """Normalize extracted PDF text: fix encoding, then reverse visual Hebrew if needed."""
    text = try_fix_encoding(raw_text)
    return reverse_hebrew_words(text)


def extract_text(pdf_path: str) -> str:
    """Extract all text from a PDF file (normalized to logical order)."""
    return extract_text_pair(pdf_path)[0]


def extract_text_pair(pdf_path: str):
    """Extract text from a PDF, returning (normalized_text, raw_text).

    Raw text preserves the original token order from pdfplumber, which keeps
    digit strings (IDs, tax-file numbers) intact even when the surrounding
    Hebrew is in visual order — normalization reverses such mixed tokens.
    """
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"WARNING: Could not read {pdf_path}: {e}", file=sys.stderr)
    return (normalize_text(text) if text else text, text)


def classify_document(text: str, filename: str) -> str:
    """Classify a document based on its text content."""
    if re.search(r'טופס\s*106|106\s*טופס|דוח\s*שנתי\s*למעביד|סיכום\s*שנתי', text):
        return "form_106"
    if re.search(r'סעיף\s*46|תרומה|קבלה|אישור\s*תרומה', text):
        return "donation"
    if re.search(r'867|רווח\s*הון|ניירות\s*ערך|דוח.*ברוקר', text):
        return "brokerage"
    if re.search(r'קופת\s*גמל|פנסי|ביטוח\s*מנהלים|קרן\s*השתלמות', text):
        return "pension"
    return "unknown"


def extract_form_106(text: str, filename: str, raw_text: str = "") -> dict:
    """Extract fields from a Form 106 PDF."""
    data = {
        "file": filename,
        "person_id": "",
        "person_name": "",
        "employer_name": "",
        "employer_id": "",
        "gross_salary": 0.0,
        "tax_withheld": 0.0,
        "bituach_leumi": 0.0,
        "health_tax": 0.0,
        "pension_employee": 0.0,
        "pension_employer": 0.0,
        "keren_hishtalmut_employee": 0.0,
        "keren_hishtalmut_employer": 0.0,
        "keren_hishtalmut_salary": 0.0,
        "insured_income": 0.0,
        "life_insurance": 0.0,
        "section_45a_credit": 0.0,
    }

    # Person name + ID: look for "NAMEת.זDIGITS" pattern (concatenated Hebrew)
    name_id_match = re.search(r'([֐-׿]+[֐-׿\s]*?)ת\.?ז\.?\s*:?\s*(\d{7,9})', text)
    if name_id_match:
        raw_name = name_id_match.group(1).strip()
        data["person_id"] = name_id_match.group(2).zfill(9)
        # Split concatenated Hebrew name (e.g. "כהנאהלל" → "כהנא הלל")
        if raw_name and not ' ' in raw_name and len(raw_name) > 3:
            data["person_name"] = raw_name
        else:
            data["person_name"] = raw_name
    else:
        id_match = re.search(r'ת\.?ז\.?\s*:?\s*(\d{7,9})', text)
        if id_match:
            data["person_id"] = id_match.group(1).zfill(9)
        else:
            company_match = re.search(r'חברה\s*:?\s*(\d{9})', text)
            company_id = company_match.group(1) if company_match else None
            for m in re.finditer(r'(\d{9})', text):
                if m.group(1) != company_id:
                    data["person_id"] = m.group(1)
                    break

    # Company/employer ID
    emp_id_match = re.search(r'חברה\s*:?\s*(\d+)', text)
    if emp_id_match:
        data["employer_id"] = emp_id_match.group(1)

    # Employer name: find "בע"מ" on a single line, skip processing companies
    for line in text.split('\n'):
        bam_match = re.search(r'(\S+בע"מ)', line)
        if bam_match:
            candidate = bam_match.group(1)
            if 'חילן' not in candidate and 'עיבוד' not in candidate:
                data["employer_name"] = candidate
                break
    if not data["employer_name"]:
        emp_name = re.search(r'שם\s*המעביד\s*:?\s*(.+?)(?:\n|$)', text)
        if emp_name:
            data["employer_name"] = emp_name.group(1).strip()

    # Nekudot zikui already applied by employer
    nz_match = re.search(r'([\d,]+)\s*ערך\s*נקודות\s*זיכוי|ערכנקודותזיכוי', text)
    if nz_match:
        try:
            data["nekudot_zikui_employer_nis"] = float(nz_match.group(1).replace(",", ""))
        except (ValueError, AttributeError):
            pass

    # Form 106 field codes (number BEFORE label pattern: "AMOUNT LABEL CODE")
    field_code_patterns = {
        "gross_salary": [r'([\d,]+)\s*משכורת\s*\d+'],
        "tax_withheld": [r'([\d,]+)\s*מס\s*הכנסה\s*\d+', r'([\d,]+)\s*מסהכנסה\s*\d+'],
        "bituach_leumi": [r'([\d,]+)\s*דמי\s*ביטוח\s*לאומי', r'([\d,]+)\s*דמיביטוחלאומי'],
        "health_tax": [r'([\d,]+)\s*דמי\s*ביטוח\s*בריאות', r'([\d,]+)\s*דמיביטוחבריאות'],
        "pension_employee": [r'([\d,]+)\s*ניכוי\s*לקופות', r'([\d,]+)\s*ניכוילקופות'],
    }

    for field, patterns in field_code_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value_str = match.group(1).replace(",", "")
                try:
                    data[field] = float(value_str)
                except ValueError:
                    pass
                break

    # Fallback: label THEN number patterns (standard format)
    if data["gross_salary"] == 0:
        fallback = {
            "gross_salary": [r'שכר\s*ברוטו.*?([\d,]+)', r'הכנסת?\s*עבודה.*?([\d,]+)'],
            "tax_withheld": [r'מס\s*שנוכה.*?([\d,]+)', r'ניכוי\s*מס.*?([\d,]+)'],
            "bituach_leumi": [r'ביטוח\s*לאומי.*?([\d,]+)'],
            "health_tax": [r'מס\s*בריאות.*?([\d,]+)', r'בריאות.*?([\d,]+)'],
        }
        for field, patterns in fallback.items():
            if data[field] == 0:
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        value_str = match.group(1).replace(",", "")
                        try:
                            data[field] = float(value_str)
                        except ValueError:
                            pass
                        break

    # Pension: sum קופ"ג לקצבה employer contributions
    pension_employer_total = 0
    for m in re.finditer(r'([\d,]+)\s+([\d,]+)\s+[\d.]+%\s+[\d,]+\s+קופ"?ג\s*לקצבה|קופ"גלקצבה', text):
        try:
            pension_employer_total += float(m.group(2).replace(",", ""))
        except (ValueError, AttributeError):
            pass
    if pension_employer_total > 0:
        data["pension_employer"] = pension_employer_total

    # Field-code anchors for both readable and garbled text.
    # These match "AMOUNT label CODE" where CODE is e.g. "219/218" or "245/244".
    field_code_extra = {
        "keren_hishtalmut_salary": r'219/218',
        "insured_income": r'245/244',
        "life_insurance": r'081\s*,\s*036|036\s*,\s*081',
    }
    for field, code_pat in field_code_extra.items():
        if data[field] == 0:
            for line in text.split('\n'):
                if re.search(code_pat, line):
                    m = re.match(r'\s*([\d,]+)', line)
                    if m:
                        try:
                            data[field] = float(m.group(1).replace(",", ""))
                        except ValueError:
                            pass
                    break

    # Structured "סעיף / שדה" table fallback (e.g. Clalit / מלם שכר payroll format).
    _apply_structured_106(text, raw_text, data)

    return data


def _amount_on_line(text: str, line_pattern: str) -> float | None:
    """Return the leading numeric amount of the first line matching line_pattern.

    Structured Form 106 rows put the amount first: "135,921 <label> [field code]".
    The Hebrew label words may be in visual (reversed) order, so callers should
    anchor on a field code or on individual words rather than a fixed phrase.
    """
    for line in text.split('\n'):
        if not re.search(line_pattern, line):
            continue
        m = re.match(r'\s*([\d,]+)(?:\.\d+)?\b', line)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _words_anywhere(*words: str) -> str:
    """Build a pattern requiring all words on a line, in any order."""
    return "".join(rf'(?=[^\n]*{re.escape(w)})' for w in words)


def _apply_structured_106(text: str, raw_text: str, data: dict) -> None:
    """Fill missing Form 106 fields from a labeled 'סעיף / שדה' table."""
    if not re.search(r'סעיף\s*/\s*שדה|שדה\s*/\s*סעיף', text):
        return

    # The structured table is authoritative for this format, so overwrite any
    # values the loose text patterns may have picked up from other lines.
    anchors = {
        # Field codes are the most reliable anchors (immune to Hebrew word order).
        "gross_salary": r'172/158',
        "pension_employee": r'086\s*,\s*045|045\s*,\s*086',
        "pension_employer": r'249/248',
        "keren_hishtalmut_salary": r'219/218',
        "insured_income": r'245/244',
        "life_insurance": r'081\s*,\s*036|036\s*,\s*081',
        # Word-set anchors for rows without a stable code.
        "tax_withheld": _words_anywhere('הכנסה', 'שנוכה', 'במקור'),
        "bituach_leumi": _words_anywhere('ביטוח', 'לאומי')
            + r'(?=[^\n]*\.\s*נ|[^\n]*נ\s*\.)',
        "health_tax": _words_anywhere('ביטוח', 'בריאות')
            + r'(?=[^\n]*\.\s*נ|[^\n]*נ\s*\.)',
    }
    for field, pattern in anchors.items():
        value = _amount_on_line(text, pattern)
        if value is not None:
            # Don't overwrite pension_employer from the detailed table sum
            # (field 249/248 on some 106s includes severance/pitsuyim).
            if field == "pension_employer" and data[field] > 0:
                continue
            data[field] = value

    # נקודות זיכוי credit applied by the employer (NIS). Anchor on "על פי" so we
    # don't match the month-column header row that also contains "נקודות".
    nz = _amount_on_line(text, _words_anywhere('זיכוי', 'נקודות', 'פי'))
    if nz is not None:
        data["nekudot_zikui_employer_nis"] = nz

    # Section 45A credit applied by employer.
    s45a = _amount_on_line(text, r'45\s*א|א\s*45')
    if s45a is not None:
        data["section_45a_credit"] = s45a

    # The header line carrying מעסיק: / עובד: is in visual (reversed) word order.
    # Reversing its words restores logical order for clean field extraction.
    header = None
    for line in text.split('\n'):
        if 'מעסיק' in line and 'עובד' in line and re.search(r'ת\.?\s*ז', line):
            header = ' '.join(line.split()[::-1])
            break

    if header:
        # "מעסיק:שרותי בריאות כללית" → employer name (up to end / next label).
        emp = re.search(r'מעסיק\s*:?\s*(.+?)\s*$', header)
        if emp and not data["employer_name"]:
            data["employer_name"] = emp.group(1).strip()

        # "עובד:בורשטיין כהנא אביגי[מספר]" → name (stop at מספר / ת.ז).
        nm = re.search(r'עובד\s*:?\s*(.+?)(?:מספר|\s*ת\.?\s*ז|$)', header)
        if nm:
            name = nm.group(1).strip()
            if name:
                data["person_name"] = name

    # Person ID from the raw text, where digit strings stay intact even when the
    # surrounding Hebrew is in visual order. Match "ת.ז." followed by a number,
    # allowing the number to appear before it (reversed line).
    if raw_text:
        rid = re.search(r'ת\.?\s*ז\.?\s*(\d{7,9})', raw_text)
        if not rid:
            rid = re.search(r'(\d{7,9})\.?\s*ז\.?\s*ת', raw_text)
        if rid:
            data["person_id"] = rid.group(1).zfill(9)


def _looks_like_year(value: float) -> bool:
    """True if a number looks like a calendar year (2020-2030) rather than an amount."""
    return value == int(value) and 2020 <= value <= 2030


def _normalize_amount_token(token: str) -> float | None:
    """Parse an amount token, repairing reversed digit strings like '00.001,1' -> 1100.00."""
    token = token.strip()
    for candidate in (token, token[::-1]):
        # Israeli receipts use ',' as thousands sep and '.' as decimal.
        if re.fullmatch(r'[\d,]+\.\d{1,2}', candidate) or re.fullmatch(r'[\d,]+', candidate):
            try:
                return float(candidate.replace(",", ""))
            except ValueError:
                continue
    return None


def extract_donation(text: str, filename: str) -> dict:
    """Extract fields from a donation receipt PDF."""
    data = {
        "file": filename,
        "institution": "",
        "amuta_id": "",
        "amount": 0.0,
        "date": "",
        "section_46_number": "",
        "section_46": False,
    }

    lines = [ln.strip() for ln in text.split('\n') if ln.strip()]

    # Section 46 recognition (handles both word orders)
    if re.search(r'סעיף\s*46|46\s*סעיף', text):
        data["section_46"] = True
        s46_num = re.search(r'(?:סעיף\s*46|46\s*סעיף).*?(\d{5,})', text)
        if s46_num:
            data["section_46_number"] = s46_num.group(1)

    # --- Amount ---
    # Prefer numbers adjacent to a currency marker (₪, ש"ח, NIS) or a total label (סה"כ),
    # filtering out year-like values. Fall back to a bare decimal near סה"כ/סכום.
    total_amounts = []
    currency = r'₪|ש"ח|ש״ח|NIS'
    patterns = [
        rf'(?:{currency})\s*([\d,]+\.?\d*)',
        rf'([\d,]+\.?\d*)\s*(?:{currency})',
        rf'(?:סה"כ|סה״כ|סכום)\s*:?\s*([\d,.]+)',
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            amount = _normalize_amount_token(m.group(1))
            if amount is not None and amount > 0 and not _looks_like_year(amount):
                total_amounts.append(amount)

    if not total_amounts:
        # Fallback for formats without a currency symbol (e.g. "73.00" possibly
        # followed by a garbled shekel glyph). Look for standalone decimals.
        for m in re.finditer(r'(?<!\d)(\d+\.\d{2})(?!\d)', text):
            amount = _normalize_amount_token(m.group(1))
            if amount is not None and amount > 0 and not _looks_like_year(amount):
                total_amounts.append(amount)

    if total_amounts:
        data["amount"] = max(total_amounts)

    # --- Amuta / registration number (ע.ר / ח.פ / מלכ"ר) ---
    # In normalized text the number may sit before OR after the marker, since the
    # source line was in visual (RTL) order.
    marker = r'ע\.?ר/ח\.?פ|ע\.?ר|ע"ר|ח\.?פ|מלכ"ר|עמותה/חל"צ'
    amuta_match = re.search(rf'(?:{marker})\s*[:/]?\s*(\d{{8,9}})', text)
    if not amuta_match:
        amuta_match = re.search(rf'(\d{{8,9}})\s*[-:]?\s*(?:{marker})', text)
    if amuta_match:
        data["amuta_id"] = amuta_match.group(1)

    # --- Date ---
    date_match = re.search(r'(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})', text)
    if date_match:
        data["date"] = date_match.group(1)

    # --- Institution name ---
    data["institution"] = _extract_institution(lines, text)

    return data


def _extract_institution(lines: list, text: str) -> str:
    """Extract the donating institution's name, excluding the donor and the signing service."""
    donor_markers = ('לכבוד', 'עבור')
    noise = ('smartbee', 'tranzila', 'ע"י', 'ונחתם', 'הופק', 'ממוחשב',
             'מסמך', 'דוא"ל', 'טלפון', 'דיגיטלית', 'page ', 'מקור')

    def is_noise(s: str) -> bool:
        low = s.lower()
        return any(n.lower() in low for n in noise)

    # 1. מאת: line names the institution (opposite of לכבוד:). In visual-order
    #    text the name can appear before OR after the מאת: marker.
    for i, ln in enumerate(lines):
        if 'מאת:' in ln:
            before, after = ln.split('מאת:', 1)
            for candidate in (before.strip(), re.split(r'לכבוד', after)[0].strip()):
                if len(candidate) > 2 and not is_noise(candidate) \
                        and not any(m in candidate for m in donor_markers) \
                        and any('֐' <= c <= '׿' for c in candidate):
                    return candidate
            # Institution may sit on the next line.
            for nxt in lines[i + 1:i + 3]:
                if any('֐' <= c <= '׿' for c in nxt) and not is_noise(nxt) \
                        and not any(m in nxt for m in donor_markers) \
                        and not re.search(r'ע\.?ר|ח\.?פ|מלכ"ר', nxt):
                    return nxt

    # 2. Line carrying an עמותה/חל"צ / ע.ר marker — the org name is usually the
    #    first Hebrew line(s) above it.
    org_marker_idx = None
    for i, ln in enumerate(lines):
        if re.search(r'עמותה/חל"צ|ע\.?ר/ח\.?פ|ע\.?ר\b|ע"ר|מלכ"ר', ln):
            org_marker_idx = i
            break
    if org_marker_idx is not None:
        collected = []
        for ln in lines[:org_marker_idx]:
            if not any('֐' <= c <= '׿' for c in ln):
                continue
            if is_noise(ln) or any(m in ln for m in donor_markers):
                continue
            collected.append(ln)
        if collected:
            name = collected[0]
            # Some org names spill onto a second short line (e.g. a surname).
            if len(collected) > 1 and len(collected[1]) <= 12:
                name = f"{name} ({collected[1]})"
            return name

    # 3. Fallback: first Hebrew, non-noise, non-donor line.
    for ln in lines:
        if any('֐' <= c <= '׿' for c in ln) and not is_noise(ln) \
                and not any(m in ln for m in donor_markers) and 2 < len(ln) < 80:
            return ln

    return ""


def extract_brokerage(text: str, filename: str) -> list:
    """Extract capital gains transactions from a brokerage statement."""
    transactions = []
    rows = re.findall(
        r'(\S+)\s+(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})\s+(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
        text
    )
    for row in rows:
        security, buy_date, sell_date, buy_price_s, sell_price_s = row
        buy_price = float(buy_price_s.replace(",", ""))
        sell_price = float(sell_price_s.replace(",", ""))
        transactions.append({
            "security": security,
            "buy_date": buy_date,
            "sell_date": sell_date,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "gain_loss": sell_price - buy_price,
            "file": filename,
        })
    return transactions


def parse_folder(folder_path: str, tax_year: str) -> dict:
    """Parse all documents in the folder and return structured data."""
    result = {
        "tax_year": tax_year,
        "folder": folder_path,
        "files": [],
        "form_106": [],
        "donations": [],
        "brokerage": [],
        "persons": {"primary": None, "spouse": None},
    }

    folder = Path(folder_path)
    pdf_files = sorted(folder.glob("*.pdf"))
    image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
    image_files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in image_exts
    )
    if not pdf_files and not image_files:
        print(f"WARNING: No PDF or image files found in {folder_path}", file=sys.stderr)

    # Image documents (e.g. photographed donation receipts) can't be text-parsed
    # here — flag them for manual data entry but keep them in the output.
    for img_path in image_files:
        result["files"].append({
            "path": img_path.name, "type": "unknown",
            "status": "manual", "reason": "Image file — requires manual data entry",
        })

    person_ids_seen = []

    for pdf_path in pdf_files:
        filename = pdf_path.name
        text, raw_text = extract_text_pair(str(pdf_path))

        if not text.strip():
            result["files"].append({
                "path": filename, "type": "unknown",
                "status": "skipped", "reason": "Could not extract text (scanned PDF — OCR not available)"
            })
            continue

        doc_type = classify_document(text, filename)

        if doc_type == "form_106":
            form_data = extract_form_106(text, filename, raw_text)
            result["form_106"].append(form_data)
            result["files"].append({"path": filename, "type": "form_106", "status": "used", "reason": ""})

            pid = form_data["person_id"]
            if pid and pid not in person_ids_seen:
                person_ids_seen.append(pid)
                person_info = {"id": pid, "name": form_data.get("person_name", "")}
                if result["persons"]["primary"] is None:
                    result["persons"]["primary"] = person_info
                else:
                    result["persons"]["spouse"] = person_info

        elif doc_type == "donation":
            donation_data = extract_donation(text, filename)
            result["donations"].append(donation_data)
            result["files"].append({"path": filename, "type": "donation", "status": "used", "reason": ""})

        elif doc_type == "brokerage":
            transactions = extract_brokerage(text, filename)
            result["brokerage"].extend(transactions)
            result["files"].append({"path": filename, "type": "brokerage", "status": "used", "reason": ""})

        elif doc_type == "pension":
            result["files"].append({"path": filename, "type": "pension", "status": "used", "reason": "Pension data supplementary"})

        else:
            result["files"].append({"path": filename, "type": "unknown", "status": "skipped", "reason": "Not recognized as a tax document"})

    # Aggregate Form 106 data per person
    aggregated_106 = {}
    for form in result["form_106"]:
        pid = form["person_id"] or "unknown"
        if pid not in aggregated_106:
            aggregated_106[pid] = {
                "person_id": pid,
                "person_name": form["person_name"],
                "employers": [],
                "total_gross_salary": 0,
                "total_tax_withheld": 0,
                "total_bituach_leumi": 0,
                "total_health_tax": 0,
                "total_pension_employee": 0,
                "total_pension_employer": 0,
                "total_nekudot_zikui_employer_nis": 0,
                "total_keren_hishtalmut_salary": 0,
                "total_insured_income": 0,
                "total_life_insurance": 0,
                "total_section_45a_credit": 0,
            }
        agg = aggregated_106[pid]
        agg["employers"].append(form["employer_name"] or form["file"])
        agg["total_gross_salary"] += form["gross_salary"]
        agg["total_tax_withheld"] += form["tax_withheld"]
        agg["total_bituach_leumi"] += form["bituach_leumi"]
        agg["total_health_tax"] += form["health_tax"]
        agg["total_pension_employee"] += form["pension_employee"]
        agg["total_pension_employer"] += form["pension_employer"]
        agg["total_nekudot_zikui_employer_nis"] += form.get("nekudot_zikui_employer_nis", 0)
        agg["total_keren_hishtalmut_salary"] += form.get("keren_hishtalmut_salary", 0)
        agg["total_insured_income"] += form.get("insured_income", 0)
        agg["total_life_insurance"] += form.get("life_insurance", 0)
        agg["total_section_45a_credit"] += form.get("section_45a_credit", 0)

    result["aggregated_106"] = aggregated_106

    # Presentation-friendly donation summary.
    donation_summary = []
    index = 1
    for d in result["donations"]:
        notes = []
        if d["amount"] == 0:
            notes.append("Amount not found — manual entry needed")
        elif _looks_like_year(d["amount"]):
            notes.append("Amount may be wrong")
        if not d.get("section_46"):
            notes.append("No Section 46 language found")
        if not d.get("institution"):
            notes.append("Institution not found")
        if not d.get("amuta_id"):
            notes.append("Amuta ID not found")
        donation_summary.append({
            "index": index,
            "file": d["file"],
            "institution": d.get("institution", ""),
            "amuta_id": d.get("amuta_id", ""),
            "amount": d["amount"],
            "date": d.get("date", ""),
            "section_46": d.get("section_46", False),
            "status": "parsed" if d["amount"] > 0 else "needs_review",
            "notes": "; ".join(notes),
        })
        index += 1

    for f in result["files"]:
        if f.get("status") == "manual":
            donation_summary.append({
                "index": index,
                "file": f["path"],
                "institution": "",
                "amuta_id": "",
                "amount": 0.0,
                "date": "",
                "section_46": False,
                "status": "manual",
                "notes": "Image file - manual entry needed",
            })
            index += 1

    result["donation_summary"] = donation_summary

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 parse_documents.py <folder_path> [--year YYYY]", file=sys.stderr)
        sys.exit(1)

    folder = sys.argv[1]
    year = "2024"
    if "--year" in sys.argv:
        idx = sys.argv.index("--year")
        if idx + 1 < len(sys.argv):
            year = sys.argv[idx + 1]

    if not os.path.isdir(folder):
        print(f"ERROR: {folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    result = parse_folder(folder, year)
    print(json.dumps(result, ensure_ascii=False, indent=2))
