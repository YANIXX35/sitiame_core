# -*- coding: utf-8 -*-
"""
PME360 — Script 1 : correction des écritures et des comptes d'affectation
=========================================================================

Corrige les cinq défauts relevés dans « Audit des écritures et des comptes
d'affectation — PME360 v1.0 » (20/10/2026), sans modifier une seule ligne
du cœur de Frappe ou d'ERPNext.

CE QUE CE SCRIPT NE FAIT JAMAIS
-------------------------------
  * Il ne supprime aucune ligne de `tabGL Entry`. Jamais. Sous aucune option.
  * Il ne modifie aucune écriture existante.
  * Il ne valide (submit) aucun document comptable.
  * Il ne touche à aucun fichier de apps/frappe, apps/erpnext ou apps/hrms.

Les régularisations sont produites sous forme d'écritures de journal
EN BROUILLON (docstatus 0), que le comptable relit et valide lui-même.
C'est la seule manière compatible avec le grand livre immuable et avec
l'article de l'AUDCIF qui impose la correction par inscription en négatif.

EMPLACEMENT
-----------
  apps/sitiame_core/sitiame_core/scripts/correction_ecritures_comptes.py

UTILISATION
-----------
  # 1. Diagnostic seul, aucune écriture (à faire en premier, toujours)
  bench --site erp.sitiame-capital.com execute \
      sitiame_core.scripts.correction_ecritures_comptes.main

  # 2. Simulation d'une étape précise
  bench --site erp.sitiame-capital.com execute \
      sitiame_core.scripts.correction_ecritures_comptes.main \
      --kwargs "{'etapes': ['parametres', 'comptes_attente']}"

  # 3. Application réelle, société par société
  bench --site erp.sitiame-capital.com execute \
      sitiame_core.scripts.correction_ecritures_comptes.main \
      --kwargs "{'apply': True, 'societe': 'SITIAME', 'etapes': ['parametres']}"

ORDRE IMPOSÉ
------------
  parametres -> comptes_attente -> tva -> articles -> permissions
  -> inventaire -> regularisation

  L'étape « regularisation » refuse de s'exécuter si « parametres » n'a pas
  été appliquée : nettoyer avant d'avoir bloqué la cause revient à
  recommencer la semaine suivante.
"""

import json
import os
from collections import defaultdict

import frappe
from frappe.utils import flt, nowdate, getdate


# =============================================================================
# PARAMÈTRES — à relire avec l'expert-comptable AVANT la première application
# =============================================================================

# Compte d'attente créé par société. Il remplace 6011 comme compte de charge
# par défaut : une ligne non affectée doit sauter aux yeux, pas se cacher
# dans les achats de marchandises.
COMPTE_ATTENTE = {
    "numero": "6589",
    "nom": "Charges en attente d'imputation",
    "parent_numero": "658",          # Autres charges diverses
    "root_type": "Expense",
}

# Table de correspondance « nature d'achat -> compte SYSCOHADA -> TVA ».
# Reprise de l'onglet 4 de la feuille de travail d'audit.
# C'est LE livrable à faire valider par un expert-comptable inscrit à l'OEC-CI :
# tant qu'il ne l'a pas signée, laissez APPLIQUER_AFFECTATION à False.
AFFECTATION_PAR_GROUPE = {
    # Groupe d'articles ERPNext : (compte d'achat, compte de vente, TVA achat)
    "Marchandises":            ("601", "701", "4452"),
    "Matières premières":      ("604", "701", "4452"),
    "Raw Material":            ("604", "701", "4452"),
    "Consumable":              ("604", "701", "4452"),
    "Eau":                     ("6051", None, "4452"),
    "Électricité":             ("6052", None, "4452"),
    "Énergie":                 ("6053", None, "4452"),
    "Maintenance":             ("6243", "706", "4454"),
    "Transport":               ("61",   "706", "4453"),
    "Honoraires":              ("632",  "706", "4454"),
    "Services":                ("632",  "706", "4454"),
    "Télécommunications":      ("628",  "706", "4454"),
    "Publicité":               ("627",  "706", "4454"),
}
APPLIQUER_AFFECTATION = False   # passer à True APRÈS validation par l'OEC-CI

# Comptes de TVA déductible par nature, pour les modèles de taxes par article.
TVA_DEDUCTIBLE = {
    "Immobilisations":        "4451",
    "Achats":                 "4452",
    "Transport":              "4453",
    "Services extérieurs":    "4454",
}
TAUX_TVA = 18.0

