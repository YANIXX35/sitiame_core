# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Scanned invoice -> complete draft Purchase/Sales Invoice.

The accountant uploads the paper invoice; this creates the whole invoice as
a draft (party found or created, one line per line read when they add up
to the HT -- else a single HT line --, each on the account proposed by
ocr_accounts, the stamp and fees apart, the VAT on the SYSCOHADA account of
its nature or added to the cost when it is not recoverable -- see
ocr_plan.py --, dates, supplier invoice number, the scan attached). Nothing is
submitted here: the accountant reviews the draft and clicks "Soumettre",
and ERPNext's own GL engine then books charge/produit + TVA + tiers into
the journal, general ledger and trial balance.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from sitiame_core import ocr_plan
from sitiame_core.ocr_plan import franc
from sitiame_core.api import read_invoice_file
from sitiame_core.ocr_accounts import _fold, remembered_account

SUPPORTED_DOCTYPES = ("Purchase Invoice", "Sales Invoice")

# A HT + TVA vs TTC gap above this (XOF) is flagged for the accountant.
AMOUNT_TOLERANCE = 1.0

# Legal forms left out when comparing a printed party name with the
# company's own name ("SITIAME CAPITAL SARL" vs Company "SITIAME").
_LEGAL_FORMS = {"sarl", "sa", "sas", "sasu", "suarl", "sci", "eurl", "gie", "ets", "ste", "societe", "cie"}


def _name_tokens(name):
	return set(re.findall(r"[a-z0-9]+", _fold(name))) - _LEGAL_FORMS


def _is_own_company(name, company):
	printed = _name_tokens(name)
	for own in (company, frappe.get_cached_value("Company", company, "company_name")):
		tokens = _name_tokens(own)
		if printed and tokens and tokens <= printed:
			return True
	return False


def _check_direction(is_purchase, fields, company):
	"""A purchase invoice is issued TO the company, a sales invoice BY it.
	When the document's issuer is the company and its customer someone
	else, it is one of the company's own sales invoices imported as a
	purchase (and vice versa): refuse, rather than create the company as
	its own supplier/customer. Only both parties read and disagreeing
	counts -- a supplier merely sharing a word with the company (company
	"yao" buying from "Yao Transport") is still billed to the company."""
	issuer, customer = fields.get("supplier_name"), fields.get("customer_name")
	if not issuer or not customer:
		return
	if is_purchase and _is_own_company(issuer, company) and not _is_own_company(customer, company):
		frappe.throw(
			_("Ce document est une facture emise par votre societe (client : {0}) : importez-la depuis Factures de vente.").format(
				customer
			)
		)
	if not is_purchase and _is_own_company(customer, company) and not _is_own_company(issuer, company):
		frappe.throw(
			_("Ce document est une facture recue de {0} : importez-la depuis Factures d'achat.").format(issuer)
		)


# Fields shown, and correctable, on the review screen (ocr_read_invoice_for_review).
REVIEW_FIELDS = (
	"invoice_number",
	"invoice_date",
	"due_date",
	"supplier_name",
	"customer_name",
	"subtotal",
	"tax_amount",
	"grand_total",
	"stamp_duty",
	"non_vat_charges",
	"previous_balance",
)
REVIEW_AMOUNT_FIELDS = ("subtotal", "tax_amount", "grand_total", "stamp_duty", "non_vat_charges", "previous_balance")
REVIEW_LABELS = {
	"invoice_number": "numero",
	"invoice_date": "date",
	"due_date": "echeance",
	"supplier_name": "fournisseur",
	"customer_name": "client",
	"subtotal": "HT",
	"tax_amount": "TVA",
	"grand_total": "TTC",
	"stamp_duty": "timbre",
	"non_vat_charges": "taxes hors TVA",
	"previous_balance": "impayes anterieurs",
	"has_fne": "FNE",
}
REVIEW_CACHE_SECONDS = 60 * 60


def _review_cache_key(file_url):
	# per user: read_invoice_file checked this user's right to read the file
	return f"sitiame:ocr_review:{frappe.session.user}:{file_url}"


def _check_doctype_and_company(doctype, company):
	if doctype not in SUPPORTED_DOCTYPES:
		frappe.throw(_("Type de document non pris en charge : {0}").format(doctype))
	company = company or _default_company()
	if not company:
		frappe.throw(_("Aucune societe selectionnee pour cette facture."))
	return company


