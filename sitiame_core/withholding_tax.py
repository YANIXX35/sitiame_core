# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Retenues à la source Côte d'Ivoire (SYSCOHADA).

Deux types supportés :
  BNC/BIC 7,5%  — honoraires, commissions, prestations de professions
                  libérales ou d'entreprises sous régime BNC/BIC.
  RME 2%        — achats auprès d'un fournisseur sous régime microentreprises.

Usage : appeler apply_withholding(payment, doc) après get_payment_entry()
dans pay_on_submit.py.  Si le fournisseur n'a pas de retenue définie, la
fonction ne fait rien.

Compte de contrepartie : 4452 (Retenues à la source prélevées, à reverser).
"""

import frappe
from frappe import _
from frappe.utils import flt

# (option value in sitiame_withholding_type) → taux
WITHHOLDING_RATES = {
    "BNC/BIC 7,5%": 7.5,
    "RME 2%":       2.0,
}

_ACCOUNT_NUMBER = "4452"


def _withholding_account(company: str) -> str | None:
    """Trouve le compte 4452 (ou sous-compte 4452x) pour la société."""
    exact = frappe.db.get_value(
        "Account",
        {"account_number": _ACCOUNT_NUMBER, "company": company},
        "name",
    )
    if exact:
        return exact
    return frappe.db.get_value(
        "Account",
        {"account_number": ("like", f"{_ACCOUNT_NUMBER}%"), "company": company},
        "name",
        order_by="account_number asc",
    )


def apply_withholding(payment, doc) -> bool:
    """Calcule et applique la retenue à la source sur *payment*.

    Réduit `paid_amount` / `received_amount` du montant retenu et ajoute
    une ligne dans `deductions` vers le compte 4452.

    Retourne True si une retenue a été appliquée, False sinon.
    """
    supplier = doc.get("supplier") or doc.get("party")
    if not supplier:
        return False

    wh_type = frappe.db.get_value("Supplier", supplier, "sitiame_withholding_type")
    rate = WITHHOLDING_RATES.get(wh_type or "")
    if not rate:
        return False

    gross = flt(payment.paid_amount)
    if gross <= 0:
        return False

    # Arrondi à l'entier (XOF sans décimale)
    amount = round(gross * rate / 100)
    if amount <= 0:
        return False

    wh_account = _withholding_account(doc.company)
    if not wh_account:
        frappe.msgprint(
            _("Compte {0} introuvable pour {1} : retenue {2} non appliquée.").format(
                _ACCOUNT_NUMBER, doc.company, wh_type
            ),
            indicator="orange",
        )
        return False

    payment.paid_amount     -= amount
    payment.received_amount -= amount
    row = frappe._dict(
        account=wh_account,
        cost_center=payment.cost_center,
        amount=amount,
    )
    # Vrai Document Frappe → payment.append("deductions", row)
    # frappe._dict de test    → payment.deductions.append(row)
    if callable(getattr(payment, "append", None)):
        payment.append("deductions", row)
    else:
        payment.deductions.append(row)
    payment.remarks = (payment.remarks or "") + (
        f" | Retenue {wh_type} : {amount:,.0f} XOF → {wh_account}"
    )
    return True
