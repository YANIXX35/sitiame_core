# Copyright (c) 2026, Sitiame Capital
# License: MIT

# Staff who work the Scoring and Financement modules (credit scoring and
# financing dossiers of every PME, the financial ranking) without being
# System Manager. Given from the User form; created by setup.py.
CREDIT_ANALYST_ROLE = "Analyste Credit Sitiame"

# Staff who follow a portfolio of PMEs (Company.sitiame_charge_affaires):
# they see only those PMEs, prepare their scoring and financing dossiers,
# and leave the decision to a validator. See portfolio.py.
CHARGE_AFFAIRES_ROLE = "Charge d'affaires Sitiame"

# Who takes the credit decision on a dossier a chargé d'affaires prepared.
VALIDATOR_ROLES = ("System Manager", CREDIT_ANALYST_ROLE)

# One of these is assigned to every PME account — it mirrors Company.sitiame_offer
# and lets permission checks read the offer without an extra DB query.
PME360_ROLE_ESSENTIEL      = "PME360 Essentiel"
PME360_ROLE_PILOTAGE       = "PME360 Pilotage"
PME360_ROLE_TRANSFORMATION = "PME360 Transformation"
PME360_OFFER_ROLES = (PME360_ROLE_ESSENTIEL, PME360_ROLE_PILOTAGE, PME360_ROLE_TRANSFORMATION)
_OFFER_TO_ROLE = {
	"Essentiel":      PME360_ROLE_ESSENTIEL,
	"Pilotage":       PME360_ROLE_PILOTAGE,
	"Transformation": PME360_ROLE_TRANSFORMATION,
}
