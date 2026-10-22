# -*- coding: utf-8 -*-
"""
PME360 — Script 2 : mise en œuvre de la gestion des exercices
==============================================================

Met en place le verrouillage des périodes décrit dans « Gestion des exercices
dans PME360 v1.0 » (20/10/2026), sans modifier une seule ligne du cœur de
Frappe ou d'ERPNext.

PRINCIPE
--------
ERPNext ne sélectionne pas un exercice : il le déduit de la date de
comptabilisation. On ne revient donc pas à un sélecteur d'exercice — on
installe ce que le modèle à conteneur apportait vraiment : un état visible
et un acte délibéré pour écrire dans le passé.

Deux verrous, deux rôles distincts, et c'est volontaire :

  1. Date de gel par société + rôle « Comptable SITIAME »
     -> filet de sécurité courant. SITIAME peut encore corriger le passé
        récent sans cérémonie.

  2. Période comptable + rôle « PME360 Dérogation Période »
     -> verrou fort. PERSONNE ne porte ce rôle en permanence. Il est accordé
        pour 48 heures par une demande d'ouverture exceptionnelle, puis
        retiré automatiquement.

CE QUE CE SCRIPT NE FAIT JAMAIS
-------------------------------
  * Il ne touche à aucun fichier de apps/frappe, apps/erpnext, apps/hrms.
  * Il ne crée ni ne valide aucune écriture comptable.
  * Il ne ferme jamais le mois en cours.

EMPLACEMENT
-----------
  apps/sitiame_core/sitiame_core/scripts/mise_en_oeuvre_exercices.py

UTILISATION
-----------
  # 1. Diagnostic (toujours en premier)
  bench --site erp.sitiame-capital.com execute \
      sitiame_core.scripts.mise_en_oeuvre_exercices.main

  # 2. Socle : rôles, dates de gel, libellés, permissions — en simulation
  bench --site erp.sitiame-capital.com execute \
      sitiame_core.scripts.mise_en_oeuvre_exercices.main \
      --kwargs "{'etapes': ['roles','gel','dates','permissions','doctype_derogation']}"

  # 3. Application réelle
  bench --site erp.sitiame-capital.com execute \
      sitiame_core.scripts.mise_en_oeuvre_exercices.main \
      --kwargs "{'apply': True, 'etapes': ['roles','gel','dates','permissions','doctype_derogation']}"

  # 4. Clôture des mois écoulés, société par société
  bench --site erp.sitiame-capital.com execute \
      sitiame_core.scripts.mise_en_oeuvre_exercices.main \
      --kwargs "{'apply': True, 'societe': 'SITIAME', 'etapes': ['periodes'], 'jusqu_au': '2026-09-30'}"

À AJOUTER DANS hooks.py APRÈS LA PREMIÈRE APPLICATION
------------------------------------------------------
    doc_events = {
        "Company": {
            "after_insert": "sitiame_core.scripts.mise_en_oeuvre_exercices.provisionner_societe",
        },
        "Ouverture Exceptionnelle de Periode": {
            "on_submit": "sitiame_core.scripts.mise_en_oeuvre_exercices.ouvrir_derogation",
            "on_cancel": "sitiame_core.scripts.mise_en_oeuvre_exercices.fermer_derogation",
        },
    }

    scheduler_events = {
        "hourly": [
            "sitiame_core.scripts.mise_en_oeuvre_exercices.fermer_derogations_echues",
        ],
        "cron": {
            # clôture automatique du mois écoulé, le 10 à 2 h du matin
            "0 2 10 * *": ["sitiame_core.scripts.mise_en_oeuvre_exercices.cloture_mensuelle_auto"],
        },
    }
"""

import json
import os
from datetime import timedelta

import frappe
from frappe.utils import (add_days, add_months, get_first_day, get_last_day,
                          getdate, nowdate, now_datetime)


# =============================================================================
# PARAMÈTRES
# =============================================================================

ROLE_COMPTABLE_SITIAME = "Comptable Sitiame"          # filet de sécurité courant
ROLE_DEROGATION = "PME360 Derogation Periode"         # verrou fort, temporaire
ROLE_CHARGE_AFFAIRES = "Charge d'affaires Sitiame"    # déjà présent sur la plateforme

