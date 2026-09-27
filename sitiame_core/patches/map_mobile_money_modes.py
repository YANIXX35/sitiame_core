# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Wave/Orange Money/MTN MoMo/Moov Money were linked to an account for
SITIAME only: link them to every company's 552 Mobile Money account."""

import frappe

from sitiame_core.ocr_accounts import ensure_mobile_money_modes


def execute():
	for company in frappe.get_all("Company", pluck="name"):
		ensure_mobile_money_modes(company)
