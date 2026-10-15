# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Two isolation rules in one handler:

1. STAFF isolation: staff accounts do not see each other's business documents.
   A staff member's own documents are visible; PME documents are visible to all
   staff. Documents created by the API user or Administrator are always visible.

2. PME isolation: a PME account only sees documents belonging to its own Company.
   ERPNext's Company User Permission provides a first layer, but it is not
   reliable on all transactional doctypes and can be absent for orphan accounts.
   This hook adds an explicit SQL condition + has_permission check as a guarantee.

"Staff"  = System User without a Company User Permission, other than exempt users.
"PME"    = System User with the "PME Client" role.
"Orphan" = PME Client without a Company User Permission → sees nothing.
"""

import frappe

ISOLATED_DOCTYPES = (
    "Sales Invoice",
    "Purchase Invoice",
    "POS Invoice",
    "Payment Entry",
    "Journal Entry",
    "Quotation",
    "Sales Order",
    "Delivery Note",
    "Supplier Quotation",
    "Request for Quotation",
    "Purchase Order",
    "Purchase Receipt",
    "Material Request",
    "Stock Entry",
    "Stock Reconciliation",
    "Customer",
    "Supplier",
    "Item",
)

# These users bypass all isolation: they see every company's documents and
# their own documents are visible to all staff.
EXEMPT_USERS = ("Administrator", "api-pme360@sitiame-capital.com")

# Items are intentionally shared across PMEs: PME360 matches items by label
# and a single item record can be on invoices of multiple PMEs.
_PME_SHARED_DOCTYPES = frozenset(["Item"])

# Customers and suppliers are private to the PME account that created them,
# even from the other accounts of the same company (asked 2026-10-15).
# Sitiame staff still see every PME's.
OWNER_ONLY_DOCTYPES = frozenset(["Customer", "Supplier"])

_UNSET = object()  # sentinel distinguishing "not yet computed" from None


# ---------------------------------------------------------------------------
# Staff isolation helpers
# ---------------------------------------------------------------------------

def _staff_users():
    """Every staff account, cached for the request."""
    if getattr(frappe.local, "sitiame_staff_users", None) is None:
        frappe.local.sitiame_staff_users = set(
            frappe.db.sql_list(
                """
                select u.name from `tabUser` u
                where u.user_type = 'System User'
                    and u.name not in %(exempt)s
                    and not exists (
                        select 1 from `tabUser Permission` up
                        where up.user = u.name and up.allow = 'Company'
                    )
                """,
                {"exempt": EXEMPT_USERS},
            )
        )
    return frappe.local.sitiame_staff_users


def _hidden_owners(user):
    """Owners whose documents `user` must not see (empty if not staff)."""
    staff = _staff_users()
    if user not in staff:
        return set()
    return staff - {user}


# ---------------------------------------------------------------------------
# PME isolation helpers
# ---------------------------------------------------------------------------

def _pme_company(user):
    """Return the PME's Company, None if PME orphan, or _UNSET if staff/admin.

    Cached in frappe.local for the lifetime of the HTTP request.
    """
    attr = f"_sitiame_iso_company_{user}"
    cached = getattr(frappe.local, attr, _UNSET)
    if cached is not _UNSET:
        return cached

    if user in EXEMPT_USERS or "PME Client" not in frappe.get_roles(user):
        result = _UNSET  # not a PME → fall through to staff logic
    else:
        from sitiame_core.party_isolation import company_of
        result = company_of(user)  # None when no Company User Permission

    setattr(frappe.local, attr, result)
    return result


# ---------------------------------------------------------------------------
# Frappe hooks
# ---------------------------------------------------------------------------

def get_permission_query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if doctype not in ISOLATED_DOCTYPES:
        return ""

    company = _pme_company(user)

    # ── PME Client on a non-shared doctype ──────────────────────────────────
    if company is not _UNSET and doctype not in _PME_SHARED_DOCTYPES:
        if not company:
            return "0 = 1"  # orphan PME → empty list
        condition = f"`tab{doctype}`.`company` = {frappe.db.escape(company)}"
        if doctype in OWNER_ONLY_DOCTYPES:
            condition += f" and `tab{doctype}`.`owner` = {frappe.db.escape(user)}"
        return condition

    # ── Staff: hide other staff members' documents ───────────────────────────
    hidden = _hidden_owners(user)
    if not hidden:
        return ""
    owners = ", ".join(frappe.db.escape(owner) for owner in sorted(hidden))
    return f"`tab{doctype}`.`owner` not in ({owners})"


def has_permission(doc, ptype=None, user=None, debug=False):
    user = user or frappe.session.user
    if doc.doctype not in ISOLATED_DOCTYPES or not doc.get("owner"):
        return True

    company = _pme_company(user)

    # ── PME Client on a non-shared doctype ──────────────────────────────────
    if company is not _UNSET and doc.doctype not in _PME_SHARED_DOCTYPES:
        if not company:
            return False  # orphan PME → no access
        if doc.doctype in OWNER_ONLY_DOCTYPES and doc.get("owner") != user:
            return False
        return doc.get("company") == company

    # ── Staff ────────────────────────────────────────────────────────────────
    return doc.owner not in _hidden_owners(user)
