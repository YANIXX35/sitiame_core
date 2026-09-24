# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Scanned payment receipt -> draft Payment Entry settled against the
matching open invoice.

Companion of ocr_invoice.py: once an invoice is booked, its settlement no
longer has to be keyed in. The receipt (Wave/Orange/MTN/Moov screenshot,
bank transfer notice, cheque, cash receipt) is read, matched to an open
Purchase/Sales Invoice of the company, and ERPNext's own get_payment_entry
builds the draft (party account, bank/cash account, allocation). Nothing
is submitted: the accountant reviews and submits, which books 4011/4111
against 52xx/55xx/57xx and moves the invoice to Paid.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from sitiame_core.api import _AMOUNT_VALUE, _parse_amount, read_invoice_file
from sitiame_core.ocr_invoice import AMOUNT_TOLERANCE, _attach_scan, _default_company

INVOICE_DOCTYPES = ("Purchase Invoice", "Sales Invoice")

# Receipt wording -> Mode of Payment (names as configured on this site).
# Checked in order: the mobile money brands first, so a Wave receipt that
# also says "virement" is still booked as Wave.
_MODE_KEYWORDS = [
	("Wave", r"\bwave\b"),
	("Orange Money", r"orange\s*money|\bom\b"),
	("MTN MoMo", r"\bmtn\b|\bmomo\b"),
	("Moov Money", r"\bmoov\b|\bflooz\b"),
	("Cheque", r"ch[eè]que"),
	("Wire Transfer", r"virement|transfer"),
	("Cash", r"esp[eè]ces|\bcash\b|\bcaisse\b"),
]

# Receipts rarely say "Total TTC": they say what was paid.
_PAID_AMOUNT_RE = re.compile(
	r"(?:montant\s*(?:pay[ée]|re[çc]u|vers[ée]|r[ée]gl[ée]|transf[ée]r[ée])|somme\s*(?:de|re[çc]ue)?|montant|total)"
	r"\s*[:\-]?\s*" + _AMOUNT_VALUE,
	re.IGNORECASE,
)


@frappe.whitelist()
def ocr_create_payment_draft(file_url, company=None, invoice_doctype=None, invoice_name=None):
	"""invoice_doctype/invoice_name: set when started from an invoice's own
	"Importer le recu de paiement" button -- the receipt is then settled
	against that invoice without any matching."""
	data = read_invoice_file(file_url)
	text = data.get("text") or ""
	fields = data.get("fields") or {}
	warnings = []

	if invoice_doctype and invoice_name:
		if invoice_doctype not in INVOICE_DOCTYPES:
			frappe.throw(_("Type de facture non pris en charge : {0}").format(invoice_doctype))
		invoice = frappe.get_doc(invoice_doctype, invoice_name)
		company = invoice.company
		if invoice.docstatus != 1 or flt(invoice.outstanding_amount) <= 0:
			frappe.throw(_("La facture {0} n'a plus de montant a regler.").format(invoice_name))
	else:
		company = company or _default_company()
		if not company:
			frappe.throw(_("Aucune societe selectionnee pour ce paiement."))
		invoice = _match_open_invoice(text, company, _read_paid_amount(text, fields), warnings)

	amount = _read_paid_amount(text, fields)
	outstanding = flt(invoice.outstanding_amount)
	if not amount:
		amount = outstanding
		warnings.append(_("Montant non lu sur le recu : le reste a payer ({0}) a ete repris.").format(outstanding))
	elif abs(amount - outstanding) > AMOUNT_TOLERANCE:
		warnings.append(
			_("Montant du recu ({0}) different du reste a payer de la facture ({1}) : paiement {2}.").format(
				amount, outstanding, _("partiel") if amount < outstanding else _("superieur a la facture")
			)
		)

	mode_of_payment = _detect_mode_of_payment(text)
	account = _mode_account(mode_of_payment, company)
	if mode_of_payment and not account:
		warnings.append(
			_("Moyen de paiement {0} detecte, mais aucun compte n'y est associe pour {1} : compte banque par defaut utilise.").format(
				mode_of_payment, company
			)
		)

	payment_date = fields.get("invoice_date") or data.get("date") or today()
	pe = get_payment_entry(
		invoice.doctype,
		invoice.name,
		party_amount=min(amount, outstanding),
		bank_account=account,
		reference_date=payment_date,
	)
	if amount > outstanding:
		pe.paid_amount = pe.received_amount = amount
	pe.posting_date = payment_date
	pe.reference_date = payment_date
	pe.reference_no = fields.get("invoice_number") or _("Recu scanne du {0}").format(payment_date)
	if mode_of_payment:
		pe.mode_of_payment = mode_of_payment
	pe.remarks = _("Paiement cree depuis le recu scanne, pour {0} {1}.").format(_(invoice.doctype), invoice.name)
	pe.insert()

	_attach_scan(file_url, pe)
	pe.add_comment(
		"Comment",
		"<b>"
		+ _("Paiement cree depuis le recu scanne -- a verifier puis soumettre.")
		+ "</b><ul>"
		+ "".join(
			f"<li>{frappe.utils.escape_html(line)}</li>"
			for line in [
				_("Facture reglee : {0} ({1})").format(invoice.name, invoice.get("supplier") or invoice.get("customer")),
				_("Montant : {0}").format(amount),
				_("Moyen de paiement : {0}").format(mode_of_payment or _("non detecte")),
				*warnings,
			]
		)
		+ "</ul>",
	)

	return {"doctype": "Payment Entry", "name": pe.name, "invoice": invoice.name, "warnings": warnings}


