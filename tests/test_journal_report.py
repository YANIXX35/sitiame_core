# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Journal des ecritures: every ledger line of a company, invoices included
(sitiame_core/sitiame_core/report/journal_des_ecritures)."""

import datetime

import frappe
import pytest

from sitiame_core.sitiame_core.report.journal_des_ecritures import journal_des_ecritures as journal


@pytest.fixture
def ledger(monkeypatch):
	state = {"sql": None, "params": None, "permission": []}
	rows = [
		frappe._dict(posting_date=datetime.date(2026, 9, 28), voucher_type="Purchase Invoice", voucher_no="ACC-PINV-2026-00005",
			account="6222 - Locations de bâtiments - S", party_type=None, party=None, against="IVOIRE SERVICES PRO SARL", remarks="No Remarks", debit=300000.0, credit=0.0),
		frappe._dict(posting_date=datetime.date(2026, 9, 28), voucher_type="Purchase Invoice", voucher_no="ACC-PINV-2026-00005",
			account="4011 - Fournisseurs - S", party_type="Supplier", party="IVOIRE SERVICES PRO SARL", against="6222 - Locations de bâtiments - S", remarks="No Remarks", debit=0.0, credit=590000.0),
		frappe._dict(posting_date=datetime.date(2026, 9, 29), voucher_type="Journal Entry", voucher_no="ACC-JV-2026-00001",
			account="5711 - Caisse - S", party_type=None, party=None, against=None, remarks="Apport en caisse", debit=50000.0, credit=0.0),
	]

	def sql(query, params=None, as_dict=False):
		state["sql"], state["params"] = query, params
		return rows

	def has_permission(doctype, ptype, doc, throw=False):
		state["permission"].append((doctype, ptype, doc, throw))
		return True

	monkeypatch.setattr(frappe.db, "sql", sql, raising=False)
	monkeypatch.setattr(frappe, "has_permission", has_permission, raising=False)
	return state


def test_nothing_without_a_company(ledger):
	columns, data = journal.execute({})
	assert data == [] and ledger["sql"] is None


def test_company_permission_is_checked(ledger):
	journal.execute({"company": "SITIAME"})
	assert ledger["permission"] == [("Company", "read", "SITIAME", True)]


def test_filters_become_conditions(ledger):
	journal.execute({"company": "S", "from_date": "2026-09-01", "to_date": "2026-09-30", "account": "4011 - Fournisseurs - S", "voucher_type": "Purchase Invoice"})
	query = ledger["sql"]
	for condition in ("company = %(company)s", "is_cancelled = 0", "posting_date >= %(from_date)s", "posting_date <= %(to_date)s", "account = %(account)s", "voucher_type = %(voucher_type)s"):
		assert condition in query
	assert ledger["params"]["account"] == "4011 - Fournisseurs - S"


def test_rows_read_like_a_journal(ledger):
	columns, data = journal.execute({"company": "S"})
	assert [c["fieldname"] for c in columns] == ["posting_date", "voucher_label", "voucher_type", "voucher_no", "account", "libelle", "debit", "credit"]
	assert data[0]["voucher_label"] == "Facture d'achat"
	assert data[0]["libelle"] == "IVOIRE SERVICES PRO SARL"  # no party: the counterpart
	assert data[1]["libelle"] == "IVOIRE SERVICES PRO SARL"  # the supplier
	assert data[2]["voucher_label"] == "Écriture manuelle"
	assert data[2]["libelle"] == "Apport en caisse"  # the remark
	assert (data[0]["debit"], data[1]["credit"]) == (300000.0, 590000.0)
