# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""SYSCOHADA revise financial statements (audit F-16): Bilan actif, Bilan
passif and Compte de resultat, computed from the ERPNext general ledger
by account number.

Line structure and account groupings follow PME360's BceaoLiasseService
(app/Services/BceaoLiasseService.php) so both platforms show the same
postes, with three corrections to that mapping:
- RI/RJ: 79x are reprises de provisions (RI), 78x transferts de charges
  (RJ); PME360 had them swapped.
- WA/WB: participation des travailleurs is 87, impot sur le resultat 89;
  PME360 used 891/892/895 and counted 87 as an HAO charge.
- Class 4/5 accounts are split by the side of their own balance (a
  supplier with a debit balance is an "autre creance"), so the balance
  sheet balances instead of silently dropping such balances.

Balances: classes 1-5 are cumulative up to the closing date; classes 6-8
cover the fiscal year only. Profit or loss of earlier years that was
never closed into class 12/13 is carried into "Report a nouveau" (CF).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

# ---------------------------------------------------------------------------
# Balance sheet mapping: (prefixes, side, line, component)
#   side: "D" = only accounts with a debit balance, "C" = credit balance,
#         "any" = signed balance whatever its side
#   component (actif): "brut" or "amort"; (passif): "net"
# The longest matching prefix wins, so specific accounts override classes.
# ---------------------------------------------------------------------------
ACTIF_RULES = [
	(["20"], "any", "AA", "brut"), (["280", "290"], "any", "AA", "amort"),
	(["21"], "any", "AB", "brut"), (["281", "291"], "any", "AB", "amort"),
	(["22"], "any", "AC", "brut"), (["282", "292"], "any", "AC", "amort"),
	(["23"], "any", "AD", "brut"), (["283", "293"], "any", "AD", "amort"),
	(["24"], "any", "AE", "brut"), (["284", "294"], "any", "AE", "amort"),
	(["245"], "any", "AF", "brut"), (["2845"], "any", "AF", "amort"),
	(["25"], "any", "AH", "brut"), (["295"], "any", "AH", "amort"),
	(["26", "27"], "any", "AG", "brut"), (["296", "297"], "any", "AG", "amort"),
	(["3"], "any", "BA", "brut"), (["39"], "any", "BA", "amort"),
	(["41"], "D", "BB", "brut"), (["491"], "any", "BB", "amort"),
	(["40", "42", "43", "44", "45", "46", "47", "48"], "D", "BC", "brut"),
	# 491 is BB's own and 499 a passif provision (ED), hence no bare "49"
	(["492", "493", "494", "495", "496", "497", "498"], "any", "BC", "amort"),
	(["478"], "D", "DA", "brut"),
	(["50"], "D", "CA", "brut"), (["590"], "any", "CA", "amort"),
	(["51"], "D", "CB", "brut"), (["591"], "any", "CB", "amort"),
	(["52", "53", "54", "55", "56", "57", "58"], "D", "CC", "brut"),
	(["59"], "any", "CC", "amort"),
]

PASSIF_RULES = [
	(["101", "102", "103", "104"], "any", "CA"),
	(["109"], "any", "CB"),
	(["105"], "any", "CC"),
	(["106"], "any", "CD"),
	(["11"], "any", "CE"),
	(["12"], "any", "CF"),
	(["13"], "any", "CG"),
	(["14"], "any", "CH"),
	(["15"], "any", "CI"),
	(["16", "18"], "any", "DA"),
	(["17"], "any", "DB"),
	(["19"], "any", "DC"),
	(["40"], "C", "EA"),
	(["42", "43", "44"], "C", "EB"),
	(["41", "45", "46", "47"], "C", "EC"),
	(["499"], "any", "ED"),
	(["48"], "C", "EE"),
	(["479"], "C", "GA"),
	(["561"], "C", "FA"),
	(["564", "565", "566"], "C", "FB"),
	(["52", "53", "54", "55", "56", "57", "58"], "C", "FC"),
]

