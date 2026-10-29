"""Neotec Loans — calculations checked against the client's workbook
(IRSAA LOAN), and every option combination checked to balance."""
import datetime as dt
import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import loan_core as c  # noqa: E402

ANB = {"disbursement_date": "2025-12-25", "principal": 444648, "schedule": [
    {"due_date": "2026-03-01", "principal": 37053, "profit": 16427.26},
    {"due_date": "2026-06-01", "principal": 37053, "profit": 14582.83},
    {"due_date": "2026-09-01", "principal": 37053, "profit": 13300.00}]}


def mon(plan):
    return {m.strftime("%Y-%m"): v for m, v in plan.items()}


class Workbook(unittest.TestCase):
    """Figures from the sheet: rows 15, 21, 23, 26, 35."""

    def test_anb_quarterly_interest_accrues_over_the_quarter_before(self):
        p = mon(c.profit_plan(ANB))
        self.assertEqual([p["2025-12"], p["2026-01"]], [5475.75, 5475.75])        # row 15, Dec–Feb
        self.assertEqual([p["2026-03"], p["2026-04"]], [4860.94, 4860.94])        # Mar–May
        self.assertAlmostEqual(sum(c.profit_plan(ANB).values()), 16427.26 + 14582.83 + 13300.00, places=2)

    def test_riyad_90_day_tranches(self):
        p = mon(c.profit_plan({"disbursement_date": "2026-01-06",
                               "schedule": [{"due_date": "2026-04-06", "profit": 23749.73}]}))
        self.assertEqual(list(p), ["2026-01", "2026-02", "2026-03"])            # row 23: I, J, K
        self.assertEqual(p["2026-01"], 7916.58)
        p = mon(c.profit_plan({"disbursement_date": "2025-11-19", "first_month": c.AFTER,
                               "schedule": [{"due_date": "2026-02-17", "profit": 23987.64}]}))
        self.assertEqual((list(p), p["2025-12"]), (["2025-12", "2026-01", "2026-02"], 7995.88))   # row 21

    def test_manafea_six_months(self):
        p = mon(c.profit_plan({"disbursement_date": "2025-11-20", "first_month": c.AFTER,
                               "schedule": [{"due_date": "2026-05-20", "profit": 17150}]}))
        self.assertEqual((len(p), p["2025-12"], round(sum(p.values()), 2)), (6, 2858.33, 17150.0))   # row 26

    def test_riyad_charge_vat_split_and_amortised(self):
        fee = {"fee_amount": 241500, "fee_vat": "Amount includes VAT", "vat_rate": 15, "fee_months": 12,
               "fee_start_date": "2026-01-01"}
        self.assertEqual(c.fee_net(fee), (210000.0, 31500.0))                       # rows 34/35
        plan = c.fee_plan(fee)
        self.assertEqual((len(plan), set(plan.values())), (12, {17500.0}))


class Options(unittest.TestCase):
    def test_pieces_always_add_up(self):
        for basis, after in itertools.product((c.EQUAL, c.DAYS), (False, True)):
            parts = c.spread(10000.01, "2026-01-17", "2026-07-03", basis, after)
            self.assertAlmostEqual(sum(a for _m, a in parts), 10000.01, places=2, msg=(basis, after))

    def test_actual_days_weights(self):
        parts = dict(c.spread(9000, "2026-01-01", "2026-04-01", c.DAYS))
        self.assertEqual([round(v) for v in parts.values()], [3100, 2800, 3100])   # 31 / 28 / 31 of 90 days

    def test_vat_options(self):
        base = {"fee_amount": 1000, "vat_rate": 15}
        self.assertEqual(c.fee_net({**base, "fee_vat": "Amount excludes VAT"}), (1000, 150.0))
        self.assertEqual(c.fee_net({**base, "fee_vat": "No VAT"}), (1000, 0.0))

    def test_treatments(self):
        acc = {**ANB, "profit_treatment": c.ACCRUE}
        dfr = {**ANB, "profit_treatment": c.DEFERRED}
        self.assertEqual(len(c.lines_drawdown(acc)), 2)
        self.assertIn(("deferred_finance_cost_account", 44310.09, 0.0), c.lines_drawdown(dfr))
        self.assertEqual(c.lines_month(acc, "2025-12-31")[1][0], "accrued_profit_account")
        self.assertEqual(c.lines_month(dfr, "2025-12-31")[1][0], "deferred_finance_cost_account")
        row = ANB["schedule"][0]
        self.assertEqual(c.lines_repayment(acc, row)[1], ("accrued_profit_account", 16427.26, 0.0))
        self.assertEqual(c.lines_repayment(dfr, row)[0], ("loan_payable_account", 53480.26, 0.0))

    def test_every_combination_balances(self):
        fee = {"fee_amount": 241500, "fee_vat": "Amount includes VAT", "vat_rate": 15, "fee_months": 12,
               "fee_start_date": "2025-12-01"}
        for tr, basis, first, vat in itertools.product((c.ACCRUE, c.DEFERRED), (c.EQUAL, c.DAYS),
                                                       ("Month of drawdown (or previous due date)", c.AFTER),
                                                       ("Amount includes VAT", "Amount excludes VAT", "No VAT")):
            f = {**ANB, **fee, "profit_treatment": tr, "accrual_basis": basis, "first_month": first, "fee_vat": vat}
            for lines in [c.lines_drawdown(f), c.lines_fee_payment(f), c.lines_month(f, "2026-01-31"),
                          *[c.lines_repayment(f, r) for r in f["schedule"]]]:
                self.assertTrue(c.balanced(lines), (tr, basis, first, vat, lines))

    def test_deferred_balance_clears_to_zero(self):
        f = {**ANB, "profit_treatment": c.DEFERRED}
        bal = sum(d_ - cr for k, d_, cr in c.lines_drawdown(f) if k == "deferred_finance_cost_account")
        for me in c.profit_plan(f):
            bal += sum(d_ - cr for k, d_, cr in c.lines_month(f, me) if k == "deferred_finance_cost_account")
        self.assertAlmostEqual(bal, 0.0, places=2)

    def test_missing_accounts_reported(self):
        self.assertEqual(c.required_accounts({"bank_account": "Bank"}, c.lines_drawdown(ANB)), ["loan_payable_account"])
        self.assertEqual(c.month_end(dt.date(2028, 2, 3)), dt.date(2028, 2, 29))


class Api(unittest.TestCase):
    def test_posting_endpoints_are_post_only(self):
        import ast
        src = (Path(__file__).resolve().parents[1] / "api.py").read_text()
        wl = {n.name: ast.unparse(d) for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)
              for d in n.decorator_list if "whitelist" in ast.unparse(d)}
        for name in ("post_drawdown", "post_fee_payment", "post_month", "post_repayment", "run_month"):
            self.assertIn("POST", wl[name], name)
        self.assertIn("preview", wl)


if __name__ == "__main__":
    unittest.main()