# Types de documents fermés par une période comptable.
DOCUMENTS_FERMES = [
    "Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry",
    "Stock Entry", "Delivery Note", "Purchase Receipt",
]

# Rôles considérés comme « clients ».
ROLES_CLIENTS = [
    "PME Client", "PME360 Essentiel", "PME360 Conformite",
    "PME360 Pilotage", "PME360 Transformation",
]

# Documents sur lesquels la case « Modifier la date de comptabilisation »
# passe en permlevel 1 : invisible et non modifiable pour les clients.
DOCUMENTS_DATE_VERROUILLEE = [
    "Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry",
    "Stock Entry", "Delivery Note", "Purchase Receipt", "POS Invoice",
    "Stock Reconciliation",
]

DUREE_DEROGATION_HEURES = 48

ETAPES = ["diagnostic", "roles", "gel", "periodes", "dates",
          "permissions", "doctype_derogation"]


# =============================================================================
# SOCLE
# =============================================================================

class Journal:
    def __init__(self, apply_mode):
        self.apply = apply_mode
        self.lignes = []
        self.anomalies = []

    def _log(self, niveau, message, detail=None):
        prefixe = "   APPLIQUÉ " if self.apply else "   SIMULÉ   "
        if niveau in ("info", "titre", "alerte"):
            prefixe = "            "
        self.lignes.append({"niveau": niveau, "message": message, "detail": detail})
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

    def titre(self, m):          self._log("titre", m)
    def info(self, m, d=None):   self._log("info", m, d)
    def action(self, m, d=None): self._log("action", m, d)
    def alerte(self, m, d=None): self._log("alerte", m, d)

    def rapport(self, chemin):
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"mode": "apply" if self.apply else "simulation",
                       "date": nowdate(), "lignes": self.lignes,
                       "anomalies": self.anomalies}, f, ensure_ascii=False, indent=2)
        print(f"\nRapport écrit dans {chemin}")


def societes(filtre=None):
    if filtre:
        return [filtre] if frappe.db.exists("Company", filtre) else []
    return frappe.get_all("Company", pluck="name", order_by="name")


def _creer_role(nom, jrn, apply_mode, desk=True):
    if frappe.db.exists("Role", nom):
        jrn.info(f"Rôle « {nom} » : déjà présent.")
        return
    jrn.action(f"Créer le rôle « {nom} »")
    if apply_mode:
        frappe.get_doc({"doctype": "Role", "role_name": nom,
                        "desk_access": 1 if desk else 0}).insert(ignore_permissions=True)


# =============================================================================
# ÉTAPE — diagnostic
# =============================================================================

def etape_diagnostic(jrn, _apply_mode, societe=None):
    jrn.titre("DIAGNOSTIC — état des verrous, par société")

    for soc in societes(societe):
        gel = frappe.db.get_value("Company", soc, "accounts_frozen_till_date")
        role = frappe.db.get_value("Company", soc, "role_allowed_for_frozen_entries")
        per = frappe.db.count("Accounting Period", {"company": soc, "disabled": 0})
        pcv = frappe.db.count("Period Closing Voucher", {"company": soc, "docstatus": 1})
        jrn.info(f"{soc:42} gel={gel or 'AUCUN':12} role={role or '-':24} "
                 f"periodes={per:3}  clotures={pcv}")
        if not gel:
            jrn.alerte(f"{soc} : aucune date de gel. Une écriture peut être "
                       f"comptabilisée à n'importe quelle date passée.")

    fy = frappe.get_all("Fiscal Year", fields=["name", "disabled"], order_by="name")
    jrn.info(f"Exercices déclarés : {', '.join(f.name for f in fy)}")
    for f in fy:
        rattaches = frappe.get_all("Fiscal Year Company",
                                   filters={"parent": f.name}, pluck="company")
        if not rattaches:
            jrn.alerte(f"Exercice {f.name} : rattaché à aucune société, il vaut donc "
                       f"pour les {len(societes())} sociétés de la plateforme.")

    for role in (ROLE_DEROGATION,):
        if frappe.db.exists("Role", role):
            porteurs = frappe.get_all("Has Role", filters={"role": role,
                                                           "parenttype": "User"},
                                      pluck="parent")
            if porteurs:
                jrn.alerte(f"Le rôle « {role} » est porté en permanence par : "
                           f"{', '.join(porteurs)}. Il ne devrait l'être que le temps "
                           f"d'une dérogation.")


