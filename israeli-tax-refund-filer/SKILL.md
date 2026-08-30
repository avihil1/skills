---
name: israeli-tax-refund-filer
description: "Prepare and file an Israeli tax refund (Form 135) for salaried employees. Reads Form 106 + donation receipts from a local folder, calculates the refund, generates a detailed report and pre-filled PDF, and optionally auto-fills the SHAAM portal. Use when user says 'tax refund', 'hechzer mas', 'form 135', 'החזר מס', 'דוח מקוצר', or 'submit refund'. Do NOT use for self-employed (Form 1301), corporate (Form 1214), or VAT. For tax knowledge only (no filing), use israeli-tax-returns instead."
allowed-tools: Bash(python3:*), Bash(pip:*), Bash(open:*), Read, Write, Edit
---

# Israeli Tax Refund Filer

Automates Form 135 (דוח שנתי מקוצר) preparation and filing for salaried employees.

## Displaying Hebrew in chat (read this before printing anything)

The terminal picks a line's direction from its **first strong character**. One Hebrew word at the
start of a Markdown row flips the whole row RTL — columns swap sides, values detach from their
labels, and a mixed row like `| שכר 158/172 | 120,000 |` renders as garbage.

Rules for anything you print to the user:

- **Start every line and every table row with a Latin character.** English label first, Hebrew after.
  Put digits and field numbers in the Latin part and the Hebrew label last in the cell:
  `| Salary (158/172) — שכר | 120,000 |` renders correctly; `| שכר 158/172 | 120,000 |` does not.
- **Never paste the generated Hebrew `.md` report into chat.** It is Hebrew-first by design and is
  meant to be read in an editor. Summarize it in English instead and point at the file.
- Hebrew inside a value (employer name, institution) is fine — it is not the first character of the line.
- Do not "fix" it with spaces or by reversing strings; that corrupts the text. Reorder the line.

## Prerequisites

Install once (the skill checks and installs if missing):
```bash
pip install pdfplumber reportlab
```

For scanned PDFs (optional): `brew install tesseract` + `pip install pytesseract`

## Steps

### Step 1: Set up the data folder

Ask the user for:
- **Tax year** (default: previous calendar year)
- **Document folder** (default: `~/Documents/tax-refund-<YEAR>/`)

Verify the folder exists and list its contents. If empty, tell the user to place their documents there:
- Form 106 PDFs (from each employer)
- Donation receipts (PDFs **and** images — jpg, jpeg, bmp, gif)
- Bank account management confirmation (אישור ניהול חשבון) — required for refund deposit
- Brokerage statements (optional)
- Pension fund annual statements (optional)
- ID card / appendix documents (optional)

### Step 2: Parse documents

```bash
python3 ~/.claude/skills/israeli-tax-refund-filer/scripts/parse_documents.py "<FOLDER>" --year <YEAR> > /tmp/tax-parsed-<YEAR>.json
```

Review the output. Report to the user:
- How many documents were found and classified
- Any documents that were skipped and why
- If multiple Form 106s were found for the same person (summed)
- If a spouse was detected (second ID number)
- **Every donation receipt, one row each** — index, amount, date, institution. Never report only a
  count or a total: a receipt the parser mis-read or dropped is invisible in a total, and the user
  is the only one who can spot a missing one. Latin-first rows (see *Displaying Hebrew in chat*):

  | # | Amount | Date | Institution |
  |---|---|---|---|
  | 1 | 1,000 | 01/01/YYYY | עמותה לדוגמה |

- **Reconcile the file count.** `len(files)` must equal the number of non-hidden files in the
  folder. Anything missing means a classifier or glob dropped it silently.
- **If any key fields are zero or missing, ask the user to provide them**

Do not trust the parser's numbers. Before using them, dump the raw text of each Form 106
(`pdfplumber` / `pdftotext -layout`) and check every field against it. Fields observed to parse as
0 when the PDF clearly shows a value: `tax_withheld`, `pension_employee`, `life_insurance`,
`person_name`, `employer_name`. Also confirm `person_id` is the person's ת.ז and not the employer's
תיק ניכויים — both are 9 digits and sit near each other on the form.

