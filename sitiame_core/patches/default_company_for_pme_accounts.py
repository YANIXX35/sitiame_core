# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""A PME account's Company User Permission was not its default: reports
with a mandatory Company filter (Sales/Purchase Order Trends...) opened
empty and failed with "Societe est obligatoire". A user limited to a
single company now gets it as default."""

import frappe


def execute():
	users = frappe.db.sql(
		"""
		select user from `tabUser Permission`
		where allow = 'Company'
		group by user
		having count(*) = 1 and max(is_default) = 0
		""",
		pluck=True,
	)
	for user in users:
		name = frappe.db.get_value("User Permission", {"user": user, "allow": "Company"}, "name")
		frappe.db.set_value("User Permission", name, "is_default", 1)
		frappe.cache().hdel("user_permissions", user)