# =============================================================================
# ÉTAPE — rôles
# =============================================================================

def etape_roles(jrn, apply_mode, _societe=None):
    jrn.titre("ÉTAPE — Rôles de verrouillage")
    _creer_role(ROLE_COMPTABLE_SITIAME, jrn, apply_mode)
    _creer_role(ROLE_DEROGATION, jrn, apply_mode)
    jrn.info("Règle : personne ne porte « " + ROLE_DEROGATION + " » en permanence. "
             "Il est accordé pour la durée d'une dérogation, puis retiré automatiquement.")


# =============================================================================
# ÉTAPE — date de gel par société
# =============================================================================

def etape_gel(jrn, apply_mode, societe=None, date_gel=None):
    """Pose la date de gel au dernier jour du mois clos, par société.

    Pour une société créée récemment, on remonte la date de gel à la veille
    de son premier exercice sur la plateforme : un client arrivé en 2026 ne
    peut alors pas écrire en 2024, même par faute de frappe.
    """
    jrn.titre("ÉTAPE — Date de gel des comptes")

    defaut = date_gel or get_last_day(add_months(getdate(nowdate()), -1))

    for soc in societes(societe):
        creation = frappe.db.get_value("Company", soc, "creation")
        veille_creation = add_days(getdate(creation), -1) if creation else None
        cible = defaut
        if veille_creation and veille_creation > getdate(defaut):
            cible = veille_creation
            jrn.info(f"{soc} : société créée le {getdate(creation)}, "
                     f"gel remonté à sa veille.")

        actuel = frappe.db.get_value("Company", soc, "accounts_frozen_till_date")
        if actuel and getdate(actuel) >= getdate(cible):
            jrn.info(f"{soc} : gel déjà au {actuel}, pas de recul.")
        else:
            jrn.action(f"{soc} : date de gel {actuel or 'aucune'} -> {cible}")
            if apply_mode:
                frappe.db.set_value("Company", soc, "accounts_frozen_till_date", cible)

        role_actuel = frappe.db.get_value("Company", soc, "role_allowed_for_frozen_entries")
        if role_actuel != ROLE_COMPTABLE_SITIAME:
            jrn.action(f"{soc} : rôle dérogatoire {role_actuel or 'aucun'} "
                       f"-> {ROLE_COMPTABLE_SITIAME}")
            if apply_mode:
                frappe.db.set_value("Company", soc,
                                    "role_allowed_for_frozen_entries",
                                    ROLE_COMPTABLE_SITIAME)
        else:
            jrn.info(f"{soc} : rôle dérogatoire déjà correct.")


# =============================================================================
# ÉTAPE — périodes comptables mensuelles
# =============================================================================

def etape_periodes(jrn, apply_mode, societe=None, jusqu_au=None):
    """Crée une période comptable par mois écoulé.

    Une période comptable BLOQUE les documents de sa plage de dates. On ne
    crée donc jamais celle du mois en cours : ce serait bloquer le travail
    du jour.
    """
    jrn.titre("ÉTAPE — Périodes comptables mensuelles")

    limite = getdate(jusqu_au) if jusqu_au else get_last_day(
        add_months(getdate(nowdate()), -1))
    mois_courant = get_first_day(getdate(nowdate()))
    if limite >= mois_courant:
        frappe.throw(
            f"La limite {limite} tombe dans le mois en cours. Une période comptable "
            f"bloque sa plage de dates : fermer le mois courant arrêterait la saisie. "
            f"Choisissez une date antérieure au {mois_courant}."
        )

    if not frappe.db.exists("Role", ROLE_DEROGATION):
        frappe.throw(f"Le rôle « {ROLE_DEROGATION} » n'existe pas. "
                     f"Exécutez d'abord l'étape « roles ».")

    for soc in societes(societe):
        debut = frappe.db.get_value("Company", soc, "creation")
        curseur = get_first_day(getdate(debut)) if debut else get_first_day(limite)
        crees = 0
        while curseur <= limite:
            fin = get_last_day(curseur)
            nom = f"{curseur.strftime('%Y-%m')} - {soc}"
            existe = frappe.db.exists("Accounting Period", {
                "company": soc, "start_date": curseur, "end_date": fin})
            if existe:
                curseur = add_months(curseur, 1)
                continue

            jrn.action(f"{soc} : fermer la période {curseur} -> {fin}")
            if apply_mode:
                frappe.get_doc({
                    "doctype": "Accounting Period",
                    "period_name": nom[:140],
                    "company": soc,
                    "start_date": curseur,
                    "end_date": fin,
                    "exempted_role": ROLE_DEROGATION,
                    "closed_documents": [
                        {"document_type": dt, "closed": 1}
                        for dt in DOCUMENTS_FERMES
                        if frappe.db.exists("DocType", dt)
                    ],
                }).insert(ignore_permissions=True)  # provisionnement : exception assumée
            crees += 1
            curseur = add_months(curseur, 1)
        jrn.info(f"{soc} : {crees} période(s) à fermer jusqu'au {limite}.")


