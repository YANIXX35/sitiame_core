# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""An invoice already paid when it is booked (a cash purchase, a scanned
invoice paid by Wave...): with "Payee : creer le paiement a la validation"
ticked, its Payment Entry is created and submitted together with it. It
then shows under "Ecriture de paiement", the invoice is Paid, and the cash
/ bank / Mobile Money account moves.

ERPNext's own "Est paye" books the payment inside the invoice and creates
no Payment Entry: nothing showed under Paiements, which is what users
looked for. This runs in the invoice's submit transaction, so a payment
that can't be created cancels the validation instead of leaving an
invoice marked paid without its payment."""

import frappe
from frappe import _
from frappe.utils import flt

from sitiame_core.ocr_payment import _mode_account
from sitiame_core.withholding_tax import apply_withholding


def create_payment(doc, method=None):
	if not doc.get("sitiame_pay_on_submit") or flt(doc.get("outstanding_amount")) <= 0:
		return
	mode = doc.get("sitiame_payment_mode")
	if not mode:
		frappe.throw(_("Choisissez le moyen de paiement de la facture payee."))

	# Idempotence : ne pas créer un second paiement si un Payment Entry
	# validé existe déjà pour cette facture (double soumission d'événement).
	if frappe.db.exists(
		"Payment Entry Reference",
		{"reference_name": doc.name, "docstatus": 1},
	):
		return

	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	payment = get_payment_entry(doc.doctype, doc.name, bank_account=_mode_account(mode, doc.company))
	payment.mode_of_payment = mode
	payment.posting_date = doc.posting_date
	payment.reference_date = doc.posting_date
	# what bank reconciliation matches on
	payment.reference_no = doc.get("bill_no") or doc.name
	payment.remarks = _("Paiement cree a la validation de {0} {1}.").format(_(doc.doctype), doc.name)

	# Retenue à la source (BNC/BIC 7,5% ou RME 2%) si le fournisseur y est assujetti
	withheld = apply_withholding(payment, doc)

	payment.insert()
	payment.submit()

	msg = _("Paiement {0} cree et valide : la facture est payee.").format(
		frappe.utils.get_link_to_form("Payment Entry", payment.name)
	)
	if withheld:
		msg += " " + _("Retenue a la source appliquee.")
	frappe.msgprint(msg, alert=True)
