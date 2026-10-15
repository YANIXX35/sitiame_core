# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Which account an OCR-read invoice line is booked on, and which account
a Mobile Money receipt lands on.

An invoice line gets, in order: the account the accountant already
validated on this party's last submitted invoice (in this company); the
SYSCOHADA account its wording points to (purchases: loyer -> 6222,
electricite -> 6052...; sales: travaux -> 7051, prestation -> 7061...);
otherwise the company's default account, flagged for review. Stamps,
utility fees and the VAT rules on top of this live in ocr_plan.py. Nothing is submitted here: the accountant still checks every
proposal on the draft before booking it.
"""

import re
import unicodedata

import frappe

# (pattern on the lower-cased, accent-free line label, SYSCOHADA account
# number). First match wins, so the more specific wordings come first
# ("produits d'entretien" before "entretien", "honoraires" before
# "prestation", "site internet" before "internet", "assurance vehicule"
# before "assurance"). Mirrors step 3 of the comptabilisation-syscohada
# reference.
PURCHASE_KEYWORD_ACCOUNTS = [
	(r"\btimbres?\b|droits? de timbre", "6462"),
	(r"honoraires?|\bavocats?\b|\bnotaires?\b|expert[- ]?comptable|commissaires? aux comptes|\bhuissiers?\b", "6324"),
	(r"frais d.?actes?|contentieux|\bgreffe\b", "6325"),
	(r"\bloyers?\b|\blocation (?:de |du |des |d un )?(?:bureaux?|local|locaux|batiments?|magasins?|entrepots?)\b", "6222"),
	(
		r"\blocation (?:de |du |des |d un |d une )?(?:vehicules?|voitures?|materiels?|engins?|camions?|groupes? electrogenes?|outillages?)\b",
		"6223",
	),
	(r"electricite|\bcie\b|\benergie\b|prime fixe|\bkwh\b", "6052"),
	(r"\beau\b|\bsodeci\b", "6051"),
	(r"carburant|gasoil|gas-oil|gazole|\bessence\b|super sans plomb|\bgaz\b|butane", "6042"),
	(r"frais (?:wave|orange money|mtn|moov)|orange money|mobile money|\bmomo\b|moov money|frais de transfert", "6317"),
	(r"telephon|forfait mobile|credit de communication", "6281"),
	(r"hebergement (?:web|du site|de site|site|serveur|cloud|internet)|nom de domaine|site (?:web|internet)", "6345"),
	(r"internet|\bfibre\b|\bwifi\b|\badsl\b", "6288"),
	(r"logiciels?|licences?|\bsaas\b", "6343"),
	(r"maintenance", "6243"),
	(r"produits? d.?entretien|nettoyage|detergents?", "6043"),
	(
		r"main.?d.?oeuvre|entretien|reparations?|vidange|pneumatiques?|\bpneus?\b|carrosserie|depannage|\bgarage\b",
		"6242",
	),
	# "ramettes" and "classeurs" fell through to 6327 (2026-10-15 test import)
	(
		r"fournitures? de bureau|papeterie|\bram(?:e|ette)s?\b|\bpapiers?\b|cartouches?|\btoners?\b|\bencres?\b"
		r"|classeurs?|enveloppes?|\bstylos?\b|agrafe|trombones?|chemises? cartonnees?|sous.?chemises?|cahiers?"
		r"|\bblocs? notes?\b|post.?it|surligneurs?|intercalaires?",
		"6047",
	),
	(r"petit materiel|outillage", "6056"),
	(r"assurances? (?:auto|automobile|vehicules?|flotte|moto)", "6252"),
	(r"assurances?", "6258"),
	(r"restaurants?|\brepas\b|dejeuners?|\bdiners?\b|\breceptions?\b|traiteur|cocktail", "6383"),
	(r"billets? d.?avion|\bhotels?\b|hebergement|nuitees?|voyages?|deplacements?|\bmissions?\b", "6181"),
	(r"publicite|annonces?|affichage|spots? (?:radio|tv|television)|insertions?", "6271"),
	(r"cadeaux?", "6276"),
	(r"seminaires?|colloques?|conferences?", "6277"),
	(r"\bformations?\b", "633"),
	(r"frais bancaires|commissions? bancaires?|\bagios?\b|tenue de compte", "6318"),
	(r"commissions? sur ventes?|apporteurs? d.?affaires|courtages?", "6322"),
	(r"interim", "6371"),
	(r"patentes?", "6412"),
	(r"vignettes?", "6464"),
	(r"sous.?traitance", "621"),
	(r"\bfret\b|\btransit\b|frais de port|dedouanement|frais d.?approche", "6015"),
	(r"transport du personnel", "614"),
	(r"cotisations?", "6351"),
	(r"documentation|abonnements? (?:presse|journal|journaux|revues?)", "6265"),
	(r"conseil|consultant|consulting|prestations?|expertise|\baudit\b|\betudes?\b|gardiennage", "6327"),
]
_KEYWORD_PATTERNS = [(re.compile(pattern), number) for pattern, number in PURCHASE_KEYWORD_ACCOUNTS]

# Sales: travaux 7051, services 7061, marchandises 7011, frais refactures
# 7071. Port/frais first: "frais de transport" is not a transport service.
SALES_KEYWORD_ACCOUNTS = [
	(r"frais (?:de )?(?:port|livraison|transport|expedition|dossier|deplacement)|\bport\b|emballages?|refactur", "7071"),
	(r"\btravaux\b|chantier|construction|genie civil|maconnerie|terrassement|plomberie|\bpose\b", "7051"),
	(
		r"prestations?|services?|conseil|consulting|formations?|maintenance|honoraires?|assistance|accompagnement"
		r"|\betudes?\b|\baudit\b|gestion|abonnements?|\bmissions?\b|location|reparations?|entretien|main.?d.?oeuvre"
		r"|developpement|transport|installation",
		"7061",
	),
	(r"marchandises?|articles?|produits?|cartons?|\bsacs?\b|\bkg\b|litres?|bouteilles?|caisses?|\blots?\b|pieces?", "7011"),
]
_SALES_PATTERNS = [(re.compile(pattern), number) for pattern, number in SALES_KEYWORD_ACCOUNTS]

# Lines printed next to the VAT but outside its base.
STAMP_PATTERN = re.compile(r"\btimbres?\b|droits? de timbre")
# taxes and fees on utility bills (CIE, SODECI): booked with the energy itself
FEE_PATTERN = re.compile(
	r"redevances? (?:d.?)?(?:electrification|rti|radio|television|audiovisuelle|ordures|enlevement|assainissement|eclairage|communale)"
	r"|electrification rurale|ordures menageres|taxe d.?enlevement|\brti\b|surtaxe|taxe communale|fonds national de l.?eau"
)
# Excluded from the VAT deduction right in Cote d'Ivoire: lodging, meals,
# receptions, entertainment, passenger cars.
VAT_EXCLUDED_PATTERN = re.compile(
	r"restaurants?|\brepas\b|dejeuners?|\bdiners?\b|\breceptions?\b|traiteur|cocktail|\bhotels?\b|nuitees?"
	r"|hebergement(?! (?:web|du site|de site|site|serveur|cloud|internet))|representation"
	r"|vehicules? de tourisme|voitures? particulieres?|vehicules? particuliers?"
)
VAT_EXCLUDED_ACCOUNTS = ("6383",)
# A repair job: the parts fitted go with the labour (6242), not into goods
# bought for resale.
REPAIR_PATTERN = re.compile(r"main.?d.?oeuvre|reparations?|ordre de reparation|vidange|carrosserie|depannage")
# Consultants and liberal professions: withholding tax when they are paid.
WITHHOLDING_PATTERN = re.compile(
	r"honoraires?|consultant|consulting|conseil|expert|\bavocats?\b|\bnotaires?\b|\bhuissiers?\b|\bmedecins?\b"
)
WITHHOLDING_ACCOUNTS = ("6324", "6327")


def _fold(text):
	# NFKD leaves the ligatures: "main-d'œuvre" must fold to "main d oeuvre"
	text = (text or "").replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae").replace("Æ", "AE")
	text = unicodedata.normalize("NFKD", text)
	text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
	return re.sub(r"[’']", " ", text)


def keyword_account_number(label, is_purchase=True):
	folded = _fold(label)
	for pattern, number in _KEYWORD_PATTERNS if is_purchase else _SALES_PATTERNS:
		if pattern.search(folded):
			return number
	return None


def is_stamp(label):
	return bool(STAMP_PATTERN.search(_fold(label)))


def is_fee(label):
	return bool(FEE_PATTERN.search(_fold(label)))


def is_vat_excluded(label, account_number=None):
	return account_number in VAT_EXCLUDED_ACCOUNTS or bool(VAT_EXCLUDED_PATTERN.search(_fold(label)))


def is_repair(label):
	return bool(REPAIR_PATTERN.search(_fold(label)))


def needs_withholding(label, account_number=None):
	return account_number in WITHHOLDING_ACCOUNTS or bool(WITHHOLDING_PATTERN.search(_fold(label)))


def vat_nature(is_purchase, account_number):
	"""What the VAT on a line bought/sold on this account is: purchases ->
	goods (60x), transport (61x), service (62x-63x...), fixed_asset (2x);
	sales -> goods (701-704), works (705), service (706-707...)."""
	number = str(account_number or "")
	if is_purchase:
		if number.startswith("2"):
			return "fixed_asset"
		if number.startswith("6057"):
			return "service"
		if number.startswith("60") or not number:
			return "goods"
		if number.startswith("61"):
			return "transport"
		return "service"
	if number.startswith("705"):
		return "works"
	if number[:3] in ("701", "702", "703", "704"):
		return "goods"
	return "service"


# VAT account per nature: 4452 achats, 4453 transport, 4454 services
# exterieurs, 4451 immobilisations ; 4431 ventes, 4432 prestations, 4433
# travaux. The next number is used when the company lacks the first leaf.
PURCHASE_VAT_ACCOUNTS = {
	"goods": ("4452",),
	"transport": ("4453", "4454"),
	"service": ("4454",),
	"fixed_asset": ("4451", "4452"),
}
SALES_VAT_ACCOUNTS = {
	"goods": ("4431",),
	"service": ("4432",),
	"works": ("4433", "4432"),
}


def account_number_of(account):
	if not account:
		return None
	return frappe.db.get_value("Account", account, "account_number")


def leaf_by_number(company, number):
	return _active_leaf(company, account_number=number) if number else None


def _active_leaf(company, **filters):
	return frappe.db.get_value("Account", {"company": company, "is_group": 0, "disabled": 0, **filters}, "name")


def keyword_account(company, label, is_purchase=True):
	number = keyword_account_number(label, is_purchase)
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
	account = keyword_account(company, label, is_purchase)
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
