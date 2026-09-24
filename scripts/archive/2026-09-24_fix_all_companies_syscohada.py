#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de migration et de régularisation intégrale du plan comptable SYSCOHADA dans ERPNext.
Auteur : Sitiame Capital / PME360
Cible : VPS ERPNext (erp.sitiame-capital.com)

Ce script réalise automatiquement les opérations suivantes sur toutes les sociétés :
1. Détection des sociétés avec un plan comptable erroné (Plan 'Standard' 95 comptes ou sans code).
2. Pour les sociétés sans écritures comptables réelles (0 GL Entry) : réinitialisation complète
   avec 'Syscohada - Plan Comptable avec code' (~1 370 comptes numérotés).
3. Éradication du compte parasite 'Metric' et suppression des modèles de taxes 'Ivory Coast' obsolètes.
4. Création des modèles officiels de TVA :
   - Ventes : 'TVA 18% Vente' sur le compte 4431 (TVA facturée).
   - Achats : 'TVA 18% Achat' sur le compte 4452 (TVA récupérable sur achats).
5. Configuration automatique des 6 comptes par défaut obligatoires sur la fiche Company :
   - Client : 4111 (Clients) [Receivable]
   - Fournisseur : 4011 (Fournisseurs) [Payable]
   - Banque : 5211 (Banques locales) [Bank]
   - Caisse : 5711 (Caisse siège) [Cash]
   - Produits : 7061 ou 7011 (Prestations / Ventes)
   - Charges : 6011 (Achats de marchandises)
   - Arrondi : compte 658 ou 758 (Charges/Produits divers ordinaires)