# Rôles considérés comme « clients ». Ils perdent le droit de supprimer une
# pièce comptable. À tenir à jour si de nouveaux rôles d'offre sont créés.
ROLES_CLIENTS = [
    "PME Client",
    "PME360 Essentiel",
    "PME360 Conformite",
    "PME360 Pilotage",
    "PME360 Transformation",
]

# Documents comptables dont la suppression est retirée aux rôles clients.
DOCTYPES_COMPTABLES = [
    "Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry",
    "Stock Entry", "Delivery Note", "Purchase Receipt", "Period Closing Voucher",
]

ETAPES = [
    "parametres", "comptes_attente", "tva", "articles",
    "permissions", "inventaire", "regularisation",
]


# =============================================================================
# SOCLE — journalisation, simulation, garde-fous
# =============================================================================

class Journal:
    """Trace tout ce que le script fait ou ferait. Rien n'est silencieux."""

    def __init__(self, apply_mode):
        self.apply = apply_mode
        self.lignes = []
        self.anomalies = []

    def _log(self, niveau, message, detail=None):
        prefixe = "   APPLIQUÉ " if self.apply else "   SIMULÉ   "
        if niveau in ("info", "titre", "alerte"):
            prefixe = "            "
        ligne = {"niveau": niveau, "message": message, "detail": detail}
        self.lignes.append(ligne)
        if niveau == "titre":
            print("\n" + "=" * 78)
            print(message)
            print("=" * 78)
        elif niveau == "alerte":
            print("   /!\\  " + message)
            self.anomalies.append(message)
        else:
            print(prefixe + message)
        if detail:
            print("              " + str(detail))

    def titre(self, m):            self._log("titre", m)
    def info(self, m, d=None):     self._log("info", m, d)
    def action(self, m, d=None):   self._log("action", m, d)
    def alerte(self, m, d=None):   self._log("alerte", m, d)

    def rapport(self, chemin):
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"mode": "apply" if self.apply else "simulation",
                       "date": nowdate(), "lignes": self.lignes,
                       "anomalies": self.anomalies}, f,
                      ensure_ascii=False, indent=2)
        print(f"\nRapport écrit dans {chemin}")


def garde_fous(jrn):
    """Refuse de démarrer si les conditions ne sont pas réunies."""
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw("Ce script doit être exécuté par Administrator ou un System Manager.")

    immuable = frappe.db.get_single_value("Accounts Settings", "enable_immutable_ledger")
    if not immuable:
        frappe.throw(
            "Le grand livre immuable est désactivé. Ce script suppose qu'il est actif : "
            "il corrige par contrepassation, jamais par modification. "
            "Activez-le avant de continuer, ou arrêtez-vous ici."
        )
    jrn.info("Grand livre immuable : actif. Correction par contrepassation uniquement.")


def societes(filtre=None):
    if filtre:
        return [filtre] if frappe.db.exists("Company", filtre) else []
    return frappe.get_all("Company", pluck="name", order_by="name")


def compte(numero, societe):
    """Retourne le nom complet d'un compte à partir de son numéro SYSCOHADA."""
    return frappe.db.get_value(
        "Account", {"account_number": numero, "company": societe, "is_group": 0}, "name"
    )


# =============================================================================
# ÉTAPE 1 — paramètres de comptabilité (corrige le défaut A3)
# =============================================================================

def etape_parametres(jrn, apply_mode, _societe=None):
    """La suppression d'un document doit emporter ses écritures.

    C'est la cause directe des quatre pièces orphelines de SITIAME : le
    paramètre est à 0, donc supprimer une facture annulée laisse ses lignes
    au grand livre, sans document pour les justifier.
    """
    jrn.titre("ÉTAPE 1 — Paramètres de comptabilité")

    actuel = frappe.db.get_single_value("Accounts Settings", "delete_linked_ledger_entries")
    if actuel:
        jrn.info("« Supprimer les écritures liées » : déjà activé. Rien à faire.")
    else:
        jrn.action("Activer « Supprimer les écritures comptables et de stock "
                   "à la suppression d'une transaction »")
        if apply_mode:
            frappe.db.set_single_value("Accounts Settings", "delete_linked_ledger_entries", 1)

    # Le contrôle d'unicité des factures fournisseurs évite les doublons du
    # type PINV-00004 / PINV-00005, identiques à 417 720 FCFA chacune.
    if not frappe.db.get_single_value("Accounts Settings", "check_supplier_invoice_uniqueness"):
        jrn.action("Activer le contrôle d'unicité du numéro de facture fournisseur")
        if apply_mode:
            frappe.db.set_single_value(
                "Accounts Settings", "check_supplier_invoice_uniqueness", 1)
    else:
        jrn.info("Contrôle d'unicité des factures fournisseurs : déjà actif.")