# =============================================================================
# ÉTAPE — les deux dates, enfin distinguées
# =============================================================================

def etape_dates(jrn, apply_mode, _societe=None):
    """Verrouille la date de comptabilisation et met en avant la date fournisseur.

    C'est la correction au meilleur rapport entre effort et effet : la
    confusion entre « date de la facture du fournisseur » et « date de
    comptabilisation » est à l'origine de l'incident du 15 octobre.
    """
    jrn.titre("ÉTAPE — Distinguer date fournisseur et date de comptabilisation")

    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    from frappe.permissions import add_permission, update_permission_property

    # 1. La case d'échappement passe en permlevel 1 : invisible aux clients.
    for dt in DOCUMENTS_DATE_VERROUILLEE:
        if not frappe.db.exists("DocType", dt):
            continue
        meta = frappe.get_meta(dt)
        if not meta.get_field("set_posting_time"):
            continue
        jrn.action(f"{dt} : set_posting_time -> permlevel 1")
        if apply_mode:
            make_property_setter(dt, "set_posting_time", "permlevel", 1, "Int",
                                 validate_fields_for_doctype=False)
        for role in (ROLE_COMPTABLE_SITIAME, "Accounts Manager"):
            if not frappe.db.exists("Role", role):
                continue
            jrn.action(f"{dt} : accorder le niveau 1 à « {role} »")
            if apply_mode:
                try:
                    add_permission(dt, role, 1)
                    update_permission_property(dt, role, 1, "write", 1)
                    update_permission_property(dt, role, 1, "read", 1)
                except Exception as e:
                    jrn.alerte(f"    {dt}/{role} niveau 1 : {e}")

    # 2. La date du fournisseur devient obligatoire et explicite.
    for dt, champ, label, desc in [
        ("Purchase Invoice", "bill_date", "Date de la facture du fournisseur",
         "Date portée sur le document reçu. N'affecte PAS l'exercice de comptabilisation."),
        ("Purchase Invoice", "posting_date", "Date de comptabilisation",
         "Détermine l'exercice. Doit se situer dans la période ouverte."),
        ("Sales Invoice", "posting_date", "Date de comptabilisation",
         "Détermine l'exercice. Doit se situer dans la période ouverte."),
    ]:
        if not frappe.db.exists("DocType", dt):
            continue
        jrn.action(f"{dt}.{champ} : libellé et description explicites")
        if apply_mode:
            make_property_setter(dt, champ, "label", label, "Data",
                                 validate_fields_for_doctype=False)
            make_property_setter(dt, champ, "description", desc, "Text",
                                 validate_fields_for_doctype=False)

    if frappe.db.exists("DocType", "Purchase Invoice"):
        jrn.action("Purchase Invoice.bill_date : rendre obligatoire")
        if apply_mode:
            make_property_setter("Purchase Invoice", "bill_date", "reqd", 1, "Check",
                                 validate_fields_for_doctype=False)

    jrn.alerte("À éprouver en recette : un compte client doit pouvoir enregistrer une "
               "facture d'achat sans voir la case « Modifier la date de comptabilisation », "
               "et la date doit valoir le jour même.")


# =============================================================================
# ÉTAPE — permissions sur les objets de période
# =============================================================================

