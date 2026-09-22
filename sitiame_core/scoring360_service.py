# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""ERPNext port of PME360's Scoring360Service (app/Services/Scoring360Service.php)
and its Scoring360Defaults (app/Support/Scoring360Defaults.php).

Same 3-block (Banque/Investisseur/Interne) + Composite weighted scoring
engine, reading GL Entry per ERPNext Company instead of PME360's
AccountingEntry per user. This is now the single scoring engine for the
app -- also powers the "Classement financier" portfolio ranking
(classement_erpnext below), formerly a separate, slightly divergent
engine in financial_ratio_service.py (deleted).

Config is stored on the "Scoring 360 Settings" single DocType (thresholds,
weights, decision cutoffs -- same editable surface as PME360's
/admin/scoring-parameters form). Labels/lectures are fixed, exactly like
PME360 (its update() endpoint never lets the admin edit those either).

Deliberate simplification: PME360's "treasury_net" comes from a separate
Tresorerie module (encaissements/decaissements "effectues") that has no
ERPNext equivalent. Scoring360Service itself already computes a GL-based
cash/cash-liabilities pair for the current-ratio inputs (lines 56/62 of the
PHP source) -- that same figure (cash - cash_liabilities) is reused here as
the treasury_net proxy, documented as such.
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

CRITERIA_DIRECTIONS = {
	"bank": {
		"dscr": "gte",
		"interest_coverage": "gte",
		"current_ratio": "gte",
		"debt_asset": "lte",
		"bfr_days": "lte",
	},
	"investor": {
		"revenue_growth": "gte",
		"ebitda_margin": "gte",
		"roe": "gte",
		"fcf_margin": "gte",
		"asset_turnover": "gte",
	},
	"internal": {
		"net_margin": "gte",
		"quick_ratio": "gte",
		"receivable_days": "lte",
		"inventory_days": "lte",
		"ebitda_growth": "gte",
	},
}

DECISION_LABELS = {
	"bank": {"strong": "FINANCABLE", "medium": "A SURVEILLER", "weak": "RISQUE ELEVE"},
	"investor": {"strong": "ATTRACTIF", "medium": "POTENTIEL", "weak": "A AMELIORER"},
	"internal": {"strong": "MAITRISE", "medium": "SOUS CONTROLE", "weak": "A CORRIGER"},
	"composite": {"strong": "PRET A DEPLOYER", "medium": "SOLIDE MAIS A CADRER", "weak": "RISQUE A TRAITER"},
}

DECISION_LECTURES = {
	"bank": {
		"strong": "Financement bancaire possible sous reserve de due diligence.",
		"medium": "Financement possible avec covenants et montant prudent.",
		"weak": "Preferer restructuration ou financement encadre.",
	},
	"investor": {
		"strong": "Dossier investissable avec potentiel de croissance.",
		"medium": "Interet possible avec plan d'amelioration.",
		"weak": "Rentabilite/cash insuffisants pour un investisseur exigeant.",
	},
	"internal": {
		"strong": "Pilotage interne robuste.",
		"medium": "Pilotage correct avec points de vigilance.",
		"weak": "Action manageriale prioritaire recommandee.",
	},
	"composite": {
		"strong": "Le dossier peut servir simultanement a un usage interne, plateforme PME et decision de financement.",
		"medium": "La PME est exploitable mais necessite des garde-fous sur credit ou execution.",
		"weak": "Priorite a l'assainissement financier avant mise a l'echelle.",
	},
}


def get_config():
	doc = frappe.get_single("Scoring 360 Settings")

	cfg = {"coefficients": {"strong": doc.coeff_strong, "medium": doc.coeff_medium, "weak": doc.coeff_weak}}

	for block, criteria in CRITERIA_DIRECTIONS.items():
		thresholds = {}
		weights = {}
		for crit, direction in criteria.items():
			thresholds[crit] = {
				"strong": doc.get(f"{block}_{crit}_strong"),
				"medium": doc.get(f"{block}_{crit}_medium"),
				"direction": direction,
			}
			weights[crit] = doc.get(f"{block}_{crit}_weight")
		cfg[block] = {
			"thresholds": thresholds,
			"weights": weights,
			"decision": {
				"strong_min": doc.get(f"{block}_decision_strong_min"),
				"medium_min": doc.get(f"{block}_decision_medium_min"),
				"labels": DECISION_LABELS[block],
				"lectures": DECISION_LECTURES[block],
			},
		}

	cfg["composite"] = {
		"weights": {
			"bank": doc.composite_weight_bank,
			"investor": doc.composite_weight_investor,
			"internal": doc.composite_weight_internal,
		},
		"decision": {
			"strong_min": doc.composite_decision_strong_min,
			"medium_min": doc.composite_decision_medium_min,
			"labels": DECISION_LABELS["composite"],
			"lectures": DECISION_LECTURES["composite"],
		},
	}

	return cfg


