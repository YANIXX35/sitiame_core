# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Server-side port of the scoring calculation from the standalone HTML
mockup (Maquette_scoring_credit.html): each criterion contributes
weight * note / 5 points; the dossier is only "ready" (score/grade shown)
once all 10 criteria are noted and weights sum to exactly 100."""

import frappe
from frappe.model.document import Document

CRITERIA_FIELDS = [
	"capacite_remboursement",
	"structure_financiere",
	"rentabilite",
	"historique_paiement",
	"marche_clientele",
	"direction_organisation",
	"qualite_informations",
	"projet_financement",
	"liquidite_generale",
	"garanties_recouvrement",
]


class CreditScoringDossier(Document):
	def validate(self):
		total_weight = 0
		sum_score = 0.0
		count = 0
		valid = True

		for fname in CRITERIA_FIELDS:
			weight = self.get(f"{fname}_weight")
			weight = int(weight) if weight not in (None, "") else 0
			if weight < 0 or weight > 100:
				valid = False
			total_weight += weight

			note = self.get(f"{fname}_note")
			if note not in (None, ""):
				note = int(note)
				if note < 0 or note > 5:
					valid = False
				else:
					count += 1
					sum_score += weight * note / 5.0

		ready = valid and total_weight == 100 and count == len(CRITERIA_FIELDS)

		self.criteria_evaluated_count = count
		self.ready = 1 if ready else 0

		if ready:
			self.score = round(sum_score, 1)
			if sum_score >= 80:
				self.grade = "A"
			elif sum_score >= 65:
				self.grade = "B"
			elif sum_score >= 50:
				self.grade = "C"
			else:
				self.grade = "D"
		else:
			self.score = None
			self.grade = None