# =============================================================================
# ÉTAPE 2 — compte d'attente et comptes par défaut (corrige A4)
# =============================================================================

def etape_comptes_attente(jrn, apply_mode, societe=None):
    """Remplace 6011 comme compte de charge par défaut.

    6011 « Achats de marchandises » recevait tout ce qui n'était pas affecté,
    y compris l'électricité. Un compte d'attente dédié rend le défaut visible
    au lieu de le dissimuler dans un compte légitime.
    """
    jrn.titre("ÉTAPE 2 — Compte d'attente et comptes par défaut")

    for soc in societes(societe):
        parent = frappe.db.get_value(
            "Account",
            {"account_number": COMPTE_ATTENTE["parent_numero"], "company": soc, "is_group": 1},
            "name")
        if not parent:
            jrn.alerte(f"{soc} : compte parent {COMPTE_ATTENTE['parent_numero']} introuvable. "
                       f"Société ignorée — plan comptable non standard, à traiter à la main.")
            continue

        attente = compte(COMPTE_ATTENTE["numero"], soc)
        if not attente:
            jrn.action(f"{soc} : créer le compte {COMPTE_ATTENTE['numero']} "
                       f"« {COMPTE_ATTENTE['nom']} »")
            if apply_mode:
                doc = frappe.get_doc({
                    "doctype": "Account",
                    "account_number": COMPTE_ATTENTE["numero"],
                    "account_name": COMPTE_ATTENTE["nom"],
                    "parent_account": parent,
                    "company": soc,
                    "root_type": COMPTE_ATTENTE["root_type"],
                    "is_group": 0,
                })
                doc.insert(ignore_permissions=True)  # provisionnement : exception assumée
                attente = doc.name
        else:
            jrn.info(f"{soc} : compte d'attente déjà présent ({attente}).")

        actuel = frappe.db.get_value("Company", soc, "default_expense_account")
        if attente and actuel != attente:
            jrn.action(f"{soc} : compte de charge par défaut {actuel or 'vide'} -> {attente}")
            if apply_mode:
                frappe.db.set_value("Company", soc, "default_expense_account", attente)
        elif attente:
            jrn.info(f"{soc} : compte de charge par défaut déjà correct.")


# =============================================================================
# ÉTAPE 3 — ventilation de la TVA déductible (corrige A5)
# =============================================================================

def etape_tva(jrn, apply_mode, societe=None):
    """Crée un modèle de taxes par article et par nature.

    Le modèle d'achat actuel ne contient qu'une ligne, sur 4452. Résultat :
    une prestation de services est taxée en 4452 et des marchandises en 4454.
    Le compte de TVA doit suivre la nature de la ligne, pas celle de la facture.
    """
    jrn.titre("ÉTAPE 3 — Ventilation de la TVA déductible")

    for soc in societes(societe):
        abbr = frappe.db.get_value("Company", soc, "abbr")
        for nature, numero in TVA_DEDUCTIBLE.items():
            cpt = compte(numero, soc)
            if not cpt:
                jrn.alerte(f"{soc} : compte de TVA {numero} introuvable. Nature « {nature} » ignorée.")
                continue

            nom = f"TVA {int(TAUX_TVA)}% {nature} - {abbr}"
            if frappe.db.exists("Item Tax Template", nom):
                jrn.info(f"{soc} : modèle « {nom} » déjà présent.")
                continue

            jrn.action(f"{soc} : créer le modèle de taxes par article « {nom} » -> {numero}")
            if apply_mode:
                frappe.get_doc({
                    "doctype": "Item Tax Template",
                    "title": f"TVA {int(TAUX_TVA)}% {nature}",
                    "company": soc,
                    "taxes": [{"tax_type": cpt, "tax_rate": TAUX_TVA}],
                }).insert(ignore_permissions=True)  # provisionnement : exception assumée

    jrn.info("Rappel : le paramètre « ajouter les taxes depuis le modèle de l'article » "
             "est déjà actif. Ces modèles seront donc pris en compte dès qu'ils seront "
             "rattachés aux articles ou à leurs groupes.")


