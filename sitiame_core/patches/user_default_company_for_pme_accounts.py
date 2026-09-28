# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Follow-up to default_company_for_pme_accounts: the User Permission's
is_default is ignored while a site-wide default company exists (SITIAME,
which a PME may not see, so the default resolved to nothing and reports
still failed with "Societe est obligatoire"). A per-user default does
take precedence: set it for every user limited to a single company."""

import frappe


def execute():
	rows = frappe.db.sql(
		"""
		select user, max(for_value) company from `tabUser Permission`
		where allow = 'Company'
		group by user
		having count(*) = 1
		""",
		as_dict=True,
	)
	for row in rows:
		if frappe.db.exists("User", row.user):
			frappe.defaults.set_user_default("company", row.company, row.user)
