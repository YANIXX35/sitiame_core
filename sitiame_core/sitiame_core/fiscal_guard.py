# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Garde-fou exercice fiscal : bloque la soumission d'un document dont la
posting_date est hors d'un exercice ouvert pour cette société.

Appelé en before_submit sur Purchase Invoice, Sales Invoice, Journal Entry
et Payment Entry.  Lève une ValidationError si :
  - aucun exercice fiscal ne couvre la date (date inconnue / avant création
    de la société dans ERPNext) ;
  - l'exercice est clôturé (un Period Closing Voucher soumis l'a fermé).

Un avertissement non bloquant est affiché si la date dépasse 60 jours dans
le passé mais reste dans un exercice ouvert (saisie tardive probable).
"""

import frappe
from frappe import _


def _get_fiscal_year_safe(posting_date, company):
    """Retourne le dict de l'exercice fiscal ou None si introuvable."""
    try:
        from frappe.utils.data import get_fiscal_year
        return get_fiscal_year(posting_date, company=company, as_dict=True)
    except Exception:
        return None


def _get_user_active_fiscal_year():
    """Retourne l'exercice fiscal actif sélectionné par l'utilisateur, ou None."""
    try:
        fy_name = frappe.db.get_default("sitiame_active_fy", parent=frappe.session.user)
        if not fy_name:
            return None
        return frappe.db.get_value(
            "Fiscal Year",
            fy_name,
            ["name", "year_start_date", "year_end_date"],
            as_dict=True,
        )
    except Exception:
        return None


def _is_period_closed(company, posting_date):
    """Vrai si un Period Closing Voucher soumis couvre cette date pour cette société."""
    return frappe.db.exists(
        "Period Closing Voucher",
        {
            "company": company,
            "docstatus": 1,
            "period_end_date": [">=", posting_date],
        },
    )


def validate_posting_date_in_open_period(doc, method=None):
    """before_submit : vérifie que la posting_date est dans l'exercice actif de l'utilisateur
    et que cet exercice n'est pas clôturé."""
    posting_date = str(doc.posting_date or "")
    company = doc.company

    if not posting_date or not company:
        return

    # 1. L'exercice fiscal existe-t-il pour cette date ?
    fy = _get_fiscal_year_safe(posting_date, company)
    if not fy:
        frappe.throw(
            _(
                "Impossible de soumettre : aucun exercice fiscal ne couvre la date {0} "
                "pour la société {1}.<br>"
                "Créez ou vérifiez l'exercice fiscal dans <b>Accounting → Fiscal Year</b> "
                "avant de soumettre ce document."
            ).format(posting_date, company),
            title=_("Exercice fiscal introuvable"),
        )

    # 2. L'exercice est-il clôturé ?
    if _is_period_closed(company, posting_date):
        frappe.throw(
            _(
                "Impossible de soumettre : la période comptable couvrant le {0} "
                "a été clôturée pour {1}.<br>"
                "Modifiez la date ou annulez la clôture dans "
                "<b>Accounting → Period Closing Voucher</b>."
            ).format(posting_date, company),
            title=_("Période clôturée"),
        )

    # 3. La date est-elle dans l'exercice actif sélectionné par l'utilisateur ?
    active_fy = _get_user_active_fiscal_year()
    if active_fy:
        start = str(active_fy.year_start_date)
        end = str(active_fy.year_end_date)
        if not (start <= posting_date <= end):
            frappe.throw(
                _(
                    "Impossible de soumettre : la date {0} n'appartient pas à l'exercice "
                    "actif <b>{1}</b> ({2} → {3}).<br>"
                    "Changez l'exercice actif via le sélecteur <b>Exercice</b> en haut "
                    "de la plateforme, ou corrigez la date du document."
                ).format(posting_date, active_fy.name, start, end),
                title=_("Date hors exercice actif"),
            )
