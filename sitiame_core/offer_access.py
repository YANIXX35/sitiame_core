# Copyright (c) 2026, Sitiame Capital
# License: MIT
#
# Contrôle serveur des accès par module selon l'offre PME360.
#
# Les rôles PME360 Essentiel / Pilotage / Transformation masquent les menus
# dans boot.py, mais seul ce fichier constitue la barrière réelle : un
# utilisateur Essentiel qui appelle l'API directement se voit refuser l'accès.
#
# Deux mécanismes :
#   1. Hooks Frappe has_permission + get_permission_query_conditions — bloque
#      l'accès aux doctypes restreints sans modifier les rôles ERPNext natifs.
#   2. Décorateur require_offer(min_offer) — pour les API methods @whitelist.
#
# La vérification est transparente pour le staff (non-PME) : ils passent toujours.

import functools

import frappe

# ---------------------------------------------------------------------------
# Tables de correspondance offre ↔ doctypes
# ---------------------------------------------------------------------------

_PILOTAGE_DOCTYPES = (
    # Immobilisations
    "Asset",
    "Asset Category",
    "Asset Movement",
    "Asset Maintenance",
    "Asset Repair",
    "Asset Value Adjustment",
    # Ressources humaines
    "Employee",
    "Employee Type",
    "Leave Application",
    "Leave Allocation",
    "Leave Type",
    "Attendance",
    "Attendance Request",
    # Paie
    "Salary Slip",
    "Payroll Entry",
    "Salary Structure",
    "Salary Structure Assignment",
    "Employee Tax Exemption Declaration",
)

_TRANSFORMATION_DOCTYPES = (
    "Budget",
    "Budget Amendment",
)

# Doctype → offre minimum requise pour un utilisateur PME Client
OFFER_RESTRICTED_DOCTYPES: dict = {dt: "Pilotage" for dt in _PILOTAGE_DOCTYPES}
OFFER_RESTRICTED_DOCTYPES.update({dt: "Transformation" for dt in _TRANSFORMATION_DOCTYPES})

_OFFER_RANK = {"Essentiel": 0, "Pilotage": 1, "Transformation": 2}


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _pme_offer(user=None):
    """Retourne l'offre active d'un utilisateur PME, ou None si staff/admin."""
    user = user or frappe.session.user
    roles = frappe.get_roles(user)
    if "PME Client" not in roles:
        return None  # staff ou Administrator — pas soumis au contrôle offre
    for offer in ("Transformation", "Pilotage", "Essentiel"):
        if f"PME360 {offer}" in roles:
            return offer
    return "Essentiel"  # fallback conservateur (jamais en production normale)


def _rank(offer):
    return _OFFER_RANK.get(offer or "Essentiel", 0)


def _allowed(user, doctype):
    """True si l'utilisateur a le niveau d'offre requis pour ce doctype."""
    required = OFFER_RESTRICTED_DOCTYPES.get(doctype)
    if not required:
        return True
    offer = _pme_offer(user)
    if offer is None:
        return True  # staff — toujours autorisé
    return _rank(offer) >= _rank(required)


# ---------------------------------------------------------------------------
# Hooks Frappe
# ---------------------------------------------------------------------------

def get_permission_query_conditions(user=None, doctype=None):
    """Enregistré dans hooks.py permission_query_conditions.
    Retourne '0 = 1' (aucun résultat) si l'offre est insuffisante."""
    user = user or frappe.session.user
    return "" if _allowed(user, doctype) else "0 = 1"


def has_permission(doc, ptype=None, user=None, debug=False):
    """Enregistré dans hooks.py has_permission.
    Retourne False si l'offre PME est insuffisante pour ce doctype."""
    user = user or frappe.session.user
    return _allowed(user, doc.doctype)


# ---------------------------------------------------------------------------
# Décorateur pour les API methods @frappe.whitelist()
# ---------------------------------------------------------------------------

def require_offer(min_offer):
    """Décorateur pour les endpoints API réservés à une offre PME360 minimum.

    Le staff (sans rôle PME Client) passe toujours.
    Un PME dont le rang est insuffisant reçoit une PermissionError.

    Usage :
        @frappe.whitelist()
        @require_offer("Pilotage")
        def export_payroll_summary():
            ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            offer = _pme_offer()
            if offer is not None and _rank(offer) < _rank(min_offer):
                frappe.throw(
                    f"Cette fonctionnalité est réservée à l'offre PME360 {min_offer} ou supérieure.",
                    frappe.PermissionError,
                )
            return fn(*args, **kwargs)
        return wrapper
    return decorator