@frappe.whitelist()
def ocr_read_invoice_for_review(file_url, doctype, company=None):
	"""Read the scan WITHOUT creating anything, for the review screen: the
	user sees the image next to the fields read (with their confidence),
	corrects or completes them, then ocr_create_invoice_draft(corrections=)
	builds the draft. An unreadable party or total no longer blocks the
	import: the user types it in."""
	company = _check_doctype_and_company(doctype, company)
	data = read_invoice_file(file_url)
	frappe.cache().set_value(_review_cache_key(file_url), data, expires_in_sec=REVIEW_CACHE_SECONDS)

	is_purchase = doctype == "Purchase Invoice"
	fields = data.get("fields") or {}
	_check_direction(is_purchase, fields, company)

	warnings = list(data.get("warnings") or [])
	if data.get("document_type") not in ("invoice", "unknown"):
		warnings.insert(
			0,
			_("Ce document ne ressemble pas a une facture (type detecte : {0}) : verifiez avant de continuer.").format(
				data.get("document_type")
			),
		)

	party_key = "supplier_name" if is_purchase else "customer_name"
	party_type = "Supplier" if is_purchase else "Customer"
	existing_party = _find_party(party_type, fields[party_key]) if fields.get(party_key) else None
	fne = data.get("fne") or {}
	return {
		"file_url": file_url,
		"source": data.get("source"),
		"fields": {key: fields.get(key) for key in REVIEW_FIELDS},
		"confidence": {key: (data.get("confidence") or {}).get(key) for key in REVIEW_FIELDS},
		"warnings": warnings,
		"line_count": len(data.get("line_items") or []),
		"party_key": party_key,
		"existing_party": existing_party,
		"fne": {"present": fne.get("present"), "number": fne.get("number")},
		"regime": ocr_plan.regime_code(_company_regime(company)),
		"plan": _review_plan(is_purchase, company, data, existing_party or fields.get(party_key)),
	}


def _review_plan(is_purchase, company, data, party):
	"""The accounting the draft would get from this reading, shown on the
	review screen (recomputed from the corrected values at creation)."""
	try:
		plan = _build_plan(is_purchase, company, data, party, remembered_account(is_purchase, party, company) if party else None)
	except Exception:
		# an unreadable total: the user types it in, the plan comes at creation
		return None
	return _plan_for_display(plan)


def _plan_for_display(plan):
	return {
		"lines": [
			{
				"item_name": line["item_name"],
				"amount": line["amount"],
				"account": line.get("account"),
				"reason": line.get("reason"),
			}
			for line in plan["lines"]
		],
		"taxes": [{"account": row["account"], "amount": row["amount"]} for row in plan["taxes"]],
		"summary": plan["summary"],
		"warnings": plan["warnings"],
		"notes": plan["notes"],
	}


def _company_regime(company):
	return frappe.get_cached_value("Company", company, "sitiame_regime_fiscal")


def _build_plan(is_purchase, company, data, party, remembered):
	fields = data.get("fields") or {}
	return ocr_plan.build_plan(
		is_purchase,
		company,
		data,
		party,
		fields.get("invoice_number") or _("sans numero"),
		frappe.get_cached_value(
			"Company", company, "default_expense_account" if is_purchase else "default_income_account"
		),
		remembered,
		_company_regime(company),
		fields.get("invoice_date") or today(),
		_company_vat_account(company, is_purchase),
	)


def _apply_corrections(data, corrections):
	"""The reviewed values replace the ones read; returns the corrected
	field names. A value validated by the user is certain (confidence 1)."""
	fields = data.setdefault("fields", {})
	confidence = data.setdefault("confidence", {})
	corrected = []
	for key in REVIEW_FIELDS:
		if key not in corrections:
			continue
		value = corrections[key]
		if key in REVIEW_AMOUNT_FIELDS:
			value = flt(value) or None
		elif isinstance(value, str):
			value = value.strip() or None
		if value != fields.get(key):
			corrected.append(key)
		if value is None:
			fields.pop(key, None)
			confidence.pop(key, None)
		else:
			fields[key] = value
			confidence[key] = 1.0
	if corrections.get("has_fne") is not None:
		# the accountant looked at the paper: FNE marks there or not
		fne = data.setdefault("fne", {})
		present = bool(int(corrections["has_fne"] or 0))
		if present != fne.get("present"):
			corrected.append("has_fne")
		fne["present"] = present
	return corrected


