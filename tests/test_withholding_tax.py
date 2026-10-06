# Copyright (c) 2026, Sitiame Capital
# License: MIT

import pytest
import frappe
from sitiame_core import withholding_tax as wt


@pytest.fixture(autouse=True)
def _patch_frappe(monkeypatch):
    monkeypatch.setattr(frappe, "msgprint", lambda *a, **k: None, raising=False)


def _make_payment(paid=100_000):
    return frappe._dict(
        paid_amount=paid,
        received_amount=paid,
        cost_center=None,
        remarks="Paiement test.",
        deductions=[],
    )


def _make_doc(supplier="SUP-001", company="TestPME"):
    return frappe._dict(supplier=supplier, company=company)


# ── helpers ───────────────────────────────────────────────────────────────────

def test_rates_map_is_complete():
    assert "BNC/BIC 7,5%" in wt.WITHHOLDING_RATES
    assert "RME 2%" in wt.WITHHOLDING_RATES
    assert wt.WITHHOLDING_RATES["BNC/BIC 7,5%"] == 7.5
    assert wt.WITHHOLDING_RATES["RME 2%"] == 2.0


# ── apply_withholding ─────────────────────────────────────────────────────────

def test_no_withholding_when_type_absent(monkeypatch):
    monkeypatch.setattr(frappe.db, "get_value", lambda *a, **k: None, raising=False)
    payment = _make_payment()
    result = wt.apply_withholding(payment, _make_doc())
    assert result is False
    assert payment.paid_amount == 100_000
    assert payment.deductions == []


def test_bnc_bic_deducts_7_5_percent(monkeypatch):
    def _get_value(doctype, name, field, *a, **k):
        if doctype == "Supplier":
            return "BNC/BIC 7,5%"
        return "4452 - Retenues - TestPME"

    monkeypatch.setattr(frappe.db, "get_value", _get_value, raising=False)
    payment = _make_payment(100_000)
    result = wt.apply_withholding(payment, _make_doc())
    assert result is True
    assert payment.paid_amount == 92_500           # 100 000 − 7 500
    assert payment.received_amount == 92_500
    assert len(payment.deductions) == 1
    assert payment.deductions[0]["amount"] == 7_500
    assert "7,5%" in payment.remarks


def test_rme_deducts_2_percent(monkeypatch):
    def _get_value(doctype, name, field, *a, **k):
        if doctype == "Supplier":
            return "RME 2%"
        return "4452 - Retenues - TestPME"

    monkeypatch.setattr(frappe.db, "get_value", _get_value, raising=False)
    payment = _make_payment(50_000)
    result = wt.apply_withholding(payment, _make_doc())
    assert result is True
    assert payment.paid_amount == 49_000           # 50 000 − 1 000
    assert payment.deductions[0]["amount"] == 1_000


def test_no_withholding_when_account_missing(monkeypatch):
    def _get_value(doctype, name, field, *a, **k):
        if doctype == "Supplier":
            return "BNC/BIC 7,5%"
        return None  # compte introuvable

    monkeypatch.setattr(frappe.db, "get_value", _get_value, raising=False)
    payment = _make_payment(100_000)
    result = wt.apply_withholding(payment, _make_doc())
    assert result is False
    assert payment.paid_amount == 100_000          # rien déduit
    assert payment.deductions == []


def test_no_supplier_field_returns_false(monkeypatch):
    monkeypatch.setattr(frappe.db, "get_value", lambda *a, **k: "BNC/BIC 7,5%", raising=False)
    payment = _make_payment()
    # doc sans champ supplier
    result = wt.apply_withholding(payment, frappe._dict(company="TestPME"))
    assert result is False


def test_rounding_to_integer_xof(monkeypatch):
    def _get_value(doctype, name, field, *a, **k):
        if doctype == "Supplier":
            return "BNC/BIC 7,5%"
        return "4452 - Retenues - TestPME"

    monkeypatch.setattr(frappe.db, "get_value", _get_value, raising=False)
    payment = _make_payment(10_001)   # 7.5% = 750.075 → arrondi à 750
    wt.apply_withholding(payment, _make_doc())
    assert isinstance(payment.deductions[0]["amount"], int)
    assert payment.deductions[0]["amount"] == 750