def etape_permissions(jrn, apply_mode, _societe=None):
    """Un client ne doit pas pouvoir créer, clore ni rouvrir une période."""
    jrn.titre("ÉTAPE — Permissions sur les objets de période")

    from frappe.permissions import update_permission_property

    cibles = ["Accounting Period", "Fiscal Year", "Period Closing Voucher"]
    roles_a_restreindre = ROLES_CLIENTS + ["Accounts Manager", "Accounts User"]

    for dt in cibles:
        if not frappe.db.exists("DocType", dt):
            continue
        for role in roles_a_restreindre:
            if not frappe.db.exists("Role", role):
                continue
            jrn.action(f"{dt} / {role} : retirer création, écriture, validation, "
                       f"annulation et suppression")
            if apply_mode:
                for ptype in ("create", "write", "submit", "cancel", "delete"):
                    try:
                        update_permission_property(dt, role, 0, ptype, 0)
                    except Exception as e:
                        jrn.alerte(f"    {dt}/{role}/{ptype} : {e}")

    jrn.info("La lecture reste ouverte : un client doit pouvoir constater qu'une "
             "période est fermée, c'est ce qui rend le refus compréhensible.")
    jrn.alerte("Tant qu'un compte client porte le rôle Accounts Manager sans restriction "
               "de société, ces réglages restent contournables. Voir le chantier de "
               "cloisonnement du 15 octobre.")


# =============================================================================
# ÉTAPE — doctype « Ouverture Exceptionnelle de Periode »
# =============================================================================

