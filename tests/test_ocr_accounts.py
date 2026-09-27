# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Account proposed for each OCR-read invoice line, and the Mobile Money
account a receipt lands on (sitiame_core.ocr_accounts)."""

import frappe
import pytest

from sitiame_core import ocr_accounts as oa


@pytest.mark.parametrize(
	"label, number",
	[
		("Loyer bureau septembre 2026", "6222"),
		("Facture électricité CIE août", "6052"),
		("Consommation d'eau SODECI", "6051"),
		("Carburant véhicule de service", "6042"),
		("Maintenance mensuelle serveur", "6243"),
		("Produits d'entretien et détergents", "6043"),
		("Réparation climatiseur", "6242"),
		("Honoraires expert-comptable", "6324"),
		("Prestation de conseil informatique", "6327"),
		("Licence logiciel annuelle", "6343"),
		("Hébergement site internet", "6345"),
		("Abonnement internet fibre", "6288"),
		("Fournitures de bureau", "6047"),
		("Billet d'avion Abidjan-Dakar", "6181"),
		("Frais bancaires trimestriels", "6318"),
		("Formation Excel du personnel", "633"),
		("Carton tomates 5kg", None),
	],
)
def test_keyword_account_number(label, number):
	assert oa.keyword_account_number(label) == number


def test_information_is_not_formation():
	assert oa.keyword_account_number("Système d'information") is None


def test_commission_bancaire_is_not_a_mission():
	assert oa.keyword_account_number("Commission bancaire") == "6318"


@pytest.fixture
def ledger(monkeypatch):
	"""Accounts of company "C": 6222/6327/6011 active leaves, 6243 disabled."""
	accounts = {
		"6222 - Locations de bâtiments - C": {"company": "C", "account_number": "6222", "is_group": 0, "disabled": 0},
		"6327 - Autres prestataires - C": {"company": "C", "account_number": "6327", "is_group": 0, "disabled": 0},
		"6243 - Maintenance - C": {"company": "C", "account_number": "6243", "is_group": 0, "disabled": 1},
		"6011 - Dans la Région - C": {"company": "C", "account_number": "6011", "is_group": 0, "disabled": 0},
	}
	state = {"invoices": [], "items": {}}

	def matches(row, filters):
		return all(row.get(key) == value for key, value in filters.items() if key != "name")

	def get_value(doctype, filters, fieldname=None, **kwargs):
		if doctype == "Account":
			for name, row in accounts.items():
				if filters.get("name", name) == name and matches(row, filters):
					return name
			return None
		if doctype.endswith(" Item"):
			return state["items"].get(filters["parent"])
		return None

	def get_all(doctype, filters=None, pluck=None, **kwargs):
		return [name for dt, invoice_filters, name in state["invoices"] if dt == doctype and invoice_filters == filters][:1]

	monkeypatch.setattr(frappe.db, "get_value", get_value, raising=False)
	monkeypatch.setattr(frappe, "get_all", get_all, raising=False)
	return state


def test_keyword_account_resolves_an_active_leaf(ledger):
	assert oa.keyword_account("C", "Loyer bureau") == "6222 - Locations de bâtiments - C"
	assert oa.keyword_account("C", "Maintenance serveur") is None  # 6243 disabled here
	assert oa.keyword_account("C", "Carton tomates") is None


def test_remembered_account_takes_the_last_submitted_invoice(ledger):
	ledger["invoices"].append(("Purchase Invoice", {"supplier": "ACME", "company": "C", "docstatus": 1}, "PINV-9"))
	ledger["items"]["PINV-9"] = "6327 - Autres prestataires - C"
	assert oa.remembered_account(True, "ACME", "C") == "6327 - Autres prestataires - C"
	assert oa.remembered_account(True, "OTHER", "C") is None


def test_remembered_account_ignores_a_disabled_account(ledger):
	ledger["invoices"].append(("Purchase Invoice", {"supplier": "ACME", "company": "C", "docstatus": 1}, "PINV-1"))
	ledger["items"]["PINV-1"] = "6243 - Maintenance - C"
	assert oa.remembered_account(True, "ACME", "C") is None


def test_choose_account_priority(ledger):
	default = "6011 - Dans la Région - C"
	remembered = "6327 - Autres prestataires - C"
	assert oa.choose_account(True, "C", "Loyer bureau", default, remembered) == (remembered, "memoire")
	assert oa.choose_account(True, "C", "Loyer bureau", default, None) == ("6222 - Locations de bâtiments - C", "mot-cle")
	assert oa.choose_account(True, "C", "Carton tomates", default, None) == (default, "defaut")
	# no keywords on sales: the income account depends on the PME's business
	assert oa.choose_account(False, "C", "Loyer bureau", "7061 - C", None) == ("7061 - C", "defaut")


def _mobile_money_accounts(monkeypatch, rows):
	monkeypatch.setattr(frappe, "get_all", lambda doctype, **kwargs: [frappe._dict(r) for r in rows], raising=False)


def test_mobile_money_prefers_the_brand_sub_account(monkeypatch):
	_mobile_money_accounts(
		monkeypatch,
		[
			{"name": "5521 - Wave - S", "account_name": "Wave", "account_number": "5521"},
			{"name": "5522 - Orange Money - S", "account_name": "Orange Money", "account_number": "5522"},
		],
	)
	assert oa.mobile_money_account("S", "Orange Money") == "5522 - Orange Money - S"


def test_mobile_money_falls_back_to_the_generic_552(monkeypatch):
	_mobile_money_accounts(
		monkeypatch,
		[
			{
				"name": "552 - Monnaie électronique téléphone portable - Y",
				"account_name": "Monnaie électronique téléphone portable",
				"account_number": "552",
			}
		],
	)
	assert oa.mobile_money_account("Y", "Wave") == "552 - Monnaie électronique téléphone portable - Y"


def test_mobile_money_none_without_a_552_account(monkeypatch):
	_mobile_money_accounts(monkeypatch, [])
	assert oa.mobile_money_account("Z", "Wave") is None
