# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Customer/Supplier/Contact/Address get their "company" field, and the
existing records a company (see sitiame_core.party_isolation)."""

import frappe

from sitiame_core import party_isolation


def execute():
	if not frappe.db.exists("Company", party_isolation.SITIAME_COMPANY):
		return
	party_isolation.create_company_fields()
	for doctype, name, company in party_isolation.backfill(dry_run=False):
		print(f"party_company_field: {doctype} {name} -> {company}")
