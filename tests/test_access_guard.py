# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""A desk account tied to no company only logs in if it is Sitiame staff
(access_guard.py): isolation would otherwise show it every PME."""

import frappe
import pytest

from sitiame_core import access_guard as guard

USERS = {
	# user: (user_type, has company permission, roles)
	"pme@client.ci": ("System User", True, ["PME Client", "Accounts Manager"]),
	"oublie@client.ci": ("System User", False, ["Accounts Manager", "Sales Manager"]),
	"orpheline@client.ci": ("System User", False, ["PME Client", "Accounts Manager"]),
	"admin@sitiame.ci": ("System User", False, ["System Manager"]),
	"compta@sitiame.ci": ("System User", False, ["Accounts Manager", guard.STAFF_ROLE]),
	"ca@sitiame.ci": ("System User", False, ["Charge d'affaires Sitiame"]),
	"analyste@sitiame.ci": ("System User", False, ["Analyste Credit Sitiame"]),
	"site@web.ci": ("Website User", False, []),
	"api-pme360@sitiame-capital.com": ("System User", False, ["Accounts Manager"]),
}


class Refused(Exception):
	pass


@pytest.fixture(autouse=True)
def world(monkeypatch):
	state = {"logged": [], "added": [], "defaults": {}}

	def get_value(doctype, name, field=None, **kwargs):
		return USERS[name][0]

	def exists(doctype, filters=None, *a, **k):
		return USERS[filters["user"]][1]

	class User:
		def __init__(self, name):
			self.name, self.flags = name, frappe._dict()

		def add_roles(self, *roles):
			state["added"].append((self.name, roles))

	monkeypatch.setattr(frappe.db, "get_value", get_value, raising=False)
	monkeypatch.setattr(frappe.db, "exists", exists, raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: USERS[user][2], raising=False)
	monkeypatch.setattr(frappe, "log_error", lambda title=None, message=None: state["logged"].append((title, message)), raising=False)
	monkeypatch.setattr(frappe, "AuthenticationError", Refused, raising=False)
	monkeypatch.setattr(frappe, "throw", lambda msg, exc=None: (_ for _ in ()).throw(Refused(msg)), raising=False)
	monkeypatch.setattr(frappe, "get_doc", lambda doctype, name: User(name), raising=False)
	monkeypatch.setattr(frappe, "get_all", lambda doctype, filters=None, pluck=None, **k: list(USERS), raising=False)
	monkeypatch.setattr(frappe.db, "get_default", lambda key: state["defaults"].get(key), raising=False)
	monkeypatch.setattr(frappe.db, "set_default", lambda key, value: state["defaults"].__setitem__(key, value), raising=False)
	monkeypatch.setattr(frappe.db, "commit", lambda: None, raising=False)
	return state


def _login(user):
	guard.check_login(frappe._dict(user=user))


@pytest.mark.parametrize(
	"user",
	["pme@client.ci", "admin@sitiame.ci", "compta@sitiame.ci", "ca@sitiame.ci", "analyste@sitiame.ci", "site@web.ci", "api-pme360@sitiame-capital.com"],
)
def test_attached_or_staff_accounts_log_in(world, user):
	_login(user)
	assert world["logged"] == []


@pytest.mark.parametrize("user", ["oublie@client.ci", "orpheline@client.ci"])
def test_account_without_company_nor_staff_role_is_refused(world, user):
	"""oublie: a PME account created by hand, its company forgotten -- it
	would have seen every PME's books as 'staff'."""
	with pytest.raises(Refused, match="rattaché à aucune société"):
		_login(user)
	assert world["logged"] == [("Connexion refusée : compte sans société", user)]


def test_backfill_marks_only_existing_staff_once(world):
	"""PME accounts are never marked staff, even without a company."""
	assert guard.backfill_staff_role() == ["oublie@client.ci"]
	assert world["added"] == [("oublie@client.ci", (guard.STAFF_ROLE,))]
	assert guard.backfill_staff_role() == []
