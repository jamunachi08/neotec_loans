"""Neotec Loans — posting. Journal Entries are built from loan_core lines,
recorded on the facility (Posted entries), and never posted twice: a period
is free again only if its entry was cancelled."""
from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate

from neotec_loans import loan_core as core

DT = "Finance Facility"


def _fac(name: str):
    if not frappe.has_permission(DT, "write", doc=name):
        frappe.throw(_("Not permitted to post for this facility."), frappe.PermissionError)
    return frappe.get_doc(DT, name)


def _as_dict(doc) -> dict:
    d = doc.as_dict()
    d["schedule"] = [r.as_dict() for r in doc.schedule]
    return d


def _already(doc, posting_type: str, key: str) -> str | None:
    for p in doc.postings:
        if p.posting_type == posting_type and p.period_key == key and p.journal_entry:
            if frappe.db.get_value("Journal Entry", p.journal_entry, "docstatus") != 2:
                return p.journal_entry
    return None


def _post(doc, posting_type: str, key: str, posting_date, lines, remark: str) -> str:
    done = _already(doc, posting_type, key)
    if done:
        frappe.throw(_("{0} for {1} is already posted: {2}.").format(_(posting_type), key, done))
    lines = [x for x in lines if flt(x[1]) or flt(x[2])]
    if not lines:
        frappe.throw(_("Nothing to post for {0}.").format(key))
    fac = _as_dict(doc)
    missing = core.required_accounts(fac, lines)
    if missing:
        labels = [frappe.get_meta(DT).get_label(m) for m in missing]
        frappe.throw(_("Set these accounts on the facility first: {0}.").format(", ".join(labels)))
    if not core.balanced(lines):
        frappe.throw(_("Internal error: entry does not balance."))
    rows = []
    for key_, dr, cr in lines:
        acc = fac[key_]
        row = {"account": acc, "debit_in_account_currency": flt(dr, 2), "credit_in_account_currency": flt(cr, 2)}
        if doc.cost_center:
            row["cost_center"] = doc.cost_center
        if frappe.db.get_value("Account", acc, "account_type") == "Payable":
            if not doc.lender_supplier:
                frappe.throw(_("Account {0} is a Payable account: set “Lender as supplier” on the facility.").format(acc))
            row.update({"party_type": "Supplier", "party": doc.lender_supplier})
        rows.append(row)
    je = frappe.get_doc({"doctype": "Journal Entry", "voucher_type": "Journal Entry", "company": doc.company,
                         "posting_date": getdate(posting_date), "accounts": rows,
                         "user_remark": f"{doc.facility_name} — {remark}"})
    je.insert()
    if doc.submit_entries:
        je.submit()
    doc.append("postings", {"posting_type": posting_type, "period_key": key, "posting_date": getdate(posting_date),
                            "amount": flt(sum(x[1] for x in lines), 2), "journal_entry": je.name})
    if doc.status == "Draft":
        doc.status = "Active"
    doc.save()
    return je.name


@frappe.whitelist()
def preview(name=None):
    """Month-by-month plan: profit and charge to recognise, and what is posted."""
    doc = frappe.get_doc(DT, name)
    fac = _as_dict(doc)
    profit, fee = core.profit_plan(fac), core.fee_plan(fac)
    posted = {p.period_key: p.journal_entry for p in doc.postings if p.posting_type == "Profit"}
    months = sorted(set(profit) | set(fee))
    return [{"month": m.isoformat(), "profit": profit.get(m, 0.0), "fee": fee.get(m, 0.0),
             "journal_entry": posted.get(m.strftime("%Y-%m"))} for m in months]


@frappe.whitelist(methods=["POST"])
def post_drawdown(name=None):
    doc = _fac(name)
    if not doc.disbursement_date or not flt(doc.principal):
        frappe.throw(_("Set the drawdown date and principal first."))
    return _post(doc, "Drawdown", "drawdown", doc.disbursement_date, core.lines_drawdown(_as_dict(doc)), _("drawdown"))


@frappe.whitelist(methods=["POST"])
def post_fee_payment(name=None):
    doc = _fac(name)
    if not flt(doc.fee_amount) or not doc.fee_paid_on:
        frappe.throw(_("Set the charge amount and the date it was paid."))
    return _post(doc, "Fee Payment", "fee", doc.fee_paid_on, core.lines_fee_payment(_as_dict(doc)),
                 _("facility charge paid"))


