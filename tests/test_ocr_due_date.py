# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Due date of an imported invoice that prints none (ocr_invoice.payment_delay):
before 2026-10-15 it was the invoice date, so every import was overdue."""

import pytest

from sitiame_core.ocr_invoice import DEFAULT_PAYMENT_DAYS, payment_delay


@pytest.mark.parametrize(
	"text, expected",
	[
		("Paiement à 30 jours. Mode : virement ou Mobile Money.", (30, "lu")),
		("Conditions de règlement : 45 jours fin de mois", (45, "lu")),
		("Payable sous 15 jours", (15, "lu")),
		("Délai de paiement : 60 jours", (60, "lu")),
		("Paiement comptant", (0, "lu")),
		("Payable à réception de la facture", (0, "lu")),
		("Total TTC 333 940 FCFA", (DEFAULT_PAYMENT_DAYS, "defaut")),
		("", (DEFAULT_PAYMENT_DAYS, "defaut")),
		(None, (DEFAULT_PAYMENT_DAYS, "defaut")),
		# a quantity of days of service is not a payment delay
		("Location de véhicule 5 jours", (DEFAULT_PAYMENT_DAYS, "defaut")),
	],
)
def test_payment_delay(text, expected):
	assert payment_delay(text) == expected
