# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Accounting of a scanned invoice (sitiame_core.ocr_plan), on the real
invoices of the comptabilisation-syscohada reference: SYSCOHADA accounts
per line, VAT per nature and per tax regime, FNE, stamp, utility fees and
past unpaid invoices kept out of the total."""

import frappe
import pytest

from sitiame_core import ocr_invoice, ocr_plan
from sitiame_core import vision_invoice as vision

COMPANY = "C"
NUMBERS = (
	"6011", "6042", "6047", "6052", "6181", "6242", "6252", "6258", "6324", "6327", "6383", "6462",
	"7011", "7051", "7061", "7071",
	"4431", "4432", "4433", "4451", "4452", "4453", "4454",
)  # fmt: skip
ACCOUNTS = {f"{number} - Compte {number} - C": number for number in NUMBERS}
DEFAULT_PURCHASE = "6011 - Compte 6011 - C"
DEFAULT_SALES = "7011 - Compte 7011 - C"


def acc(number):
	return f"{number} - Compte {number} - C"


@pytest.fixture(autouse=True)
def chart(monkeypatch):
	def get_value(doctype, filters=None, fieldname=None, **kwargs):
		if doctype != "Account":
			return None
		if isinstance(filters, str):
			return ACCOUNTS.get(filters) if fieldname == "account_number" else None
		for name, number in ACCOUNTS.items():
			if filters.get("company", COMPANY) != COMPANY:
				continue
			if filters.get("account_number", number) == number and filters.get("name", name) == name:
				return name
		return None

	monkeypatch.setattr(frappe.db, "get_value", get_value, raising=False)


def plan(fields, line_items=(), is_purchase=True, regime="RNI", fne=None, remembered=None, party="X"):
	data = {"fields": dict(fields), "line_items": [dict(item) for item in line_items], "fne": fne}
	return ocr_plan.build_plan(
		is_purchase,
		COMPANY,
		data,
		party,
		fields.get("invoice_number") or "sans numero",
		DEFAULT_PURCHASE if is_purchase else DEFAULT_SALES,
		remembered,
		regime,
		fields.get("invoice_date"),
	)


def by_account(result):
	totals = {}
	for line in result["lines"]:
		number = line["account_number"]
		totals[number] = totals.get(number, 0) + line["amount"]
	return totals


def taxes(result):
	return {row["account_number"]: row["amount"] for row in result["taxes"]}


def grand_total(result):
	return sum(line["amount"] for line in result["lines"]) + sum(row["amount"] for row in result["taxes"])


# --- CIE electricity bill: energy + fees + stamp, past unpaid excluded --------

CIE_FIELDS = {
	"supplier_name": "COMPAGNIE IVOIRIENNE D'ELECTRICITE",
	"invoice_number": "180",
	"invoice_date": "2021-04-08",
	"subtotal": 277870,
	"tax_amount": 50020,
	"stamp_duty": 500,
	"non_vat_charges": 13910,
	"previous_balance": 32100,
	# the "MONTANT TOTAL A REGLER" read as the total
	"grand_total": 374400,
}
CIE_LINES = [
	{"item_name": "Energie tranche 1", "qty": 1, "rate": 148800, "line_type": "goods"},
	{"item_name": "Energie tranche 2", "qty": 1, "rate": 114210, "line_type": "goods"},
	{"item_name": "Prime fixe", "qty": 1, "rate": 14860},
	{"item_name": "Redevance électrification rurale", "qty": 1, "rate": 3710, "line_type": "fee"},
	{"item_name": "Taxe d'enlèvement des ordures ménagères", "qty": 1, "rate": 8200},
	{"item_name": "Redevance RTI", "qty": 1, "rate": 2000},
	{"item_name": "Timbre d'État", "qty": 1, "rate": 500},
]


def test_cie_bill_energy_fees_stamp_and_unpaid_excluded():
	result = plan(CIE_FIELDS, CIE_LINES)
	assert result["amounts"].gross == 342300  # not 374 400
	assert any("32100 d'impayes anterieurs" in w for w in result["warnings"])
	assert by_account(result) == {"6052": 277870 + 13910, "6462": 500}
	assert taxes(result) == {"4452": 50020}
	assert grand_total(result) == 342300
	stamp = next(line for line in result["lines"] if line["kind"] == "stamp")
	assert stamp["account_number"] == "6462" and stamp["source"] == "timbre"
	fees = [line for line in result["lines"] if line["kind"] == "fee"]
	assert sum(line["amount"] for line in fees) == 13910
	assert all(line["account_number"] == "6052" and line["source"] == "redevance" for line in fees)
	assert result["summary"]["fne"].startswith("non exigee")
	assert not any("Ecart" in w for w in result["warnings"])


def test_cie_bill_without_lines_still_splits_stamp_and_fees():
	# the single HT line is named after the supplier: "...ELECTRICITE" -> 6052
	result = plan(dict(CIE_FIELDS, grand_total=342300), party=CIE_FIELDS["supplier_name"])
	assert by_account(result) == {"6052": 291780, "6462": 500}
	assert taxes(result) == {"4452": 50020}
	assert grand_total(result) == 342300


def test_cie_fees_read_only_as_lines_explain_the_total():
	fields = {k: v for k, v in CIE_FIELDS.items() if k not in ("stamp_duty", "non_vat_charges")}
	result = plan(dict(fields, grand_total=342300), CIE_LINES)
	assert by_account(result) == {"6052": 291780, "6462": 500}
	assert grand_total(result) == 342300
	assert not any("Ecart" in w for w in result["warnings"])


def test_vision_brings_the_amount_due_back_to_the_invoice_total():
	answer = {
		"document_type": "invoice",
		"fields": {k: CIE_FIELDS[k] for k in ("subtotal", "tax_amount", "stamp_duty", "non_vat_charges", "previous_balance", "grand_total")},
		"confidence": {},
		"line_items": [],
		"amount_in_words_value": 374400,
		"fne": None,
	}
	data = vision.normalize(answer)
	assert data["fields"]["grand_total"] == 342300
	assert len(data["warnings"]) == 1 and "impayes anterieurs" in data["warnings"][0]


# --- TRACTAFRIC repair: parts net of discount + labour, VAT per nature -------

TRACTAFRIC_FIELDS = {
	"supplier_name": "TRACTAFRIC MOTORS",
	"invoice_number": "FA7354176",
	"invoice_date": "2025-09-30",
	"subtotal": 243749,
	"tax_amount": 43875,
	"vat_goods_amount": 32850,
	"vat_services_amount": 11025,
	"grand_total": 287624,
}
TRACTAFRIC_LINES = [
	{"item_name": "Pièces", "qty": 1, "rate": 178189, "line_type": "goods"},
	{"item_name": "AfterMarket", "qty": 1, "rate": 39948, "line_type": "goods"},
	{"item_name": "Remise", "qty": 1, "rate": -35638, "line_type": "discount"},
	{"item_name": "Main-d'œuvre", "qty": 1, "rate": 61250, "line_type": "service"},
]


def test_tractafric_parts_net_of_discount_and_labour_with_vat_split():
	result = plan(TRACTAFRIC_FIELDS, TRACTAFRIC_LINES)
	lines = [(line["amount"], line["account_number"]) for line in result["lines"]]
	assert lines == [(182499, "6242"), (61250, "6242")]
	assert "net de remise" in result["lines"][0]["item_name"]
	assert result["lines"][0]["source"] == "reparation"
	assert taxes(result) == {"4452": 32850, "4454": 11025}
	assert grand_total(result) == 287624
	assert result["summary"]["vat_recovered"] is True


def test_tractafric_for_a_company_in_rme_adds_the_vat_to_the_cost():
	result = plan(TRACTAFRIC_FIELDS, TRACTAFRIC_LINES, regime="RME")
	assert result["taxes"] == []
	assert by_account(result) == {"6242": 243749 + 43875}
	cost = [line for line in result["lines"] if line["kind"] == "vat_cost"]
	assert len(cost) == 1 and cost[0]["amount"] == 43875
	assert grand_total(result) == 287624
	assert result["summary"]["vat_recovered"] is False
	assert any("non recuperable" in w and "RME" in w for w in result["warnings"])


def test_tee_regime_read_from_the_company_field_label():
	assert ocr_plan.regime_code("TEE") == "TEE"
	assert ocr_plan.regime_code("RME - Régime des microentreprises") == "RME"
	assert ocr_plan.regime_code("") is None and ocr_plan.regime_code(None) is None


# --- VAT rates: 9% fuel, 0% insurance -----------------------------------------


def test_fuel_at_nine_percent_is_not_flagged():
	fields = {"invoice_date": "2025-11-15", "subtotal": 100000, "tax_amount": 9000, "grand_total": 109000}
	result = plan(fields, [{"item_name": "Gasoil", "qty": 1, "rate": 100000}])
	assert by_account(result) == {"6042": 100000}
	assert taxes(result) == {"4452": 9000}
	assert not any("%" in w for w in result["warnings"])
	assert vision.normalize({"fields": fields, "confidence": {}, "line_items": []})["warnings"] == []


def test_insurance_without_vat_is_not_flagged():
	fields = {"invoice_date": "2025-11-15", "subtotal": 250000, "grand_total": 250000}
	result = plan(fields, [{"item_name": "Prime d'assurance flotte automobile", "qty": 1, "rate": 250000}])
	assert by_account(result) == {"6252": 250000}
	assert result["taxes"] == [] and result["warnings"] == []
	assert vision.normalize({"fields": fields, "confidence": {}, "line_items": []})["warnings"] == []


def test_a_vat_at_an_impossible_rate_is_flagged():
	fields = {"invoice_date": "2025-11-15", "subtotal": 100000, "tax_amount": 20400, "grand_total": 120400}
	result = plan(fields, [{"item_name": "Gasoil", "qty": 1, "rate": 100000}])
	assert any("ni 18 % ni 9 %" in w for w in result["warnings"])


# --- FNE ----------------------------------------------------------------------

JANUARY_2026 = {"invoice_date": "2026-01-15", "subtotal": 100000, "tax_amount": 18000, "grand_total": 118000}
OFFICE = [{"item_name": "Fournitures de bureau", "qty": 1, "rate": 100000}]


def test_purchase_from_january_2026_without_fne_keeps_the_vat_out_of_445():
	result = plan(JANUARY_2026, OFFICE, fne={"present": False, "number": None})
	assert result["taxes"] == []
	assert by_account(result) == {"6047": 118000}
	assert any("sans marque de FNE" in w for w in result["warnings"])
	assert result["summary"]["vat_recovered"] is False and result["summary"]["fne"] == "absente"


def test_unknown_fne_is_treated_as_missing():
	result = plan(JANUARY_2026, OFFICE, fne=None)
	assert result["taxes"] == [] and result["summary"]["fne"] == "non detectee"


def test_purchase_with_fne_recovers_its_vat():
	result = plan(JANUARY_2026, OFFICE, fne={"present": True, "number": "FNE-2026-000123"})
	assert taxes(result) == {"4452": 18000}
	assert "FNE-2026-000123" in result["summary"]["fne"]
	assert not any("FNE" in w for w in result["warnings"])


def test_accountant_confirms_the_fne_on_the_review_screen():
	data = {"fields": {}, "confidence": {}, "fne": {"present": False}}
	assert ocr_invoice._apply_corrections(data, {"has_fne": 1}) == ["has_fne"]
	assert data["fne"]["present"] is True


# --- sales --------------------------------------------------------------------


def test_sale_of_services_goes_to_7061_and_4432():
	fields = {"invoice_date": "2026-02-10", "subtotal": 500000, "tax_amount": 90000, "grand_total": 590000}
	result = plan(fields, [{"item_name": "Mission de conseil", "qty": 1, "rate": 500000}], is_purchase=False)
	assert by_account(result) == {"7061": 500000}
	assert taxes(result) == {"4432": 90000}
	assert not any("FNE" in w for w in result["warnings"])


@pytest.mark.parametrize(
	"label, number, vat",
	[
		("Vente de 10 cartons de savon", "7011", "4431"),
		("Travaux de maçonnerie", "7051", "4433"),
	],
)
def test_sale_accounts_by_keyword(label, number, vat):
	fields = {"invoice_date": "2026-02-10", "subtotal": 100000, "tax_amount": 18000, "grand_total": 118000}
	result = plan(fields, [{"item_name": label, "qty": 1, "rate": 100000}], is_purchase=False)
	assert by_account(result) == {number: 100000}
	assert taxes(result) == {vat: 18000}


def test_shipping_recharged_goes_to_7071_even_with_a_remembered_account():
	fields = {"invoice_date": "2026-02-10", "subtotal": 110000, "grand_total": 110000}
	lines = [{"item_name": "Ciment CPJ 45", "qty": 1, "rate": 100000}, {"item_name": "Frais de livraison", "qty": 1, "rate": 10000}]
	result = plan(fields, lines, is_purchase=False, remembered=acc("7011"))
	assert by_account(result) == {"7011": 100000, "7071": 10000}


def test_company_in_tee_invoicing_vat_is_warned():
	fields = {"invoice_date": "2026-02-10", "subtotal": 100000, "tax_amount": 18000, "grand_total": 118000}
	result = plan(fields, [{"item_name": "Prestation de service", "qty": 1, "rate": 100000}], is_purchase=False, regime="TEE")
	assert any("ne doit pas facturer la TVA" in w for w in result["warnings"])


# --- regime, exclusions, mixed natures, withholding, defaults ----------------


def test_blank_regime_recovers_the_vat_but_warns():
	fields = {"invoice_date": "2025-11-15", "subtotal": 100000, "tax_amount": 18000, "grand_total": 118000}
	result = plan(fields, OFFICE, regime=None)
	assert taxes(result) == {"4452": 18000}
	assert any("Regime fiscal de la societe non renseigne" in w for w in result["warnings"])
	assert result["summary"]["regime"] == "non renseigne"


def test_restaurant_vat_is_excluded_from_the_deduction():
	fields = {"invoice_date": "2025-11-15", "subtotal": 150000, "tax_amount": 27000, "grand_total": 177000}
	lines = [
		{"item_name": "Repas d'affaires restaurant", "qty": 1, "rate": 50000},
		{"item_name": "Prestation de conseil", "qty": 1, "rate": 100000},
	]
	result = plan(fields, lines)
	assert by_account(result) == {"6383": 50000 + 9000, "6327": 100000}
	assert taxes(result) == {"4454": 18000}
	assert grand_total(result) == 177000
	assert any("exclues du droit a deduction" in w for w in result["warnings"])


def test_single_vat_on_mixed_lines_goes_to_the_dominant_nature_and_is_flagged():
	fields = {"invoice_date": "2025-11-15", "subtotal": 150000, "tax_amount": 27000, "grand_total": 177000}
	lines = [
		{"item_name": "Gasoil", "qty": 1, "rate": 50000},
		{"item_name": "Réparation climatiseur", "qty": 1, "rate": 100000},
	]
	result = plan(fields, lines)
	assert taxes(result) == {"4454": 27000}
	assert any("natures differentes" in w for w in result["warnings"])


def test_consultant_fees_get_a_withholding_reminder_but_no_entry():
	fields = {"invoice_date": "2025-11-15", "subtotal": 500000, "grand_total": 500000}
	result = plan(fields, [{"item_name": "Honoraires de conseil fiscal", "qty": 1, "rate": 500000}], party="M. KOUASSI")
	assert by_account(result) == {"6324": 500000}
	assert len(result["notes"]) == 1 and "7,5 %" in result["notes"][0] and "2 %" in result["notes"][0]
	assert all(line["kind"] == "taxable" for line in result["lines"])


def test_unrecognised_service_line_is_not_booked_as_goods():
	fields = {"invoice_date": "2025-11-15", "subtotal": 80000, "grand_total": 80000}
	result = plan(fields, [{"item_name": "Intervention technique site Yopougon", "qty": 1, "rate": 80000, "line_type": "service"}])
	assert by_account(result) == {"6327": 80000}
	assert result["lines"][0]["source"] == "nature"


def test_unknown_goods_line_keeps_the_flagged_default():
	fields = {"invoice_date": "2025-11-15", "subtotal": 69000, "grand_total": 69000}
	result = plan(fields, [{"item_name": "Carton tomates 5kg", "qty": 10, "rate": 6900}])
	assert by_account(result) == {"6011": 69000}
	assert result["lines"][0]["source"] == "defaut"
	assert any("Compte par defaut" in w for w in result["warnings"])


def test_allocation_preserves_the_total():
	assert ocr_plan.allocate(43875, [182499, 61250]) == [32850, 11025]
	assert sum(ocr_plan.allocate(100, [1, 1, 1])) == 100


# --- the draft itself ---------------------------------------------------------


class FakeInvoice(frappe._dict):
	def append(self, table, row):
		self.setdefault(table, []).append(row)


def test_draft_rows_carry_the_planned_accounts(monkeypatch):
	monkeypatch.setattr(frappe, "get_cached_value", lambda *a: "Main - C", raising=False)
	result = plan(TRACTAFRIC_FIELDS, TRACTAFRIC_LINES)
	invoice = FakeInvoice()
	ocr_invoice._fill_invoice(invoice, True, COMPANY, result)
	assert [(row["rate"], row["expense_account"]) for row in invoice["items"]] == [
		(182499, acc("6242")),
		(61250, acc("6242")),
	]
	assert [(row["account_head"], row["tax_amount"], row["add_deduct_tax"]) for row in invoice["taxes"]] == [
		(acc("4452"), 32850, "Add"),
		(acc("4454"), 11025, "Add"),
	]
