# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""The role must exist before the doctypes granting it are synced."""

from sitiame_core.setup import ensure_credit_analyst_role


def execute():
	ensure_credit_analyst_role()