ACTIF_LINES = [
	("AA", _("Charges immobilisées")),
	("AB", _("Immobilisations incorporelles")),
	("AC", _("Terrains")),
	("AD", _("Bâtiments, installations techniques et agencements")),
	("AE", _("Matériel, mobilier et actifs biologiques")),
	("AF", _("Matériel de transport")),
	("AG", _("Immobilisations financières")),
	("AH", _("Avances et acomptes versés sur immobilisations")),
	("AZ", _("TOTAL ACTIF IMMOBILISÉ"), ["AA", "AB", "AC", "AD", "AE", "AF", "AG", "AH"]),
	("BA", _("Stocks et en-cours")),
	("BB", _("Créances clients et comptes rattachés")),
	("BC", _("Autres créances")),
	("BZ", _("TOTAL ACTIF CIRCULANT"), ["BA", "BB", "BC"]),
	("CA", _("Titres de placement")),
	("CB", _("Valeurs à encaisser")),
	("CC", _("Banques, caisse, chèques postaux et Mobile Money")),
	("CZ", _("TOTAL TRÉSORERIE ACTIF"), ["CA", "CB", "CC"]),
	("DA", _("Écart de conversion Actif")),
	("TA_ACTIF", _("TOTAL GÉNÉRAL ACTIF"), ["AZ", "BZ", "CZ", "DA"]),
]

PASSIF_LINES = [
	("CA", _("Capital social ou individuel")),
	("CB", _("Actionnaires, capital non appelé (-)")),
	("CC", _("Primes liées au capital social")),
	("CD", _("Écarts de réévaluation")),
	("CE", _("Réserves indisponibles et libres")),
	("CF", _("Report à nouveau (+/-)")),
	("CG", _("Résultat net de l'exercice (bénéfice + ou perte -)")),
	("CH", _("Subventions d'investissement")),
	("CI", _("Provisions réglementées et fonds assimilés")),
	("CZ", _("TOTAL CAPITAUX PROPRES ET RESSOURCES ASSIMILÉES"), ["CA", "CB", "CC", "CD", "CE", "CF", "CG", "CH", "CI"]),
	("DA", _("Emprunts et dettes financières diverses")),
	("DB", _("Dettes de crédit-bail et assimilés")),
	("DC", _("Provisions financières pour risques et charges")),
	("DZ", _("TOTAL DETTES FINANCIÈRES ET RESSOURCES ASSIMILÉES"), ["DA", "DB", "DC"]),
	("EA", _("Dettes fournisseurs et comptes rattachés")),
	("EB", _("Dettes fiscales et sociales")),
	("EC", _("Autres dettes")),
	("ED", _("Provisions pour risques à court terme")),
	("EE", _("Autres dettes hors exploitation")),
	("EZ", _("TOTAL PASSIF CIRCULANT"), ["EA", "EB", "EC", "ED", "EE"]),
	("FA", _("Banques, crédits d'escompte")),
	("FB", _("Banques, crédits de trésorerie et découverts")),
	("FC", _("Autres établissements financiers et instruments de trésorerie")),
	("FZ", _("TOTAL TRÉSORERIE PASSIF"), ["FA", "FB", "FC"]),
	("GA", _("Écart de conversion Passif")),
	("TP_PASSIF", _("TOTAL GÉNÉRAL PASSIF"), ["CZ", "DZ", "EZ", "FZ", "GA"]),
]

