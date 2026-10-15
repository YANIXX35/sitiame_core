# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Export Liasse SYSCOHADA (liasse_export.py) : le modèle Excel est rempli
par ses feuilles Journal / Journal_N1 et PARAMETRES -- sans base de données."""

import datetime
import io
import sys

import pytest

# fonctions frappe.utils absentes du stub du conftest
_utils = sys.modules["frappe.utils"]
_utils.get_site_path = lambda *args: "/tmp/fake_site"
_utils.date_diff = lambda a, b: (_utils.getdate(a) - _utils.getdate(b)).days


def _add_months(date, months):
	d = _utils.getdate(date)
	month = d.month - 1 + months
	return d.replace(year=d.year + month // 12, month=month % 12 + 1)


_utils.add_months = _add_months

from sitiame_core import liasse_export as le  # noqa: E402

PLAN = ["10", "101", "1011000", "1301000", "1309000", "411", "4111000", "401", "4011000", "4431000", "4452000",
	"52", "521", "5211000", "57", "571", "5711000", "552", "601", "6011000", "6047000", "633", "701", "7011000", "7061000"]  # fmt: skip
GROUPS = ["10", "101", "411", "401", "52", "521", "57", "571", "601", "701"]


@pytest.fixture
def resolve():
	return le.account_resolver(PLAN, GROUPS)


# ── comptes ─────────────────────────────────────────────────────────────────

def test_extract_and_normalize():
	assert le._extract_account_code("4111 - Clients - S") == "4111"
	assert le._extract_account_code("Debtors - KE") == ""
	assert le._normalize_to_7("4111") == "4111000"
	assert le._normalize_to_7("12345678") == "1234567"
	assert le._normalize_to_7("") == ""


@pytest.mark.parametrize(
	"code, expected",
	[
		("4111", "4111000"),  # 4 chiffres -> 7
		("633", "633"),  # compte imputable à 3 chiffres dans le modèle
		("5521", "552"),  # sous-compte Mobile Money -> compte imputable le plus précis
		("4111000", "4111000"),
		("411", None),  # regroupement : jamais imputé
		("999", None),
	],
)
def test_account_resolver(resolve, code, expected):
	assert resolve(code) == expected


# ── journal ─────────────────────────────────────────────────────────────────

def gl(voucher_type, voucher_no, account_number, debit=0, credit=0, account_type="", **extra):
	return {"posting_date": "2025-03-10", "voucher_type": voucher_type, "voucher_no": voucher_no,
		"account": f"{account_number} - X - S", "account_number": account_number, "account_type": account_type,
		"debit": debit, "credit": credit, **extra}  # fmt: skip


def test_journal_codes_by_voucher(resolve):
	rows, unknown = le.build_journal_rows(
		[
			gl("Sales Invoice", "SINV-1", "4111", debit=118000),
			gl("Sales Invoice", "SINV-1", "7061", credit=100000),
			gl("Sales Invoice", "SINV-1", "4431", credit=18000),
			gl("Purchase Invoice", "PINV-1", "6047", debit=50000),
			gl("Payment Entry", "PE-1", "5211", debit=118000, account_type="Bank"),
			gl("Payment Entry", "PE-1", "4111", credit=118000, account_type="Receivable"),
			gl("Payment Entry", "PE-2", "5711", credit=5000, account_type="Cash"),
			gl("Journal Entry", "JV-1", "6011", debit=1000),
			gl("Journal Entry", "JV-2", "1011", credit=1000000, is_opening="Yes"),
		],
		resolve,
	)
	journals = {(row["piece"], row["account"]): row["journal"] for row in rows}
	assert journals[("SINV-1", "4111000")] == "VT" and journals[("PINV-1", "6047000")] == "AC"
	assert journals[("PE-1", "5211000")] == "BQ" and journals[("PE-1", "4111000")] == "BQ"
	assert journals[("PE-2", "5711000")] == "CS" and journals[("JV-1", "6011000")] == "OD"
	assert journals[("JV-2", "1011000")] == "AN"
	assert unknown == set()


def test_amounts_are_net_per_line_and_dates_are_dates(resolve):
	rows, _unknown = le.build_journal_rows(
		[gl("Journal Entry", "JV-1", "6011", debit=700, credit=200), gl("Journal Entry", "JV-1", "5711", debit=0, credit=0)], resolve
	)
	assert len(rows) == 1 and (rows[0]["debit"], rows[0]["credit"]) == (500, 0)
	assert rows[0]["date"] == datetime.date(2025, 3, 10)


def test_unknown_accounts_are_reported(resolve):
	_rows, unknown = le.build_journal_rows([gl("Journal Entry", "JV-1", "999", debit=10), gl("Journal Entry", "JV-1", "", debit=5)], resolve)
	assert unknown == {"999 - X - S", " - X - S"}


# ── reports d'ouverture ─────────────────────────────────────────────────────

def test_opening_carries_balance_sheet_accounts_and_past_results(resolve):
	"""Un compte de bilan sans mouvement dans l'exercice reste au bilan, et
	les charges/produits des années passées ne gonflent pas le résultat N."""
	rows, unknown = le.build_opening_rows(
		[
			{"account": "1011 - Capital", "account_number": "1011", "balance": -1000000},
			{"account": "5211 - Banque", "account_number": "5211", "balance": 1150000},
			{"account": "6047 - Fournitures", "account_number": "6047", "balance": 50000},
			{"account": "7061 - Services", "account_number": "7061", "balance": -200000},
		],
		resolve,
		"2026-01-01",
	)
	by_account = {row["account"]: (row["debit"], row["credit"]) for row in rows}
	assert by_account == {"1011000": (0, 1000000), "5211000": (1150000, 0), le.PROFIT_ACCOUNT: (0, 150000)}
	assert all(row["journal"] == "AN" and row["date"] == datetime.date(2026, 1, 1) for row in rows)
	assert sum(row["debit"] for row in rows) == sum(row["credit"] for row in rows)
	assert unknown == set()


def test_past_loss_goes_to_1309(resolve):
	rows, _unknown = le.build_opening_rows([{"account": "6047", "account_number": "6047", "balance": 30000}, {"account": "5711", "account_number": "5711", "balance": -30000}], resolve, "2026-01-01")
	assert {row["account"]: row["debit"] for row in rows}[le.LOSS_ACCOUNT] == 30000


def test_compact_over_capacity_keeps_the_totals(resolve):
	rows = [
		{"date": datetime.date(2025, 3, d), "journal": "VT", "piece": f"S{d}", "account": "7061000", "label": "", "debit": 0, "credit": 100, "party": "", "cost_center": ""}
		for d in range(1, 21)
	] + [{"date": datetime.date(2025, 1, 1), "journal": "AN", "piece": "AN", "account": "5211000", "label": "", "debit": 5, "credit": 0, "party": "", "cost_center": ""}]
	out = le.compact(rows, capacity=10)
	assert len(out) == 2
	assert sum(r["credit"] for r in out if r["journal"] == "VT") == 2000


def test_previous_period():
	assert le.previous_period("2026-01-01", "2026-12-31") == (datetime.date(2025, 1, 1), datetime.date(2025, 12, 31))


# ── classeur ────────────────────────────────────────────────────────────────

def _template():
	openpyxl = pytest.importorskip("openpyxl")
	wb = openpyxl.Workbook()
	wb.remove(wb.active)
	for name in ("Journal", "Journal_N1"):
		ws = wb.create_sheet(name)
		ws["A1"], ws["D1"], ws["E1"] = "Date", "Compte", "Intitule compte"
		# ligne d'exemple du modèle + formules
		ws["A2"], ws["B2"], ws["C2"], ws["D2"], ws["G2"] = "01/01/2026", "VT", "FV-001", "411", 118000
		for r in (2, 3, 4):
			ws[f"E{r}"] = f"=IFERROR(VLOOKUP(D{r},Plan_Comptable!$B$2:$C$1456,2,FALSE()),\"\")"
		ws["N2"] = "=SUM(G2:G20001)"
	p = wb.create_sheet("PARAMETRES")
	p["B3"], p["F3"], p["F4"] = "Dénomination sociale de l'entreprise", "Code", "AN"
	return wb


def test_workbook_gets_journals_and_parameters():
	openpyxl = pytest.importorskip("openpyxl")
	row = {"date": datetime.date(2025, 6, 15), "journal": "VT", "piece": "SINV-9", "account": "7061000", "label": "Vente", "debit": 0, "credit": 50000, "party": "Client", "cost_center": ""}
	content = le.fill_workbook(
		_template(), [row], [],
		{"company_name": "SITIAME", "abbr": "S", "address": "Abidjan", "tax_id": "CI123", "from_date": "2025-01-01", "to_date": "2025-12-31", "previous_to_date": "2024-12-31", "months": 12},
	)  # fmt: skip
	wb = openpyxl.load_workbook(io.BytesIO(content))
	j, n1, p = wb["Journal"], wb["Journal_N1"], wb["PARAMETRES"]
	assert [j[f"{c}2"].value for c in "BCDFGHI"] == ["VT", "SINV-9", "7061000", "Vente", 0, 50000, "Client"]
	assert j["A2"].value.date() == datetime.date(2025, 6, 15) and j["D2"].number_format == "@"
	assert j["E2"].value.startswith("=IFERROR") and j["N2"].value == "=SUM(G2:G20001)"  # formules intactes
	assert n1["A2"].value is None and n1["G2"].value is None  # ligne d'exemple effacée
	assert [p[c].value for c in ("D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11")] == [
		"SITIAME", "S", "Abidjan", "CI123", "31/12/2025", 12, "01/01/2025", "31/12/2025", "31/12/2024"
	]
	assert p["F3"].value == "Code" and p["F4"].value == "AN"  # table des journaux intacte
	assert wb.calculation.fullCalcOnLoad
