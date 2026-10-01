# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Unit tests for the 5 OCR accounting improvements:

  1. VAT accounts typed correctly (4433/4451/4453 as Tax) -- api.py
  2. Purchase default fallback: unrecognised service -> 6327, not 6011 -- ocr_plan.py
  3. Withholding note in payment comment -- ocr_payment.py
  4. Anti-duplicate check on Payment Entry reference_no -- ocr_payment.py
  5. list_pending_drafts() structure -- api.py

All tests run without a database (frappe stub from conftest.py).
"""

import pytest
import frappe

from sitiame_core import ocr_accounts as oa
from sitiame_core import ocr_plan
from sitiame_core import ocr_payment


# ---------------------------------------------------------------------------
# Étape 1 — VAT account types in _SYSCOHADA_ACCOUNT_TYPES
# ---------------------------------------------------------------------------

def test_syscohada_account_types_covers_all_vat_accounts():
    """4433, 4451 and 4453 must be typed 'Tax' so plan_vat() finds them."""
    from sitiame_core.api import _SYSCOHADA_ACCOUNT_TYPES

    for number in ("4431", "4432", "4433", "4451", "4452", "4453", "4454"):
        assert _SYSCOHADA_ACCOUNT_TYPES.get(number) == "Tax", (
            f"Account {number} must be typed 'Tax' in _SYSCOHADA_ACCOUNT_TYPES "
            f"(currently: {_SYSCOHADA_ACCOUNT_TYPES.get(number)!r})"
        )


def test_vat_nature_service_accounts_map_to_4454():
    """Services (62x/63x/64x...) must route to PURCHASE_VAT_ACCOUNTS['service'] = 4454."""
    assert oa.PURCHASE_VAT_ACCOUNTS["service"] == ("4454",)


def test_vat_nature_transport_maps_to_4453():
    """Transport (61x) must route to PURCHASE_VAT_ACCOUNTS['transport'] first choice 4453."""
    assert oa.PURCHASE_VAT_ACCOUNTS["transport"][0] == "4453"


def test_vat_nature_fixed_asset_maps_to_4451():
    """Immobilisations (2x) must route to PURCHASE_VAT_ACCOUNTS['fixed_asset'] first choice 4451."""
    assert oa.PURCHASE_VAT_ACCOUNTS["fixed_asset"][0] == "4451"


def test_vat_nature_works_maps_to_4433():
    """Sales travaux (705x) must route to SALES_VAT_ACCOUNTS['works'] first choice 4433."""
    assert oa.SALES_VAT_ACCOUNTS["works"][0] == "4433"


def test_vat_nature_detects_service_from_account_number():
    """Account numbers starting with 62x-63x must yield 'service' nature."""
    for prefix in ("6222", "6281", "6327", "633", "6318"):
        assert oa.vat_nature(True, prefix) == "service", (
            f"Account {prefix} should be 'service', got {oa.vat_nature(True, prefix)!r}"
        )


def test_vat_nature_detects_goods_from_account_number():
    """Account numbers starting with 60x must yield 'goods' nature."""
    for prefix in ("6011", "6042", "6047", "6052"):
        assert oa.vat_nature(True, prefix) == "goods", (
            f"Account {prefix} should be 'goods', got {oa.vat_nature(True, prefix)!r}"
        )


def test_vat_nature_detects_transport():
    """Account numbers starting with 61x must yield 'transport' nature."""
    assert oa.vat_nature(True, "612") == "transport"
    assert oa.vat_nature(True, "614") == "transport"


# ---------------------------------------------------------------------------
# Étape 2 — Better default account for unrecognised purchases
# ---------------------------------------------------------------------------

class _FakeDB:
    """Minimal frappe.db stub: leaf_by_number returns a fake account name."""

    def get_value(self, doctype, filters=None, fieldname="name", *args, **kwargs):
        if isinstance(filters, dict) and filters.get("is_group") == 0:
            number = filters.get("account_number")
            if number:
                return f"{number} - Fake - CO"
        return None


def _accounts_for_lines(lines, is_purchase=True, company="CO"):
    """Run choose_line_accounts with a monkeypatched leaf_by_number."""
    original_leaf = oa.leaf_by_number
    original_keyword = oa.keyword_account

    def fake_leaf(company, number):
        if number:
            return f"{number} - Fake - {company}"
        return None

    def fake_keyword(company, label, is_pur):
        # Only respond to patterns we have in PURCHASE_KEYWORD_ACCOUNTS
        number = oa.keyword_account_number(label, is_pur)
        return fake_leaf(company, number) if number else None

    oa.leaf_by_number = fake_leaf
    oa.keyword_account = fake_keyword
    try:
        result = ocr_plan.choose_line_accounts(is_purchase, company, lines, "6011 - Default - CO", None)
    finally:
        oa.leaf_by_number = original_leaf
        oa.keyword_account = original_keyword
    return result


def _make_line(label, amount=100000):
    return {
        "item_name": label,
        "qty": 1,
        "rate": amount,
        "amount": amount,
        "kind": "taxable",
        "description": "test",
    }


def test_unrecognised_purchase_service_uses_6327_not_6011():
    """A purchase line with no keyword match and no goods signal should fall
    back to 6327 (general service) rather than 6011 (goods/merchandise)."""
    lines = [_make_line("Consultation juridique annuelle")]
    result = _accounts_for_lines(lines)
    account = result[0]["account"]
    assert "6327" in (account or ""), (
        f"Expected fallback to 6327 for an unrecognised service label, got {account!r}"
    )
    assert result[0]["source"] == "defaut"


def test_goods_label_keeps_6011_fallback():
    """A purchase line with a physical goods signal must NOT be rerouted to
    6327 -- 6011 (or the company default) must remain."""
    lines = [_make_line("Achat de marchandises divers")]
    result = _accounts_for_lines(lines)
    account = result[0]["account"]
    assert "6327" not in (account or ""), (
        f"Goods label should NOT fall back to 6327, got {account!r}"
    )


def test_keyword_match_overrides_fallback():
    """A recognised keyword (e.g. 'loyer') must still route to its account
    (6222), not to the 6327 fallback."""
    lines = [_make_line("Loyer bureau mois de septembre")]
    result = _accounts_for_lines(lines)
    account = result[0]["account"]
    assert "6222" in (account or ""), (
        f"Keyword 'loyer' should map to 6222, got {account!r}"
    )
    assert result[0]["source"] == "mot-cle"


def test_goods_regex_matches_physical_goods():
    """_GOODS_LABEL_RE must match labels that clearly describe physical goods."""
    from sitiame_core.ocr_plan import _GOODS_LABEL_RE

    hits = [
        "Vente de marchandises",
        "Articles bureau 10 pieces",
        "Stock de produits finis",
        "Cartons emballage 50 kg",
    ]
    for label in hits:
        assert _GOODS_LABEL_RE.search(oa._fold(label)), (
            f"Expected _GOODS_LABEL_RE to match {label!r}"
        )


def test_goods_regex_does_not_match_services():
    """_GOODS_LABEL_RE must NOT match service labels."""
    from sitiame_core.ocr_plan import _GOODS_LABEL_RE

    misses = [
        "Consultation juridique",
        "Formation Excel avancé",
        "Maintenance serveur mensuel",
        "Honoraires d'audit",
    ]
    for label in misses:
        assert not _GOODS_LABEL_RE.search(oa._fold(label)), (
            f"Expected _GOODS_LABEL_RE NOT to match {label!r}"
        )


# ---------------------------------------------------------------------------
# Étape 3 — Withholding note in Payment Entry comment
# ---------------------------------------------------------------------------

def test_withholding_note_returned_for_consultant(monkeypatch):
    """When the invoice's first line is on 6324/6327, _withholding_note()
    must return a non-empty string with the two withholding amounts."""
    monkeypatch.setattr(
        frappe, "get_all",
        lambda doctype, filters=None, fields=None, limit=None:
            [frappe._dict(expense_account="6324 - Honoraires - CO", item_name="Honoraires avocat")]
            if "Item" in doctype else [],
    )
    monkeypatch.setattr(oa, "account_number_of", lambda account: "6324")
    monkeypatch.setattr(oa, "leaf_by_number", lambda company, number: f"{number} - Fake - {company}")

    invoice = frappe._dict(doctype="Purchase Invoice", name="PINV-001", grand_total=1000000)
    note = ocr_payment._withholding_note(invoice, "CO")

    assert note is not None, "Expected a withholding note for honoraires/consultant"
    assert "75 000" in note or "7,5" in note, f"Expected 7.5% amount in note: {note!r}"
    assert "20 000" in note or "2 %" in note, f"Expected 2% amount in note: {note!r}"
    assert "4471" in note, f"Expected account 4471 in note: {note!r}"


def test_no_withholding_note_for_electricity(monkeypatch):
    """A CIE electricity bill (6052) must NOT trigger a withholding note."""
    monkeypatch.setattr(
        frappe, "get_all",
        lambda doctype, filters=None, fields=None, limit=None:
            [frappe._dict(expense_account="6052 - Electricite - CO", item_name="Facture CIE")]
            if "Item" in doctype else [],
    )
    monkeypatch.setattr(oa, "account_number_of", lambda account: "6052")
    monkeypatch.setattr(oa, "leaf_by_number", lambda company, number: None)

    invoice = frappe._dict(doctype="Purchase Invoice", name="PINV-002", grand_total=500000)
    note = ocr_payment._withholding_note(invoice, "CO")
    assert note is None, f"Expected no withholding note for electricity, got {note!r}"


def test_no_withholding_note_when_no_items(monkeypatch):
    """No items on the invoice -> no note."""
    monkeypatch.setattr(
        frappe, "get_all",
        lambda *args, **kwargs: [],
    )
    invoice = frappe._dict(doctype="Purchase Invoice", name="PINV-003", grand_total=200000)
    note = ocr_payment._withholding_note(invoice, "CO")
    assert note is None


# ---------------------------------------------------------------------------
# Étape 4 — Anti-duplicate check on Payment Entry reference_no
# ---------------------------------------------------------------------------

def test_duplicate_payment_reference_is_refused(monkeypatch):
    """Importing the same receipt reference twice must raise ValidationError."""
    monkeypatch.setattr(
        frappe.db, "get_value",
        lambda doctype, filters=None, fieldname="name", *a, **k:
            "PE-0042" if doctype == "Payment Entry" and (filters or {}).get("reference_no") == "TXN-12345" else None,
    )
    with pytest.raises(frappe.ValidationError, match="deja ete importe"):
        ocr_payment._assert_payment_not_already_imported("TXN-12345", "CO")


def test_new_payment_reference_passes(monkeypatch):
    """A reference not yet in the database must pass silently."""
    monkeypatch.setattr(frappe.db, "get_value", lambda *a, **k: None)
    ocr_payment._assert_payment_not_already_imported("TXN-99999", "CO")  # no exception


def test_empty_reference_no_is_skipped(monkeypatch):
    """An empty reference_no (receipt without transaction ID) must not query
    the database and must never raise."""
    called = []
    monkeypatch.setattr(frappe.db, "get_value", lambda *a, **k: called.append(a) or None)
    ocr_payment._assert_payment_not_already_imported("", "CO")
    ocr_payment._assert_payment_not_already_imported(None, "CO")
    assert called == [], "get_value must not be called for empty reference_no"


# ---------------------------------------------------------------------------
# Étape 5 — list_pending_drafts structure
# ---------------------------------------------------------------------------

def test_list_pending_drafts_returns_summary(monkeypatch):
    """list_pending_drafts() must return a dict with 'rows' and 'summary'."""
    monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(
        frappe, "get_list",
        lambda doctype, filters=None, fields=None, order_by=None, limit_page_length=None:
            [
                frappe._dict(
                    name=f"{doctype[:3]}-001",
                    posting_date="2026-10-01",
                    company="CO",
                    supplier_name="ACME",
                    customer_name="ACME",
                    party="ACME",
                    party_name="ACME",
                    grand_total=500000,
                    paid_amount=500000,
                    payment_type="Pay",
                    creation="2026-10-01 10:00:00",
                )
            ],
    )
    monkeypatch.setattr(
        frappe.utils, "format_datetime",
        lambda dt, fmt: str(dt),
    )

    from sitiame_core.api import list_pending_drafts

    result = list_pending_drafts("CO")
    assert "rows" in result
    assert "summary" in result
    summary = result["summary"]
    assert summary["total"] == summary["purchase_invoices"] + summary["sales_invoices"] + summary["payment_entries"]
    assert summary["total"] == len(result["rows"])


def test_list_pending_drafts_has_required_fields(monkeypatch):
    """Each row must expose doctype, name, company, party, amount, created_at."""
    monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(
        frappe, "get_list",
        lambda doctype, **k: [
            frappe._dict(
                name="PINV-001", posting_date="2026-10-01", company="CO",
                supplier_name="FOURNISSEUR", customer_name="CLIENT",
                party="X", party_name="X",
                grand_total=118000, paid_amount=118000, payment_type="Pay",
                creation="2026-10-01 09:00:00",
            )
        ],
    )
    monkeypatch.setattr(frappe.utils, "format_datetime", lambda dt, fmt: str(dt))

    from sitiame_core.api import list_pending_drafts

    result = list_pending_drafts("CO")
    for row in result["rows"]:
        for key in ("doctype", "name", "company", "amount", "created_at"):
            assert key in row, f"Row missing key {key!r}: {row}"
