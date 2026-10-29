# Neotec Loans

Loan and financing schedules for ERPNext, with month-end profit/interest accrual, deferred-cost amortisation, facility-charge amortisation, and repayment Journal Entries. It works on Frappe/ERPNext v15 and v16.

## Setting up a facility (Accounting → Finance Facility)
Create one **Finance Facility** per loan or tranche:

| Your workbook | Facility | Type | Schedule |
|---|---|---|---|
| Arab National Bank (rows 3–14) | 1 | Term Loan | 12 rows (due date, principal, interest) |
| Riyad Bank (rows 21–25) | 1 per tranche | Short-term Financing | 1 row (maturity, principal, profit) |
| Manafea (rows 26–29) | 1 per tranche | Short-term Financing | 1 row |
| Facility charges (rows 33–35) | the charge fields on a facility, or a separate facility | Facility Charge | — |

The schedule grid supports **Download / Upload** (Excel), so rows can be pasted from the bank's schedule.

## Importing the loan workbook (Finance Facility list → Import workbook)
Attach the workbook in the IRSAA LOAN layout. Choose the company, the treatment for term loans and for short-term financings, the VAT rate, and optionally default accounts. Press **Preview**; nothing is created until you press **Create facilities**.

What the importer does:
- **Finds the blocks by content, not fixed row numbers:**
  - the term loan: rows with a due date, principal and interest, grouped per lender into one facility with its full schedule;
  - the short-term tranches: below the "Financing Date / Payment Date" header, one facility per tranche;
  - the facility charges: rows labelled "…Charges".
- **Takes options from the sheet:**
  - a tranche whose first monthly figure falls after its drawdown month gets "Month after drawdown";
  - a charge's months and start come from its monthly cells.
- **Detects a gross-and-net pair:** a charge row equal to another divided by (1 + VAT) is the same charge net of VAT. It is imported once, as "Amount includes VAT", with a note. A charge without a net twin is imported as "No VAT", because the sheet amortises its full amount; the note says so.
- **Self-checks every facility** against the sheet's monthly cells:
  - **matches sheet:** every month agrees;
  - **bank figures; sheet rounding:** every month is within 0.25 and the totals equal the bank's interest column. On the IRSAA workbook the sheet's grid totals 103,420.24 against the bank's 103,421.96, so the tool accrues the bank's figure and the accrued account clears to zero at each payment;
  - **check:** a real difference; review before posting.
- **Creates facilities as Draft:** names that already exist are skipped, so importing twice is harmless. Set "Charge paid on" on charge facilities before posting their payment.

## Options (every accounting choice is a setting)

| Setting | Choices | Effect |
|---|---|---|
| Profit / interest treatment | **Accrue monthly, pay with instalment** | Monthly: Dr Finance cost / Cr Accrued profit. Instalment: Dr Loan payable + Dr Accrued profit / Cr Bank |
| | **Deferred upfront, amortise monthly** (Murabaha / Tawarruq) | Drawdown: also Dr Deferred finance cost / Cr Loan payable (total profit). Monthly: Dr Finance cost / Cr Deferred finance cost. Instalment: Dr Loan payable (principal + profit) / Cr Bank |
| Spread profit | **Equal amount per month** | The workbook's rule: as many months as the calendar months between the dates (6 Jan → 6 Apr = 3) |
| | **By actual days** | Weighted by the days falling in each month |
| First accrual month | Month of drawdown (or previous due date) / Month after drawdown | Where the first instalment's spread starts |
| VAT on the charge | Amount includes VAT / excludes VAT / No VAT, plus the VAT rate | Payment: Dr Prepaid charges (net) + Dr Input VAT / Cr Bank. Monthly: Dr Facility charges / Cr Prepaid charges |
| Submit journal entries | off / on | Off creates drafts for review |

Each instalment's profit is spread over the months between the previous due date (the drawdown for the first instalment) and its own due date. With the workbook's figures this reproduces:
- **ANB:** 5,475.75 for Dec–Feb, then 4,860.94;
- **Riyad:** 7,916.58 a month for the 6 Jan tranche;
- **Manafea:** 2,858.33 a month for six months;
- **Riyad charge:** 241,500 incl. VAT = 210,000 expense + 31,500 input VAT, 17,500 a month.

## Posting (Loan menu on the facility)
- **Preview plan:** each month's profit and charge amortisation, and what is already posted.
- **Postings:** Post drawdown · Post charge payment · Post month (any month-end) · Post repayment (choose the instalment and the payment date).
- **Run month-end (all facilities):** posts the month for every open facility of the company and reports posted, already posted, nothing due or errors.

Every posting is recorded under **Posted entries**, and the same period is never posted twice. Cancelling a Journal Entry frees that period to be posted again. If an account is missing, the posting stops and names it before anything is created. A Payable account uses **Lender as supplier** as the party.

## Permissions
Accounts Manager and System Manager set up facilities and post. Accounts User can read.

## Tests
`python -m pytest neotec_loans/tests` runs 19 tests: the workbook's figures, every option combination balancing, the deferred cost clearing to zero, POST-only endpoints, and the importer (on a synthetic workbook in the same layout).