# Compte de resultat: (line, label, prefixes, nature) -- nature "P" produit
# (credit - debit), "C" charge (debit - credit).
RESULTAT_RULES = [
	("RA", _("Ventes de marchandises"), ["701"], "P"),
	("RB", _("Ventes de produits fabriqués"), ["702", "703", "704"], "P"),
	("RC", _("Travaux, services vendus et produits annexes"), ["705", "706", "707"], "P"),
	("RE", _("Production stockée (ou déstockage)"), ["73"], "P"),
	("RF", _("Production immobilisée"), ["72"], "P"),
	("RG", _("Subventions d'exploitation"), ["71"], "P"),
	("RH", _("Autres produits d'exploitation"), ["75"], "P"),
	("RI", _("Reprises de provisions et dépréciations d'exploitation"), ["791", "798", "799"], "P"),
	("RJ", _("Transferts de charges d'exploitation"), ["781"], "P"),
	("SA", _("Achats de marchandises"), ["601"], "C"),
	("SB", _("Variation de stocks de marchandises"), ["6031"], "C"),
	("SC", _("Achats de matières premières et fournitures rattachées"), ["602"], "C"),
	("SD", _("Variation de stocks de matières premières"), ["6032"], "C"),
	("SE", _("Autres achats et variations de stocks"), ["604", "605", "608", "609", "6033"], "C"),
	("SF", _("Transports"), ["61"], "C"),
	("SG", _("Services extérieurs"), ["62", "63"], "C"),
	("SH", _("Impôts et taxes"), ["64"], "C"),
	("SI", _("Autres charges d'exploitation"), ["65"], "C"),
	("SJ", _("Charges de personnel"), ["66"], "C"),
	("SK", _("Dotations aux amortissements, dépréciations et provisions"), ["681", "691"], "C"),
	("UA", _("Revenus financiers et produits assimilés"), ["77", "787", "797"], "P"),
	("UB", _("Frais financiers et charges assimilées"), ["67", "687", "697"], "C"),
	("VA", _("Produits hors activités ordinaires (HAO)"), ["82", "84", "86", "88"], "P"),
	("VB", _("Charges hors activités ordinaires (HAO)"), ["81", "83", "85"], "C"),
	("WA", _("Participation des travailleurs"), ["87"], "C"),
	("WB", _("Impôts sur le résultat"), ["89"], "C"),
]

RESULTAT_TOTALS = [
	("TA", _("MARGE BRUTE SUR MARCHANDISES"), {"RA": 1, "SA": -1, "SB": -1}),
	("TB", _("MARGE BRUTE SUR MATIÈRES"), {"RB": 1, "RC": 1, "SC": -1, "SD": -1}),
	("TC", _("VALEUR AJOUTÉE"), {"TA": 1, "TB": 1, "RE": 1, "RF": 1, "RG": 1, "RH": 1, "SE": -1, "SF": -1, "SG": -1}),
	("TD", _("EXCÉDENT BRUT D'EXPLOITATION (EBE)"), {"TC": 1, "SH": -1, "SI": -1, "SJ": -1}),
	("TE", _("RÉSULTAT D'EXPLOITATION"), {"TD": 1, "RI": 1, "RJ": 1, "SK": -1}),
	("UC", _("RÉSULTAT FINANCIER"), {"UA": 1, "UB": -1}),
	("UD", _("RÉSULTAT DES ACTIVITÉS ORDINAIRES (RAO)"), {"TE": 1, "UC": 1}),
	("VC", _("RÉSULTAT HORS ACTIVITÉS ORDINAIRES (HAO)"), {"VA": 1, "VB": -1}),
	("XZ", _("RÉSULTAT NET DE L'EXERCICE"), {"UD": 1, "VC": 1, "WA": -1, "WB": -1}),
]

# Display order of the income statement: each total right after its block.
RESULTAT_ORDER = [
	"RA", "SA", "SB", "TA",
	"RB", "RC", "SC", "SD", "TB",
	"RE", "RF", "RG", "RH", "SE", "SF", "SG", "TC",
	"SH", "SI", "SJ", "TD",
	"RI", "RJ", "SK", "TE",
	"UA", "UB", "UC",
	"UD",
	"VA", "VB", "VC",
	"WA", "WB", "XZ",
]