# =============================================================================
# ÉTAPE 4 — affectation des articles (corrige A4, suite)
# =============================================================================

def etape_articles(jrn, apply_mode, societe=None):
    """Réaffecte les comptes des articles selon leur groupe.

    Les 38 lignes de valeurs par défaut portent toutes 6011 et 7011, quelle
    que soit la nature de l'article. On remplace cette copie uniforme par une
    affectation issue du groupe d'articles.
    """
    jrn.titre("ÉTAPE 4 — Affectation des articles")

    if not APPLIQUER_AFFECTATION:
        jrn.alerte("APPLIQUER_AFFECTATION est à False : étape en inventaire seul. "
                   "Passez-la à True une fois la table validée par l'expert-comptable.")

    sans_groupe, a_corriger = [], []
    for d in frappe.get_all("Item Default",
                            fields=["name", "parent", "company",
                                    "expense_account", "income_account"]):
        if societe and d.company != societe:
            continue
        groupe = frappe.db.get_value("Item", d.parent, "item_group")
        regle = AFFECTATION_PAR_GROUPE.get(groupe)
        if not regle:
            sans_groupe.append((d.parent, groupe, d.company))
            continue

        num_achat, num_vente, _num_tva = regle
        cible_achat = compte(num_achat, d.company) if num_achat else None
        cible_vente = compte(num_vente, d.company) if num_vente else None
        if (cible_achat and d.expense_account != cible_achat) or \
           (cible_vente and d.income_account != cible_vente):
            a_corriger.append((d.name, d.parent, d.company,
                               d.expense_account, cible_achat,
                               d.income_account, cible_vente))

    jrn.info(f"{len(a_corriger)} ligne(s) d'affectation à corriger.")
    for nom, article, soc, ea, ca, ia, ci in a_corriger:
        jrn.action(f"{soc} / {article} : achat {ea} -> {ca} · vente {ia} -> {ci}")
        if apply_mode and APPLIQUER_AFFECTATION:
            if ca:
                frappe.db.set_value("Item Default", nom, "expense_account", ca)
            if ci:
                frappe.db.set_value("Item Default", nom, "income_account", ci)

    if sans_groupe:
        jrn.alerte(f"{len(sans_groupe)} ligne(s) sans règle d'affectation — groupe absent "
                   f"de la table ou non renseigné. À qualifier avec le comptable.")
        for article, groupe, soc in sans_groupe[:20]:
            jrn.info(f"    {soc} / {article} : groupe = {groupe or 'NON RENSEIGNÉ'}")

    # Les tiers sans groupe empêchent toute règle d'affectation par type de tiers.
    for dt, champ in (("Supplier", "supplier_group"), ("Customer", "customer_group")):
        orphelins = [d.name for d in frappe.get_all(dt, fields=["name", champ])
                     if not d.get(champ)]
        if orphelins:
            jrn.alerte(f"{len(orphelins)} {dt}(s) sans groupe : {', '.join(orphelins[:10])}")


# =============================================================================
# ÉTAPE 5 — permissions sur les pièces comptables (corrige A3, prévention)
# =============================================================================

def etape_permissions(jrn, apply_mode, _societe=None):
    """Retire aux rôles clients le droit de supprimer une pièce comptable.

    Une pièce annulée doit rester annulée, pas disparaître. C'est la
    prévention du défaut A3 côté utilisateur.
    """
    jrn.titre("ÉTAPE 5 — Permissions de suppression")

    from frappe.permissions import update_permission_property

    for dt in DOCTYPES_COMPTABLES:
        if not frappe.db.exists("DocType", dt):
            continue
        for role in ROLES_CLIENTS:
            if not frappe.db.exists("Role", role):
                continue
            perm = frappe.db.exists("Custom DocPerm", {"parent": dt, "role": role, "permlevel": 0}) \
                or frappe.db.exists("DocPerm", {"parent": dt, "role": role, "permlevel": 0})
            if not perm:
                continue
            jrn.action(f"{dt} / {role} : retirer le droit de suppression")
            if apply_mode:
                update_permission_property(dt, role, 0, "delete", 0)

    # Les permissions sur les objets de période (Accounting Period, Fiscal Year,
    # Period Closing Voucher) relèvent du script 2 — mise_en_oeuvre_exercices.
    # Elles ne sont pas traitées ici pour éviter que deux scripts se disputent
    # le même réglage.
    jrn.info("Permissions sur les objets de période : voir le script 2.")

    jrn.alerte("Rappel : tant qu'un compte client porte le rôle Accounts Manager, "
               "ces restrictions sont contournables. Voir le chantier de cloisonnement "
               "du 15 octobre.")


