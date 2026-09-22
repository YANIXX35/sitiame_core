# Copyright (c) 2026, Sitiame Capital
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document


class SubscriptionPayment(Document):
	def after_insert(self):
		from sitiame_core.subscription_api import generate_payment_link_on_insert

		generate_payment_link_on_insert(self)

	def validate(self):
		if self.is_new() or not self.transaction_id:
			return

		previous = frappe.db.get_value(
			"Subscription Payment", self.name, ["company", "amount", "duration_months"], as_dict=True
		)
		if not previous:
			return

		for field in ("company", "amount", "duration_months"):
			if self.get(field) != previous.get(field):
				frappe.throw(
					_("Impossible de modifier {0} : un lien de paiement a deja ete genere pour ce document.").format(
						field
					)
				)
