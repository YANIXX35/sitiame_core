# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Lists every PME uses but none owns (customer, supplier and item groups,
territories, price lists, units, payment modes): a PME reads them, Sitiame
staff maintain them. A PME could rename or delete "Services" for every other
PME (cloisonnement audit D7, 2026-10-15).

Payment modes stay editable: each PME sets its own account on a mode (its
Mode of Payment Account row); it only cannot delete one. Item prices are not
here: each PME prices its own items."""

import frappe

READ_ONLY_FOR_PME = frozenset(["Customer Group", "Supplier Group", "Item Group", "Territory", "Price List", "UOM"])
NO_DELETE_FOR_PME = frozenset(["Mode of Payment"])
SHARED_MASTERS = READ_ONLY_FOR_PME | NO_DELETE_FOR_PME

_CHANGES = frozenset(["write", "create", "delete", "submit", "cancel", "amend", "import"])


def has_permission(doc, ptype=None, user=None, debug=False):
	"""hooks.py has_permission. A hook can only refuse: Frappe 16 reads any
	falsy answer, None included, as a refusal -- so True when it allows."""
	user = user or frappe.session.user
	if user == "Administrator" or "PME Client" not in frappe.get_roles(user):
		return True
	if doc.doctype in READ_ONLY_FOR_PME and ptype in _CHANGES:
		return False
	if doc.doctype in NO_DELETE_FOR_PME and ptype == "delete":
		return False
	return True
