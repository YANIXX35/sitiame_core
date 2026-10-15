# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""ERPNext DocType classes extended by sitiame_core (hooks.py
override_doctype_class)."""

import frappe
from erpnext.buying.doctype.supplier.supplier import Supplier

from sitiame_core.party_isolation import unique_party_name


class SitiameSupplier(Supplier):
	def autoname(self):
		"""Named after the supplier like ERPNext, with a " - N" suffix when
		another PME or account already uses the name (as for customers)."""
		super().autoname()
		if frappe.defaults.get_global_default("supp_master_name") == "Supplier Name":
			self.name = unique_party_name("Supplier", self.name)
