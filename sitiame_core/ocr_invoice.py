# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Scanned invoice -> complete draft Purchase/Sales Invoice.

The accountant uploads the paper invoice; this creates the whole invoice as
a draft (party found or created, one HT line, the VAT on the company's own
TVA account, dates, supplier invoice number, the scan attached). Nothing is
submitted here: the accountant reviews the draft and clicks "Soumettre",
and ERPNext's own GL engine then books charge/produit + TVA + tiers into
the journal, general ledger and trial balance.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from sitiame_core.api import read_invoice_file

SUPPORTED_DOCTYPES = ("Purchase Invoice", "Sales Invoice")

# A HT + TVA vs TTC gap above this (XOF) is flagged for the accountant.
AMOUNT_TOLERANCE = 1.0


@frappe.whitelist()
def ocr_create_invoice_draft(file_url, doctype, company=None):
	if doctype not in SUPPORTED_DOCTYPES:
		frappe.throw(_("Type de document non pris en charge : {0}").format(doctype))

	company = company or _default_company()
	if not company:
		frappe.throw(_("Aucune societe selectionnee pour cette facture."))

	data = read_invoice_file(file_url)
	if data.get("document_type") not in ("invoice", "unknown"):
		frappe.throw(
			_("Le document n'a pas ete reconnu comme une facture (type detecte : {0}).").format(
				data.get("document_type")
			)
		)

	fields = data.get("fields") or {}
	is_purchase = doctype == "Purchase Invoice"
	warnings = []

	party_name = fields.get("supplier_name") if is_purchase else fields.get("customer_name")
	if not party_name:
		frappe.throw(
			_("Impossible de lire le {0} sur le document : creez la facture manuellement.").format(
				_("fournisseur") if is_purchase else _("client")
			)
		)

	net, tax, amount_warnings = _resolve_amounts(fields)
	warnings += amount_warnings

	if is_purchase and fields.get("invoice_number"):
		_assert_not_already_imported(fields["invoice_number"], party_name, company)

	party, created = _get_or_create_party("Supplier" if is_purchase else "Customer", party_name)
	if created:
		warnings.append(
			_("{0} « {1} » n'existait pas : il a ete cree automatiquement.").format(
				_("Fournisseur") if is_purchase else _("Client"), party
			)
		)

	invoice = frappe.new_doc(doctype)
	invoice.company = company
	invoice.set_posting_time = 1
	invoice.posting_date = fields.get("invoice_date") or today()
	if is_purchase:
		invoice.supplier = party
		invoice.bill_no = fields.get("invoice_number")
		invoice.bill_date = fields.get("invoice_date")
	else:
		invoice.customer = party
	if fields.get("due_date") and getdate(fields["due_date"]) >= getdate(invoice.posting_date):
		invoice.due_date = fields["due_date"]

	account_field = "expense_account" if is_purchase else "income_account"
	company_account = frappe.get_cached_value(
		"Company", company, "default_expense_account" if is_purchase else "default_income_account"
	)
	reference = fields.get("invoice_number") or _("sans numero")
	invoice.append(
		"items",
		{
			"item_name": _("Facture {0} - {1}").format(reference, party)[:140],
			"description": _("Montant HT importe depuis la facture scannee -- verifiez le compte de charge/produit."),
			"qty": 1,
			"uom": "Nos",
			"rate": net,
			account_field: company_account,
			"cost_center": frappe.get_cached_value("Company", company, "cost_center"),
		},
	)

	if tax > 0:
		tax_account = _company_vat_account(company, is_purchase)
		if tax_account:
			row = {
				"charge_type": "Actual",
				"account_head": tax_account,
				"description": _("TVA ({0}% du HT)").format(round(tax / net * 100, 2) if net else "?"),
				"tax_amount": tax,
			}
			if is_purchase:
				row.update({"category": "Total", "add_deduct_tax": "Add"})
			invoice.append("taxes", row)
		else:
			warnings.append(
				_("TVA lue ({0}) mais aucun modele TVA par defaut pour {1} : ajoutez la ligne de TVA a la main.").format(
					tax, company
				)
			)

	invoice.insert()
	_attach_scan(file_url, invoice)
	_add_review_comment(invoice, fields, data.get("confidence") or {}, warnings)

	return {"doctype": doctype, "name": invoice.name, "warnings": warnings}


