# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""ERPNext port of PME360's SmeFinancialRatioService (app/Services/SmeFinancialRatioService.php).

Same OHADA-prefix-based ratio/scoring/classification rules, but reading GL
Entry (joined to Account.account_number) per Company instead of PME360's
AccountingEntry rows per user. Companies whose chart of accounts doesn't
carry OHADA account numbers (account_number empty) simply won't have
matching balances, so the analysis degrades gracefully to "donnees
insuffisantes" rather than producing garbage.

Deliberately ported: summarize (bilan/resultat), verdicts, scores,
qualite_donnees, classement (solvable/financable/non_retenu/insuffisant).
Deliberately NOT ported: the narrative "interpretation"/"modele_financier"
text blocks -- PME360's ranking page (financial-ranking.blade.php) never
displays them, only the per-company analysis page does, which is out of
scope here.
"""

import frappe
from frappe.utils import flt


def _account_ledger(company, date_from=None, date_to=None):
	conditions = ["gle.company = %(company)s", "gle.is_cancelled = 0"]
	params = {"company": company}
	if date_from:
		conditions.append("gle.posting_date >= %(date_from)s")
		params["date_from"] = date_from
	if date_to:
		conditions.append("gle.posting_date <= %(date_to)s")
		params["date_to"] = date_to

	rows = frappe.db.sql(
		f"""
		select acc.account_number as code, sum(gle.debit) as debit, sum(gle.credit) as credit
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where {" and ".join(conditions)}
			and acc.account_number is not null and acc.account_number != ''
		group by acc.account_number
		""",
		params,
		as_dict=True,
	)

	ledger = {}
	for r in rows:
		debit = flt(r.debit)
		credit = flt(r.credit)
		ledger[r.code] = {
			"debit": debit,
			"credit": credit,
			"debit_net": max(debit - credit, 0.0),
			"credit_net": max(credit - debit, 0.0),
		}
	return ledger


def _entries_count(company, date_from=None, date_to=None):
	conditions = ["company = %(company)s", "is_cancelled = 0"]
	params = {"company": company}
	if date_from:
		conditions.append("posting_date >= %(date_from)s")
		params["date_from"] = date_from
	if date_to:
		conditions.append("posting_date <= %(date_to)s")
		params["date_to"] = date_to

	row = frappe.db.sql(
		f"""select count(distinct concat(voucher_type, '||', voucher_no)) as c
		from `tabGL Entry` where {" and ".join(conditions)}""",
		params,
	)
	return int(row[0][0]) if row and row[0][0] else 0


def _sum_by_prefixes(ledger, prefixes, column="credit_net"):
	total = 0.0
	for code, row in ledger.items():
		for prefix in prefixes:
			if prefix and code.startswith(prefix):
				total += row.get(column, 0.0)
				break
	return total


def summarize(company, date_from=None, date_to=None):
	ledger = _account_ledger(company, date_from, date_to)

	def sbp(prefixes, column="credit_net"):
		return _sum_by_prefixes(ledger, prefixes, column)

	income = sbp(["7"], "credit_net")
	expenses = sbp(["6"], "debit_net")
	net_result = income - expenses

	capital = sbp(["101"], "credit_net")
	primes_reserves = sbp(["104", "105", "106", "107"], "credit_net")
	subventions = sbp(["131"], "credit_net")
	provisions_assimilees = sbp(["141", "142", "143", "144", "145", "146", "147", "148"], "credit_net")
	equity = capital + primes_reserves + subventions + provisions_assimilees + net_result

	dettes_fin = sbp(["161", "162", "163"], "credit_net")
	dettes_credit_bail = sbp(["164"], "credit_net")
	dettes_fin_diverses = sbp(["109", "165", "166"], "credit_net")
	provisions_fin = sbp(["19"], "credit_net")
	fournisseurs = sbp(["401", "403", "408"], "credit_net")
	dettes_fiscales = sbp(["441", "442", "443", "444", "445", "447"], "credit_net")
	dettes_sociales = sbp(["428", "431"], "credit_net")
	autres_dettes = sbp(["421", "451", "455", "467"], "credit_net")
	risques_provisionnes = sbp(["19", "49"], "credit_net")
	tresorerie_passif = sbp(["512", "514", "515", "521", "531", "541", "542", "566", "581"], "credit_net")

	liabilities = (
		dettes_fin
		+ dettes_credit_bail
		+ dettes_fin_diverses
		+ provisions_fin
		+ fournisseurs
		+ dettes_fiscales
		+ dettes_sociales
		+ autres_dettes
		+ risques_provisionnes
		+ tresorerie_passif
	)

	charges_immob = max(sbp(["201"], "debit_net") - sbp(["291"], "credit_net"), 0.0)
	primes_remb = max(sbp(["206"], "debit_net"), 0.0)
	actif_incorporel = max(sbp(["203", "205", "207", "208"], "debit_net") - sbp(["2811", "291"], "credit_net"), 0.0)
	actif_corporel = max(
		sbp(["211", "212", "213", "221", "215", "241", "244", "231"], "debit_net")
		- sbp(["2812", "2813", "2814", "2815", "2818", "292"], "credit_net"),
		0.0,
	)
	actif_financier = max(sbp(["261", "271", "275"], "debit_net"), 0.0)
	immobilisations_brutes = charges_immob + primes_remb + actif_incorporel + actif_corporel + actif_financier

	stocks_actif = max(
		sbp(["311", "321", "322", "331", "335", "341", "351", "355"], "debit_net") - sbp(["391", "392"], "credit_net"),
		0.0,
	)
	receivables_net = max(
		sbp(
			[
				"401", "403", "411", "413", "418", "421", "425", "428", "431", "438",
				"441", "442", "443", "444", "445", "447", "451", "455", "467",
			],
			"debit_net",
		),
		0.0,
	)
	tresorerie_actif = max(sbp(["512", "514", "515", "521", "531", "541", "542", "566", "581"], "debit_net"), 0.0)

	assets = immobilisations_brutes + stocks_actif + receivables_net + tresorerie_actif
	cash_ledger = tresorerie_actif - tresorerie_passif

	return {
		"assets": max(assets, 0.0),
		"liabilities": max(liabilities, 0.0),
		"income": max(income, 0.0),
		"expenses": max(expenses, 0.0),
		"receivables_net": max(receivables_net, 0.0),
		"cash_ledger": cash_ledger,
	}


def _niveau_score(valeur):
	if valeur >= 72.0:
		return "success"
	if valeur >= 50.0:
		return "warning"
	return "danger"


def _libelle_score(valeur):
	if valeur >= 75.0:
		return "Eleve"
	if valeur >= 58.0:
		return "Correct"
	if valeur >= 42.0:
		return "Fragile"
	return "Faible"


def _sous_score_marge(marge_nette, revenue):
	if revenue <= 0 or marge_nette is None:
		return 52.0
	if marge_nette < 0:
		return 18.0
	if marge_nette < 3.0:
		return 40.0 + marge_nette * 4.5
	if marge_nette < 10.0:
		return 53.5 + (marge_nette - 3.0) * 5.2
	if marge_nette < 25.0:
		return 90.0 + (marge_nette - 10.0) * 0.55
	return min(100.0, 98.5 + min(1.5, (marge_nette - 25.0) * 0.02))


def _sous_score_roa(roa):
	if roa is None:
		return 56.0
	if roa < -8.0:
		return 10.0
	if roa < 0:
		return 12.0 + (roa + 8.0) * 4.125
	if roa < 2.0:
		return 45.0 + roa * 13.5
	if roa < 8.0:
		return 72.0 + (roa - 2.0) * 3.33
	return min(100.0, 92.0 + min(8.0, (roa - 8.0) * 0.4))


def _sous_score_roe(roe):
	if roe is None:
		return 56.0
	if roe < -20.0:
		return 10.0
	if roe < 0:
		return 15.0 + (roe + 20.0) * 1.25
	if roe < 10.0:
		return 48.0 + roe * 3.5
	if roe < 25.0:
		return 83.0 + (roe - 10.0) * 0.85
	return min(100.0, 95.0 + min(5.0, (roe - 25.0) * 0.1))


def _score_brut_rentabilite(net_result, revenue, roa, roe, marge_nette):
	if net_result < 0:
		den = max(abs(revenue), 1.0)
		return round(max(5.0, min(38.0, 38.0 + (net_result / den) * 28.0)), 1)

	if abs(net_result) < 1e-6:
		return 44.0

	sm = _sous_score_marge(marge_nette, revenue)
	sr = _sous_score_roa(roa)
	se = _sous_score_roe(roe)

	if revenue <= 0:
		return round(sr * 0.55 + se * 0.45, 1)
	if roa is None and roe is None:
		return round(sm, 1)
	if roa is None:
		return round(sm * 0.58 + se * 0.42, 1)
	if roe is None:
		return round(sm * 0.52 + sr * 0.48, 1)
	return round(sm * 0.38 + sr * 0.32 + se * 0.30, 1)


def _sous_score_endettement_actif(pct):
	if pct is None:
		return 58.0
	if pct <= 0:
		return 100.0
	if pct <= 40.0:
		return 100.0 - pct * 0.45
	if pct <= 70.0:
		return 82.0 - (pct - 40.0) * 1.2
	if pct <= 90.0:
		return 46.0 - (pct - 70.0) * 0.85
	return max(12.0, 29.0 - (pct - 90.0) * 1.1)


def _sous_score_levier(levier):
	if levier is None:
		return 68.0
	if levier <= 0:
		return 100.0
	if levier <= 1.5:
		return 100.0 - levier * 9.0
	if levier <= 2.5:
		return 86.5 - (levier - 1.5) * 15.0
	if levier <= 4.0:
		return 71.5 - (levier - 2.5) * 12.0
	return max(15.0, 53.5 - (levier - 4.0) * 8.0)


def _sous_score_liquidite(ratio_lg):
	if ratio_lg is None:
		return 62.0
	if ratio_lg < 0.6:
		return 28.0
	if ratio_lg < 1.0:
		return 28.0 + (ratio_lg - 0.6) * 82.5
	if ratio_lg < 1.5:
		return 61.0 + (ratio_lg - 1.0) * 54.0
	if ratio_lg < 2.5:
		return 88.0 + (ratio_lg - 1.5) * 8.0
	return min(100.0, 96.0 + min(4.0, (ratio_lg - 2.5) * 2.0))


def _score_brut_solvabilite(equity, endettement_actif, levier, ratio_liquidite_generale):
	if equity <= 0.01:
		if endettement_actif is not None and endettement_actif > 55.0:
			return 20.0
		return 36.0

	s1 = _sous_score_endettement_actif(endettement_actif)
	s2 = _sous_score_levier(levier)
	s3 = _sous_score_liquidite(ratio_liquidite_generale)
	return round(s1 * 0.36 + s2 * 0.34 + s3 * 0.30, 1)


def _calculer_indice_fiabilite_donnees(entries_count, qualite_donnees):
	pen = 0.0
	if entries_count < 10:
		pen += 14.0
	elif entries_count < 25:
		pen += 7.0

	for a in qualite_donnees:
		n = a.get("niveau", "warning")
		if n == "warning":
			pen += 7.0
		elif n == "info":
			pen += 3.0

	pen = min(38.0, pen)
	pourcent = round(max(40.0, 100.0 - pen), 1)
	return {"pourcent": pourcent, "motif": "Indice derive du volume d'ecritures et des alertes qualite."}


def _build_qualite_donnees_alerts(entries_count, revenue, charges, assets, liabilities, net_result):
	out = []

	if entries_count == 0:
		out.append(
			{
				"niveau": "warning",
				"titre": "Aucune ecriture sur la periode",
				"texte": "Les agregats et ratios sont vides ou non significatifs.",
			}
		)
		return out

	if entries_count < 25:
		out.append(
			{
				"niveau": "warning",
				"titre": "Volume d'ecritures limite",
				"texte": f"Seulement {entries_count} ecriture(s) : les indicateurs restent indicatifs.",
			}
		)

	if revenue > 0.0:
		tol_rn = max(1.0, abs(revenue) * 1e-9)
		part_charges = charges / revenue
		rn_egal_ca = abs(net_result - revenue) < tol_rn
		if part_charges < 0.01 or rn_egal_ca:
			out.append(
				{
					"niveau": "warning",
					"titre": "Compte de resultat probablement incomplet",
					"texte": "Les charges (classe 6) sont tres faibles ou absentes par rapport au chiffre d'affaires.",
				}
			)

	if assets > 1000.0 and liabilities < 1.0:
		out.append(
			{
				"niveau": "info",
				"titre": "Passif (dettes) quasi nul",
				"texte": "Aucune dette significative detectee : le ratio actif / passif n'a pas de sens mathematique.",
			}
		)

	if revenue > 1000.0 and liabilities < 1.0 and assets > 1000.0:
		ecart_relatif = abs(assets - revenue) / revenue
		tol_rn2 = max(1.0, abs(revenue) * 1e-9)
		if ecart_relatif < 0.02 and abs(net_result - revenue) < tol_rn2:
			out.append(
				{
					"niveau": "info",
					"titre": "Scenario comptable minimal",
					"texte": "Les montants cles (CA, resultat, actif, capitaux propres estimes) sont tres proches : saisie probablement partielle.",
				}
			)

	return out


def _build_verdicts(entries_count, net_result, roa, marge_nette, equity, endettement_actif, ratio_liquidite_generale, levier):
	if entries_count == 0:
		non_evaluable = {
			"label": "Non evaluable",
			"niveau": "secondary",
			"resume": "Pas d'ecriture sur la periode.",
		}
		return {"rentabilite": non_evaluable, "solvabilite": dict(non_evaluable)}

	if net_result < 0:
		rent = {"label": "Non rentable (sur la periode)", "niveau": "danger", "resume": "Le resultat net est negatif."}
	elif net_result == 0.0:
		rent = {"label": "A la limite", "niveau": "warning", "resume": "Resultat net nul."}
	else:
		roa_ok = roa is None or roa >= 2.0
		marge_ok = marge_nette is None or marge_nette >= 3.0
		if roa_ok and marge_ok:
			rent = {
				"label": "Rentable (synthese favorable)",
				"niveau": "success",
				"resume": "Resultat net positif, ROA et marge nette dans des fourchettes saines.",
			}
		elif marge_nette is not None and 0 <= marge_nette < 3.0:
			rent = {
				"label": "Rentable mais fragile",
				"niveau": "warning",
				"resume": "Resultat positif mais marge nette faible.",
			}
		else:
			rent = {"label": "Rentable (a surveiller)", "niveau": "warning", "resume": "Resultat net positif ; a affiner."}

	if equity <= 0.01 and endettement_actif is not None and endettement_actif > 50:
		solv = {
			"label": "Situation tres tendue",
			"niveau": "danger",
			"resume": "Capitaux propres estimes quasi nuls ou negatifs avec dettes.",
		}
	elif equity <= 0.01:
		solv = {"label": "Structure a clarifier", "niveau": "warning", "resume": "Fonds propres estimes tres faibles."}
	else:
		endett_ok = endettement_actif is None or endettement_actif <= 70.0
		liq_ok = ratio_liquidite_generale is None or ratio_liquidite_generale >= 1.0
		lev_ok = levier is None or levier <= 2.5

		if endett_ok and liq_ok and lev_ok:
			solv = {
				"label": "Solvabilite favorable (synthese)",
				"niveau": "success",
				"resume": "Fonds propres positifs, endettement et levier moderes, liquidite compatible.",
			}
		elif not endett_ok or (levier is not None and levier > 3.0):
			solv = {
				"label": "Solvabilite a surveiller",
				"niveau": "warning",
				"resume": "Le poids de la dette ou du levier merite un suivi.",
			}
		else:
			solv = {
				"label": "Solvabilite correcte sous reserves",
				"niveau": "warning",
				"resume": "Structure acceptable mais un indicateur sort de la zone confort.",
			}

	return {"rentabilite": rent, "solvabilite": solv}


def _build_scores(entries_count, net_result, revenue, roa, roe, marge_nette, equity, endettement_actif, ratio_liquidite_generale, levier, qualite_donnees):
	if entries_count == 0:
		return {"rentabilite": None, "solvabilite": None, "global": None, "fiabilite_donnees_pct": None}

	r_brut = _score_brut_rentabilite(net_result, revenue, roa, roe, marge_nette)
	s_brut = _score_brut_solvabilite(equity, endettement_actif, levier, ratio_liquidite_generale)
	fiab = _calculer_indice_fiabilite_donnees(entries_count, qualite_donnees)

	moyenne = round((r_brut + s_brut) / 2.0, 1)
	fiab_pct = fiab["pourcent"]
	valeur_fiabilisee = round(moyenne * (fiab_pct / 100.0), 1)

	return {
		"rentabilite": {"valeur": r_brut, "niveau": _niveau_score(r_brut), "libelle": _libelle_score(r_brut)},
		"solvabilite": {"valeur": s_brut, "niveau": _niveau_score(s_brut), "libelle": _libelle_score(s_brut)},
		"global": {
			"valeur": moyenne,
			"valeur_fiabilisee": valeur_fiabilisee,
			"niveau": _niveau_score(valeur_fiabilisee),
			"libelle": _libelle_score(valeur_fiabilisee),
		},
		"fiabilite_donnees_pct": fiab_pct,
	}


def evaluate_classement_financier(analysis):
	entries = int(analysis.get("entries_count") or 0)
	verdicts = analysis.get("verdicts") or {}
	scores = analysis.get("scores") or {}

	solv_nv = (verdicts.get("solvabilite") or {}).get("niveau", "secondary")
	rent_nv = (verdicts.get("rentabilite") or {}).get("niveau", "secondary")

	s_solv = (scores.get("solvabilite") or {}).get("valeur")
	s_rent = (scores.get("rentabilite") or {}).get("valeur")
	fiab = scores.get("fiabilite_donnees_pct")
	syn_f = (scores.get("global") or {}).get("valeur_fiabilisee")

	motifs = []

	if entries == 0 or solv_nv == "secondary" or rent_nv == "secondary":
		return {
			"code": "insuffisant",
			"solvable": False,
			"financable": False,
			"libelle": "Non classe - donnees insuffisantes",
			"motifs": ["Pas d'ecriture exploitable sur la periode ou verdicts non calculables."],
			"score_tri": 0.0,
		}

	solvable = False
	if solv_nv == "danger":
		motifs.append("Verdict solvabilite defavorable (structure ou endettement).")
	elif solv_nv == "success" and entries >= 5:
		solvable = True
		motifs.append("Solvabilite : synthese favorable.")
	elif entries >= 5 and s_solv is not None and s_solv >= 54.0 and solv_nv != "danger":
		solvable = True
		motifs.append("Solvabilite : score >= 54/100 avec historique minimal.")
	elif entries < 5:
		motifs.append("Moins de 5 ecritures : solvabilite non retenue pour classement.")
	else:
		motifs.append("Solvabilite : score ou verdict insuffisant.")

	financable = False
	if solvable:
		if rent_nv == "danger":
			motifs.append("Rentabilite : verdict defavorable - non retenu pour financement automatique.")
		elif entries < 15:
			motifs.append("Moins de 15 ecritures : profil non retenu pour finançable (seuil prudence).")
		elif fiab is not None and fiab < 52.0:
			motifs.append("Indice de fiabilite des donnees < 52% - profil non retenu.")
		elif syn_f is not None and syn_f < 48.0:
			motifs.append("Synthese fiabilisee < 48 - profil non retenu pour financement.")
		elif rent_nv == "success" or (s_rent is not None and s_rent >= 56.0):
			financable = True
			motifs.append("Rentabilite favorable et criteres de fiabilite atteints.")
		else:
			motifs.append("Rentabilite correcte mais hors seuil finançable.")

	if financable:
		code, libelle = "financable", "Financable (automatique)"
	elif solvable:
		code, libelle = "solvable_seulement", "Solvable seulement"
	else:
		code, libelle = "non_retenu", "Non retenu"

	if syn_f is not None:
		score_tri = syn_f
	elif s_solv is not None and s_rent is not None:
		score_tri = (s_solv + s_rent) / 2.0
	else:
		score_tri = 0.0

	seen = set()
	deduped_motifs = [m for m in motifs if not (m in seen or seen.add(m))]

	return {
		"code": code,
		"solvable": solvable,
		"financable": financable,
		"libelle": libelle,
		"motifs": deduped_motifs,
		"score_tri": round(float(score_tri), 1),
	}


def analyze(company, date_from=None, date_to=None):
	summary = summarize(company, date_from, date_to)
	entries_count = _entries_count(company, date_from, date_to)

	assets = summary["assets"]
	liabilities = summary["liabilities"]
	revenue = summary["income"]
	charges = summary["expenses"]
	net_result = revenue - charges
	equity = assets - liabilities

	roa = (net_result / assets) * 100 if assets > 0 else None
	roe = (net_result / equity) * 100 if equity > 0.01 else None
	marge_nette = (net_result / revenue) * 100 if revenue > 0 else None
	levier = liabilities / equity if equity > 0.01 else None
	endettement_actif = (liabilities / assets) * 100 if assets > 0 else None
	ratio_liquidite_generale = assets / liabilities if liabilities > 0 else None

	verdicts = _build_verdicts(entries_count, net_result, roa, marge_nette, equity, endettement_actif, ratio_liquidite_generale, levier)
	qualite_donnees = _build_qualite_donnees_alerts(entries_count, revenue, charges, assets, liabilities, net_result)
	scores = _build_scores(entries_count, net_result, revenue, roa, roe, marge_nette, equity, endettement_actif, ratio_liquidite_generale, levier, qualite_donnees)

	result = {
		"entries_count": entries_count,
		"verdicts": verdicts,
		"scores": scores,
		"qualite_donnees": qualite_donnees,
		"base": {
			"chiffre_affaires_ht": revenue,
			"charges": charges,
			"resultat_net": net_result,
			"total_actif": assets,
			"total_passif": liabilities,
			"capitaux_propres_estimes": equity,
		},
		"ratios": {
			"roa_pct": round(roa, 2) if roa is not None else None,
			"roe_pct": round(roe, 2) if roe is not None else None,
			"marge_nette_pct": round(marge_nette, 2) if marge_nette is not None else None,
			"endettement_sur_actif_pct": round(endettement_actif, 2) if endettement_actif is not None else None,
			"dettes_sur_capitaux_propres": round(levier, 3) if levier is not None else None,
			"liquidite_generale": round(ratio_liquidite_generale, 3) if ratio_liquidite_generale is not None else None,
		},
	}
	result["classement"] = evaluate_classement_financier(result)
	return result


def classement_erpnext(date_from=None, date_to=None):
	companies = frappe.get_all("Company", fields=["name", "company_name"], order_by="company_name")

	lignes = []
	for company in companies:
		analysis = analyze(company.name, date_from, date_to)
		classement = analysis["classement"]
		lignes.append(
			{
				"company": company.name,
				"company_name": company.company_name,
				"classement": classement,
				"synthese_fiabilisee": (analysis.get("scores") or {}).get("global", {}).get("valeur_fiabilisee")
				if (analysis.get("scores") or {}).get("global")
				else None,
				"entries_count": analysis["entries_count"],
			}
		)

	prio = {"financable": 4, "solvable_seulement": 3, "non_retenu": 2, "insuffisant": 1}

	def sort_key(row):
		code = row["classement"]["code"]
		p = prio.get(code, 0)
		syn = row["synthese_fiabilisee"]
		return (-p, -(syn if syn is not None else -1), -row["entries_count"])

	lignes.sort(key=sort_key)

	compteurs = {"financable": 0, "solvable_seulement": 0, "non_retenu": 0, "insuffisant": 0}
	for row in lignes:
		code = row["classement"]["code"]
		if code in compteurs:
			compteurs[code] += 1

	return {"lignes": lignes, "compteurs": compteurs}