def get_account_balances(company, to_date, from_date=None):
	"""{account_number: debit - credit} over non-cancelled GL entries."""
	conditions = ["gle.company = %(company)s", "gle.is_cancelled = 0", "gle.posting_date <= %(to_date)s"]
	if from_date:
		conditions.append("gle.posting_date >= %(from_date)s")
	rows = frappe.db.sql(
		f"""
		select acc.account_number, acc.name, sum(gle.debit) - sum(gle.credit) as balance
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where {" and ".join(conditions)}
		group by acc.name, acc.account_number
		""",
		{"company": company, "to_date": to_date, "from_date": from_date},
		as_dict=True,
	)
	balances = {}
	unnumbered = []
	for row in rows:
		if not flt(row.balance):
			continue
		number = (row.account_number or "").strip()
		if not number:
			unnumbered.append(row.name)
			continue
		balances[number] = balances.get(number, 0.0) + flt(row.balance)
	return balances, unnumbered


def _match(number, rules, balance, key_len=0):
	"""Longest-prefix rule that applies to this account and balance side."""
	best = None
	for rule in rules:
		prefixes, side = rule[0], rule[1]
		if side == "D" and balance <= 0:
			continue
		if side == "C" and balance >= 0:
			continue
		for prefix in prefixes:
			if number.startswith(prefix) and (best is None or len(prefix) > best[0]):
				best = (len(prefix), rule)
	return best[1] if best else None


def compute_statements(company, from_date, to_date):
	"""Returns actif/passif/resultat line amounts for one fiscal period, plus
	the accounts no line could take (so an unbalanced sheet is explainable)."""
	cumulative, unnumbered = get_account_balances(company, to_date)
	period, _unused = get_account_balances(company, to_date, from_date)

	actif = {code: {"brut": 0.0, "amort": 0.0} for code, *_rest in ACTIF_LINES}
	passif = {code: 0.0 for code, *_rest in PASSIF_LINES}
	unclassified = []
	prior_result = 0.0

	for number, balance in cumulative.items():
		if number[0] in "678":
			# earlier years' result never closed into 12/13: report a nouveau
			prior_result -= balance - period.get(number, 0.0)
			continue
		rule = _match(number, ACTIF_RULES, balance)
		if rule:
			component = rule[3]
			actif[rule[2]][component] += balance if component == "brut" else -balance
			continue
		rule = _match(number, PASSIF_RULES, balance)
		if rule:
			passif[rule[2]] += -balance
			continue
		unclassified.append((number, balance))

	resultat = {}
	for code, _label, prefixes, nature in RESULTAT_RULES:
		resultat[code] = 0.0
	for number, balance in period.items():
		if number[0] not in "678":
			continue
		best = None
		for code, _label, prefixes, nature in RESULTAT_RULES:
			for prefix in prefixes:
				if number.startswith(prefix) and (best is None or len(prefix) > best[0]):
					best = (len(prefix), code, nature)
		if not best:
			unclassified.append((number, balance))
			continue
		resultat[best[1]] += -balance if best[2] == "P" else balance

	for code, _label, formula in RESULTAT_TOTALS:
		resultat[code] = sum(resultat[part] * sign for part, sign in formula.items())

	passif["CF"] += prior_result
	passif["CG"] += resultat["XZ"]

	actif_net = {code: values["brut"] - values["amort"] for code, values in actif.items()}
	for code, _label, *parts in ACTIF_LINES:
		if parts:
			actif[code]["brut"] = sum(actif[p]["brut"] for p in parts[0])
			actif[code]["amort"] = sum(actif[p]["amort"] for p in parts[0])
			actif_net[code] = sum(actif_net[p] for p in parts[0])
	for code, _label, *parts in PASSIF_LINES:
		if parts:
			passif[code] = sum(passif[p] for p in parts[0])

	return {
		"actif": actif,
		"actif_net": actif_net,
		"passif": passif,
		"resultat": resultat,
		"unclassified": unclassified,
		"unnumbered": unnumbered,
		"total_actif": actif_net["TA_ACTIF"],
		"total_passif": passif["TP_PASSIF"],
	}


def fiscal_year_dates(fiscal_year):
	start, end = frappe.db.get_value("Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"])
	return getdate(start), getdate(end)


def previous_fiscal_year(fiscal_year):
	start, _end = fiscal_year_dates(fiscal_year)
	return frappe.db.get_value(
		"Fiscal Year", {"year_end_date": ["<", start]}, "name", order_by="year_end_date desc"
	)
