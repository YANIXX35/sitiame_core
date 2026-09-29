# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Journal des ecritures: every ledger line of a company, whatever booked
it -- a submitted invoice, a payment, a manual journal entry...

ERPNext books an invoice's entries on the invoice itself, so none of them
shows under "Ecriture comptable" (manual journal entries only) or
"Ecriture de paiement" (payments only): this journal is where they can all
be read in one place, under Paiements. It only reads the ledger -- no
entry is duplicated."""

import frappe
from frappe import _
from frappe.utils import flt

VOUCHER_LABELS = {
	"Purchase Invoice": "Facture d'achat",
	"Sales Invoice": "Facture de vente",
	"Payment Entry": "Paiement",
	"Journal Entry": "Écriture manuelle",
	"Stock Entry": "Mouvement de stock",
	"Purchase Receipt": "Réception d'achat",
	"Delivery Note": "Bon de livraison",
	"Period Closing Voucher": "Clôture d'exercice",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		return get_columns(), []
	# the report's own role check doesn't cover which company is read: a
	# PME account only reads its own
	frappe.has_permission("Company", "read", filters.company, throw=True)
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "voucher_label", "label": _("Type"), "fieldtype": "Data", "width": 130},
		{"fieldname": "voucher_type", "label": _("Type de pièce"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "voucher_no", "label": _("Pièce"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
		{"fieldname": "account", "label": _("Compte"), "fieldtype": "Link", "options": "Account", "width": 230},
		{"fieldname": "libelle", "label": _("Libellé"), "fieldtype": "Data", "width": 220},
		{"fieldname": "debit", "label": _("Débit"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "credit", "label": _("Crédit"), "fieldtype": "Currency", "width": 130},
	]


def get_data(filters):
	conditions = ["company = %(company)s", "is_cancelled = 0"]
	if filters.from_date:
		conditions.append("posting_date >= %(from_date)s")
	if filters.to_date:
		conditions.append("posting_date <= %(to_date)s")
	if filters.account:
		conditions.append("account = %(account)s")
	if filters.voucher_type:
		conditions.append("voucher_type = %(voucher_type)s")

	rows = frappe.db.sql(
		f"""select posting_date, voucher_type, voucher_no, account, party_type, party, against, remarks, debit, credit
		from `tabGL Entry` where {" and ".join(conditions)}
		order by posting_date, creation, voucher_no, debit desc""",
		filters,
		as_dict=True,
	)
	# Read like a journal: each voucher's lines together, in the order the
	# vouchers were booked, debits before credits (ERPNext writes an
	# invoice's credit line first).
	first_seen = {}
	for position, row in enumerate(rows):
		first_seen.setdefault((row.voucher_type, row.voucher_no), position)
	rows = sorted(
		rows,
		key=lambda row: (row.posting_date, first_seen[(row.voucher_type, row.voucher_no)], flt(row.debit) <= 0),
	)
	return [
		{
			"posting_date": row.posting_date,
			"voucher_label": _(VOUCHER_LABELS.get(row.voucher_type, row.voucher_type)),
			"voucher_type": row.voucher_type,
			"voucher_no": row.voucher_no,
			"account": row.account,
			# the party, else the counterpart account/party, else the remark
			"libelle": row.party or row.against or (row.remarks if row.remarks != "No Remarks" else ""),
			"debit": flt(row.debit),
			"credit": flt(row.credit),
		}
		for row in rows
	]
