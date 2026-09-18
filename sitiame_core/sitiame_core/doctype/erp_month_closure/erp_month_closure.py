# Copyright (c) 2026, Sitiame Capital
# License: MIT

import frappe
from frappe.model.document import Document


class ERPMonthClosure(Document):
	def before_insert(self):
		self.closed_at = frappe.utils.now()
		self.closed_by = frappe.session.user
