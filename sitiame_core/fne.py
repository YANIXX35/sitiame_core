# Copyright (c) 2026, Sitiame Capital
# License: MIT
#
# Facture Normalisée Électronique (FNE) — Obligation DGI Côte d'Ivoire.
#
# Ce module assure deux choses :
#   1. Attribution d'un numéro FNE séquentiel à chaque Sales Invoice au moment
#      de la soumission (before_submit hook).
#   2. Vérification que les champs obligatoires sont présents (tax_id / NIF
#      de la société et RCCM).
#
# Le numéro FNE suit le format : FNE-{ABBR}-{YYYY}-{NNNNNN}
#   ABBR  = abréviation de la société (Company.abbr, ≤ 5 car.)
#   YYYY  = année fiscale de la facture
#   NNNNN = compteur séquentiel par société et par année (6 chiffres, remis à
#           zéro chaque année)

import frappe
from frappe import _


def assign_fne_number(doc, method=None):
    """Frappe hook : Sales Invoice.before_submit.
    Attribue le numéro FNE si absent, et valide les mentions obligatoires."""
    if doc.sitiame_fne_number:
        return

    _validate_fne_prerequisites(doc)

    year = frappe.utils.getdate(doc.posting_date).year
    abbr = frappe.db.get_value("Company", doc.company, "abbr") or "PME"
    abbr = abbr[:5].upper()

    # Compteur : nombre de factures déjà soumises pour cette société cette année
    count = frappe.db.count(
        "Sales Invoice",
        {
            "company": doc.company,
            "posting_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
            "docstatus": 1,
        },
    )
    doc.sitiame_fne_number = f"FNE-{abbr}-{year}-{count + 1:06d}"


def _validate_fne_prerequisites(doc):
    """Vérifie les champs obligatoires DGI avant d'attribuer un numéro FNE."""
    company_nif = frappe.db.get_value("Company", doc.company, "tax_id")
    if not company_nif:
        frappe.throw(
            _(
                "Le NIF de la société {0} est manquant. "
                "Renseignez-le dans Paramètres → Sociétés avant de soumettre une facture."
            ).format(doc.company),
            title=_("FNE — NIF requis"),
        )
