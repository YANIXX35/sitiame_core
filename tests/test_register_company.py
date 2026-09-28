# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Public company signup endpoint (sitiame_core.api.register_company)."""

import frappe
import pytest

from sitiame_core import api


def test_a_call_without_any_field_gets_the_form_message_not_a_crash(monkeypatch):
	"""Bots hit the guest endpoint with no parameters: Python failed before
	the validation ("register_company() missing 4 required positional
	arguments"), logging a technical error each time (audit 2026-09-28)."""
	monkeypatch.setattr(api, "_verify_signup_captcha", lambda token, answer: None)
	with pytest.raises(frappe.ValidationError, match="obligatoires"):
		api.register_company(terms_accepted=1)