Scanned PDFs and images are NOT parsed. Read each one yourself (render the PDF, view the image)
before concluding a document is irrelevant — donation receipts and insurance confirmations
routinely arrive as scans.

### Step 3: Confirm extracted data and collect missing details

First, **show the user what was already extracted** from the Form 106 documents:
- Person name and ID (from `person_name`, `person_id`)
- Employer name (from `employer_name`)
- Gross salary and tax withheld
- Nekudot zikui already applied by employer, in NIS (from `nekudot_zikui_employer_nis`)
- Pension contributions (employee + employer)
- Insured income (`insured_income`) — NOT the same as gross salary; uses the Form 106 value for fields 244/245
- Keren hishtalmut salary (`keren_hishtalmut_salary`) — fields 218/219
- Life insurance (`life_insurance`) — fields 036/081
- Section 45A credit (`section_45a_credit`)

Ask the user to **confirm** the extracted data is correct (especially the name, which may be concatenated without spaces in Hebrew PDFs).

Then ask **only** for details that are NOT in the Form 106:
- Gender (male/female)
- Children: count and ages
- Single parent? (yes/no)
- Oleh chadash? (which year of aliyah benefits, if any)
- Academic degree? (BA/MA/vocational, graduation year)
- 100% disability? (yes/no)
- Reserve service days in the tax year

Save as `/tmp/tax-personal-<YEAR>.json`:
```json
{
  "gender": "male",
  "children": [{"age": 3}, {"age": 7}],
  "single_parent": false,
  "oleh_year": null,
  "degree": "ba",
  "degree_graduation_year": 2020,
  "disability_100": false,
  "reserve_days": 0
}
```

### Step 4: Calculate tax

**First confirm the year's parameters exist and are current.** `references/tax_years.json` carries
per-year values that drift annually — brackets, `surtax_threshold`, `credit_point_value`,
`donation_floor`, `mashkoret_mezaka_monthly`. `calculate_tax.py` refuses to run when one is missing
rather than substituting a wrong basis, so a `tax_years.json is incomplete` error means look the
value up for that specific year. Never copy a figure across years and never guess one.

