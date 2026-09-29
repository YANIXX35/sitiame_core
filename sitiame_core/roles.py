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
