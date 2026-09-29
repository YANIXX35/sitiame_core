# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""An invoice marked paid gets its Payment Entry created and submitted when
it is validated (sitiame_core.pay_on_submit)."""

import sys

import frappe
import pytest

from sitiame_core import pay_on_submit


class FakePayment(frappe._dict):
	def insert(self):
		self.inserted = True

	def submit(self):
		self.submitted = True


@pytest.fixture
def erp(monkeypatch):
	state = {"calls": [], "payments": [], "alerts": []}

	def get_payment_entry(doctype, name, bank_account=None, **kwargs):
		state["calls"].append((doctype, name, bank_account))
		payment = FakePayment(name="ACC-PAY-2026-00009")
		state["payments"].append(payment)
		return payment

	module = sys.modules["erpnext.accounts.doctype.payment_entry.payment_entry"]
	monkeypatch.setattr(module, "get_payment_entry", get_payment_entry, raising=False)
	monkeypatch.setattr(pay_on_submit, "_mode_account", lambda mode, company: {"Cash": "5711 - Caisse - S", "Wave": "5521 - Wave - S"}.get(mode))
	monkeypatch.setattr(frappe, "msgprint", lambda message, **kwargs: state["alerts"].append(message), raising=False)
	monkeypatch.setattr(frappe.utils, "get_link_to_form", lambda doctype, name: name, raising=False)
	return state


def _invoice(**values):
	base = {"doctype": "Purchase Invoice", "name": "ACC-PINV-2026-00005", "company": "S", "posting_date": "2026-09-28",
		"bill_no": "FAC-2026-0917", "outstanding_amount": 590000.0, "sitiame_pay_on_submit": 1, "sitiame_payment_mode": "Cash"}
	base.update(values)
	return frappe._dict(base)


def test_unmarked_invoice_gets_no_payment(erp):
	pay_on_submit.create_payment(_invoice(sitiame_pay_on_submit=0))
	assert erp["calls"] == []


def test_marked_without_a_mode_is_refused(erp):
	with pytest.raises(frappe.ValidationError, match="moyen de paiement"):
		pay_on_submit.create_payment(_invoice(sitiame_payment_mode=None))


def test_nothing_left_to_pay_gets_no_payment(erp):
	pay_on_submit.create_payment(_invoice(outstanding_amount=0))
	assert erp["calls"] == []


def test_marked_invoice_gets_its_payment_created_and_submitted(erp):
	pay_on_submit.create_payment(_invoice())
	assert erp["calls"] == [("Purchase Invoice", "ACC-PINV-2026-00005", "5711 - Caisse - S")]
	payment = erp["payments"][0]
	assert payment.mode_of_payment == "Cash"
	assert payment.posting_date == payment.reference_date == "2026-09-28"
	assert payment.reference_no == "FAC-2026-0917"
	assert payment.inserted and payment.submitted
	assert erp["alerts"]


def test_mobile_money_lands_on_its_account_and_sales_use_the_invoice_name(erp):
	pay_on_submit.create_payment(_invoice(doctype="Sales Invoice", name="ACC-SINV-2026-00003", bill_no=None, sitiame_payment_mode="Wave"))
	assert erp["calls"] == [("Sales Invoice", "ACC-SINV-2026-00003", "5521 - Wave - S")]
	assert erp["payments"][0].reference_no == "ACC-SINV-2026-00003"