CHAMPS_DEROGATION = [
    {"fieldname": "societe", "label": "Société", "fieldtype": "Link",
     "options": "Company", "reqd": 1, "in_list_view": 1},
    {"fieldname": "periode", "label": "Période à ouvrir", "fieldtype": "Link",
     "options": "Accounting Period", "reqd": 1, "in_list_view": 1},
    {"fieldname": "col1", "fieldtype": "Column Break"},
    {"fieldname": "demandeur", "label": "Demandeur", "fieldtype": "Link",
     "options": "User", "reqd": 1, "in_list_view": 1},
    {"fieldname": "approbateur", "label": "Approbateur (comptable SITIAME)",
     "fieldtype": "Link", "options": "User", "reqd": 1},
    {"fieldname": "sec1", "fieldtype": "Section Break"},
    {"fieldname": "motif", "label": "Motif", "fieldtype": "Small Text", "reqd": 1,
     "description": "Cette pièce sera produite en cas de contrôle. Soyez précis."},
    {"fieldname": "sec2", "fieldtype": "Section Break"},
    {"fieldname": "ouvert_le", "label": "Ouvert le", "fieldtype": "Datetime",
     "read_only": 1},
    {"fieldname": "col2", "fieldtype": "Column Break"},
    {"fieldname": "expire_le", "label": "Se referme automatiquement le",
     "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
    {"fieldname": "sec3", "fieldtype": "Section Break"},
    {"fieldname": "statut", "label": "Statut", "fieldtype": "Select",
     "options": "Demandée\nOuverte\nRefermée", "default": "Demandée",
     "read_only": 1, "in_list_view": 1},
    {"fieldname": "amended_from", "label": "Amended From", "fieldtype": "Link",
     "options": "Ouverture Exceptionnelle de Periode", "read_only": 1, "no_copy": 1,
     "print_hide": 1},
]


def etape_doctype_derogation(jrn, apply_mode, _societe=None):
    """Crée le doctype de demande d'ouverture exceptionnelle.

    Il est créé en doctype personnalisé : il n'écrase rien d'ERPNext et se
    désinstalle proprement. Son comportement est porté par les fonctions de
    ce module, branchées par hooks.py — pas par un contrôleur dans le cœur.
    """
    jrn.titre("ÉTAPE — Doctype « Ouverture Exceptionnelle de Periode »")

    nom = "Ouverture Exceptionnelle de Periode"
    if frappe.db.exists("DocType", nom):
        jrn.info("Doctype déjà présent.")
    else:
        jrn.action(f"Créer le doctype « {nom} » (personnalisé, soumissible)")
        if apply_mode:
            frappe.get_doc({
                "doctype": "DocType",
                "name": nom,
                "module": "Custom",
                "custom": 1,
                "is_submittable": 1,
                "autoname": "format:OEP-{YYYY}-{#####}",
                "track_changes": 1,
                "fields": CHAMPS_DEROGATION,
                "permissions": [
                    {"role": ROLE_COMPTABLE_SITIAME, "read": 1, "write": 1,
                     "create": 1, "submit": 1, "cancel": 1, "report": 1},
                    {"role": "System Manager", "read": 1, "write": 1, "create": 1,
                     "submit": 1, "cancel": 1, "delete": 1, "report": 1},
                ],
            }).insert(ignore_permissions=True)  # provisionnement : exception assumée

    jrn.info("À ajouter dans hooks.py (voir l'en-tête de ce fichier) :")
    jrn.info('  doc_events["Ouverture Exceptionnelle de Periode"]["on_submit"] = '
             '"sitiame_core.scripts.mise_en_oeuvre_exercices.ouvrir_derogation"')
    jrn.info('  scheduler_events["hourly"] += '
             '["sitiame_core.scripts.mise_en_oeuvre_exercices.fermer_derogations_echues"]')


# =============================================================================
# COMPORTEMENT DE LA DÉROGATION — branché par hooks.py
# =============================================================================

def ouvrir_derogation(doc, method=None):
    """Ouvre la période et accorde le rôle de dérogation, pour une durée bornée."""
    if doc.approbateur == doc.demandeur:
        frappe.throw("L'approbateur ne peut pas être le demandeur.")
    if not doc.motif or len(doc.motif.strip()) < 20:
        frappe.throw("Le motif doit être explicite : il sera produit en cas de contrôle.")

    periode = frappe.get_doc("Accounting Period", doc.periode)
    if periode.company != doc.societe:
        frappe.throw("La période ne concerne pas la société indiquée.")

    expire = now_datetime() + timedelta(hours=DUREE_DEROGATION_HEURES)
    doc.db_set("ouvert_le", now_datetime())
    doc.db_set("expire_le", expire)
    doc.db_set("statut", "Ouverte")

    if not frappe.db.exists("Has Role", {"parent": doc.demandeur, "parenttype": "User",
                                         "role": ROLE_DEROGATION}):
        frappe.get_doc({"doctype": "Has Role", "parent": doc.demandeur,
                        "parenttype": "User", "parentfield": "roles",
                        "role": ROLE_DEROGATION}).insert(ignore_permissions=True)

    frappe.msgprint(
        f"Période ouverte jusqu'au {expire.strftime('%d/%m/%Y %H:%M')}. "
        f"Elle se refermera seule : aucune action n'est à prévoir.",
        title="Dérogation accordée", indicator="orange")


def fermer_derogation(doc, method=None):
    """Retire le rôle de dérogation. Appelée à l'annulation et à l'échéance."""
    lien = frappe.db.exists("Has Role", {"parent": doc.demandeur, "parenttype": "User",
                                         "role": ROLE_DEROGATION})
    if lien:
        frappe.delete_doc("Has Role", lien, ignore_permissions=True, force=True)
    if doc.statut != "Refermée":
        doc.db_set("statut", "Refermée")


def fermer_derogations_echues():
    """Tâche horaire : referme toute dérogation dont la fenêtre est passée.

    Une dérogation qu'il faut penser à retirer est une dérogation permanente.
    """
    if not frappe.db.exists("DocType", "Ouverture Exceptionnelle de Periode"):
        return
    echues = frappe.get_all(
        "Ouverture Exceptionnelle de Periode",
        filters={"statut": "Ouverte", "expire_le": ["<", now_datetime()], "docstatus": 1},
        pluck="name")
    for nom in echues:
        doc = frappe.get_doc("Ouverture Exceptionnelle de Periode", nom)
        fermer_derogation(doc)
        frappe.logger("sitiame").info(f"Dérogation {nom} refermée automatiquement.")
    if echues:
        frappe.db.commit()


# =============================================================================
# PROVISIONNEMENT ET CLÔTURE — branchés par hooks.py
# =============================================================================

def provisionner_societe(doc, method=None):
    """À la création d'une société : poser le gel à la veille de son premier jour.

    Un client arrivé en 2026 ne doit pas pouvoir écrire en 2024.
    """
    veille = add_days(getdate(doc.creation or nowdate()), -1)
    frappe.db.set_value("Company", doc.name, "accounts_frozen_till_date", veille)
    if frappe.db.exists("Role", ROLE_COMPTABLE_SITIAME):
        frappe.db.set_value("Company", doc.name, "role_allowed_for_frozen_entries",
                            ROLE_COMPTABLE_SITIAME)
    frappe.logger("sitiame").info(
        f"Société {doc.name} provisionnée : gel au {veille}.")


def cloture_mensuelle(societe, annee=None, mois=None):
    """Ferme un mois pour une société. Appelable à la main ou par le planificateur."""
    if annee and mois:
        debut = getdate(f"{annee}-{int(mois):02d}-01")
    else:
        debut = get_first_day(add_months(getdate(nowdate()), -1))
    fin = get_last_day(debut)

    if fin >= get_first_day(getdate(nowdate())):
        frappe.throw("Refus : on ne ferme pas le mois en cours.")

    if frappe.db.exists("Accounting Period", {"company": societe,
                                              "start_date": debut, "end_date": fin}):
        return None

    doc = frappe.get_doc({
        "doctype": "Accounting Period",
        "period_name": f"{debut.strftime('%Y-%m')} - {societe}"[:140],
        "company": societe,
        "start_date": debut,
        "end_date": fin,
        "exempted_role": ROLE_DEROGATION,
        "closed_documents": [{"document_type": dt, "closed": 1}
                             for dt in DOCUMENTS_FERMES
                             if frappe.db.exists("DocType", dt)],
    })
    doc.insert(ignore_permissions=True)  # provisionnement : exception assumée
    return doc.name


def cloture_mensuelle_auto():
    """Tâche planifiée : ferme le mois écoulé pour toutes les sociétés."""
    for soc in frappe.get_all("Company", pluck="name"):
        try:
            nom = cloture_mensuelle(soc)
            if nom:
                frappe.logger("sitiame").info(f"Période {nom} créée.")
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Clôture mensuelle {soc}")
    frappe.db.commit()


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

ETAPE_FN = {
    "diagnostic": etape_diagnostic,
    "roles": etape_roles,
    "gel": etape_gel,
    "periodes": etape_periodes,
    "dates": etape_dates,
    "permissions": etape_permissions,
    "doctype_derogation": etape_doctype_derogation,
}


def main(apply=False, societe=None, etapes=None, jusqu_au=None,
         date_gel=None, rapport=None):
    """Point d'entrée.

    apply     : False = simulation (par défaut). True = écriture réelle.
    societe   : limite à une société. None = toutes.
    etapes    : liste d'étapes. None = diagnostic seul.
    jusqu_au  : pour l'étape « periodes », dernier mois à fermer (AAAA-MM-JJ).
    date_gel  : pour l'étape « gel », date imposée. Sinon fin du mois dernier.
    """
    apply_mode = bool(apply)
    etapes = etapes or ["diagnostic"]
    inconnues = [e for e in etapes if e not in ETAPE_FN]
    if inconnues:
        frappe.throw(f"Étape(s) inconnue(s) : {inconnues}. Valeurs admises : {ETAPES}")

    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw("Ce script doit être exécuté par Administrator ou un System Manager.")

    jrn = Journal(apply_mode)
    jrn.titre("PME360 — MISE EN ŒUVRE DE LA GESTION DES EXERCICES")
    jrn.info("Mode : " + ("APPLICATION RÉELLE" if apply_mode else "SIMULATION — rien n'est écrit"))
    jrn.info("Société : " + (societe or "toutes"))
    jrn.info("Étapes : " + ", ".join(etapes))

    for e in etapes:
        if e == "periodes":
            etape_periodes(jrn, apply_mode, societe, jusqu_au)
        elif e == "gel":
            etape_gel(jrn, apply_mode, societe, date_gel)
        else:
            ETAPE_FN[e](jrn, apply_mode, societe)

    if apply_mode:
        frappe.db.commit()
        frappe.clear_cache()
        jrn.info("Modifications validées en base. Cache vidé — demandez aux "
                 "utilisateurs connectés de recharger leur page.")
    else:
        frappe.db.rollback()
        jrn.info("Simulation terminée — aucune modification conservée.")

    chemin = rapport or os.path.join(
        frappe.get_site_path(), f"mise_en_oeuvre_exercices_{nowdate()}.json")
    jrn.rapport(chemin)

    if jrn.anomalies:
        print(f"\n{len(jrn.anomalies)} point(s) d'attention — relisez le rapport avant d'appliquer.")
    return {"anomalies": len(jrn.anomalies), "rapport": chemin}
