# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Liasse SYSCOHADA computed from ledger balances (debit - credit)."""

import pytest

from sitiame_core import syscohada_statements as s


def _run(monkeypatch, cumulative, period=None):
	"""cumulative: balances up to year end; period: this fiscal year only
	(defaults to the class 6-8 part of cumulative, i.e. no earlier years)."""
	if period is None:
		period = {k: v for k, v in cumulative.items() if k[0] in "678"}

	def fake(company, to_date, from_date=None):
		return (period if from_date else cumulative), []

	monkeypatch.setattr(s, "get_account_balances", fake)
	return s.compute_statements("TEST", "2026-01-01", "2026-12-31")


# capital, VAT purchase and sale, supplier with a debit balance, equipment
# and its depreciation, overdrawn cash
LEDGER = {
	"1011": -1_000_000,
	"5211": 1_118_000,
	"6011": 100_000,
	"4452": 18_000,
	"4011": 5_000,
	"7011": -200_000,
	"4431": -36_000,
	"2441": 300_000,
	"2844": -60_000,
	"6813": 60_000,
	"5711": -305_000,
}


def test_balance_sheet_balances(monkeypatch):
	r = _run(monkeypatch, LEDGER)
	assert r["total_actif"] == pytest.approx(1_381_000)
	assert r["total_actif"] == pytest.approx(r["total_passif"])
	assert r["unclassified"] == []


def test_income_statement_totals(monkeypatch):
	res = _run(monkeypatch, LEDGER)["resultat"]
	assert res["RA"] == 200_000  # 7011 ventes de marchandises
	assert res["SA"] == 100_000  # 6011 achats de marchandises
	assert res["TA"] == 100_000  # marge brute
	assert res["SK"] == 60_000  # 6813 dotations
	assert res["XZ"] == 40_000  # 200k - 100k - 60k


def test_net_result_lands_in_cg(monkeypatch):
	r = _run(monkeypatch, LEDGER)
	assert r["passif"]["CG"] == r["resultat"]["XZ"]


def test_fixed_assets_gross_depreciation_net(monkeypatch):
	r = _run(monkeypatch, LEDGER)
	assert r["actif"]["AE"] == {"brut": 300_000, "amort": 60_000}
	assert r["actif_net"]["AE"] == 240_000


def test_debit_supplier_and_overdraft_are_classified_by_side(monkeypatch):
	"""Regression vs PME360: these balances used to fall out of the sheet."""
	r = _run(monkeypatch, LEDGER)
	assert r["actif_net"]["BC"] == 23_000  # 4452 VAT + 4011 supplier debit
	assert r["passif"]["FC"] == 305_000  # 5711 cash credit balance
	assert r["passif"]["EB"] == 36_000  # 4431 VAT collected


def test_reprises_and_transferts_are_not_swapped(monkeypatch):
	"""79x = reprises (RI), 78x = transferts (RJ) -- PME360 had them swapped."""
	res = _run(monkeypatch, {"7911": -10_000, "7811": -4_000, "5211": 14_000, "1011": -14_000 + 14_000})["resultat"]
	assert res["RI"] == 10_000
	assert res["RJ"] == 4_000


def test_participation_and_income_tax_accounts(monkeypatch):
	res = _run(monkeypatch, {"871": 3_000, "891": 7_000, "5211": -10_000})["resultat"]
	assert res["WA"] == 3_000
	assert res["WB"] == 7_000
	assert res["XZ"] == -10_000


def test_earlier_years_unclosed_result_goes_to_report_a_nouveau(monkeypatch):
	cumulative = {"1011": -500_000, "5211": 560_000, "7011": -100_000, "6011": 40_000}
	period = {"7011": -30_000, "6011": 10_000}  # this year: +20k; earlier: +40k
	r = _run(monkeypatch, cumulative, period)
	assert r["resultat"]["XZ"] == 20_000
	assert r["passif"]["CF"] == pytest.approx(40_000)
	assert r["total_actif"] == pytest.approx(r["total_passif"])


def test_past_charge_reversed_this_year_keeps_the_sheet_balanced(monkeypatch):
	"""SITIAME 2026-10-15: test invoices of 2024/2025 cancelled in 2026
	(immutable ledger). 6047 nets to 0 overall, -168 000 this year: it was
	skipped from the earlier years' result and the sheet was off by 168 000."""
	cumulative = {"4452": 127_440, "4011": -417_720, "5521": -417_720, "6243": 208_000, "6327": 500_000}
	period = {"6047": -168_000, "6243": 208_000, "6327": 500_000}
	r = _run(monkeypatch, cumulative, period)
	assert r["resultat"]["XZ"] == pytest.approx(-540_000)  # this year's loss
	assert r["passif"]["CF"] == pytest.approx(-168_000)  # earlier years' loss, reversed this year
	assert r["total_actif"] == pytest.approx(r["total_passif"])


def test_provision_499_is_a_liability_not_an_asset_depreciation(monkeypatch):
	r = _run(monkeypatch, {"4991": -8_000, "5211": 8_000})
	assert r["passif"]["ED"] == 8_000
	assert r["actif"]["BC"]["amort"] == 0


def test_unmapped_account_is_reported(monkeypatch):
	r = _run(monkeypatch, {"9999": 1_000, "5211": -1_000})
	assert ("9999", 1_000) in r["unclassified"]
