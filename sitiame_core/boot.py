# Copyright (c) 2026, Sitiame Capital
# License: MIT

import json

import frappe


def extend_bootinfo(bootinfo):
	"""Per-individual-user overrides (managed from the "Gérer le menu" admin
	page), independent of roles -- on top of Frappe's normal role-based
	filtering:

	- sitiame_hidden_sidebar_items: strips specific links from a Workspace
	  Sidebar's items (e.g. hiding "Paiements ERPNext" inside Organisation
	  for one particular Accounts Manager without touching that role).
	- sitiame_hidden_desktop_icons: strips whole top-level module tiles from
	  the /desk home screen (e.g. hiding the "Organisation" tile itself for
	  one specific user).

	Must never raise: a boot failure here would break login for everyone.
	"""
	try:
		_hide_sidebar_items(bootinfo)
	except Exception:
		frappe.log_error(title="sitiame_core.boot.extend_bootinfo: sidebar items failed")

	try:
		_hide_desktop_icons(bootinfo)
	except Exception:
		frappe.log_error(title="sitiame_core.boot.extend_bootinfo: desktop icons failed")

	try:
		_add_subscription_status(bootinfo)
	except Exception:
		frappe.log_error(title="sitiame_core.boot.extend_bootinfo: subscription status failed")


def _add_subscription_status(bootinfo):
	"""Read by public/js/subscription_banner.js. Only PME accounts get it:
	Sitiame staff never see the renewal banner."""
	if "PME Client" not in frappe.get_roles():
		return

	from sitiame_core.subscription_api import get_company_subscription, get_user_company

	company = get_user_company()
	if company:
		bootinfo["sitiame_subscription"] = get_company_subscription(company)


def _get_hidden_set(fieldname):
	raw = frappe.db.get_value("User", frappe.session.user, fieldname)
	if not raw:
		return set()
	return set(json.loads(raw))


def _hide_sidebar_items(bootinfo):
	hidden = _get_hidden_set("sitiame_hidden_sidebar_items")
	if not hidden:
		return

	sidebar_map = bootinfo.get("workspace_sidebar_item") or {}
	for sidebar in sidebar_map.values():
		items = sidebar.get("items") or []
		sidebar["items"] = [item for item in items if item.get("link_to") not in hidden]


def _hide_desktop_icons(bootinfo):
	hidden = _get_hidden_set("sitiame_hidden_desktop_icons")
	if not hidden:
		return

	icons = bootinfo.get("desktop_icons") or []
	bootinfo["desktop_icons"] = [icon for icon in icons if icon.get("label") not in hidden]
