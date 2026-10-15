# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""A validated quotation cannot be edited (ERPNext: UpdateAfterSubmitError,
"Impossible de modifier après validation"). It is changed the ERPNext way
-- cancelled, then amended into a new draft (SAL-QTN-2026-00002-1) that
keeps the link to the original -- in one action, the "Modifier le devis"
button (public/js/quotation.js). Seen 2026-10-13: a quotation was cancelled
and typed again from scratch instead."""

import frappe
from frappe import _

# turned into a sales order: changed on the order, and cancelling the
# quotation would be refused anyway (linked document)
ORDERED_STATUSES = ("Ordered", "Partially Ordered")


@frappe.whitelist()
def amend_quotation(name):
	"""Cancels the validated quotation `name` and returns the name of its
	new draft version. One request: if the draft cannot be created, the
	cancellation is rolled back with it."""
	doc = frappe.get_doc("Quotation", name)
	if doc.docstatus == 0:
		frappe.throw(_("Ce devis est un brouillon : modifiez-le directement puis enregistrez."))
	if doc.docstatus == 2:
		frappe.throw(_("Ce devis est annulé : utilisez le bouton « Modifier » pour en créer une nouvelle version."))
	if doc.status in ORDERED_STATUSES:
		frappe.throw(_("Ce devis a déjà été transformé en commande client : modifiez la commande."))

	# the same rights as cancelling then amending by hand (company
	# isolation included: has_permission hooks run on the document)
	doc.check_permission("cancel")
	if not frappe.has_permission("Quotation", "create"):
		frappe.throw(_("Vous n'avez pas le droit de créer un devis."), frappe.PermissionError)

	doc.cancel()
	amended = frappe.copy_doc(doc)
	amended.amended_from = doc.name
	amended.docstatus = 0
	amended.insert()
	return amended.name
