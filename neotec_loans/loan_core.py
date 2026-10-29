"""Neotec Loans — calculations and journal lines. Pure: no site needed.

Every accounting choice is an option on the facility:
  profit_treatment  "Accrue monthly, pay with instalment"
                    "Deferred upfront, amortise monthly"   (Murabaha / Tawarruq)
  accrual_basis     "Equal amount per month" | "By actual days"
  first_month       "Month of drawdown (or previous due date)" | "Month after drawdown"
  fee_vat           "Amount includes VAT" | "Amount excludes VAT" | "No VAT"

Profit of each schedule row is spread over the months between the previous
due date (the drawdown for the first row) and its own due date — the method
of the client's workbook (e.g. a 1 March instalment accrues Dec, Jan, Feb).
"""
from __future__ import annotations

import calendar
import datetime as dt

ACCRUE = "Accrue monthly, pay with instalment"
DEFERRED = "Deferred upfront, amortise monthly"
EQUAL = "Equal amount per month"
DAYS = "By actual days"
AFTER = "Month after drawdown"


def d(x) -> dt.date:
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x)[:10])


def month_end(x: dt.date) -> dt.date:
    return x.replace(day=calendar.monthrange(x.year, x.month)[1])


def add_months(x: dt.date, n: int) -> dt.date:
    m = x.month - 1 + n
    y, m = x.year + m // 12, m % 12 + 1
    return x.replace(year=y, month=m, day=min(x.day, calendar.monthrange(y, m)[1]))


def months_in(start: dt.date, end: dt.date, after: bool = False) -> list[dt.date]:
    """Month-ends of the months the period [start, end) touches. With
    `after`, the start month is skipped (accrual begins the month after)."""
    out, cur = [], month_end(start)
    if after:
        cur = month_end(add_months(start.replace(day=1), 1))
    last = month_end(end - dt.timedelta(days=1)) if end > start else month_end(start)
    while cur <= last:
        out.append(cur)
        cur = month_end(add_months(cur.replace(day=1), 1))
    return out or [month_end(start)]


def r2(x: float) -> float:
    return round(x + 1e-9, 2)


def spread(amount: float, start, end, basis: str = EQUAL, after: bool = False) -> list[tuple[dt.date, float]]:
    """Spread `amount` over the period; the last month absorbs rounding so the
    pieces always add up to the amount exactly."""
    start, end = d(start), d(end)
    if basis != DAYS:
        # The workbook's rule: as many months as the calendar months between
        # the dates (6 Jan → 6 Apr = 3; 20 Nov → 20 May = 6), starting in the
        # first month (or the month after, when chosen).
        n = max(1, (end.year - start.year) * 12 + end.month - start.month)
        first = month_end(add_months(start.replace(day=1), 1 if after else 0))
        months = [month_end(add_months(first.replace(day=1), i)) for i in range(n)]
        raw = [amount / n] * n
        pieces = [r2(x) for x in raw[:-1]]
        pieces.append(r2(amount - sum(pieces)))
        return list(zip(months, pieces))
    months = months_in(start, end, after)
    if end > start:
        weights = []
        for me in months:
            seg_start = max(start, me.replace(day=1))
            seg_end = min(end, me + dt.timedelta(days=1))
            weights.append(max((seg_end - seg_start).days, 0))
        total = sum(weights) or 1
        raw = [amount * w / total for w in weights]
    else:
        raw = [amount / len(months)] * len(months)
    pieces = [r2(x) for x in raw[:-1]]
    pieces.append(r2(amount - sum(pieces)))
    return list(zip(months, pieces))


