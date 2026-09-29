# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""The role must exist before the doctypes and pages granting it are synced."""

from sitiame_core.setup import ensure_charge_affaires_role


def execute():
	ensure_charge_affaires_role()