@frappe.whitelist()
def ocr_create_invoice_draft(file_url, doctype, company=None, corrections=None, paid_mode=None):
	"""corrections: the values validated on the review screen (JSON). Without
	it (older callers), the reading is used as is, like before.
	paid_mode: the invoice is already paid, by this Mode of Payment -- its
	Payment Entry is created when the draft is validated (pay_on_submit)."""
	company = _check_doctype_and_company(doctype, company)

	reviewed = corrections is not None
	data = None
	if reviewed:
		corrections = frappe.parse_json(corrections) or {}
		data = frappe.cache().get_value(_review_cache_key(file_url))
	if not data:
		data = read_invoice_file(file_url)

	corrected = _apply_corrections(data, corrections) if reviewed else []
	if not reviewed and data.get("document_type") not in ("invoice", "unknown"):
		frappe.throw(
			_("Le document n'a pas ete reconnu comme une facture (type detecte : {0}).").format(
				data.get("document_type")
			)
		)

	fields = data.get("fields") or {}
	is_purchase = doctype == "Purchase Invoice"
	# once reviewed, the reading's own alerts have been seen and dealt with
	warnings = [] if reviewed else list(data.get("warnings") or [])
	_check_direction(is_purchase, fields, company)

	party_name = fields.get("supplier_name") if is_purchase else fields.get("customer_name")
	if not party_name:
		frappe.throw(
			_("Impossible de lire le {0} sur le document : creez la facture manuellement.").format(
				_("fournisseur") if is_purchase else _("client")
			)
		)

	if is_purchase and fields.get("invoice_number"):
		_assert_not_already_imported(fields["invoice_number"], party_name, company)

	# fails before anything is created when no amount was read
	ocr_plan.resolve_amounts(fields)

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

	plan = _build_plan(is_purchase, company, data, party, remembered_account(is_purchase, party, company))
	warnings += plan["warnings"]
	_fill_invoice(invoice, is_purchase, company, plan)

	_apply_payment(invoice, paid_mode)
	invoice.insert()
	_attach_scan(file_url, invoice)
	reviewed_note = None
	if reviewed:
		reviewed_note = _("Lecture relue et validee par {0} avant creation").format(frappe.session.user) + (
			_(" -- corrige a la main : {0}").format(", ".join(_(REVIEW_LABELS[key]) for key in corrected))
			if corrected
			else _(" -- aucune correction")
		)
	_add_review_comment(invoice, fields, data.get("confidence") or {}, warnings, plan, reviewed_note)
	frappe.cache().delete_value(_review_cache_key(file_url))

	return {"doctype": doctype, "name": invoice.name, "warnings": warnings}


def _apply_payment(invoice, paid_mode):
	"""Ticked "Facture deja payee" on the review screen: pay_on_submit
	creates the invoice's Payment Entry when the draft is validated."""
	if not paid_mode:
		return
	if not frappe.db.exists("Mode of Payment", paid_mode):
		frappe.throw(_("Moyen de paiement inconnu : {0}").format(paid_mode))
	invoice.sitiame_pay_on_submit = 1
	invoice.sitiame_payment_mode = paid_mode


def _default_company():
	return frappe.db.get_value(
		"User Permission", {"user": frappe.session.user, "allow": "Company"}, "for_value"
	) or frappe.defaults.get_user_default("Company")


def _fill_invoice(invoice, is_purchase, company, plan):
	account_field = "expense_account" if is_purchase else "income_account"
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	for line in plan["lines"]:
		invoice.append(
			"items",
			{
				"item_name": line["item_name"][:140],
				"description": line["description"],
				"qty": line["qty"],
				"uom": "Nos",
				"rate": line["rate"],
				account_field: line.get("account"),
				"cost_center": cost_center,
			},
		)
	for tax in plan["taxes"]:
		row = {
			"charge_type": "Actual",
			"account_head": tax["account"],
			"description": tax["description"],
			"tax_amount": tax["amount"],
		}
		if is_purchase:
			row.update({"category": "Total", "add_deduct_tax": "Add"})
		invoice.append("taxes", row)


def _resolve_amounts(fields):
	"""Returns (HT, TVA, warnings) from whatever the OCR read (see
	ocr_plan.resolve_amounts): any two of HT/TVA/TTC give the third; TTC
	alone is booked as HT with no VAT and flagged."""
	amounts = ocr_plan.resolve_amounts(fields)
	gap = ocr_plan.gap_warning(amounts)
	return amounts.net, amounts.tax, amounts.warnings + ([gap] if gap else [])


def _invoice_lines(line_items, net, reference, party):
	"""One draft line per line read on the document when they add up to
	the HT; otherwise the single HT line (see ocr_plan.build_lines)."""
	amounts = frappe._dict(net=franc(net), tax=0, gross=0, stamp=0, charges=0, previous=0, gap=0)
	lines, warnings = ocr_plan.build_lines(line_items, amounts, reference, party)
	return [
		{"item_name": line["item_name"], "qty": line["qty"], "rate": line["rate"], "description": line["description"]}
		for line in lines
	], warnings


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