def _default_company():
	return frappe.db.get_value(
		"User Permission", {"user": frappe.session.user, "allow": "Company"}, "for_value"
	) or frappe.defaults.get_user_default("Company")


def _resolve_amounts(fields):
	"""Returns (HT, TVA, warnings) from whatever the OCR read: any two of
	HT/TVA/TTC give the third; TTC alone is booked as HT with no VAT and
	flagged, rather than inventing a VAT the document may not carry."""
	net = flt(fields.get("subtotal"))
	tax = flt(fields.get("tax_amount"))
	gross = flt(fields.get("grand_total"))
	warnings = []

	if not net and gross:
		net = gross - tax if tax else gross
		if not tax:
			warnings.append(_("Seul le TTC a ete lu : facture enregistree sans TVA, a verifier."))
	if not tax and net and gross and gross - net > AMOUNT_TOLERANCE:
		tax = gross - net

	if net <= 0:
		frappe.throw(_("Aucun montant n'a pu etre lu sur le document : creez la facture manuellement."))

	if gross and abs(net + tax - gross) > AMOUNT_TOLERANCE:
		warnings.append(
			_("Ecart sur les montants lus : HT {0} + TVA {1} != TTC {2}. Verifiez avant de soumettre.").format(
				net, tax, gross
			)
		)
	return net, tax, warnings


def _assert_not_already_imported(bill_no, party_name, company):
	existing = frappe.db.get_value(
		"Purchase Invoice",
		{"bill_no": bill_no, "company": company, "supplier_name": party_name, "docstatus": ["<", 2]},
		"name",
	)
	if existing:
		frappe.throw(
			_("Cette facture ({0}) a deja ete importee : {1}.").format(
				bill_no, frappe.utils.get_link_to_form("Purchase Invoice", existing)
			)
		)


def _get_or_create_party(party_type, party_name):
	name_field = "supplier_name" if party_type == "Supplier" else "customer_name"
	exact = frappe.db.get_value(party_type, {name_field: party_name}, "name")
	if exact:
		return exact, False

	matches = frappe.get_all(party_type, filters={name_field: ["like", f"%{party_name}%"]}, pluck="name", limit=2)
	if len(matches) == 1:
		return matches[0], False

	party = frappe.get_doc({"doctype": party_type, name_field: party_name})
	party.insert()
	return party.name, True


def _company_vat_account(company, is_purchase):
	template_doctype = "Purchase Taxes and Charges Template" if is_purchase else "Sales Taxes and Charges Template"
	template = frappe.db.get_value(template_doctype, {"company": company, "is_default": 1}, "name")
	if not template:
		return None
	return frappe.db.get_value(
		"Purchase Taxes and Charges" if is_purchase else "Sales Taxes and Charges",
		{"parent": template, "parenttype": template_doctype},
		"account_head",
	)


def _attach_scan(file_url, invoice):
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		return
	file_doc = frappe.get_doc("File", file_name)
	file_doc.attached_to_doctype = invoice.doctype
	file_doc.attached_to_name = invoice.name
	file_doc.save(ignore_permissions=True)


def _add_review_comment(invoice, fields, confidence, warnings):
	labels = {
		"invoice_number": _("Numero"),
		"invoice_date": _("Date"),
		"due_date": _("Echeance"),
		"supplier_name": _("Fournisseur"),
		"customer_name": _("Client"),
		"subtotal": _("HT"),
		"tax_amount": _("TVA"),
		"grand_total": _("TTC"),
	}
	lines = [
		f"<li>{label} : {frappe.utils.escape_html(str(fields[key]))}"
		+ (f" ({round(confidence[key] * 100)}%)" if confidence.get(key) else "")
		+ "</li>"
		for key, label in labels.items()
		if fields.get(key) not in (None, "")
	]
	html = "<b>" + _("Facture creee depuis le document scanne -- a verifier puis soumettre.") + "</b>"
	html += "<ul>" + "".join(lines) + "</ul>"
	if warnings:
		html += "<b>" + _("Points a verifier :") + "</b><ul>"
		html += "".join(f"<li>{frappe.utils.escape_html(w)}</li>" for w in warnings) + "</ul>"
	invoice.add_comment("Comment", html)