6. Correction du typage strict des comptes comptables (Cash pour 5711, Tax pour 4431/4432/4452/4454).
7. Association du compte de stock 3111 au Magasin principal de chaque société.
"""

import sys
import frappe
from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts


def log(msg):
    print(f"[SYSCOHADA-FIX] {msg}")


def find_account_by_prefix(company_name, prefix):
    """Recherche un compte feuille (non groupe) de la société commençant par un numéro donné."""
    # 1. Par numéro exact de compte
    accs = frappe.get_all(
        "Account",
        filters={"company": company_name, "is_group": 0},
        fields=["name", "account_number", "account_name"],
        order_by="name asc"
    )
    for a in accs:
        num = str(a.account_number or "").strip()
        if num.startswith(prefix):
            return a.name

    # 2. Par nom ou libellé de compte commençant par le numéro
    for a in accs:
        clean_name = a.name.split(" - ")[0].strip()
        if clean_name.startswith(prefix) or a.account_name.strip().startswith(prefix):
            return a.name

    return None


def reset_company_chart_to_syscohada(company_name):
    """
    Réinitialise proprement l'arborescence des comptes d'une société vers le plan
    'Syscohada - Plan Comptable avec code', uniquement si 0 GL Entry existe.
    """
    gl_count = frappe.db.count("GL Entry", {"company": company_name})
    if gl_count > 0:
        log(f"ATTENTION: {company_name} contient {gl_count} écriture(s) GL. Impossible d'effacer les comptes. Passage aux correctifs taxes/défauts.")
        return False

    log(f"--- Réinitialisation intégrale du plan comptable pour : {company_name} ---")

    # 1. Détacher tous les comptes par défaut sur la fiche Company dynamiquement
    frappe.db.commit()
    company_doc = frappe.get_doc("Company", company_name)
    for field in company_doc.meta.fields:
        if field.fieldtype == "Link" and field.options == "Account":
            setattr(company_doc, field.fieldname, None)
    company_doc.chart_of_accounts = "Syscohada - Plan Comptable avec code"
    company_doc.db_update()
    frappe.db.commit()

    # 2. Détacher les comptes sur les Entrepôts et Modes de Paiement
    frappe.db.sql("UPDATE `tabWarehouse` SET account=NULL WHERE company=%s", company_name)
    frappe.db.sql("DELETE FROM `tabMode of Payment Account` WHERE company=%s", company_name)

    # 3. Supprimer les modèles de taxes obsolètes
    frappe.db.sql("""
        DELETE FROM `tabSales Taxes and Charges`
        WHERE parent IN (SELECT name FROM `tabSales Taxes and Charges Template` WHERE company=%s)
    """, company_name)
    frappe.db.sql("DELETE FROM `tabSales Taxes and Charges Template` WHERE company=%s", company_name)

    frappe.db.sql("""
        DELETE FROM `tabPurchase Taxes and Charges`
        WHERE parent IN (SELECT name FROM `tabPurchase Taxes and Charges Template` WHERE company=%s)
    """, company_name)
    frappe.db.sql("DELETE FROM `tabPurchase Taxes and Charges Template` WHERE company=%s", company_name)
    frappe.db.commit()

    # 4. Supprimer tous les anciens comptes si présents
    acc_count = frappe.db.count("Account", {"company": company_name})
    if acc_count > 0:
        frappe.db.sql("UPDATE `tabAccount` SET parent_account=NULL WHERE company=%s", company_name)
        frappe.db.sql("DELETE FROM `tabAccount` WHERE company=%s", company_name)
        frappe.db.commit()

    # 5. Régénérer l'arborescence complète SYSCOHADA avec code
    log(f"Génération des 1 370 comptes 'Syscohada - Plan Comptable avec code' pour {company_name}...")
    create_charts(company_name, chart_template="Syscohada - Plan Comptable avec code")
    frappe.db.commit()

    log(f"Plan SYSCOHADA révisé généré avec succès pour {company_name}.")
    return True


def clean_metric_and_setup_taxes(company_name):
    """
    Supprime le compte parasite 'Metric' et crée les modèles de taxes corrects (4431 / 4452).
    """
    abbr = frappe.db.get_value("Company", company_name, "abbr")

    # 1. Supprimer le compte 'Metric' s'il existe et n'a pas d'écriture
    metric_accounts = frappe.get_all(
        "Account",
        filters={"company": company_name, "account_name": ["like", "%Metric%"]},
        fields=["name"]
    )
    for m in metric_accounts:
        gl = frappe.db.count("GL Entry", {"account": m.name})
        if gl == 0:
            frappe.db.sql("DELETE FROM `tabSales Taxes and Charges` WHERE account_head=%s", m.name)
            frappe.db.sql("DELETE FROM `tabPurchase Taxes and Charges` WHERE account_head=%s", m.name)
            frappe.delete_doc("Account", m.name, force=1, ignore_permissions=True)
            log(f"Compte parasite supprimé : {m.name}")
        else:
            log(f"AVERTISSEMENT: {m.name} contient des écritures GL, conservation.")

    # 2. Supprimer les modèles 'Ivory Coast - ...' pointant sur Metric
    old_templates = frappe.get_all(
        "Sales Taxes and Charges Template",
        filters={"company": company_name},
        fields=["name"]
    )
    for t in old_templates:
        if "Ivory Coast" in t.name or "Metric" in t.name:
            frappe.delete_doc("Sales Taxes and Charges Template", t.name, force=1, ignore_permissions=True)
            log(f"Ancien modèle de taxe supprimé : {t.name}")

    old_p_templates = frappe.get_all(
        "Purchase Taxes and Charges Template",
        filters={"company": company_name},
        fields=["name"]
    )
    for t in old_p_templates:
        if "Ivory Coast" in t.name or "Metric" in t.name:
            frappe.delete_doc("Purchase Taxes and Charges Template", t.name, force=1, ignore_permissions=True)
            log(f"Ancien modèle de taxe achat supprimé : {t.name}")

    # 3. Trouver les comptes légaux SYSCOHADA
    tax_vente_4431 = find_account_by_prefix(company_name, "4431") or find_account_by_prefix(company_name, "443")
    tax_achat_4452 = find_account_by_prefix(company_name, "4452") or find_account_by_prefix(company_name, "445")

    # 4. Créer le modèle de taxe de vente : TVA 18% (4431)
    existing_sales = frappe.get_all("Sales Taxes and Charges Template", filters={"company": company_name})
    has_sales_vat = any("TVA 18%" in s.name for s in existing_sales)
    if tax_vente_4431 and not has_sales_vat:
        try:
            doc = frappe.get_doc({
                "doctype": "Sales Taxes and Charges Template",
                "title": "TVA 18%",
                "company": company_name,
                "is_default": 1,
                "taxes": [
                    {
                        "charge_type": "On Net Total",
                        "account_head": tax_vente_4431,
                        "description": "TVA 18%",
                        "rate": 18.0
                    }
                ]
            })
            doc.insert(ignore_permissions=True)
            log(f"Modèle de TVA Vente créé pour {company_name} -> {tax_vente_4431}")
        except frappe.DuplicateEntryError:
            pass

    # 5. Créer le modèle de taxe d'achat : TVA 18% Déductible (4452)
    existing_purch = frappe.get_all("Purchase Taxes and Charges Template", filters={"company": company_name})
    has_purch_vat = any("TVA 18%" in p.name for p in existing_purch)
    if tax_achat_4452 and not has_purch_vat:
        try:
            doc = frappe.get_doc({
                "doctype": "Purchase Taxes and Charges Template",
                "title": "TVA 18% Achat",
                "company": company_name,
                "is_default": 1,
                "taxes": [
                    {
                        "charge_type": "On Net Total",
                        "account_head": tax_achat_4452,
                        "description": "TVA 18% Déductible",
                        "rate": 18.0
                    }
                ]
            })
            doc.insert(ignore_permissions=True)
            log(f"Modèle de TVA Achat créé pour {company_name} -> {tax_achat_4452}")
        except frappe.DuplicateEntryError:
            pass


def configure_company_defaults_and_types(company_name):
    """
    Assigne les 6 comptes par défaut indispensables et corrige les account_type.
    """
    acc_4111 = find_account_by_prefix(company_name, "4111") or find_account_by_prefix(company_name, "411")
    acc_4011 = find_account_by_prefix(company_name, "4011") or find_account_by_prefix(company_name, "401")
    acc_5211 = find_account_by_prefix(company_name, "5211") or find_account_by_prefix(company_name, "521")
    acc_5711 = find_account_by_prefix(company_name, "5711") or find_account_by_prefix(company_name, "571")
    acc_7061 = find_account_by_prefix(company_name, "7061") or find_account_by_prefix(company_name, "7011") or find_account_by_prefix(company_name, "70")
    acc_6011 = find_account_by_prefix(company_name, "6011") or find_account_by_prefix(company_name, "601") or find_account_by_prefix(company_name, "60")
    acc_6031 = find_account_by_prefix(company_name, "6031") or find_account_by_prefix(company_name, "603")
    acc_3111 = find_account_by_prefix(company_name, "3111") or find_account_by_prefix(company_name, "311")
    acc_arrondi = find_account_by_prefix(company_name, "658") or find_account_by_prefix(company_name, "758") or acc_6011

    # Typage des comptes
    if acc_4111:
        frappe.db.set_value("Account", acc_4111, "account_type", "Receivable")
    if acc_4011:
        frappe.db.set_value("Account", acc_4011, "account_type", "Payable")
    if acc_5211:
        frappe.db.set_value("Account", acc_5211, "account_type", "Bank")
    if acc_5711:
        frappe.db.set_value("Account", acc_5711, "account_type", "Cash")

    # Typage TVA
    for pfx in ["4431", "4432", "4452", "4454"]:
        a = find_account_by_prefix(company_name, pfx)
        if a:
            frappe.db.set_value("Account", a, "account_type", "Tax")

    # Mise à jour Company directe en base de données (évite le bug on_update d'ERPNext v16)
    frappe.db.set_value("Company", company_name, {
        "default_receivable_account": acc_4111,
        "default_payable_account": acc_4011,
        "default_bank_account": acc_5211,
        "default_cash_account": acc_5711,
        "default_income_account": acc_7061,
        "default_expense_account": acc_6011,
        "round_off_account": acc_arrondi,
        "stock_adjustment_account": acc_6031,
        "default_inventory_account": acc_3111,
        "chart_of_accounts": "Syscohada - Plan Comptable avec code"
    })

    # Entrepôt principal
    warehouses = frappe.get_all("Warehouse", filters={"company": company_name}, fields=["name"])
    for wh in warehouses:
        if acc_3111:
            frappe.db.set_value("Warehouse", wh.name, "account", acc_3111)

    log(f"Comptes par défaut configurés avec succès pour : {company_name}")


def process_all_companies():
    """Point d'entrée principal pour traiter l'intégralité des sociétés existantes."""
    companies = frappe.get_all("Company", fields=["name", "abbr", "chart_of_accounts"])
    log(f"Début du traitement de {len(companies)} société(s) trouvée(s)...")

    for comp in companies:
        name = comp.name
        log(f"\n==================================================")
        log(f"Vérification de la société : {name} ({comp.abbr})")

        # Vérifier le nombre de comptes et la présence de numéros
        total_accounts = frappe.db.count("Account", {"company": name})
        numbered_accounts = frappe.db.sql(
            "SELECT count(*) FROM `tabAccount` WHERE company=%s AND account_number IS NOT NULL AND account_number != ''",
            name
        )[0][0]

        log(f"État actuel : {total_accounts} compte(s), dont {numbered_accounts} numéroté(s).")

        # Si la société a moins de 500 comptes ou très peu de comptes numérotés,
        # c'est qu'elle a le plan Standard ou sans code.
        needs_full_reset = (total_accounts < 500 or numbered_accounts < 500)

        if needs_full_reset:
            log(f"Société sur plan incomplet ou non SYSCOHADA détectée !")
            reset_success = reset_company_chart_to_syscohada(name)
            if not reset_success:
                log(f"Échec ou report de réinitialisation sur {name}.")
        else:
            log(f"Plan comptable volumineux déjà présent ({total_accounts} comptes).")

        # Nettoyage TVA / Metric et rattachement des comptes par défaut
        clean_metric_and_setup_taxes(name)
        configure_company_defaults_and_types(name)
        frappe.db.commit()

    log("\n==================================================")
    log("TRAITEMENT TERMINÉ POUR TOUTES LES SOCIÉTÉS AVEC SUCCÈS !")


def run():
    """Fonction appelée par `bench execute`."""
    process_all_companies()


if __name__ == "__main__":
    process_all_companies()