def profit_plan(fac: dict) -> dict[dt.date, float]:
    """Month-end → profit to recognise, from the schedule."""
    after = (fac.get("first_month") or "") == AFTER
    basis = fac.get("accrual_basis") or EQUAL
    prev = d(fac["disbursement_date"]) if fac.get("disbursement_date") else None
    out: dict[dt.date, float] = {}
    for row in sorted(fac.get("schedule") or [], key=lambda r: d(r["due_date"])):
        due = d(row["due_date"])
        start = prev or due
        profit = float(row.get("profit") or 0)
        if profit:
            for me, amt in spread(profit, start, due, basis, after and prev == d(fac.get("disbursement_date") or due)):
                out[me] = r2(out.get(me, 0.0) + amt)
        prev = due
    return dict(sorted(out.items()))


def fee_net(fac: dict) -> tuple[float, float]:
    """(expense, input VAT) of the facility charge."""
    amt = float(fac.get("fee_amount") or 0)
    rate = float(fac.get("vat_rate") or 0) / 100
    mode = fac.get("fee_vat") or "No VAT"
    if mode == "Amount includes VAT" and rate:
        net = r2(amt / (1 + rate))
        return net, r2(amt - net)
    if mode == "Amount excludes VAT" and rate:
        return amt, r2(amt * rate)
    return amt, 0.0


def fee_plan(fac: dict) -> dict[dt.date, float]:
    net, _vat = fee_net(fac)
    n = int(fac.get("fee_months") or 0)
    start = fac.get("fee_start_date") or fac.get("fee_paid_on")
    if not net or n <= 0 or not start:
        return {}
    s = d(start)
    end = add_months(s.replace(day=1), n)
    return {me: amt for me, amt in spread(net, s.replace(day=1), end, EQUAL, False)}


# ── journal lines: (account key, debit, credit) — accounts resolved by caller ──

def lines_drawdown(fac: dict) -> list[tuple[str, float, float]]:
    p = r2(float(fac.get("principal") or 0))
    lines = [("bank_account", p, 0.0), ("loan_payable_account", 0.0, p)]
    if (fac.get("profit_treatment") or ACCRUE) == DEFERRED:
        total = r2(sum(float(r.get("profit") or 0) for r in fac.get("schedule") or []))
        if total:
            lines += [("deferred_finance_cost_account", total, 0.0), ("loan_payable_account", 0.0, total)]
    return [x for x in lines if x[1] or x[2]]


def lines_month(fac: dict, me) -> list[tuple[str, float, float]]:
    me = month_end(d(me))
    lines = []
    profit = profit_plan(fac).get(me, 0.0)
    if profit:
        credit = "deferred_finance_cost_account" if (fac.get("profit_treatment") or ACCRUE) == DEFERRED \
            else "accrued_profit_account"
        lines += [("finance_cost_account", profit, 0.0), (credit, 0.0, profit)]
    fee = fee_plan(fac).get(me, 0.0)
    if fee:
        lines += [("fee_expense_account", fee, 0.0), ("prepaid_fee_account", 0.0, fee)]
    return lines


def lines_repayment(fac: dict, row: dict) -> list[tuple[str, float, float]]:
    principal, profit = r2(float(row.get("principal") or 0)), r2(float(row.get("profit") or 0))
    if (fac.get("profit_treatment") or ACCRUE) == DEFERRED:
        # profit was added to the payable at drawdown
        lines = [("loan_payable_account", r2(principal + profit), 0.0)]
    else:
        lines = [("loan_payable_account", principal, 0.0), ("accrued_profit_account", profit, 0.0)]
    lines.append(("bank_account", 0.0, r2(principal + profit)))
    return [x for x in lines if x[1] or x[2]]


def lines_fee_payment(fac: dict) -> list[tuple[str, float, float]]:
    net, vat = fee_net(fac)
    lines = [("prepaid_fee_account", net, 0.0)]
    if vat:
        lines.append(("input_vat_account", vat, 0.0))
    lines.append(("bank_account", 0.0, r2(net + vat)))
    return [x for x in lines if x[1] or x[2]]


def balanced(lines) -> bool:
    return abs(sum(x[1] for x in lines) - sum(x[2] for x in lines)) < 0.005


def required_accounts(fac: dict, lines) -> list[str]:
    return sorted({k for k, _d, _c in lines if not fac.get(k)})