def _evaluate_criterion(value, weight, strong, medium, direction, coeffs):
	if value is None:
		return {"value": None, "score": 0.0, "level": "missing"}

	is_strong = (value <= strong) if direction == "lte" else (value >= strong)
	is_medium = (value <= medium) if direction == "lte" else (value >= medium)

	if is_strong:
		level, coef = "strong", coeffs.get("strong", 1.0)
	elif is_medium:
		level, coef = "medium", coeffs.get("medium", 0.6)
	else:
		level, coef = "weak", coeffs.get("weak", 0.2)

	return {"value": round(value, 4), "score": round(weight * coef, 2), "level": level}


def _decision_from_score(score, decision):
	strong_min = decision.get("strong_min", 80.0)
	medium_min = decision.get("medium_min", 60.0)
	labels = decision.get("labels", {})
	lectures = decision.get("lectures", {})

	if score >= strong_min:
		level = "strong"
	elif score >= medium_min:
		level = "medium"
	else:
		level = "weak"

	return {"level": level, "label": labels.get(level, level.upper()), "lecture": lectures.get(level, "")}


def _score_block(block_key, ratios, cfg, coeffs):
	block = cfg.get(block_key, {})
	thresholds = block.get("thresholds", {})
	weights = block.get("weights", {})
	decision_cfg = block.get("decision", {})

	rows = {}
	total = 0.0
	for crit, weight in weights.items():
		t = thresholds.get(crit, {})
		direction = t.get("direction", "gte")
		strong = float(t.get("strong") or 0)
		medium = float(t.get("medium") or 0)
		value = ratios.get(crit)

		eva = _evaluate_criterion(value, float(weight or 0), strong, medium, direction, coeffs)
		rows[crit] = eva
		total += eva["score"]

	return {"total": round(total, 1), "decision": _decision_from_score(total, decision_cfg), "criteria": rows}


def _score_composite(bank, investor, internal, cfg):
	weights = cfg.get("composite", {}).get("weights", {})
	decision_cfg = cfg.get("composite", {}).get("decision", {})

	sb, si, sn = bank["total"], investor["total"], internal["total"]
	wb = float(weights.get("bank") or 0)
	wi = float(weights.get("investor") or 0)
	wn = float(weights.get("internal") or 0)

	cb = sb * wb / 100.0
	ci = si * wi / 100.0
	cn = sn * wn / 100.0
	total = cb + ci + cn

	return {
		"total": round(total, 1),
		"decision": _decision_from_score(total, decision_cfg),
		"contributions": {"bank": round(cb, 2), "investor": round(ci, 2), "internal": round(cn, 2)},
	}


def _metric_value(company, date_from, date_to, metric):
	ledger = _account_ledger(company, date_from, date_to)

	def sbp(prefixes, column="credit_net"):
		return _sum_by_prefixes(ledger, prefixes, column)

	revenue = sbp(["7"], "credit_net")
	expenses = sbp(["6"], "debit_net")
	net_result = revenue - expenses
	interest_expense = sbp(["66"], "debit_net")

	if metric == "revenue":
		return revenue
	if metric == "ebitda":
		return net_result + interest_expense
	return 0.0


def _growth_ratio(company, date_from, date_to, metric):
	if not date_from or not date_to:
		return None

	d_from = frappe.utils.getdate(date_from)
	d_to = frappe.utils.getdate(date_to)
	days = max(1, (d_to - d_from).days + 1)

	prev_from = frappe.utils.add_days(d_from, -days)
	prev_to = frappe.utils.add_days(d_to, -days)

	n = _metric_value(company, date_from, date_to, metric)
	n1 = _metric_value(company, prev_from, prev_to, metric)

	if n1 <= 0.0001:
		return None

	return (n / n1) - 1.0