# =============================================================================
# ÉTAPE 6 — inventaire des écritures orphelines et des contrepassations
# =============================================================================

def _inventaire(societe=None):
    """Lecture seule. Retourne les pièces du grand livre sans document."""
    filtres = {"is_cancelled": 0}
    if societe:
        filtres["company"] = societe

    lignes = frappe.get_all(
        "GL Entry", filters=filtres,
        fields=["company", "voucher_type", "voucher_no", "account",
                "debit", "credit", "posting_date", "remarks"],
        limit_page_length=0)

    par_piece = defaultdict(list)
    for l in lignes:
        par_piece[(l.company, l.voucher_type, l.voucher_no)].append(l)

    orphelines, contrepassees = [], []
    for (soc, vt, vn), rows in par_piece.items():
        existe = frappe.db.exists(vt, vn)
        net = defaultdict(float)
        for r in rows:
            net[r.account] += flt(r.debit) - flt(r.credit)
        net = {k: round(v, 2) for k, v in net.items() if round(v, 2) != 0}
        enreg = {"societe": soc, "type": vt, "piece": vn,
                 "lignes": len(rows), "net": net,
                 "a_contrepassation": any(
                     (r.remarks or "").startswith("On cancellation of") for r in rows)}
        if not existe:
            orphelines.append(enreg)
        if enreg["a_contrepassation"]:
            contrepassees.append(enreg)
    return orphelines, contrepassees


def etape_inventaire(jrn, _apply_mode, societe=None):
    jrn.titre("ÉTAPE 6 — Inventaire des pièces orphelines (lecture seule)")

    orphelines, contrepassees = _inventaire(societe)

    jrn.info(f"{len(contrepassees)} pièce(s) portant une contrepassation d'annulation.")
    jrn.info(f"{len(orphelines)} pièce(s) dont le document n'existe plus.")

    a_regulariser = [o for o in orphelines if o["net"]]
    sans_effet = [o for o in orphelines if not o["net"]]

    for o in sans_effet:
        jrn.info(f"  {o['societe']} / {o['piece']} : orpheline mais soldée "
                 f"(écriture et contrepassation se compensent). Aucune régularisation.")

    for o in a_regulariser:
        jrn.alerte(f"{o['societe']} / {o['piece']} : orpheline AVEC solde résiduel.")
        for cpt, montant in o["net"].items():
            sens = "débit" if montant > 0 else "crédit"
            jrn.info(f"    {cpt} : {abs(montant):,.0f} au {sens}".replace(",", " "))

    return a_regulariser


# =============================================================================
# ÉTAPE 7 — proposition de régularisation (BROUILLONS uniquement)
# =============================================================================