Cross-check two of them against documents you already have, which is cheaper than trusting the file:
`credit_point_value` = the 106's נקודות זיכוי value ÷ its point count, and `mashkoret_mezaka_monthly`
= (the 106's §45א credit ÷ 0.35 ÷ 0.07) ÷ 12.


```bash
python3 ~/.claude/skills/israeli-tax-refund-filer/scripts/calculate_tax.py /tmp/tax-parsed-<YEAR>.json /tmp/tax-personal-<YEAR>.json > /tmp/tax-calc-<YEAR>.json
```

**Sanity-check the result before showing it.** Recompute what the employer should have withheld —
brackets + surtax on salary alone, minus the credits the 106 says were applied — and compare with
the 106's actual withholding. An employer's payroll system is right far more often than this
calculator is; a gap over ~1% means the model is wrong, not the employer. This check is what
surfaces bracket-table and ceiling errors, which otherwise show up only as an implausibly large
refund.

Treat any refund over a few thousand ₪ as a red flag to investigate, not a result to report.

### Step 5: Generate report

```bash
python3 ~/.claude/skills/israeli-tax-refund-filer/scripts/generate_report.py /tmp/tax-calc-<YEAR>.json --output "<FOLDER>/refund-report-<YEAR>.md"
```

**Do not print the Markdown file into chat** — it is Hebrew-first and the terminal will scramble it
(see *Displaying Hebrew in chat*). Instead:

1. `open "<FOLDER>/refund-report-<YEAR>.md"` so the user reads it with correct RTL rendering.
2. Print an English-first summary table in chat, one row per figure, Latin label first:

   | Field | Value |
   |---|---|
   | Salary (158/172) — שכר | 120,000 |
   | Tax withheld (042) — מס שנוכה | 0 |
   | Donations credit — זיכוי תרומות | 3,500 |
   | **Expected refund** | **4,200** |

### Step 6: Generate PDF

```bash
python3 ~/.claude/skills/israeli-tax-refund-filer/scripts/generate_pdf.py /tmp/tax-calc-<YEAR>.json --output "<FOLDER>/form-135-filled-<YEAR>.pdf"
```

Open the PDF for the user: `open "<FOLDER>/form-135-filled-<YEAR>.pdf"`

### Step 7: Auto-fill SHAAM portal (optional)

Ask the user if they want to auto-fill the SHAAM portal.

If yes:
1. Ask the user to open Chrome with remote debugging (or reuse an existing session):
   ```
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
   ```
2. Tell the user to log in to https://secapp.taxes.gov.il/shdochshana1301/frmMenu.aspx
3. Connect via Playwright CDP (`pip install playwright && playwright install chromium`):
   ```python
   from playwright.sync_api import sync_playwright
   p = sync_playwright().start()
   browser = p.chromium.connect_over_cdp('http://localhost:9222')
   ```
4. The form has 4 tabs navigated via `__doPostBack('ctl00$ctl00$ContentUsersPage$ChildContent1$wcTabs1$LinkButtonN', '')`:
   - LinkButton0: פרטים אישיים (Personal details) — pre-filled from login
   - LinkButton1: פרטים כלליים (General details) — radio buttons for salaried employee
   - LinkButton2/4: פירוט הכנסות (Income / Form 1301) — the main data entry page
   - LinkButton8: נספחים (Appendices)

#### Tab navigation
- Direct `__doPostBack` bypasses client-side validation; use it to move between tabs.
- Before any navigation or save, clear stale validation state:
  ```js
  CNT_LAST_TEXTBOX_ERR = ''; Page_IsValid = true;
  ```

#### Personal details tab (LinkButton0)
Most fields are pre-filled from login. **Verify and fill:**
- **Email**: check that the email checkbox is checked and the email field is filled. If empty, ask the user for their email or read from previous filing data.
- **Phone (נייד)**: check that the phone checkbox is checked and mobile number is filled. If empty, ask the user or read from previous filing data.
These are required for the Tax Authority to send confirmation and correspondence.

#### General details tab (LinkButton1)

Nothing is pre-selected and **every group is a required field** — the form will not
validate with any left blank. Enumerate the groups rather than working from this list alone;
the form changes between tax years.

**Never assume an option's index.** Read each option's own `<label for=...>` text and match on
that. `_1` is "לא" in a כן/לא pair but "תושב חוזר ותיק" in the עולה groups — a positional guess
puts a wrong declaration on a tax return.

```js
[...document.querySelectorAll("input[type=radio]")].forEach(r=>{ /* group by id.replace(/_\d+$/,'') */ })
// then per option: document.querySelector("label[for='"+id+"']").innerText
```

For a salaried employee filing jointly:

| Group | Set to | Meaning |
|---|---|---|
| `rbl02Hul` | לא | No foreign-income annex ד' |
| `rbl02Hon` | כן **if** any capital gain is reported | Return includes a capital-gains annex |
| `rbl02DochAl` | הכנסותי והכנסות בן/בת זוגי | Joint return covering both incomes |
| `rbl03Meshutaf` | לא | Section 66(d) joint assessment = No |
| `rbl04OleBzr` | לא רלוונטי | **עולה חדש / תושב חוזר — registered spouse** |
| `rbl04OleBz` | לא רלוונטי | **עולה חדש / תושב חוזר — spouse** |
| `rbl02PrisaDmeyLeda` | לא | No maternity-pay spreading |
| `rbl02BaalShlita` / `rbl02BaalZhuyot` | לא | Not a controlling shareholder in a foreign body |
| `rbl03Shudar` | לא רלוונטי | Form 6111 not required |
| `rbl02Kupa` | לא | Operated no cash register (`הפעלתי קופה רושמת`) |
| `rbl02Nemanut` | לא רלוונטי | Not a trust settlor/beneficiary |
| `rbl02Meatim`, `rbl02KayemetPeula`, `rbl02KshurimBeHul`, `rbl02RevahimLoMehulakim`, `rbl02RevahimLoMehulakimNeches`, `rbl02SiyumBniya`, `rbl02HavatDaat`, `rbl02ChayavDivuach` | לא | Reportable-position / related-party declarations |

**עולה חדש groups** (`rbl04OleBzr` = registered spouse, `rbl04OleBz` = spouse): options are
`0`=עולה חדש, `1`=תושב חוזר ותיק, `2`=תושב חוזר, `3`=לא רלוונטי. Pick `3` unless the person is
inside their benefit window; an aliyah decades ago is לא רלוונטי. Choosing 0–2 reveals a
`תאריך הגעה לארץ` date field that must then be filled.

**Checkboxes on this tab** — enumerate these too; they are easy to miss because they sit
between the radio blocks:

- `chkHacnasaHayevet` — the **מס יסף** (surtax) declaration: *"בשנת המס היתה לי או לבן/בת זוגי
  הכנסה חייבת כהגדרתה בסעיף 121ב(ה) לפקודה העולה על <threshold> ש''ח"*. Check it whenever combined
  taxable income — **salary plus capital gains**, not salary alone — exceeds that year's threshold.
  Read the figure off the label on screen and compare against `surtax_threshold` in
  `references/tax_years.json`; **the threshold changes between years** (698,280 in 2023, 721,560 in
  2024–2025), so never carry a remembered number across tax years. If the label and the JSON
  disagree, the JSON is stale — fix it before trusting any computed figure, since the same
  threshold drives the surtax calculation. The portal may tick the box automatically once income
  fields are filled; verify rather than trust, and re-verify after every save.

**Leave unselected** (business-only, and they offer no "not relevant" option):
`rbl02HanhalatHeshb` (כפולה/חד-צידית) and `rbl02NihulSfarim` (ממוחשב/ידני). `rbl02BenZugi` is
disabled whenever `rbl02DochAl` = joint — its validator will not block.

**Re-verify this whole tab after any portal error or re-entry.** Radio selections are the first
thing lost when the session hiccups, and they fail silently — the tab still looks filled.

#### Income tab (LinkButton2/4) — field mapping
Fill from the **per-person Form 106 parsed data**, NOT from calculated totals:

| SHAAM Field | Form 106 Key | Description |
|-------------|-------------|-------------|
| `txt158` | primary `gross_salary` | Salary — registered spouse |
| `txt172` | spouse `gross_salary` | Salary — spouse |
| `txtMasNuka69Rashum` | primary `tax_withheld` | Tax withheld — registered (per-person) |
| `txtMasNuka69Bz` | spouse `tax_withheld` | Tax withheld — spouse (per-person) |
| `txt042` | sum of both | Tax withheld — total salary |
| `txtSeif69` | number of 106 forms | Number of Form 106 attached |
| `txt045` | primary `pension_employee` | Pension employee deposit — registered |
| `txt086` | spouse `pension_employee` | Pension employee deposit — spouse |
| `txt036` | primary `life_insurance` | Life insurance — registered |
| `txt081` | spouse `life_insurance` | Life insurance — spouse |
| `txt244` | primary `insured_income` | Insured income — registered (**NOT gross salary**) |
| `txt245` | spouse `insured_income` | Insured income — spouse (**NOT gross salary**) |
| `txt248` | primary `pension_employer` | Employer pension deposit — registered |
| `txt249` | spouse `pension_employer` | Employer pension deposit — spouse |
| `txt218` | primary `keren_hishtalmut_salary` | Keren hishtalmut salary — registered |
| `txt219` | spouse `keren_hishtalmut_salary` | Keren hishtalmut salary — spouse |

**Critical**: `txt244`/`txt245` (insured income) is the income insured for pension, NOT the gross salary. Use the `insured_income` value from the Form 106 parser.

#### Filling technique
- Use JavaScript `el.focus(); el.value = X; el.dispatchEvent(new Event('change', {bubbles: true})); el.blur()` to set values.
- Employer name fields (`txtMaavid1`, `txtMaavid2`) require a Hebrew first character — use employer names, not IDs.
- `txt037` (donations) is disabled/read-only. Use the donations wizard instead (see below).

#### Children wizard (nekudot zikui for children)
For married filers, run the wizard **twice** — once for each spouse:
1. **Registered spouse**: click `lnk260_190Help` (calls `showWizardYeladim('Bzr')`) — fills fields `txt260_*`
2. **Spouse**: click `lnk262_291Help` (calls `showWizardYeladim('BnBtZug')`) — fills fields `txt262_*`

Each wizard has 2 screens:
- **Screen 1**: select number of children (under 19), then for each child: select birth year from dropdown + select "ילד/ה בחזקתי" (in custody) radio button.
- **Screen 2**: auto-populated summary with disabled fields. Just click `btnIshur` (Confirm).

Both parents should receive credit for children aged 6-17 (1.0 point each). Forgetting the spouse wizard means losing those credits entirely.

**Important**: the `ddl024` / `ddl124` fields are for "חייל משוחרר" (discharged soldier mandatory service months) — NOT for reserve service (miluim). Do not confuse with reserve days.

#### Donations wizard
Click `lnkTrumot` (calls `showWizardTrumot('037','237')`) to open the wizard in `frmCst` iframe:
1. The wizard shows donations already reported to the Tax Authority — check the rows.
2. Fill `txt037` (total donations registered spouse) and `txt237` (total donations spouse) inside the wizard iframe.
3. Click `btnHaba` (Next), then `btnIshur` (Confirm) to transfer values to the main form.

**⚠ Donations field clearing bug**: `txt037`/`txt237` are disabled fields that get cleared by ANY postback — including other wizard confirmations and form saves. Always run the donations wizard **last** (after all other wizards), then save **immediately**. After save, verify `txt037` retained its value.

#### Recommended fill order
1. Personal details tab — verify email + phone
2. General details tab — radio buttons
3. Income tab — salary, tax, pension, insurance fields
4. Children wizard — registered spouse first (`Bzr`), then spouse (`BnBtZug`)
5. Donations wizard — **always last** (values clear on any postback)
6. Save immediately after donations, then **stop touching the form**

**"Last" means last, not "last in this pass."** After the donations save, going back to *any*
other tab — even just to tick one checkbox — wipes `txt037` again, because leaving a tab is a
postback. The failure is silent: the other tab saves fine, the donations field empties, and
nothing warns you.

So if you discover anything else that needs changing after donations are in:

1. Make that change first.
2. Re-run the donations wizard.
3. Save, and end there.

Treat the donations wizard as a commit you can only do once, at the very end. Before telling the
user the form is complete, re-read `txt037` one final time — a value you set earlier in the
session is not evidence it is still there.

**Children fields are NOT fragile this way.** `txt260_*` / `txt262_*` survive postbacks and
server errors normally, so an empty `txt260_6_17` means the wizard never ran, not that a postback
cleared it. Note that only the age brackets that apply get populated: with all children aged
6-17, `txt260_6_17` holds the count and `txt260Nolad` / `txt260_1_2` / `txt260_3` / `txt260_4_5`
are correctly empty — that is not a missing value.

#### Validate with בדיקת טופס before declaring the form done

Always click `#btnBdikatTofes` and read the verdict. Never report the form complete on the strength
of having filled the fields.

**Attach a dialog handler first.** Playwright auto-dismisses `window.alert`/`confirm`, so a popup
verdict disappears with no trace and the run looks clean:

```python
pg.on("dialog", lambda d: (captured.append(d.message), d.accept()))
pg.eval_on_selector('#btnBdikatTofes', "e=>e.click()")
```

**Read the verdict from the hidden state, not from scraped page text:**

| Read | Meaning |
|---|---|
| `hidHaveErr` | `"false"` = the form passed. This is the authoritative answer. |
| `txtErr1` | The blocking message, when there is one. Populated even when not rendered where a text scrape would find it. |
| `hidSumKodsError` | Field-total mismatch flag. |

**Do not read `errBcolor` or `hidErrCtlID` as errors.** `hidErrCtlID` is a *static registry* of every
control capable of showing an error, and dozens of fields carry the `errBcolor` class routinely — in
one real run 49 fields were pink while `hidHaveErr` was `false`. Counting pink fields reports
failures that do not exist.

**בדיקת טופס does NOT clear `txt037`** (verified), but navigating to another tab afterwards does. So
run it, and if you then move anywhere in the form, re-run the donations wizard before saving.

**A "cannot request a refund, income exceeds the threshold" verdict is not a form defect.** It means
the filer is above the refund-request ceiling and must file as an obligated filer with a תיק opened
at their פקיד שומה (number shown in the פרטי תיק header). No field edit clears it.

#### When the blocker is the filer's status, not the data

Some verdicts cannot be cleared by editing any field — the filer's *file type* is wrong, not their
numbers. The clearest example: `txtErr1` returning *"לא ניתן לבקש בקשה להחזר מס במקרה וההכנסה
החייבת גבוהה מ..."*. That means income exceeds the refund-request ceiling, so the short
refund-request route is closed and the person must file as an obligated filer with a proper תיק.

**Check for an existing פנייה before telling the user to open one.** They have very likely already
hit this and asked. Read `https://secapp.taxes.gov.il/sr-crm-pniyot/main/historyIncident` — the
same login already covers it — and report the inquiry number, date and status instead of sending
them to do work twice.

**Route for a new one:** אזור אישי → **הפניות שלי** → פנייה חדשה, category
**מס הכנסה > פתיחת או סגירת תיק ועדכון פרטים**. Quote the portal's exact error text in the body;
it identifies the problem to the assessor immediately.

**The "פתיחת תיק" tile in אזור אישי is a decoy here** — it opens only עוסק פטור, עסק זעיר or
rental-income files, none of which fit a salaried filer. Sending someone there wastes a round trip.

**The legal basis, useful if the assessor asks:** §131 requires an annual return from anyone liable
for the §121ב surtax — taxable income over the threshold — **even when the employer withheld
everything at source**. Salary plus capital gains both count toward it. This is the same condition
as the `chkHacnasaHayevet` checkbox.

**Fallback only if the פנייה stalls:** the פ"ש office named in the form's פרטי תיק header (code +
חוליה). Some offices additionally want **טופס 5329** (דו"ח פרטים אישיים והצהרה על מקורות הכנסה) as
the file-opening declaration. Do not submit 5329 or send the user to an office preemptively — the
פנייה is often sufficient, and filing the wrong instrument creates its own cleanup.

#### Capital-gains annex tab

Answering `rbl02Hon` = כן makes a **רווח הון** tab appear (`LinkButton4`) that was not in the tab strip
before. It holds `txtNumNispachim`, the `lnkRH` ("נספחי רווח הון") link and `ddlNispach` for building
נספח ג / טופס 1322, and caps transmission at 14 annexes. Filling it needs sale proceeds and cost
basis per sale — a §102 trustee statement or טופס 867 — which a Form 106 does not carry: the 106
reports only the net gain and the tax withheld.

#### Saving
- Save button: `page.click('#btnShmiraZemani')` (NOT `__doPostBack` which may lose disabled fields).
- After save, verify all fields retained their values — especially `txt037` (donations), `txt086`, `txt249` which can be cleared by postbacks. If `txt037` was cleared, re-run the donations wizard and save again.
- Success message: "הדו''ח נשמר בהצלחה – שמירה זמנית"

#### Document upload (מערכת צרופות)
After filling the form, navigate to the נספחים tab (LinkButton8) and click "העלאת נספחים" to enter the attachments system. Upload **all** files from the data folder — PDFs **and** images (jpg, jpeg, bmp, gif). The system accepts: xlsx, docx, jpeg, jpg, bmp, gif, pdf, csv. Max 30MB per file.
- Use the "הוספת מסמכים" link to open the bulk upload dialog ("הוספה מרובה של מסמכים").
- Use Playwright `page.expect_file_chooser()` with the Kendo upload button's hidden `input[type="file"]` — click via JS: find `.k-upload-button` with `offsetParent !== null` in the `.modal.fade.in`, then `input.click()`.
- Select **all** files in a **single** file chooser action (do NOT open a second chooser within the same dialog — this crashes the server).
- Click אישור to upload.
- Repeat the dialog if needed for additional files.
- Verify each file shows "נקלט בהצלחה".
- Click "סיום" when done.

5. **NEVER click Submit (btnShidur).** Tell the user: "All fields are filled. Review the form in the browser and submit manually when ready."

### Step 8: Summary

Report to the user:
- Expected refund (or balance owed)
- Files generated: report (.md) and PDF (.pdf)
- If Playwright was used: number of fields filled, screenshots taken
- Remind: "This is an estimate. The Tax Authority may adjust based on their records. Review all values before submitting."
