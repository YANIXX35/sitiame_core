# Copyright (c) 2026, Sitiame Capital
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# Mirrors PME360's AdminScoringParametersController::assertWeightsSums() --
# each block's criteria weights (and the composite block weights) must sum
# to exactly 100.
_BLOCK_WEIGHT_FIELDS = {
	"bank": ["bank_dscr_weight", "bank_interest_coverage_weight", "bank_current_ratio_weight", "bank_debt_asset_weight", "bank_bfr_days_weight"],
	"investor": ["investor_revenue_growth_weight", "investor_ebitda_margin_weight", "investor_roe_weight", "investor_fcf_margin_weight", "investor_asset_turnover_weight"],
	"internal": ["internal_net_margin_weight", "internal_quick_ratio_weight", "internal_receivable_days_weight", "internal_inventory_days_weight", "internal_ebitda_growth_weight"],
	"composite": ["composite_weight_bank", "composite_weight_investor", "composite_weight_internal"],
}


class Scoring360Settings(Document):
	def validate(self):
		for block, fieldnames in _BLOCK_WEIGHT_FIELDS.items():
			total = sum(flt(self.get(f)) for f in fieldnames)
			if abs(total - 100.0) > 0.001:
				frappe.throw(
					_("La somme des poids du bloc {0} doit etre 100 (actuel : {1}).").format(block, total)
				)