def etape_regularisation(jrn, apply_mode, societe=None):
    """Produit une écriture de journal EN BROUILLON par société concernée.

    Elle contrepasse le solde résiduel des pièces orphelines. Elle n'est PAS
    validée : le comptable la relit, l'ajuste et la valide. Le script ne
    décide rien — ni la réalité du décaissement Wave, ni le sort de la dette
    sans justificatif, ni le traitement des exercices antérieurs.
    """
    jrn.titre("ÉTAPE 7 — Proposition de régularisation (brouillons)")

    if not frappe.db.get_single_value("Accounts Settings", "delete_linked_ledger_entries"):
        frappe.throw(
            "L'étape « parametres » n'a pas été appliquée. Nettoyer avant d'avoir bloqué "
            "la cause revient à recommencer la semaine suivante. Exécutez d'abord :\n"
            "  --kwargs \"{'apply': True, 'etapes': ['parametres']}\""
        )

    a_regulariser = [o for o in _inventaire(societe)[0] if o["net"]]
    if not a_regulariser:
        jrn.info("Aucune pièce orpheline avec solde résiduel. Rien à régulariser.")
        return

    par_societe = defaultdict(list)
    for o in a_regulariser:
        par_societe[o["societe"]].append(o)

    for soc, pieces in par_societe.items():
        comptes = defaultdict(float)
        refs = []
        for p in pieces:
            refs.append(p["piece"])
            for cpt, montant in p["net"].items():
                comptes[cpt] += montant

        comptes = {k: round(v, 2) for k, v in comptes.items() if round(v, 2) != 0}
        if not comptes:
            continue

        # Contrepassation : on inverse le solde résiduel.
        lignes = []
        for cpt, montant in comptes.items():
            ligne = {"account": cpt}
            if montant > 0:
                ligne["credit_in_account_currency"] = abs(montant)
            else:
                ligne["debit_in_account_currency"] = abs(montant)
            # Les comptes de tiers exigent un tiers : on le laisse vide
            # volontairement, pour forcer le comptable à le renseigner.
            lignes.append(ligne)

        total_d = sum(l.get("debit_in_account_currency", 0) for l in lignes)
        total_c = sum(l.get("credit_in_account_currency", 0) for l in lignes)
        if round(total_d - total_c, 2) != 0:
            jrn.alerte(f"{soc} : le solde résiduel n'est pas équilibré "
                       f"({total_d:,.0f} / {total_c:,.0f}). Brouillon non produit, "
                       f"à traiter à la main.".replace(",", " "))
            continue

        libelle = (f"Régularisation PME360 — pièces orphelines : {', '.join(sorted(refs))}. "
                   f"Écritures sans document, voir la note d'audit du 20/10/2026. "
                   f"À ARBITRER AVANT VALIDATION.")

        jrn.action(f"{soc} : créer un brouillon d'écriture de journal — "
                   f"{len(lignes)} ligne(s), {total_d:,.0f} FCFA".replace(",", " "), libelle)

        if apply_mode:
            je = frappe.get_doc({
                "doctype": "Journal Entry",
                "voucher_type": "Journal Entry",
                "company": soc,
                "posting_date": nowdate(),
                "user_remark": libelle,
                "accounts": lignes,
            })
            je.insert(ignore_permissions=True)  # provisionnement : exception assumée
            # docstatus reste à 0 : AUCUNE validation automatique.
            jrn.info(f"    Brouillon créé : {je.name} — à relire et valider par le comptable.")


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

ETAPE_FN = {
    "parametres": etape_parametres,
    "comptes_attente": etape_comptes_attente,
    "tva": etape_tva,
    "articles": etape_articles,
    "permissions": etape_permissions,
    "inventaire": etape_inventaire,
    "regularisation": etape_regularisation,
}


def main(apply=False, societe=None, etapes=None, rapport=None):
    """Point d'entrée.

    apply    : False = simulation (par défaut). True = écriture réelle.
    societe  : limite le traitement à une société. None = toutes.
    etapes   : liste d'étapes. None = toutes sauf « regularisation ».
    rapport  : chemin du rapport JSON. None = dossier du site.
    """
    apply_mode = bool(apply)
    etapes = etapes or [e for e in ETAPES if e != "regularisation"]
    inconnues = [e for e in etapes if e not in ETAPE_FN]
    if inconnues:
        frappe.throw(f"Étape(s) inconnue(s) : {inconnues}. Valeurs admises : {ETAPES}")

    jrn = Journal(apply_mode)
    jrn.titre("PME360 — CORRECTION DES ÉCRITURES ET DES COMPTES")
    jrn.info("Mode : " + ("APPLICATION RÉELLE" if apply_mode else "SIMULATION — rien n'est écrit"))
    jrn.info("Société : " + (societe or "toutes"))
    jrn.info("Étapes : " + ", ".join(etapes))

    garde_fous(jrn)

    for e in etapes:
        ETAPE_FN[e](jrn, apply_mode, societe)

    if apply_mode:
        frappe.db.commit()
        jrn.info("Modifications validées en base.")
    else:
        frappe.db.rollback()
        jrn.info("Simulation terminée — aucune modification conservée.")

    chemin = rapport or os.path.join(
        frappe.get_site_path(), f"correction_ecritures_{nowdate()}.json")
    jrn.rapport(chemin)

    if jrn.anomalies:
        print(f"\n{len(jrn.anomalies)} point(s) d'attention — relisez le rapport avant d'appliquer.")
    return {"anomalies": len(jrn.anomalies), "rapport": chemin}
