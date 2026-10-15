# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""How a scanned invoice is booked: the draft's lines, accounts and VAT
rows, following SYSCOHADA and the Ivorian tax rules.

- amounts: HT (VAT base) + VAT + stamp + non-VAT fees = the invoice's own
  total, never the "montant a regler" that adds past unpaid invoices;
- lines: one per line read (a discount is netted into the lines it
  reduces), the stamp on 6462, the utility fees (electrification rurale,
  RTI, ordures menageres) on the energy's own account;
- VAT: purchases on 4452 (goods) / 4454 (services) / 4453 (transport) /
  4451 (fixed assets), split as the invoice details it; sales on 4431 /
  4432 / 4433. Not recovered -- added to the cost of the lines -- when the
  company is in TEE or RME, when a purchase dated from December 2025 does
  not carry the FNE marks, or for expenses excluded from the deduction
  right (meals, hotels, receptions, passenger cars).

Only drafts are built from this plan; the accountant validates them.
Every amount is a whole number of francs (XOF has no centimes)."""

import re
from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe import _
from frappe.utils import flt, getdate

from sitiame_core import ocr_accounts as oa

# FCFA: VAT lines rounded separately can shift a total by a franc or two
AMOUNT_TOLERANCE = 2
# Facture normalisee electronique mandatory (DGI) from this date: without
# it, the VAT is not deductible.
FNE_MANDATORY_FROM = "2025-12-01"
REGIMES = ("TEE", "RME", "RSI", "RNI")
# neither charge VAT on their sales nor recover the VAT on their purchases
NO_VAT_REGIMES = ("TEE", "RME")
# Cote d'Ivoire 18% / 9% (and the other UEMOA rates); 0 is a plain
# "no VAT" (insurance, a TEE/RME issuer), never flagged.
VAT_RATES = (0.05, 0.09, 0.10, 0.18, 0.19)
VAT_RATE_TOLERANCE = 0.002

_DISCOUNT = re.compile(r"\bremises?\b|\brabais\b|\bristournes?\b")

# Labels that clearly signal a physical good (merchandise, raw material):
# when matched on a purchase line that falls through all keyword rules, the
# fallback is 6011 (goods). Without this signal the safer fallback is 6327
# (general consultant/service provider) -- still tagged "defaut", always
# flagged for the accountant to verify.
_GOODS_LABEL_RE = re.compile(
	r"\bmarchandises?\b|\barticles?\b|\bpieces?\b|\bstocks?\b|\bcartons?\b"
	r"|\bsacs?\b|\bkg\b|\blitres?\b|\bbouteilles?\b|\bcaisses?\b|\blots?\b",
)

SOURCE_REASONS = {
	"memoire": "derniere facture validee de ce tiers",
	"mot-cle": "mot-cle du libelle",
	"reparation": "piece posee lors d'une reparation ou d'une maintenance",
	"immobilisation": "materiel ou mobilier au-dessus du seuil d'immobilisation, a confirmer",
	"petit-materiel": "materiel ou mobilier sous le seuil d'immobilisation",
	"nature": "nature de la ligne lue sur la facture, a verifier",
	"frais": "frais refactures au client",
	"timbre": "droit de timbre, hors TVA",
	"redevance": "taxe ou redevance hors TVA, sur le compte de la ligne principale",
	"tva-cout": "TVA non recuperable, ajoutee au cout",
	"defaut": "compte par defaut, a verifier",
}

VAT_NATURE_LABELS = {
	"goods": "biens",
	"service": "services",
	"transport": "transport",
	"fixed_asset": "immobilisations",
	"works": "travaux",
}


def franc(value):
	return int(Decimal(str(flt(value))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def allocate(total, weights):
	"""Splits a whole number of francs in proportion to weights; the parts
	always add up to the total (largest remainders get the odd francs)."""
	weights = [max(int(weight), 0) for weight in weights]
	base = sum(weights)
	if not weights:
		return []
	if base <= 0:
		return [total] + [0] * (len(weights) - 1)
	parts = [total * weight // base for weight in weights]
	order = sorted(range(len(weights)), key=lambda i: (total * weights[i]) % base, reverse=True)
	for i in order[: total - sum(parts)]:
		parts[i] += 1
	return parts


def is_vat_rate(tax, base):
	return bool(base) and any(abs(tax / base - rate) <= VAT_RATE_TOLERANCE for rate in VAT_RATES)


def regime_code(value):
	"""Company.sitiame_regime_fiscal -> TEE/RME/RSI/RNI, None when not set."""
	token = re.split(r"[\s\-:(]", (value or "").strip(), maxsplit=1)[0].upper()
	return token if token in REGIMES else None


# --- amounts -----------------------------------------------------------------


def resolve_amounts(fields):
	"""HT/TVA/TTC/stamp/fees from whatever was read; any two of HT/TVA/TTC
	give the third. The "montant total a regler" (invoice + past unpaid
	invoices) is brought back to the invoice's own total. gap = TTC not
	explained by HT + TVA + stamp + fees (explained later by the lines, or
	flagged)."""
	net = franc(fields.get("subtotal"))
	tax = franc(fields.get("tax_amount"))
	gross = franc(fields.get("grand_total"))
	stamp = franc(fields.get("stamp_duty"))
	charges = franc(fields.get("non_vat_charges"))
	previous = franc(fields.get("previous_balance"))
	extra = stamp + charges
	warnings = []

	if (
		previous
		and net
		and gross
		and abs(net + tax + extra - gross) > AMOUNT_TOLERANCE
		and abs(net + tax + extra + previous - gross) <= AMOUNT_TOLERANCE
	):
		gross -= previous
		warnings.append(
			_("TTC lu incluant {0} d'impayes anterieurs : total de la facture ramene a {1} (les impayes sont deja comptabilises).").format(
				previous, gross
			)
		)

	if not net and gross:
		net = gross - tax - extra
		if not tax:
			warnings.append(_("Seul le TTC a ete lu : facture enregistree sans TVA, a verifier."))

	if net and gross and gross - net - extra > AMOUNT_TOLERANCE and abs(net + tax + extra - gross) > AMOUNT_TOLERANCE:
		gap = gross - (net + tax + extra)
		if not (tax and gap > 0 and is_vat_rate(tax, net)):
			# HT and TTC both read but the VAT doesn't reconcile (missing, or a
			# misread such as the rate "18" taken for the amount): the paper's
			# own HT/TTC pair is the more reliable source. A VAT at a real
			# rate is kept: the rest may be fees outside the VAT base.
			if tax:
				warnings.append(
					_("TVA lue ({0}) incoherente avec HT {1} / TTC {2} : recalculee a {3}.").format(
						tax, net, gross, gross - net - extra
					)
				)
			tax = gross - net - extra

	if net <= 0:
		frappe.throw(_("Aucun montant n'a pu etre lu sur le document : creez la facture manuellement."))

	return frappe._dict(
		net=net,
		tax=tax,
		gross=gross,
		stamp=stamp,
		charges=charges,
		previous=previous,
		gap=(gross - (net + tax + extra)) if gross else 0,
		warnings=warnings,
	)


def gap_warning(amounts):
	if abs(amounts.gap) <= AMOUNT_TOLERANCE:
		return None
	return _("Ecart sur les montants lus : HT {0} + TVA {1}{2} != TTC {3} (ecart {4}). Verifiez avant de soumettre.").format(
		amounts.net,
		amounts.tax,
		_(" + timbre et taxes {0}").format(amounts.stamp + amounts.charges) if amounts.stamp + amounts.charges else "",
		amounts.gross,
		amounts.gap,
	)


# --- lines -------------------------------------------------------------------


def _line_kind(label, line_type):
	if oa.is_stamp(label):
		return "stamp"
	if oa.is_fee(label) or line_type == "fee":
		return "fee"
	return "taxable"


def _read_rows(line_items):
	"""Lines read, or None when the table is unusable (a line without
	label or price)."""
	rows = []
	for item in line_items:
		label = (item.get("item_name") or "").strip()
		rate = flt(item.get("rate"))
		qty = flt(item.get("qty")) or 1
		if not label or not rate:
			return None
		amount = franc(Decimal(str(qty)) * Decimal(str(rate)))
		line_type = item.get("line_type")
		discount = amount < 0 or line_type == "discount" or bool(_DISCOUNT.search(oa._fold(label)))
		if discount:
			rows.append({"item_name": label, "amount": -abs(amount), "discount": True})
			continue
		if amount <= 0:
			return None
		rows.append(
			{
				"item_name": label,
				"qty": qty,
				"rate": rate,
				"amount": amount,
				"line_type": line_type,
				"kind": _line_kind(label, line_type),
			}
		)
	return rows


def _net_discounts(rows):
	"""A discount reduces the lines above it (commercial discount: no
	account of its own, the lines are booked net). Several lines reduced
	together become one net line: no rounding is invented between them."""
	out, pending = [], []
	for row in rows:
		if not row.get("discount"):
			out.append(row)
			if row["kind"] == "taxable":
				pending.append(row)
			continue
		base = sum(line["amount"] for line in pending)
		net = base + row["amount"]
		if not pending or net <= 0:
			return None
		largest = max(pending, key=lambda line: line["amount"])
		merged = {
			"item_name": _("{0} (net de remise)").format(", ".join(line["item_name"] for line in pending)),
			"qty": 1,
			"rate": net,
			"amount": net,
			"line_type": largest.get("line_type"),
			"kind": "taxable",
			"discount_note": _("{0} - remise {1} = {2}").format(base, -row["amount"], net),
		}
		position = out.index(pending[0])
		out = [line for line in out if not any(line is p for p in pending)]
		out.insert(position, merged)
		pending = [merged]
	return out


def _synthetic_lines(amounts):
	lines = []
	if amounts.stamp:
		lines.append({"item_name": _("Timbre fiscal"), "qty": 1, "rate": amounts.stamp, "amount": amounts.stamp, "kind": "stamp"})
	if amounts.charges:
		lines.append(
			{
				"item_name": _("Taxes et redevances hors TVA"),
				"qty": 1,
				"rate": amounts.charges,
				"amount": amounts.charges,
				"kind": "fee",
			}
		)
	return lines


def build_lines(line_items, amounts, reference, party):
	"""-> (lines, warnings). One line per line read when they add up to the
	HT (stamp and fees apart); otherwise a single HT line -- never lines
	that contradict the invoice's own total. amounts is updated when the
	lines explain the stamp/fees (or show the HT read included them)."""
	warnings = []
	rows = _read_rows(line_items) if line_items else None
	if rows is not None:
		rows = _net_discounts(rows)

	if rows:
		taxable = [row for row in rows if row["kind"] == "taxable"]
		special = [row for row in rows if row["kind"] != "taxable"]
		taxable_sum = sum(row["amount"] for row in taxable)
		special_sum = sum(row["amount"] for row in special)
		tolerance = AMOUNT_TOLERANCE * max(1, len(rows))
		extra = amounts.stamp + amounts.charges

		if taxable and abs(taxable_sum - amounts.net) <= tolerance:
			if special and (not extra or abs(special_sum - extra) <= tolerance):
				_take_special_amounts(amounts, special)
				return _finish(rows), warnings
			if special:
				warnings.append(
					_("Timbre et taxes lus en lignes ({0}) differents des montants lus ({1}) : montants lus retenus.").format(
						special_sum, extra
					)
				)
			return _finish(taxable + _synthetic_lines(amounts)), warnings

		if taxable and special and not extra and abs(taxable_sum + special_sum - amounts.net) <= tolerance:
			# the HT read included the stamp and fees: the VAT base is the rest
			amounts.net = taxable_sum
			_take_special_amounts(amounts, special)
			return _finish(rows), warnings

	if line_items:
		read_total = sum(franc((flt(item.get("qty")) or 1) * flt(item.get("rate"))) for item in line_items)
		warnings.append(
			_("Lignes lues ({0}) incoherentes avec le HT ({1}) : une seule ligne au HT a ete creee.").format(
				read_total, amounts.net
			)
		)
	single = {
		"item_name": _("Facture {0} - {1}").format(reference, party),
		"qty": 1,
		"rate": amounts.net,
		"amount": amounts.net,
		"kind": "taxable",
		"description": _("Montant HT importe depuis la facture scannee -- verifiez le compte de charge/produit."),
	}
	return _finish([single] + _synthetic_lines(amounts)), warnings


def _take_special_amounts(amounts, special):
	amounts.stamp = sum(row["amount"] for row in special if row["kind"] == "stamp")
	amounts.charges = sum(row["amount"] for row in special if row["kind"] == "fee")
	if amounts.gross:
		amounts.gap = amounts.gross - (amounts.net + amounts.tax + amounts.stamp + amounts.charges)


def _finish(rows):
	lines = []
	for row in rows:
		line = dict(row)
		line.setdefault("qty", 1)
		line.setdefault("rate", line["amount"])
		if not line.get("description"):
			line["description"] = _("Ligne lue sur la facture scannee -- verifiez le compte.") + (
				" " + line["discount_note"] if line.get("discount_note") else ""
			)
		lines.append(line)
	return lines


# --- accounts ----------------------------------------------------------------


def choose_line_accounts(is_purchase, company, lines, default_account, remembered):
	"""Sets account / account_number / source / reason on every line: the
	stamp on 6462 and the utility fees on the main line's account first
	(they never follow the party's memory), then keyword -> equipment ->
	memory -> repair context -> nature read -> company default. A line the
	keywords recognise keeps its account: the party's memory (the account of
	the first line of its last invoice) only fills the others -- a mixed
	invoice otherwise went entirely to one account (2026-10-15)."""
	repair = is_purchase and any(oa.is_repair(line["item_name"]) for line in lines)
	threshold = oa.asset_threshold(company) if is_purchase else None
	for line in lines:
		if line["kind"] != "taxable":
			continue
		label = line["item_name"]
		account, source = None, None
		if not is_purchase and oa.keyword_account_number(label, False) == "7071":
			account, source = oa.leaf_by_number(company, "7071"), "frais"
		if not account:
			account, source = oa.keyword_account(company, label, is_purchase), "mot-cle"
		if not account and is_purchase:
			number = oa.equipment_account_number(label)
			if number:
				unit_price = flt(line["amount"]) / (flt(line.get("qty")) or 1)
				if unit_price >= threshold:
					account, source = oa.leaf_by_number(company, number), "immobilisation"
				else:
					account, source = oa.leaf_by_number(company, oa.SMALL_EQUIPMENT_ACCOUNT), "petit-materiel"
		if not account and remembered:
			account, source = remembered, "memoire"
		if not account and repair:
			account, source = oa.leaf_by_number(company, "6242"), "reparation"
		if not account and line.get("line_type") in ("goods", "service"):
			number = {
				(True, "service"): "6327",
				(False, "service"): "7061",
				(False, "goods"): "7011",
			}.get((is_purchase, line["line_type"]))
			account, source = oa.leaf_by_number(company, number), "nature"
		if not account and is_purchase:
			# Last heuristic before the company default: a purchase label
			# with no recognised keyword and no goods signal is more likely a
			# service than merchandise. 6327 (other service providers) is
			# safer than the default 6011 (goods) for that case. The line is
			# still flagged "defaut" so the accountant reviews it.
			if not _GOODS_LABEL_RE.search(oa._fold(label)):
				account = oa.leaf_by_number(company, "6327")
				if account:
					source = "defaut"
		if not account:
			account, source = default_account, "defaut"
		_set_account(line, account, source)

	taxable = [line for line in lines if line["kind"] == "taxable"]
	main = max(taxable, key=lambda line: line["amount"]) if taxable else None
	main_account = main["account"] if main else default_account
	for line in lines:
		if line["kind"] == "stamp" and is_purchase:
			account = oa.leaf_by_number(company, "6462")
			_set_account(line, account or main_account, "timbre" if account else "defaut")
		elif line["kind"] != "taxable":
			_set_account(line, main_account, "redevance" if main else "defaut")
	return lines


def _set_account(line, account, source):
	line["account"] = account
	line["account_number"] = oa.account_number_of(account)
	line["source"] = source
	line["reason"] = SOURCE_REASONS[source]


# --- VAT ---------------------------------------------------------------------


def _vat_account(company, numbers, template_account, warnings, nature):
	for number in numbers:
		account = oa.leaf_by_number(company, number)
		if account:
			return account
	if template_account:
		warnings.append(
			_("Compte de TVA {0} ({1}) absent du plan comptable : TVA passee sur {2}, a verifier.").format(
				numbers[0], VAT_NATURE_LABELS[nature], template_account
			)
		)
	else:
		warnings.append(
			_("Aucun compte de TVA {0} ({1}) ni modele de TVA par defaut pour {2} : ajoutez la ligne de TVA a la main.").format(
				numbers[0], VAT_NATURE_LABELS[nature], company
			)
		)
	return template_account


def _cost_lines(lines, tax, label):
	"""Non-recoverable VAT added to the cost: one line per expense account,
	in proportion to the lines on it."""
	if tax <= 0 or not lines:
		return []
	by_account = {}
	for line in lines:
		by_account.setdefault(line["account"], []).append(line)
	accounts = list(by_account)
	parts = allocate(tax, [sum(line["amount"] for line in by_account[account]) for account in accounts])
	cost = []
	for account, amount in zip(accounts, parts):
		if amount <= 0:
			continue
		first = by_account[account][0]
		cost.append(
			{
				"item_name": label,
				"qty": 1,
				"rate": amount,
				"amount": amount,
				"kind": "vat_cost",
				"account": account,
				"account_number": first.get("account_number"),
				"source": "tva-cout",
				"reason": SOURCE_REASONS["tva-cout"],
				"description": label,
			}
		)
	return cost


def _bases_by_nature(is_purchase, lines):
	bases = {}
	for line in lines:
		nature = oa.vat_nature(is_purchase, line.get("account_number"))
		bases[nature] = bases.get(nature, 0) + line["amount"]
	return bases


def _dominant(bases):
	return max(bases, key=lambda nature: bases[nature])


def plan_vat(is_purchase, company, lines, amounts, fields, regime, fne_required, fne_present, template_account):
	"""-> (taxes, cost_lines, warnings, summary)."""
	tax = amounts.tax
	taxes, cost, warnings = [], [], []
	taxable = [line for line in lines if line["kind"] == "taxable"]
	summary = {"vat_recovered": None, "vat": _("aucune TVA sur la facture")}
	if tax <= 0 or not taxable:
		return taxes, cost, warnings, summary

	base = sum(line["amount"] for line in taxable)
	if not is_vat_rate(tax, base):
		warnings.append(
			_("TVA {0} = {1}% de la base taxable ({2}) : ni 18 % ni 9 %, verifiez les montants.").format(
				tax, round(tax / base * 100, 2), base
			)
		)

	if not regime:
		warnings.append(
			_("Regime fiscal de la societe non renseigne (fiche Societe, champ « Regime fiscal ») : TVA traitee comme {0}, a confirmer.").format(
				_("recuperable") if is_purchase else _("collectee")
			)
		)

	if not is_purchase:
		if regime in NO_VAT_REGIMES:
			warnings.append(
				_("Votre societe est en {0} : elle ne doit pas facturer la TVA. Cette facture en porte ({1}) : la TVA facturee reste due au Tresor, voyez avec le comptable (avoir et refacturation sans TVA).").format(
					regime, tax
				)
			)
		bases = _bases_by_nature(False, taxable)
		nature = _dominant(bases)
		if len([n for n in bases if bases[n]]) > 1:
			warnings.append(
				_("Lignes de natures differentes ({0}) et un seul montant de TVA : TVA passee en TVA facturee sur {1} (nature dominante), a ventiler si besoin.").format(
					", ".join(VAT_NATURE_LABELS[n] for n in bases), VAT_NATURE_LABELS[nature]
				)
			)
		account = _vat_account(company, oa.SALES_VAT_ACCOUNTS[nature], template_account, warnings, nature)
		_add_tax(taxes, account, tax, nature, base)
		summary.update(vat_recovered=None, vat=_("TVA facturee {0} sur {1}").format(tax, account or "-"))
		return taxes, cost, warnings, summary

	not_recovered = None
	if regime in NO_VAT_REGIMES:
		not_recovered = _("regime {0} : TVA non recuperable").format(regime)
	elif fne_required and fne_present is not True:
		not_recovered = _("facture sans FNE : TVA non deductible")
	if not_recovered:
		cost = _cost_lines(taxable, tax, _("TVA non recuperable ({0})").format(not_recovered))
		warnings.append(
			_("TVA de {0} non recuperable ({1}) : ajoutee au cout des charges, aucune ligne de TVA deductible.").format(
				tax, not_recovered
			)
		)
		summary.update(vat_recovered=False, vat=_("non recuperee ({0}), {1} ajoutes au cout").format(not_recovered, tax))
		return taxes, cost, warnings, summary

	excluded = [line for line in taxable if oa.is_vat_excluded(line["item_name"], line.get("account_number"))]
	deductible = [line for line in taxable if not any(line is e for e in excluded)]
	excluded_base = sum(line["amount"] for line in excluded)
	excluded_tax = allocate(tax, [excluded_base, base - excluded_base])[0] if excluded else 0
	if excluded_tax:
		label = _("TVA non deductible (restaurant, hotel, reception, representation ou vehicule de tourisme)")
		cost = _cost_lines(excluded, excluded_tax, label)
		warnings.append(
			_("{0} de TVA sur des depenses exclues du droit a deduction ({1}) : ajoutee au cout.").format(
				excluded_tax, ", ".join(line["item_name"] for line in excluded)
			)
		)
	recoverable = tax - excluded_tax

	if recoverable > 0:
		goods_vat = franc(fields.get("vat_goods_amount"))
		services_vat = franc(fields.get("vat_services_amount"))
		if (goods_vat or services_vat) and abs(goods_vat + services_vat - tax) <= AMOUNT_TOLERANCE:
			# the invoice details its VAT by nature (supplies / labour)
			buckets = dict(zip(("goods", "service"), allocate(recoverable, [goods_vat, services_vat])))
		else:
			bases = _bases_by_nature(True, deductible)
			nature = _dominant(bases)
			if len([n for n in bases if bases[n]]) > 1:
				warnings.append(
					_("Lignes de natures differentes ({0}) et un seul montant de TVA : TVA passee en TVA recuperable sur {1} (nature dominante), a ventiler si besoin.").format(
						", ".join(VAT_NATURE_LABELS[n] for n in bases), VAT_NATURE_LABELS[nature]
					)
				)
			buckets = {nature: recoverable}
		for nature, amount in buckets.items():
			if amount <= 0:
				continue
			account = _vat_account(company, oa.PURCHASE_VAT_ACCOUNTS[nature], template_account, warnings, nature)
			_add_tax(taxes, account, amount, nature, base)

	recovered = sum(row["amount"] for row in taxes)
	summary.update(
		vat_recovered=bool(recovered),
		vat=_("recuperee : {0}").format(", ".join(f"{row['amount']} en {row['account']}" for row in taxes))
		+ (_(" ; {0} non deductibles ajoutes au cout").format(excluded_tax) if excluded_tax else ""),
	)
	return taxes, cost, warnings, summary


def _add_tax(taxes, account, amount, nature, base):
	if not account:
		return
	for row in taxes:
		if row["account"] == account:
			row["amount"] += amount
			return
	taxes.append(
		{
			"account": account,
			"account_number": oa.account_number_of(account),
			"amount": amount,
			"nature": nature,
			"description": _("TVA {0} ({1}% de la base taxable)").format(
				VAT_NATURE_LABELS[nature], round(amount / base * 100, 2) if base else "?"
			),
		}
	)


# --- the whole plan ----------------------------------------------------------


def fne_status(is_purchase, posting_date, fne):
	"""-> (required, present, label)."""
	fne = fne or {}
	present = fne.get("present")
	required = is_purchase and getdate(posting_date) >= getdate(FNE_MANDATORY_FROM)
	if not is_purchase:
		return False, present, _("non controlee (facture de vente)")
	if not required:
		return False, present, _("non exigee (facture anterieure au 01/12/2025)")
	if present is True:
		return True, True, _("presente") + (f" ({fne['number']})" if fne.get("number") else "")
	return True, present, _("absente") if present is False else _("non detectee")


def build_plan(
	is_purchase,
	company,
	data,
	party,
	reference,
	default_account,
	remembered,
	regime_value,
	posting_date,
	template_account=None,
):
	"""data: the reading (fields, line_items, fne). -> dict(amounts, lines,
	taxes, warnings, notes, summary). Raises when no amount was read."""
	fields = data.get("fields") or {}
	amounts = resolve_amounts(fields)
	warnings = list(amounts.warnings)
	notes = []

	lines, line_warnings = build_lines(data.get("line_items") or [], amounts, reference, party)
	warnings += line_warnings
	gap = gap_warning(amounts)
	if gap:
		warnings.append(gap)

	choose_line_accounts(is_purchase, company, lines, default_account, remembered)
	# the accounts really used: lines without a keyword nor a goods signal
	# go to 6327, not to the company default (the message named 6011 for
	# lines booked on 6327, 2026-10-15)
	assets = [line for line in lines if line["source"] == "immobilisation"]
	if assets:
		warnings.append(
			_("Immobilisation probable ({0}) : prix unitaire au-dessus du seuil de {1} FCFA (fiche Societe). Confirmez le compte, puis creez la fiche d'immobilisation pour l'amortissement.").format(
				", ".join(line["item_name"] for line in assets), f"{int(oa.asset_threshold(company)):,}".replace(",", " ")
			)
		)
	fallback_accounts = sorted({line["account"] for line in lines if line["source"] == "defaut" and line.get("account")})
	if fallback_accounts:
		warnings.append(
			_("Compte par defaut ({0}) utilise faute d'historique ou de mot-cle reconnu : verifiez-le avant de soumettre.").format(
				", ".join(fallback_accounts)
			)
		)

	regime = regime_code(regime_value)
	fne_required, fne_present, fne_label = fne_status(is_purchase, posting_date, data.get("fne"))
	if fne_required and fne_present is not True:
		warnings.append(
			_("Facture d'achat du {0} sans marque de FNE (QR code ou sticker electronique de la DGI, numero FNE) : depuis decembre 2025, seule une FNE justifie la charge et ouvre droit a deduction de la TVA. {1}Si la facture est bien une FNE, cochez « FNE verifiee » a l'import.").format(
				posting_date,
				_("TVA non passee en 445x (ajoutee au cout). ") if amounts.tax > 0 else "",
			)
		)

	taxes, cost, vat_warnings, summary = plan_vat(
		is_purchase, company, lines, amounts, fields, regime, fne_required, fne_present, template_account
	)
	warnings += vat_warnings
	lines += cost

	if is_purchase and any(
		line["kind"] == "taxable" and oa.needs_withholding(line["item_name"], line.get("account_number")) for line in lines
	):
		notes.append(
			_("Si {0} est un consultant ou expert personne physique ou une profession liberale : retenue a la source a operer au paiement : 7,5 % (2 % si le prestataire est en RME ou entreprenant), a reverser avant le 15 du mois suivant. Aucune ecriture de retenue n'est creee automatiquement.").format(
				party
			)
		)

	summary.update(
		regime=regime or _("non renseigne"),
		fne=fne_label,
		previous_balance=amounts.previous,
	)
	return {
		"amounts": amounts,
		"lines": lines,
		"taxes": taxes,
		"warnings": warnings,
		"notes": notes,
		"summary": summary,
	}
