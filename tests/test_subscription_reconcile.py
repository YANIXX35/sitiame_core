# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Subscription payments still "En attente" settled by the every-10-minutes
job (sitiame_core.subscription_api.reconcile_pending_payments)."""

import datetime

import frappe
import pytest

from sitiame_core import subscription_api as sa

NOW = datetime.datetime(2026, 9, 28, 12, 0)


@pytest.fixture
def world(monkeypatch):
	state = {"rows": [], "cinetpay": {}, "status": {}, "paid": [], "logged": []}

	def get_all(doctype, filters=None, fields=None, **kwargs):
		assert filters == {"status": "En attente", "transaction_id": ["is", "set"]}
		return [frappe._dict(r) for r in state["rows"]]

	def payment_status(name):
		answer = state["cinetpay"][name]
		if isinstance(answer, Exception):
			raise answer
		return {"status": answer}

	monkeypatch.setattr(frappe.utils, "now_datetime", lambda: NOW, raising=False)
	monkeypatch.setattr(frappe, "get_all", get_all, raising=False)
	monkeypatch.setattr(sa, "get_payment_status", payment_status)
	monkeypatch.setattr(sa, "_mark_paid", lambda name: state["paid"].append(name))
	monkeypatch.setattr(frappe.db, "set_value", lambda dt, name, field, value: state["status"].__setitem__(name, value), raising=False)
	monkeypatch.setattr(frappe.db, "commit", lambda: None, raising=False)
	monkeypatch.setattr(frappe.db, "rollback", lambda: None, raising=False)
	monkeypatch.setattr(frappe, "get_traceback", lambda: "tb", raising=False)
	monkeypatch.setattr(frappe, "log_error", lambda title=None, message=None: state["logged"].append(title), raising=False)
	return state


def _add(world, name, days_old, cinetpay):
	world["rows"].append({"name": name, "creation": NOW - datetime.timedelta(days=days_old)})
	world["cinetpay"][name] = cinetpay


def test_old_payment_that_cinetpay_declares_failed_is_closed(world):
	"""Regression: only the last 3 days were checked, so 6 payments stayed
	"En attente" for good although CinetPay answered FAILED (2026-09-28)."""
	_add(world, "SUB-OLD", 6, "FAILED")
	sa.reconcile_pending_payments()
	assert world["status"] == {"SUB-OLD": "Échoué"}


def test_paid_payment_is_activated_whatever_its_age(world):
	_add(world, "SUB-PAID", 5, "SUCCESS")
	sa.reconcile_pending_payments()
	assert world["paid"] == ["SUB-PAID"] and world["status"] == {}


def test_still_pending_after_a_week_is_closed_as_abandoned(world):
	_add(world, "SUB-ABANDONED", 8, "PENDING")
	_add(world, "SUB-RECENT", 1, "PENDING")
	sa.reconcile_pending_payments()
	assert world["status"] == {"SUB-ABANDONED": "Échoué"}


def test_a_cinetpay_error_is_logged_and_the_others_still_run(world):
	_add(world, "SUB-ERR", 1, RuntimeError("timeout"))
	_add(world, "SUB-OK", 1, "FAILED")
	sa.reconcile_pending_payments()
	assert world["status"] == {"SUB-OK": "Échoué"}
	assert world["logged"] == ["Subscription Payment: reconciliation echouee"]
