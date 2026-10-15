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

	# earlier years' result never closed into 12/13: report a nouveau. Over
	# every class 6-8 account that moved, not only those with a cumulative
	# balance: a past charge reversed this year (cumulative 0, period -X)
	# was skipped and the sheet came out unbalanced by X (2026-10-15).
	for number in set(cumulative) | set(period):
		if number[0] in "678":
			prior_result -= cumulative.get(number, 0.0) - period.get(number, 0.0)

	for number, balance in cumulative.items():
		if number[0] in "678":
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


# ---------------------------------------------------------------------------
# TAFIRE — Tableau Financier des Ressources et des Emplois (SYSCOHADA révisé)
# ---------------------------------------------------------------------------

def get_period_movements(company, from_date, to_date):
	"""Returns {account_number: {"debit": d, "credit": c}} for non-opening
	GL entries in the period.  Opening entries (is_opening = 'Yes') are
	excluded so that Tableaux 1 and 2 only show real movements."""
	rows = frappe.db.sql(
		"""
		select acc.account_number,
		       sum(gle.debit)  as debit,
		       sum(gle.credit) as credit
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where gle.company      = %(company)s
		  and gle.is_cancelled = 0
		  and gle.posting_date >= %(from_date)s
		  and gle.posting_date <= %(to_date)s
		  and (gle.is_opening is null or gle.is_opening = 'No')
		group by acc.account_number
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	result = {}
	for row in rows:
		number = (row.account_number or "").strip()
		if number:
			result[number] = {"debit": flt(row.debit), "credit": flt(row.credit)}
	return result


def _mv_debit(movements, *prefixes):
	"""Total debits on movements whose account_number starts with any prefix."""
	return sum(v["debit"] for k, v in movements.items() if any(k.startswith(p) for p in prefixes))


def _mv_credit(movements, *prefixes):
	"""Total credits on movements whose account_number starts with any prefix."""
	return sum(v["credit"] for k, v in movements.items() if any(k.startswith(p) for p in prefixes))


def _bfe(actif_net, passif):
	"""BFE = stocks + créances actif circulant − dettes passif circulant."""
	actif_circ = actif_net["BA"] + actif_net["BB"] + actif_net["BC"]
	dettes_circ = (passif["EA"] + passif["EB"] + passif["EC"]
	               + passif["ED"] + passif["EE"])
	return actif_circ - dettes_circ


def _tresorerie_nette(actif_net, passif):
	"""Trésorerie nette = trésorerie actif − trésorerie passif."""
	return (actif_net["CA"] + actif_net["CB"] + actif_net["CC"]) - (
		passif["FA"] + passif["FB"] + passif["FC"]
	)


def _assign_immo_code(number):
	"""Longest-prefix match on class-2 brut rules → Tableau 1 row code."""
	best = None
	for rule in ACTIF_RULES:
		prefixes, _side, code, component = rule
		if component != "brut":
			continue
		if not code.startswith("A") or code == "AZ":
			continue
		for prefix in prefixes:
			if number.startswith(prefix) and (best is None or len(prefix) > best[0]):
				best = (len(prefix), code)
	return best[1] if best else None


def _assign_amort_code(number):
	"""Longest-prefix match on class-28/29 amort rules → Tableau 2 row code."""
	best = None
	for rule in ACTIF_RULES:
		prefixes, _side, code, component = rule
		if component != "amort":
			continue
		if not code.startswith("A") or code == "AZ":
			continue
		for prefix in prefixes:
			if number.startswith(prefix) and (best is None or len(prefix) > best[0]):
				best = (len(prefix), code)
	return best[1] if best else None


def compute_tafire(company, from_date, to_date, dividendes=0):
	"""Compute TAFIRE (Tableau Financier des Ressources et des Emplois).

	Returns a dict with:
	- rows: list of row dicts {ref, libelle, emplois, ressources, bold, indent, section}
	- cafg, af, xc (variation BFE), xd (ETE), fu, fv, fw (trésorerie): float
	- warning_dividendes: True when dividendes=0 was assumed (not supplied)

	dividendes — distributions versées durant l'exercice (ne figurent pas dans
	le GL standard; passer la valeur explicitement ou laisser à 0).
	"""
	import datetime as _dt

	# ── N statements ─────────────────────────────────────────────────────────
	stmts_n = compute_statements(company, from_date, to_date)
	r = stmts_n["resultat"]
	an = stmts_n["actif_net"]
	pn = stmts_n["passif"]

	# ── N-1 balance sheet (cumulative au jour précédant from_date) ────────────
	prev_date = getdate(from_date) - _dt.timedelta(days=1)
	# We only need BS positions from N-1; passing prev_date as both from/to
	# gives a correct cumulative BS and an empty single-day P&L (unused here).
	stmts_n1 = compute_statements(company, prev_date, prev_date)
	an1 = stmts_n1["actif_net"]
	pn1 = stmts_n1["passif"]

	# ── Period movements (hors écritures d'ouverture) ─────────────────────────
	mv = get_period_movements(company, from_date, to_date)

	# ── Partie 1 : CAFG ───────────────────────────────────────────────────────
	ebe = r["TD"]
	charges_dec = r["UB"] + r["VB"] + r["WA"] + r["WB"]
	produits_enc = r["RJ"] + r["UA"] + r["VA"]
	cafg = ebe - charges_dec + produits_enc
	div = flt(dividendes)
	af = cafg - div

	# ── Partie 1 : Variation BFE ──────────────────────────────────────────────
	variation_stocks = an["BA"] - an1["BA"]
	variation_creances = (an["BB"] + an["BC"]) - (an1["BB"] + an1["BC"])
	variation_dettes = (
		(pn["EA"] + pn["EB"] + pn["EC"] + pn["ED"] + pn["EE"])
		- (pn1["EA"] + pn1["EB"] + pn1["EC"] + pn1["ED"] + pn1["EE"])
	)
	xc = variation_stocks + variation_creances - variation_dettes

	# ── Partie 1 : ETE ────────────────────────────────────────────────────────
	production_immo = r["RF"]
	xd = ebe - xc - production_immo

	# ── Partie 2 : Investissements ────────────────────────────────────────────
	def _net_mv(*prefixes):
		d = _mv_debit(mv, *prefixes)
		c = _mv_credit(mv, *prefixes)
		return max(0.0, d - c), max(0.0, c - d)  # (emplois, ressources)

	fa_e, fa_r = _net_mv("20")
	fb_e, fb_r = _net_mv("21")
	fc_e, fc_r = _net_mv("22", "23", "24", "25")
	fd_e, fd_r = _net_mv("26", "27")
	ff_e = fa_e + fb_e + fc_e + fd_e
	ff_r = fa_r + fb_r + fc_r + fd_r

	fg_e = max(0.0, xc)   # BFE augmente = emploi
	fg_r = max(0.0, -xc)  # BFE diminue  = ressource
	fh_e = ff_e + fg_e
	fh_r = ff_r + fg_r

	# HAO: non suivi automatiquement
	fi_e = fi_r = 0.0

	# Remboursements d'emprunts = débits sur 16x, 17x, 18x
	fj_e = _mv_debit(mv, "16", "17", "18")
	fj_r = 0.0
	fk_e = fh_e + fi_e + fj_e
	fk_r = fh_r + fi_r + fj_r

	# ── Partie 3 : Financement ────────────────────────────────────────────────
	fl_e = div + max(0.0, -cafg)  # dividendes + CAFG négatif
	fl_r = max(0.0, cafg)

	fm_e = 0.0
	fm_r = _mv_credit(mv, "101", "102", "103", "104")

	fn_e = 0.0
	fn_r = _mv_credit(mv, "14")

	fp_e = _mv_debit(mv, "10", "11", "12", "13")
	fp_r = 0.0

	# Nouveaux emprunts = crédits sur 16x, 17x, 18x
	fq_e = 0.0
	fq_r = _mv_credit(mv, "16", "17", "18")

	fr_e = fr_r = 0.0  # autres dettes financières non ventilées

	fs_e = fl_e + fp_e
	fs_r = fl_r + fm_r + fn_r + fq_r + fr_r

	ft_net = fs_r - fk_e  # excédent (+) ou insuffisance (−)
	ft_e = max(0.0, -ft_net)
	ft_r = max(0.0, ft_net)

	# ── Trésorerie ────────────────────────────────────────────────────────────
	fu = _tresorerie_nette(an, pn)
	fv = _tresorerie_nette(an1, pn1)
	fw = fu - fv

	# ── Build rows ────────────────────────────────────────────────────────────
	def _r(ref, label, emploi, res, is_total=False, section=""):
		return {
			"ref": ref, "libelle": label,
			"emplois": flt(emploi), "ressources": flt(res),
			"bold": 1 if is_total else 0,
			"indent": 0 if is_total else 1,
			"section": section,
		}

	rows = [
		_r("",     _("PARTIE 1 — SOLDES FINANCIERS DE SYNTHÈSE"), 0, 0, True, "titre"),
		_r("TD",   _("Excédent Brut d'Exploitation (EBE)"),
		   max(0.0, -ebe), max(0.0, ebe), False, "cafg"),
		_r("UB",   _("(-) Frais financiers et charges assimilées"),
		   r["UB"], 0, False, "cafg"),
		_r("VB",   _("(-) Charges HAO décaissables"), r["VB"], 0, False, "cafg"),
		_r("WA",   _("(-) Participation des travailleurs"), r["WA"], 0, False, "cafg"),
		_r("WB",   _("(-) Impôts sur le résultat"), r["WB"], 0, False, "cafg"),
		_r("RJ",   _("(+) Transferts de charges d'exploitation"),
		   0, r["RJ"], False, "cafg"),
		_r("UA",   _("(+) Revenus financiers et produits assimilés"),
		   0, r["UA"], False, "cafg"),
		_r("VA",   _("(+) Produits HAO encaissables"), 0, r["VA"], False, "cafg"),
		_r("CAFG", _("CAPACITÉ D'AUTOFINANCEMENT GLOBALE (CAFG)"),
		   max(0.0, -cafg), max(0.0, cafg), True, "cafg"),
		_r("DIV",  _("(-) Distributions de dividendes"), div, 0, False, "cafg"),
		_r("AF",   _("AUTOFINANCEMENT (AF)"),
		   max(0.0, -af), max(0.0, af), True, "cafg"),
		# BFE
		_r("EC",   _("Variation globale nette des stocks (N − N-1)"),
		   max(0.0, variation_stocks), max(0.0, -variation_stocks), False, "bfe"),
		_r("ED",   _("Variation globale nette des créances (N − N-1)"),
		   max(0.0, variation_creances), max(0.0, -variation_creances), False, "bfe"),
		_r("EF",   _("Variation globale nette des dettes (N − N-1)"),
		   max(0.0, -variation_dettes), max(0.0, variation_dettes), False, "bfe"),
		_r("XC",   _("VARIATION DU B.F.E."),
		   max(0.0, xc), max(0.0, -xc), True, "bfe"),
		# ETE
		_r("TQ",   _("Excédent Brut d'Exploitation (rappel)"),
		   max(0.0, -ebe), max(0.0, ebe), False, "ete"),
		_r("TR",   _("(-/+) Variation du B.F.E."),
		   max(0.0, xc), max(0.0, -xc), False, "ete"),
		_r("TF",   _("(-) Production immobilisée"), production_immo, 0, False, "ete"),
		_r("XD",   _("EXCÉDENT DE TRÉSORERIE D'EXPLOITATION (ETE)"),
		   max(0.0, -xd), max(0.0, xd), True, "ete"),
		# Partie 2
		_r("",     _("PARTIE 2 — TABLEAU EMPLOIS / RESSOURCES"), 0, 0, True, "titre"),
		_r("FA",   _("I. Charges immobilisées"), fa_e, fa_r, False, "invest"),
		_r("FB",   _("I. Immobilisations incorporelles"), fb_e, fb_r, False, "invest"),
		_r("FC",   _("I. Immobilisations corporelles"), fc_e, fc_r, False, "invest"),
		_r("FD",   _("I. Immobilisations financières"), fd_e, fd_r, False, "invest"),
		_r("FF",   _("INVESTISSEMENT TOTAL (I)"), ff_e, ff_r, True, "invest"),
		_r("FG",   _("II. Variation du BFE"), fg_e, fg_r, False, "invest"),
		_r("FH",   _("A — EMPLOIS ÉCONOMIQUES (FF + II)"), fh_e, fh_r, True, "invest"),
		_r("FI",   _("III. Emplois / Ressources HAO"), fi_e, fi_r, False, "invest"),
		_r("FJ",   _("IV. Remboursements d'emprunts et dettes financières"),
		   fj_e, fj_r, False, "invest"),
		_r("FK",   _("B — EMPLOIS TOTAUX À FINANCER (A + III + IV)"),
		   fk_e, fk_r, True, "invest"),
		_r("FL",   _("V. Dividendes / CAFG"), fl_e, fl_r, False, "fin"),
		_r("FM",   _("VI. Augmentations de capital par apports nouveaux"),
		   fm_e, fm_r, False, "fin"),
		_r("FN",   _("VI. Subventions d'investissement"), fn_e, fn_r, False, "fin"),
		_r("FP",   _("VI. Prélèvements sur le capital"), fp_e, fp_r, False, "fin"),
		_r("FQ",   _("VII. Emprunts nouveaux"), fq_e, fq_r, False, "fin"),
		_r("FR",   _("VII. Autres dettes financières"), fr_e, fr_r, False, "fin"),
		_r("FS",   _("C — RESSOURCES NETTES DE FINANCEMENT"),
		   fs_e, fs_r, True, "fin"),
		_r("FT",   _("D — EXCÉDENT (+) / INSUFFISANCE (−) DE RESSOURCES (C − B)"),
		   ft_e, ft_r, True, "fin"),
		# Trésorerie
		_r("FU",   _("Trésorerie nette à la clôture"), 0, fu, False, "treso"),
		_r("FV",   _("Trésorerie nette à l'ouverture"), 0, fv, False, "treso"),
		_r("FW",   _("VARIATION DE LA TRÉSORERIE (FU − FV)"),
		   max(0.0, -fw), max(0.0, fw), True, "treso"),
	]

	return {
		"rows": rows,
		"cafg": cafg,
		"af": af,
		"xc": xc,
		"xd": xd,
		"fu": fu,
		"fv": fv,
		"fw": fw,
		"warning_dividendes": div == 0,
	}


# ---------------------------------------------------------------------------
# Tableau 1 — Mouvements des immobilisations brutes (comptes classe 2)
# ---------------------------------------------------------------------------

def compute_tableau1(company, from_date, to_date):
	"""Tableau 1 — Actif immobilisé brut.

	Ouverture (A)       = solde cumulatif au jour précédant from_date
	Acquisitions (B)    = débits de la période hors écritures d'ouverture
	Cessions/sorties (C)= crédits de la période hors écritures d'ouverture
	Clôture (D = A+B−C) = contrôlé contre le solde de fin de période
	"""
	import datetime as _dt

	prev_date = getdate(from_date) - _dt.timedelta(days=1)
	cumul_opening, _unnumbered = get_account_balances(company, prev_date)
	mv = get_period_movements(company, from_date, to_date)

	codes_order = ["AA", "AB", "AC", "AD", "AE", "AF", "AG", "AH"]
	labels = {code: label for code, label, *_rest in ACTIF_LINES if code in codes_order}
	data = {code: {"a": 0.0, "b": 0.0, "c": 0.0} for code in codes_order}

	for number, balance in cumul_opening.items():
		code = _assign_immo_code(number)
		if code:
			data[code]["a"] += max(0.0, balance)  # immos = débiteurs

	for number, mv_row in mv.items():
		code = _assign_immo_code(number)
		if code:
			data[code]["b"] += mv_row["debit"]
			data[code]["c"] += mv_row["credit"]

	rows = []
	tot = {"a": 0.0, "b": 0.0, "c": 0.0}
	for code in codes_order:
		d = data[code]
		cloture = d["a"] + d["b"] - d["c"]
		rows.append({
			"ref": code, "libelle": labels.get(code, code),
			"bold": 0, "indent": 1,
			"ouverture": flt(d["a"]),
			"acquisitions": flt(d["b"]),
			"cessions": flt(d["c"]),
			"cloture": flt(cloture),
		})
		for k in ("a", "b", "c"):
			tot[k] += d[k]

	rows.append({
		"ref": "AZ", "libelle": _("TOTAL ACTIF IMMOBILISÉ"),
		"bold": 1, "indent": 0,
		"ouverture": flt(tot["a"]),
		"acquisitions": flt(tot["b"]),
		"cessions": flt(tot["c"]),
		"cloture": flt(tot["a"] + tot["b"] - tot["c"]),
	})
	return rows


# ---------------------------------------------------------------------------
# Tableau 2 — Mouvements des amortissements et dépréciations (comptes 28x/29x)
# ---------------------------------------------------------------------------

def compute_tableau2(company, from_date, to_date):
	"""Tableau 2 — Amortissements et dépréciations cumulés.

	Cumul ouverture (A) = solde créditeur cumulatif au jour précédant from_date
	Dotations (B)       = crédits sur 28x/29x en cours d'exercice (hors AN)
	Sorties (C)         = débits sur 28x/29x (extourne sur actifs cédés)
	Cumul clôture (D = A+B−C)
	"""
	import datetime as _dt

	prev_date = getdate(from_date) - _dt.timedelta(days=1)
	cumul_opening, _unnumbered = get_account_balances(company, prev_date)
	mv = get_period_movements(company, from_date, to_date)

	codes_order = ["AA", "AB", "AC", "AD", "AE", "AF", "AG", "AH"]
	labels = {code: label for code, label, *_rest in ACTIF_LINES if code in codes_order}
	data = {code: {"a": 0.0, "b": 0.0, "c": 0.0} for code in codes_order}

	# Opening: 28x/29x ont un solde créditeur → balance = débit - crédit < 0
	for number, balance in cumul_opening.items():
		code = _assign_amort_code(number)
		if code:
			data[code]["a"] += max(0.0, -balance)  # valeur absolue du crédit

	for number, mv_row in mv.items():
		code = _assign_amort_code(number)
		if code:
			data[code]["b"] += mv_row["credit"]  # nouvelles dotations → 681x / 28x
			data[code]["c"] += mv_row["debit"]   # extournes sur cessions → 28x / 81x

	rows = []
	tot = {"a": 0.0, "b": 0.0, "c": 0.0}
	for code in codes_order:
		d = data[code]
		cloture = d["a"] + d["b"] - d["c"]
		rows.append({
			"ref": code,
			"libelle": _("{0} — amortissements").format(labels.get(code, code)),
			"bold": 0, "indent": 1,
			"cumul_ouverture": flt(d["a"]),
			"dotations": flt(d["b"]),
			"sorties": flt(d["c"]),
			"cumul_cloture": flt(cloture),
		})
		for k in ("a", "b", "c"):
			tot[k] += d[k]

	rows.append({
		"ref": "AZ", "libelle": _("TOTAL AMORTISSEMENTS ET DÉPRÉCIATIONS"),
		"bold": 1, "indent": 0,
		"cumul_ouverture": flt(tot["a"]),
		"dotations": flt(tot["b"]),
		"sorties": flt(tot["c"]),
		"cumul_cloture": flt(tot["a"] + tot["b"] - tot["c"]),
	})
	return rows