def score_company(company, date_from=None, date_to=None):
	cfg = get_config()
	coeffs = cfg.get("coefficients", {"strong": 1.0, "medium": 0.6, "weak": 0.2})

	ledger = _account_ledger(company, date_from, date_to)

	def sbp(prefixes, column="credit_net"):
		return _sum_by_prefixes(ledger, prefixes, column)

	revenue = sbp(["7"], "credit_net")
	expenses = sbp(["6"], "debit_net")
	net_result = revenue - expenses

	interest_expense = sbp(["66"], "debit_net")
	caf = net_result
	ebit = net_result + interest_expense
	ebitda = ebit

	stocks = max(sbp(["311", "321", "322", "331", "335", "341", "351", "355"], "debit_net") - sbp(["391", "392"], "credit_net"), 0.0)
	receivables = max(sbp(["411", "413", "418"], "debit_net"), 0.0)
	cash = max(sbp(["512", "514", "515", "521", "531", "541", "542", "566", "581"], "debit_net"), 0.0)

	suppliers = sbp(["401", "403", "408"], "credit_net")
	tax_debts = sbp(["441", "442", "443", "444", "445", "447"], "credit_net")
	social_debts = sbp(["428", "431"], "credit_net")
	other_debts = sbp(["421", "451", "455", "467"], "credit_net")
	cash_liabilities = sbp(["512", "514", "515", "521", "531", "541", "542", "566", "581"], "credit_net")

	current_assets = stocks + receivables + cash
	current_liabilities = suppliers + tax_debts + social_debts + other_debts + cash_liabilities

	financial_debt = (
		sbp(["161", "162", "163"], "credit_net") + sbp(["164"], "credit_net") + sbp(["109", "165", "166"], "credit_net")
	)

	immobilisations = max(
		sbp(
			["201", "203", "205", "206", "207", "208", "211", "212", "213", "215", "221", "231", "241", "244", "261", "271", "275"],
			"debit_net",
		),
		0.0,
	)
	assets = immobilisations + stocks + receivables + cash

	equity = assets - (current_liabilities + financial_debt)
	roe = (net_result / equity) if equity > 0.01 else None

	dscr = (caf / interest_expense) if interest_expense > 0.0001 else None
	interest_coverage = (ebit / interest_expense) if interest_expense > 0.0001 else None
	current_ratio = (current_assets / current_liabilities) if current_liabilities > 0.0001 else None
	quick_ratio = ((receivables + cash) / current_liabilities) if current_liabilities > 0.0001 else None
	debt_asset = (financial_debt / assets) if assets > 0.0001 else None

	bfr = current_assets - current_liabilities
	bfr_days = (bfr * 365.0 / revenue) if revenue > 0.0001 else None

	ebitda_margin = (ebitda / revenue) if revenue > 0.0001 else None
	net_margin = (net_result / revenue) if revenue > 0.0001 else None
	asset_turnover = (revenue / assets) if assets > 0.0001 else None

	# GL-based proxy for PME360's Tresorerie module (see module docstring).
	treasury_net = cash - cash_liabilities
	fcf_margin = (treasury_net / revenue) if revenue > 0.0001 else None

	receivable_days = (receivables * 365.0 / revenue) if revenue > 0.0001 else None
	purchases = sbp(["60", "61"], "debit_net")
	inventory_days = (stocks * 365.0 / purchases) if purchases > 0.0001 else None

	revenue_growth = _growth_ratio(company, date_from, date_to, "revenue")
	ebitda_growth = _growth_ratio(company, date_from, date_to, "ebitda")

	ratios = {
		"dscr": dscr,
		"interest_coverage": interest_coverage,
		"current_ratio": current_ratio,
		"debt_asset": debt_asset,
		"bfr_days": bfr_days,
		"revenue_growth": revenue_growth,
		"ebitda_margin": ebitda_margin,
		"roe": roe,
		"fcf_margin": fcf_margin,
		"asset_turnover": asset_turnover,
		"net_margin": net_margin,
		"quick_ratio": quick_ratio,
		"receivable_days": receivable_days,
		"inventory_days": inventory_days,
		"ebitda_growth": ebitda_growth,
	}

	bank = _score_block("bank", ratios, cfg, coeffs)
	investor = _score_block("investor", ratios, cfg, coeffs)
	internal = _score_block("internal", ratios, cfg, coeffs)
	composite = _score_composite(bank, investor, internal, cfg)

	return {
		"period": {"from": date_from, "to": date_to},
		"ratios": ratios,
		"blocks": {"bank": bank, "investor": investor, "internal": internal},
		"composite": composite,
		"inputs": {
			"revenue": revenue,
			"net_result": net_result,
			"interest_expense": interest_expense,
			"financial_debt": financial_debt,
			"current_assets": current_assets,
			"current_liabilities": current_liabilities,
			"assets": assets,
			"treasury_net": treasury_net,
		},
	}


RANKING_CATEGORY_FROM_DECISION_LEVEL = {
	"strong": "pret_a_deployer",
	"medium": "solide_mais_a_cadrer",
	"weak": "risque_a_traiter",
}


def classement_erpnext(date_from=None, date_to=None):
	companies = frappe.get_all("Company", fields=["name", "company_name"], order_by="company_name")

	lignes = []
	for company in companies:
		entries_count = _entries_count(company.name, date_from, date_to)

		if entries_count == 0:
			lignes.append(
				{
					"company": company.name,
					"company_name": company.company_name,
					"entries_count": 0,
					"composite_score": None,
					"decision": {
						"level": "insuffisant",
						"label": "Donnees insuffisantes",
						"lecture": "Aucune ecriture comptable sur la periode.",
					},
					"blocks": None,
				}
			)
			continue

		result = score_company(company.name, date_from, date_to)
		composite = result["composite"]
		lignes.append(
			{
				"company": company.name,
				"company_name": company.company_name,
				"entries_count": entries_count,
				"composite_score": composite["total"],
				"decision": composite["decision"],
				"blocks": {
					"bank": result["blocks"]["bank"]["total"],
					"investor": result["blocks"]["investor"]["total"],
					"internal": result["blocks"]["internal"]["total"],
				},
			}
		)

	def sort_key(row):
		score = row["composite_score"]
		return -(score if score is not None else -1)

	lignes.sort(key=sort_key)

	compteurs = {"pret_a_deployer": 0, "solide_mais_a_cadrer": 0, "risque_a_traiter": 0, "insuffisant": 0}
	for row in lignes:
		level = row["decision"]["level"]
		category = RANKING_CATEGORY_FROM_DECISION_LEVEL.get(level, "insuffisant")
		compteurs[category] += 1

	return {"lignes": lignes, "compteurs": compteurs}