@frappe.whitelist(methods=["POST"])
def post_month(name=None, month_end=None):
    """Profit accrual / amortisation and charge amortisation for one month."""
    doc = _fac(name)
    me = core.month_end(core.d(month_end))
    lines = core.lines_month(_as_dict(doc), me)
    key = me.strftime("%Y-%m")
    return _post(doc, "Profit", key, me, lines, _("finance cost {0}").format(key))


@frappe.whitelist(methods=["POST"])
def post_repayment(name=None, row=None, posting_date=None):
    doc = _fac(name)
    r = next((x for x in doc.schedule if x.name == row), None)
    if not r:
        frappe.throw(_("Schedule row not found."))
    entry = _post(doc, "Repayment", str(r.due_date), posting_date or r.due_date,
                  core.lines_repayment(_as_dict(doc), r.as_dict()), _("instalment due {0}").format(r.due_date))
    frappe.db.set_value("Finance Facility Schedule", r.name, "repayment_entry", entry)
    return entry


@frappe.whitelist(methods=["POST"])
def run_month(company=None, month_end=None):
    """Month-end run across every active facility of the company: posts what
    is due and not yet posted; reports what was skipped and why."""
    me = core.month_end(core.d(month_end))
    out = []
    for f in frappe.get_all(DT, filters={"company": company, "status": ["!=", "Closed"]}, pluck="name",
                            order_by="facility_name asc"):
        doc = frappe.get_doc(DT, f)
        key = me.strftime("%Y-%m")
        if _already(doc, "Profit", key):
            out.append({"facility": f, "status": "already posted"})
            continue
        if not core.lines_month(_as_dict(doc), me):
            out.append({"facility": f, "status": "nothing due"})
            continue
        try:
            out.append({"facility": f, "status": "posted", "journal_entry": post_month(f, me.isoformat())})
        except Exception as e:
            frappe.db.rollback()
            out.append({"facility": f, "status": "error", "error": str(e)[:300]})
    return out


# ── workbook import ───────────────────────────────────────────────────────────
ACCOUNT_FIELDS = ("bank_account", "loan_payable_account", "finance_cost_account", "accrued_profit_account",
                  "deferred_finance_cost_account", "fee_expense_account", "prepaid_fee_account",
                  "input_vat_account", "cost_center", "lender_supplier")


@frappe.whitelist(methods=["POST"])
def import_workbook(file_url=None, company=None, term_treatment=None, short_treatment=None,
                    defaults=None, vat_rate=15, create=0):
    """Read the loan workbook and preview (create=0) or create (create=1)
    one Draft facility per loan / tranche / charge. Existing names are skipped."""
    import json

    from neotec_loans import workbook_import as wi
    if not frappe.has_permission(DT, "create"):
        frappe.throw(_("Not permitted to create facilities."), frappe.PermissionError)
    if not file_url or not company:
        frappe.throw(_("Attach the workbook and choose the company."))
    content = frappe.get_doc("File", {"file_url": file_url}).get_content()
    if isinstance(content, str):
        content = content.encode("latin-1")
    try:
        res = wi.parse(wi.read_rows(content), vat_rate=flt(vat_rate) or 15)
    except Exception as e:
        frappe.throw(_("Could not read the workbook: {0}").format(str(e)[:200]))
    defaults = json.loads(defaults) if isinstance(defaults, str) else (defaults or {})
    defaults = {k: v for k, v in defaults.items() if k in ACCOUNT_FIELDS and v}
    out, created, skipped = [], [], []
    for f in res["facilities"]:
        if f["facility_type"] == "Term Loan" and term_treatment:
            f["profit_treatment"] = term_treatment
        if f["facility_type"] == "Short-term Financing" and short_treatment:
            f["profit_treatment"] = short_treatment
        exists = bool(frappe.db.exists(DT, f["facility_name"]))
        out.append({"facility_name": f["facility_name"], "facility_type": f["facility_type"], "lender": f["lender"],
                    "principal": f.get("principal") or f.get("fee_amount"), "rows": len(f["schedule"]),
                    "first_month": f.get("first_month", ""), "treatment": f.get("profit_treatment", ""),
                    "check": f["check"], "exists": exists, "source_row": f.get("source_row")})
        if not int(create or 0):
            continue
        if exists:
            skipped.append(f["facility_name"])
            continue
        doc = frappe.new_doc(DT)
        doc.update({k: v for k, v in f.items() if k not in ("schedule", "sheet_months", "check", "source_row")})
        doc.update(defaults)
        doc.company = company
        doc.status = "Draft"
        for r in f["schedule"]:
            doc.append("schedule", r)
        doc.insert()
        created.append(doc.name)
    return {"facilities": out, "warnings": res["warnings"], "created": created, "skipped": skipped}
