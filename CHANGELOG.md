# Changelog

## 1.1.0 — Workbook importer
- Finance Facility list → **Import workbook**: reads the IRSAA LOAN layout, previews, and creates Draft facilities (term loan, each short-term tranche, each charge), skipping existing names.
- The treatment for term loans and short-term financings, the VAT rate and default accounts are chosen at import. The first accrual month and charge months are taken from the sheet.
- A gross charge and its net-of-VAT twin are detected and imported once.
- Every facility is self-checked against the sheet's monthly cells and marked exact, bank figures with sheet rounding, or different.
- On the IRSAA workbook: 12 facilities, all passing (9 exact; the ANB term loan and 2 others within the sheet's rounding).

## 1.0.0 — First release
Finance Facility with options for profit treatment, spreading, first month and charge VAT. Posting of drawdown, monthly accrual and amortisation, repayments and charge payments; month-end run; no double posting.