def _read_paid_amount(text, fields):
	if fields.get("grand_total"):
		return flt(fields["grand_total"])
	match = _PAID_AMOUNT_RE.search(text)
	return flt(_parse_amount(match.group(1))) if match else 0


def _normalize(value):
	return re.sub(r"[\W_]+", " ", (value or "").casefold()).strip()


def _match_open_invoice(text, company, amount, warnings):
	"""Open invoices of the company whose reference (supplier invoice
	number or ERPNext name) appears on the receipt win outright; otherwise
	those whose party name appears on it, narrowed by amount, oldest first."""
	haystack = f" {_normalize(text)} "
	by_reference, by_party = [], []

	for doctype, party_field in (("Purchase Invoice", "supplier_name"), ("Sales Invoice", "customer_name")):
		fields = ["name", "posting_date", "outstanding_amount", party_field]
		if doctype == "Purchase Invoice":
			fields.append("bill_no")
		for row in frappe.get_all(
			doctype,
			filters={"company": company, "docstatus": 1, "outstanding_amount": [">", 0]},
			fields=fields,
			order_by="posting_date asc",
		):
			row.doctype = doctype
			references = [row.name, row.get("bill_no")]
			if any(ref and f" {_normalize(ref)} " in haystack for ref in references):
				by_reference.append(row)
			elif row.get(party_field) and f" {_normalize(row.get(party_field))} " in haystack:
				by_party.append(row)

	if len(by_reference) == 1:
		return frappe.get_doc(by_reference[0].doctype, by_reference[0].name)
	candidates = by_reference or by_party
	if not candidates:
		frappe.throw(
			_(
				"Aucune facture ouverte de {0} ne correspond a ce recu (ni numero de facture, ni nom de tiers reconnu). Ouvrez la facture concernee et utilisez son bouton « Importer le recu de paiement »."
			).format(company)
		)

	exact = [row for row in candidates if amount and abs(flt(row.outstanding_amount) - amount) <= AMOUNT_TOLERANCE]
	if len(exact) == 1:
		chosen = exact[0]
	elif len({(row.doctype, row.get("supplier_name") or row.get("customer_name")) for row in candidates}) == 1:
		chosen = candidates[0]
		if len(candidates) > 1:
			warnings.append(
				_("{0} factures ouvertes pour ce tiers : la plus ancienne ({1}) a ete choisie.").format(
					len(candidates), chosen.name
				)
			)
	else:
		frappe.throw(
			_("Plusieurs factures ouvertes correspondent a ce recu ({0}). Ouvrez la bonne facture et utilisez son bouton « Importer le recu de paiement ».").format(
				", ".join(row.name for row in candidates[:5])
			)
		)
	return frappe.get_doc(chosen.doctype, chosen.name)


def _detect_mode_of_payment(text):
	for mode, pattern in _MODE_KEYWORDS:
		if re.search(pattern, text or "", re.IGNORECASE) and frappe.db.exists("Mode of Payment", mode):
			return mode
	return None


def _mode_account(mode_of_payment, company):
	if not mode_of_payment:
		return None
	account = frappe.db.get_value(
		"Mode of Payment Account", {"parent": mode_of_payment, "company": company}, "default_account"
	)
	if account:
		return account
	if frappe.db.get_value("Mode of Payment", mode_of_payment, "type") == "Cash":
		return frappe.get_cached_value("Company", company, "default_cash_account")
	return None
