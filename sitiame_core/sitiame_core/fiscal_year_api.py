# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""API de gestion de l'exercice fiscal actif par utilisateur.

Chaque utilisateur peut basculer sur un exercice passé (max 3 ans en arrière).
L'exercice choisi est stocké dans frappe.defaults (par user) et injecté dans
le boot pour que le JS puisse filtrer toutes les listes en conséquence.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def _current_year():
    return getdate(nowdate()).year


@frappe.whitelist()
def get_available_fiscal_years():
    """Retourne les exercices fiscaux disponibles (année en cours + 3 ans max en arrière)
    pour la société de l'utilisateur connecté."""
    from sitiame_core.party_isolation import company_of

    company = company_of(frappe.session.user)
    current_year = _current_year()
    min_year = current_year - 3

    filters = {"disabled": 0}
    if company:
        # Exercices associés à cette company ou globaux
        company_abbr = frappe.db.get_value("Company", company, "abbr")

    all_fy = frappe.get_all(
        "Fiscal Year",
        filters=filters,
        fields=["name", "year_start_date", "year_end_date"],
        order_by="year_start_date desc",
    )

    result = []
    for fy in all_fy:
        start_year = getdate(fy.year_start_date).year
        end_year = getdate(fy.year_end_date).year
        # Garder seulement les exercices dans la fenêtre de 4 ans
        if start_year >= min_year:
            result.append({
                "name": fy.name,
                "label": str(start_year) if start_year == end_year else f"{start_year}-{end_year}",
                "year_start_date": str(fy.year_start_date),
                "year_end_date": str(fy.year_end_date),
                "year": start_year,
                "is_current": start_year == current_year,
            })

    return result


@frappe.whitelist()
def get_active_fiscal_year():
    """Retourne l'exercice fiscal actif pour l'utilisateur connecté.

    Si aucun n'est sélectionné, retourne l'exercice de l'année en cours.
    """
    user = frappe.session.user
    saved_fy_name = frappe.db.get_default("sitiame_active_fy", parent=user)

    all_fy = get_available_fiscal_years()
    if not all_fy:
        return None

    # Chercher l'exercice sauvegardé
    if saved_fy_name:
        for fy in all_fy:
            if fy["name"] == saved_fy_name:
                return fy

    # Par défaut : exercice de l'année en cours
    for fy in all_fy:
        if fy.get("is_current"):
            return fy

    # Dernier recours : le plus récent
    return all_fy[0] if all_fy else None


@frappe.whitelist()
def set_active_fiscal_year(fiscal_year_name):
    """Sauvegarde l'exercice fiscal actif pour l'utilisateur connecté."""
    user = frappe.session.user

    # Vérifier que cet exercice existe bien dans la liste disponible
    available = [fy["name"] for fy in (get_available_fiscal_years() or [])]
    if fiscal_year_name not in available:
        frappe.throw(
            _("Exercice fiscal {0} non disponible.").format(fiscal_year_name),
            frappe.PermissionError,
        )

    frappe.db.set_default("sitiame_active_fy", fiscal_year_name, parent=user)
    frappe.db.commit()

    # Retourner le détail complet
    return get_active_fiscal_year()
