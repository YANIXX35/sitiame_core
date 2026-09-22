# Copyright (c) 2026, Sitiame Capital
# License: MIT

import json

import frappe


def extend_bootinfo(bootinfo):
	"""Strip Workspace Sidebar Item entries a specific user has been asked to
	not see, on top of Frappe's normal role-based item filtering. This is a
	per-individual-user override (managed from the "Gérer le menu" admin
	page), independent of roles -- e.g. hiding "Paiements ERPNext" for one
	particular Accounts Manager without touching that role for everyone else.

	Must never raise: a boot failure here would break login for everyone.
	"""
	try:
		raw = frappe.db.get_value("User", frappe.session.user, "sitiame_hidden_sidebar_items")
		if not raw:
			return

		hidden = set(json.loads(raw))
		if not hidden:
			return

		sidebar_map = bootinfo.get("workspace_sidebar_item") or {}
		for sidebar in sidebar_map.values():
			items = sidebar.get("items") or []
			sidebar["items"] = [item for item in items if item.get("link_to") not in hidden]
	except Exception:
		frappe.log_error(title="sitiame_core.boot.extend_bootinfo failed")
