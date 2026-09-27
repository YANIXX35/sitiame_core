# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Which account an OCR-read invoice line is booked on, and which account
a Mobile Money receipt lands on.

An invoice line gets, in order: the account the accountant already
validated on this party's last submitted invoice (in this company); for a
purchase, the SYSCOHADA account its wording points to (loyer -> 6222,
electricite -> 6052...); otherwise the company's default account, flagged
for review. Nothing is submitted here: the accountant still checks every
proposal on the draft before booking it.
"""

import re
import unicodedata

import frappe

# (pattern on the lower-cased, accent-free line label, SYSCOHADA account
# number). First match wins, so the more specific wordings come first
# ("produits d'entretien" before "entretien", "honoraires" before
# "prestation", "site internet" before "internet").
PURCHASE_KEYWORD_ACCOUNTS = [
	(r"honoraires?|\bavocats?\b|\bnotaires?\b|expert[- ]?comptable|commissaires? aux comptes|\bhuissiers?\b", "6324"),
	(r"\bloyers?\b|\blocation (?:de |du |des |d un )?(?:bureaux?|local|locaux|batiments?|magasins?|entrepots?)\b", "6222"),
	(r"electricite|\bcie\b", "6052"),
	(r"\beau\b|\bsodeci\b", "6051"),
	(r"carburant|gasoil|gas-oil|gazole|\bessence\b|super sans plomb", "6042"),
	(r"telephon|forfait mobile|credit de communication", "6281"),
	(r"hebergement|nom de domaine|site (?:web|internet)", "6345"),
	(r"internet|\bfibre\b|\bwifi\b|\badsl\b", "6288"),
	(r"logiciels?|licences?|\bsaas\b", "6343"),
	(r"maintenance", "6243"),
	(r"produits? d.?entretien|nettoyage|detergents?", "6043"),
	(r"entretien|reparations?", "6242"),
	(r"fournitures? de bureau|papeterie|\brames?\b|cartouches?|\btoners?\b", "6047"),
	(r"assurances?", "6258"),
	(r"billets? d.?avion|\bhotels?\b|voyages?|deplacements?|\bmissions?\b", "6181"),
	(r"publicite|annonces?|affichage|spots? (?:radio|tv|television)", "6271"),
	(r"\bformations?\b", "633"),
	(r"frais bancaires|commissions? bancaires?|\bagios?\b|tenue de compte", "6318"),
	(r"conseil|consultant|consulting|prestations?", "6327"),
]
_KEYWORD_PATTERNS = [(re.compile(pattern), number) for pattern, number in PURCHASE_KEYWORD_ACCOUNTS]


def _fold(text):
	text = unicodedata.normalize("NFKD", text or "")
	text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
	return re.sub(r"[’']", " ", text)


def keyword_account_number(label):
	folded = _fold(label)
	for pattern, number in _KEYWORD_PATTERNS:
		if pattern.search(folded):
			return number
	return None


def _active_leaf(company, **filters):
	return frappe.db.get_value("Account", {"company": company, "is_group": 0, "disabled": 0, **filters}, "name")


def keyword_account(company, label):
	number = keyword_account_number(label)
	return _active_leaf(company, account_number=number) if number else None


def remembered_account(is_purchase, party, company):
	"""Account of the first line of this party's last submitted invoice in
	this company: the accountant already validated it for this party."""
	doctype = "Purchase Invoice" if is_purchase else "Sales Invoice"
	last = frappe.get_all(
		doctype,
		filters={("supplier" if is_purchase else "customer"): party, "company": company, "docstatus": 1},
		pluck="name",
		order_by="posting_date desc, creation desc",
		limit=1,
	)
	if not last:
		return None
	account = frappe.db.get_value(
		f"{doctype} Item",
		{"parent": last[0], "parenttype": doctype},
		"expense_account" if is_purchase else "income_account",
		order_by="idx asc",
	)
	return _active_leaf(company, name=account) if account else None


def choose_account(is_purchase, company, label, default_account, remembered):
	"""-> (account, source), source being "memoire", "mot-cle" or "defaut"."""
	if remembered:
		return remembered, "memoire"
	if is_purchase:
		account = keyword_account(company, label)
		if account:
			return account, "mot-cle"
	return default_account, "defaut"


def mobile_money_account(company, mode_of_payment):
	"""The brand's own 552x sub-account when the company has one (SITIAME:
	5521 - Wave...), else the generic 552 "Monnaie electronique telephone
	portable" leaf of the SYSCOHADA chart."""
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "account_number": ["like", "552%"], "is_group": 0, "disabled": 0},
		fields=["name", "account_name", "account_number"],
		order_by="account_number",
	)
	mode = _fold(mode_of_payment)
	for account in accounts:
		name = _fold(account.account_name)
		if account.account_number != "552" and name and (name in mode or mode in name):
			return account.name
	generic = [account.name for account in accounts if account.account_number == "552"]
	return generic[0] if generic else None


def ensure_mobile_money_modes(company):
	"""Links every Phone-type Mode of Payment (Wave, Orange Money...) to the
	company's Mobile Money account, typed Bank like any account a Payment
	Entry pays through (as SITIAME's 5521-5524 already are)."""
	for mode in frappe.get_all("Mode of Payment", filters={"type": "Phone"}, pluck="name"):
		doc = frappe.get_doc("Mode of Payment", mode)
		if any(row.company == company for row in doc.accounts):
			continue
		account = mobile_money_account(company, mode)
		if not account:
			continue
		if not frappe.db.get_value("Account", account, "account_type"):
			frappe.db.set_value("Account", account, "account_type", "Bank")
		doc.append("accounts", {"company": company, "default_account": account})
		doc.save(ignore_permissions=True)
