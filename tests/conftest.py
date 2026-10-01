# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Unit tests for sitiame_core's pure logic (OCR parsing, amounts, SYSCOHADA
statements, receipt parsing...), runnable anywhere with plain pytest:
no bench, no site, no database -- production is never touched.

When the real frappe package isn't importable (a laptop, GitHub Actions),
a minimal stand-in is installed below, covering only what the tested code
paths call. Anything that needs the database is monkeypatched per test.
"""

import datetime
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _install_frappe_stub():
	frappe = types.ModuleType("frappe")

	class ValidationError(Exception):
		pass

	class PermissionError(ValidationError):  # noqa: A001 - mirrors frappe
		pass

	class DoesNotExistError(ValidationError):
		pass

	class _dict(dict):
		__getattr__ = dict.get

		def __setattr__(self, key, value):
			self[key] = value

	def throw(msg, exc=ValidationError, *args, **kwargs):
		raise exc(msg)

	def whitelist(*args, **kwargs):
		if args and callable(args[0]):
			return args[0]
		return lambda fn: fn

	frappe.ValidationError = ValidationError
	frappe.PermissionError = PermissionError
	frappe.DoesNotExistError = DoesNotExistError
	frappe._dict = _dict
	frappe._ = lambda text, *args: text
	frappe.throw = throw
	frappe.whitelist = whitelist
	frappe.only_for = lambda *args, **kwargs: None
	frappe.parse_json = lambda value: json.loads(value) if isinstance(value, str) else value
	frappe.get_roles = lambda user=None: []
	frappe.has_permission = lambda *a, **k: True
	frappe.get_all = lambda *a, **k: []
	frappe.get_list = lambda *a, **k: []
	frappe.get_cached_value = lambda *a, **k: None
	frappe.generate_hash = lambda length=20: "a" * length
	frappe.defaults = types.SimpleNamespace(
		get_user_default=lambda *a, **k: None,
		set_user_default=lambda *a, **k: None,
	)
	frappe.conf = _dict()
	frappe.session = _dict(user="Administrator")
	frappe.local = _dict()
	frappe.db = types.SimpleNamespace(
		exists=lambda *a, **k: True,
		get_value=lambda *a, **k: None,
		sql=lambda *a, **k: [],
		count=lambda *a, **k: 0,
		set_value=lambda *a, **k: None,
		commit=lambda *a, **k: None,
		rollback=lambda *a, **k: None,
	)

	utils = types.ModuleType("frappe.utils")

	def flt(value, precision=None):
		try:
			return float(value or 0)
		except (TypeError, ValueError):
			return 0.0

	def getdate(value=None):
		if value is None:
			return datetime.date.today()
		if isinstance(value, datetime.date):
			return value
		return datetime.date.fromisoformat(str(value)[:10])

	utils.flt = flt
	utils.cint = lambda value: int(flt(value))
	utils.getdate = getdate
	utils.today = lambda: datetime.date.today().isoformat()
	utils.now = lambda: datetime.datetime.now().isoformat()
	utils.now_datetime = datetime.datetime.now
	utils.add_days = lambda date, days: getdate(date) + datetime.timedelta(days=days)
	utils.add_months = lambda date, months: getdate(date)  # not exercised by these tests
	utils.formatdate = lambda value, fmt=None: str(value)
	utils.format_datetime = lambda value, fmt=None: str(value)
	utils.escape_html = lambda text: str(text).replace("<", "&lt;").replace(">", "&gt;")
	utils.get_backups_path = lambda: ""
	utils.get_bench_path = lambda: ""
	utils.get_link_to_form = lambda doctype, name: f"/app/{doctype.lower().replace(' ', '-')}/{name}"
	frappe.utils = utils

	password = types.ModuleType("frappe.utils.password")
	password.encrypt = lambda text, *args, **kwargs: f"enc:{text}"
	password.decrypt = lambda text, *args, **kwargs: text[len("enc:"):]
	utils.password = password
	sys.modules["frappe.utils.password"] = password

	rate_limiter = types.ModuleType("frappe.rate_limiter")
	rate_limiter.rate_limit = lambda *args, **kwargs: (lambda fn: fn)

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.rate_limiter"] = rate_limiter

	# erpnext is only imported for get_payment_entry, never called here
	for name in (
		"erpnext",
		"erpnext.accounts",
		"erpnext.accounts.doctype",
		"erpnext.accounts.doctype.payment_entry",
		"erpnext.accounts.doctype.payment_entry.payment_entry",
	):
		sys.modules.setdefault(name, types.ModuleType(name))
	sys.modules["erpnext.accounts.doctype.payment_entry.payment_entry"].get_payment_entry = None


try:
	import frappe  # noqa: F401
except ImportError:
	_install_frappe_stub()
