# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""French translations shipped by the app (sitiame_core/translations/fr.csv),
filling the labels ERPNext / HRMS leave in English (2026-09-29)."""

import csv
import pathlib

import pytest

FR_CSV = pathlib.Path(__file__).resolve().parents[1] / "sitiame_core" / "translations" / "fr.csv"


@pytest.fixture(scope="module")
def rows():
	with FR_CSV.open(encoding="utf-8", newline="") as f:
		return list(csv.reader(f))


def test_every_row_is_source_and_translation(rows):
	# frappe.translate.get_translation_dict_from_file reads [source, translated(, context)]
	assert rows and all(len(row) == 2 and row[0] and row[1].strip() for row in rows)


def test_no_source_twice(rows):
	sources = [row[0] for row in rows]
	assert len(sources) == len(set(sources))


@pytest.mark.parametrize(
	"source, expected",
	[
		("Accounts Setup", "Paramétrage comptable"),
		("Consider for Tax Withholding", "Soumis à la retenue à la source"),
		("Book Advance Payments in Separate Party Account", "Comptabiliser les acomptes sur un compte de tiers séparé"),
		("Supplier Invoice", "Facture fournisseur"),
		("Voucher Subtype", "Sous-type de pièce"),
		("Accounting Onboarding", "Prise en main de la comptabilité"),
	],
)
def test_labels_seen_in_english_on_screen(rows, source, expected):
	assert dict(rows)[source] == expected