def _find_party(party_type, party_name):
	"""The existing Supplier/Customer: exact name, else a single partial match.
	These lookups bypass permissions: a PME only matches its own parties
	(it used to reuse, and so see, another PME's supplier)."""
	from sitiame_core.party_isolation import own_party_filters

	name_field = "supplier_name" if party_type == "Supplier" else "customer_name"
	own = own_party_filters(doctype=party_type)
	exact = frappe.db.get_value(party_type, {name_field: party_name, **own}, "name")
	if exact:
		return exact
	matches = frappe.get_all(party_type, filters={name_field: ["like", f"%{party_name}%"], **own}, pluck="name", limit=2)
	return matches[0] if len(matches) == 1 else None


def _get_or_create_party(party_type, party_name):
	existing = _find_party(party_type, party_name)
	if existing:
		return existing, False

	name_field = "supplier_name" if party_type == "Supplier" else "customer_name"
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
	# Only the caller's own fresh upload is moved onto the draft: a file
	# already attached elsewhere, or someone else's, must never be
	# re-attached (that would hand it over to the caller).
	if file_doc.attached_to_doctype or file_doc.owner != frappe.session.user:
		return
	file_doc.attached_to_doctype = invoice.doctype
	file_doc.attached_to_name = invoice.name
	file_doc.save(ignore_permissions=True)


def _add_review_comment(invoice, fields, confidence, warnings, plan=None, reviewed_note=None):
	esc = frappe.utils.escape_html
	labels = {
		"invoice_number": _("Numero"),
		"invoice_date": _("Date"),
		"due_date": _("Echeance"),
		"supplier_name": _("Fournisseur"),
		"customer_name": _("Client"),
		"subtotal": _("HT"),
		"tax_amount": _("TVA"),
		"stamp_duty": _("Timbre"),
		"non_vat_charges": _("Taxes et redevances hors TVA"),
		"grand_total": _("TTC"),
		"previous_balance": _("Impayes anterieurs (exclus du total)"),
	}
	lines = [
		f"<li>{label} : {esc(str(fields[key]))}"
		+ (f" ({round(confidence[key] * 100)}%)" if confidence.get(key) else "")
		+ "</li>"
		for key, label in labels.items()
		if fields.get(key) not in (None, "")
	]
	html = "<b>" + _("Facture creee depuis le document scanne -- a verifier puis soumettre.") + "</b>"
	if reviewed_note:
		html += "<br>" + esc(reviewed_note)
	html += "<ul>" + "".join(lines) + "</ul>"
	if plan:
		summary = plan["summary"]
		html += "<b>" + _("Traitement fiscal :") + "</b><ul>"
		html += "<li>" + _("Regime fiscal de la societe : {0}").format(esc(summary["regime"])) + "</li>"
		html += "<li>" + _("FNE : {0}").format(esc(summary["fne"])) + "</li>"
		html += "<li>" + _("TVA : {0}").format(esc(summary["vat"])) + "</li></ul>"
		html += "<b>" + _("Comptes proposes :") + "</b><ul>"
		html += "".join(
			f"<li>{esc(line['item_name'])} : {esc(str(line['amount']))} &rarr; {esc(line.get('account') or '-')}"
			f" ({esc(_(line['reason']))})</li>"
			for line in plan["lines"]
		)
		html += "".join(
			f"<li>{esc(tax['description'])} : {esc(str(tax['amount']))} &rarr; {esc(tax['account'])}</li>"
			for tax in plan["taxes"]
		)
		html += "</ul>"
		if plan["notes"]:
			html += "<b>" + _("Rappels :") + "</b><ul>"
			html += "".join(f"<li>{esc(note)}</li>" for note in plan["notes"]) + "</ul>"
	if warnings:
		html += "<b>" + _("Points a verifier :") + "</b><ul>"
		html += "".join(f"<li>{esc(w)}</li>" for w in warnings) + "</ul>"
	invoice.add_comment("Comment", html)


@frappe.whitelist()
def match_items(item_names):
	"""Scanned line label -> existing Item code, for pre-filling item rows
	on stock/buying/selling documents. Only an exact name/code match, or a
	single partial match, is returned: an ambiguous label is left for the
	user to pick rather than guessed."""
	names = frappe.parse_json(item_names) or []
	matches = {}
	for label in names:
		label = (label or "").strip()
		if not label:
			continue
		code = frappe.db.get_value("Item", {"item_code": label, "disabled": 0}, "name") or frappe.db.get_value(
			"Item", {"item_name": label, "disabled": 0}, "name"
		)
		if not code:
			partial = frappe.get_all(
				"Item", filters={"item_name": ["like", f"%{label}%"], "disabled": 0}, pluck="name", limit=2
			)
			code = partial[0] if len(partial) == 1 else None
		if code:
			matches[label] = code
	return matches
