# Copyright (c) 2026, Sitiame Capital
# License: MIT

from sitiame_core.liasse_fiscale import run_statement


def execute(filters=None):
	return run_statement("Tableau des amortissements SYSCOHADA", filters)
