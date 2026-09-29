# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Invoice/receipt reading by a vision model (Mistral OCR first, then
Gemini -- see mistral_ocr.py) instead of OCR + regex.

OCR.space turns a blurry, skewed or partly hand-written scan into broken
text, and the label regexes in api.py then find nothing. A vision model
reads the image itself: it follows the layout, reads stamps and hand
writing, and can make out a half-faded word from its context -- telling
us, per field, how sure it is.

read_document() returns the same shape as api.read_invoice_file's OCR
path (fields / confidence / line_items / document_type / text), or None
when the model is unavailable or the answer is unusable, so the caller
falls back to OCR.space."""

import base64
import hashlib
import json
import re

import frappe

from sitiame_core import gemini_assistant, mistral_ocr

# Bump when the prompt or schema changes, so cached readings are redone.
PROMPT_VERSION = 3
TIMEOUT = 90
MAX_BYTES = 15 * 1024 * 1024  # Gemini inline data limit is ~20 MB per request

MIME_TYPES = {
	"pdf": "application/pdf",
	"jpg": "image/jpeg",
	"jpeg": "image/jpeg",
	"png": "image/png",
	"webp": "image/webp",
	"heic": "image/heic",
	"heif": "image/heif",
}

FIELD_KEYS = (
	"invoice_number",
	"invoice_date",
	"due_date",
	"supplier_name",
	"customer_name",
	"tax_id",
	"subtotal",
	"tax_amount",
	"grand_total",
)
AMOUNT_KEYS = ("subtotal", "tax_amount", "grand_total")
DATE_KEYS = ("invoice_date", "due_date")
DOCUMENT_TYPES = ("invoice", "quotation", "credit_note", "purchase_order", "receipt", "unknown")

PROMPT = """Tu lis un document commercial scanne ou photographie (Afrique de l'Ouest, FCFA).
Il peut etre flou, sombre, de travers, froisse, tamponne ou en partie manuscrit.

Regles :
- Recopie ce qui est ecrit sur le document. N'invente rien et ne calcule rien :
  un montant absent ou illisible vaut null, meme s'il pourrait se deduire des autres.
- Si un caractere est abime, tu peux le reconstituer d'apres le contexte
  (nom repete ailleurs, total coherent avec les lignes...), mais baisse alors la confiance.
- supplier_name = l'emetteur du document (en-tete, cachet) ; customer_name = le destinataire.
- tax_id = le numero de compte contribuable (NCC, souvent ecrit "CC" ou "NCC", ex. 0100474J)
  ou NIF de l'EMETTEUR -- pas le numero d'une vignette ou d'un timbre TVA.
- Dates au format AAAA-MM-JJ. Montants en nombre sans separateur de milliers
  (1 234 500 FCFA -> 1234500).
- confidence : pour chaque champ, de 0 a 1 = ta certitude que la valeur est exactement
  celle du document (1 = parfaitement lisible, 0.5 = lu en partie / reconstitue,
  0 = absent).
- Sur une image floue, un chiffre dont tu n'es pas sur fait baisser la confiance du montant
  sous 0.5 : ne donne jamais 0.9 a un montant que tu as en partie devine.
- amount_in_words_value : le montant ecrit EN LETTRES ("Arrete la presente facture a la somme
  de ...") converti en nombre, ou null s'il n'y en a pas.
- image_quality : good (tout se lit), medium (lisible avec effort), poor (flou, sombre,
  coupe : des chiffres sont devines).
- line_items : une entree par ligne du tableau des articles (pas les lignes de total).
  Une remise ou un rabais est une ligne a montant NEGATIF.
- raw_text : la transcription complete du document, ligne par ligne, dans l'ordre de lecture.
- document_type : invoice (facture), quotation (devis), credit_note (avoir),
  purchase_order (bon de commande), receipt (recu de paiement, Mobile Money, virement), unknown.
"""


def _nullable(type_):
	return {"type": type_, "nullable": True}


RESPONSE_SCHEMA = {
	"type": "OBJECT",
	"properties": {
		"document_type": {"type": "STRING", "enum": list(DOCUMENT_TYPES)},
		"fields": {
			"type": "OBJECT",
			"properties": {
				key: _nullable("NUMBER" if key in AMOUNT_KEYS else "STRING") for key in FIELD_KEYS
			},
		},
		"confidence": {
			"type": "OBJECT",
			"properties": {key: {"type": "NUMBER"} for key in FIELD_KEYS},
		},
		"line_items": {
			"type": "ARRAY",
			"items": {
				"type": "OBJECT",
				"properties": {
					"item_name": {"type": "STRING"},
					"qty": _nullable("NUMBER"),
					"rate": _nullable("NUMBER"),
					"amount": _nullable("NUMBER"),
				},
				"required": ["item_name"],
			},
		},
		"amount_in_words_value": _nullable("NUMBER"),
		"image_quality": {"type": "STRING", "enum": ["good", "medium", "poor"]},
		"raw_text": {"type": "STRING"},
	},
	"required": ["document_type", "fields", "confidence", "line_items", "image_quality", "raw_text"],
}

# The model's own confidence is not enough: on a very blurry photo it
# returned invented totals at 0.8-0.9. Amounts that don't add up are
# capped to this, and flagged.
DOUBTFUL_CONFIDENCE = 0.3
# On a photo the model itself rates poor, nothing it read is shown as sure.
POOR_PHOTO_CONFIDENCE = 0.5

# FCFA amounts carry no centimes; VAT lines rounded separately can make the
# printed total differ by a franc or two, never more (a blurry photo misread
# 287 624 as 287 634 -- a relative tolerance let that through).
AMOUNT_TOLERANCE = 2
# UEMOA VAT rates (18% standard, Niger 19%, reduced 5/9/10%). On a very
# blurry photo the model invented HT/TVA/TTC that did add up -- but at 20.4%.
VAT_RATES = (0.05, 0.09, 0.10, 0.18, 0.19)
VAT_RATE_TOLERANCE = 0.002


def _amounts_differ(a, b):
	return abs(a - b) > AMOUNT_TOLERANCE


def _is_vat_rate(tax, subtotal):
	return any(abs(tax / subtotal - rate) <= VAT_RATE_TOLERANCE for rate in VAT_RATES)


def mime_type(filename):
	extension = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
	return MIME_TYPES.get(extension)


def json_schema(schema):
	"""RESPONSE_SCHEMA (Gemini's OpenAPI subset) as a standard JSON schema,
	for Mistral."""
	type_ = schema["type"].lower()
	if type_ == "object":
		converted = {"type": "object", "properties": {k: json_schema(v) for k, v in schema["properties"].items()}}
		if "required" in schema:
			converted["required"] = list(schema["required"])
		return converted
	if type_ == "array":
		return {"type": "array", "items": json_schema(schema["items"])}
	converted = {"type": [type_, "null"] if schema.get("nullable") else type_}
	if "enum" in schema:
		converted["enum"] = list(schema["enum"])
	return converted


def read_document(filename, content):
	"""Read an invoice/receipt with Mistral OCR, else Gemini (each rotating
	through its own keys). None when neither can."""
	mime = mime_type(filename)
	if not mime or not content or len(content) > MAX_BYTES:
		return None
	for reader in (_read_with_mistral, _read_with_gemini):
		data = reader(mime, content)
		if data is not None:
			return data
	return None


def _read_with_mistral(mime, content):
	if not mistral_ocr._api_keys() or not mistral_ocr.supports(mime):
		return None
	cache_key = f"mistral:vision:v{PROMPT_VERSION}:" + hashlib.sha256(content).hexdigest()
	result = mistral_ocr.annotate(mime, content, PROMPT, json_schema(RESPONSE_SCHEMA), cache_key)
	return _parse(result, "Mistral")


def _read_with_gemini(mime, content):
	if not gemini_assistant._api_keys():
		return None

	payload = {
		"contents": [
			{
				"role": "user",
				"parts": [
					{"inline_data": {"mime_type": mime, "data": base64.b64encode(content).decode()}},
					{"text": PROMPT},
				],
			}
		],
		"generationConfig": {
			"temperature": 0,
			"maxOutputTokens": 16384,
			# Uncapped, gemini-2.5-flash spent ~7900 tokens thinking on a
			# plain invoice and the JSON was cut off (finishReason MAX_TOKENS).
			"thinkingConfig": {"thinkingBudget": 2048},
			"responseMimeType": "application/json",
			"responseSchema": RESPONSE_SCHEMA,
		},
	}
	cache_key = f"gemini:vision:v{PROMPT_VERSION}:" + hashlib.sha256(content).hexdigest()
	result = gemini_assistant.generate(payload, cache_key, timeout=TIMEOUT)
	return _parse(result, "Gemini")


def _parse(result, reader):
	if not result["ok"]:
		frappe.logger("sitiame_core.ocr").warning(f"[OCR] {reader} vision unavailable: {result['error']}")
		return None
	try:
		return normalize(json.loads(result["text"]))
	except (ValueError, TypeError, AttributeError):
		frappe.logger("sitiame_core.ocr").warning(f"[OCR] {reader} vision answer unusable: {result['text'][:500]}")
		return None


def normalize(answer):
	"""Model answer -> read_invoice_file's shape; a key only when it has a
	usable value, like the regex extraction."""
	raw_fields = answer.get("fields") or {}
	raw_confidence = answer.get("confidence") or {}
	fields, confidence = {}, {}
	for key in FIELD_KEYS:
		value = _clean(key, raw_fields.get(key))
		if value is None:
			continue
		fields[key] = value
		confidence[key] = _unit(raw_confidence.get(key))

	document_type = answer.get("document_type")
	if document_type not in DOCUMENT_TYPES:
		document_type = "unknown"

	return {
		"document_type": document_type,
		"fields": fields,
		"confidence": confidence,
		"line_items": _line_items(answer.get("line_items") or []),
		"text": (answer.get("raw_text") or "").strip(),
		"warnings": _check_amounts(fields, confidence, answer),
	}


def _check_amounts(fields, confidence, answer):
	"""Cross-checks the amounts read (HT + TVA = TTC, total in words) and
	the photo quality; downgrades what doesn't add up. Returns warnings."""
	warnings = []
	subtotal, tax, total = (fields.get(key) for key in AMOUNT_KEYS)
	in_words = _number(answer.get("amount_in_words_value"))
	doubtful = False

	if subtotal and tax and total and _amounts_differ(subtotal + tax, total):
		doubtful = True
		warnings.append(
			frappe._("Montants illisibles ou mal lus : HT {0} + TVA {1} ne font pas le TTC {2}.").format(
				subtotal, tax, total
			)
		)
	if subtotal and tax and not _is_vat_rate(tax, subtotal):
		doubtful = True
		warnings.append(
			frappe._("TVA lue ({0}) = {1}% du HT ({2}) : ce n'est pas un taux de TVA, montants probablement mal lus.").format(
				tax, round(tax / subtotal * 100, 2), subtotal
			)
		)
	if in_words and in_words > 0:
		if total and _amounts_differ(in_words, total):
			doubtful = True
			warnings.append(
				frappe._("Le TTC lu en chiffres ({0}) differe du montant ecrit en lettres ({1}).").format(total, in_words)
			)
		elif not total:
			# the words are often still legible when the figures are not
			fields["grand_total"] = in_words
			confidence["grand_total"] = 0.6
			warnings.append(
				frappe._("TTC repris du montant ecrit en lettres ({0}) : a verifier.").format(in_words)
			)

	if doubtful:
		for key in AMOUNT_KEYS:
			if key in confidence:
				confidence[key] = min(confidence[key], DOUBTFUL_CONFIDENCE)

	if answer.get("image_quality") == "poor":
		for key in confidence:
			confidence[key] = min(confidence[key], POOR_PHOTO_CONFIDENCE)
		warnings.append(
			frappe._(
				"Photo de mauvaise qualite (floue, sombre ou coupee) : verifiez chaque montant, ou reprenez la photo."
			)
		)
	return warnings


def _clean(key, value):
	if value in (None, ""):
		return None
	if key in AMOUNT_KEYS:
		amount = _number(value)
		return amount if amount and amount > 0 else None
	value = str(value).strip()
	if key in DATE_KEYS:
		return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) and _valid_date(value) else None
	return value[:140] or None


def _valid_date(value):
	try:
		frappe.utils.getdate(value)
		return True
	except Exception:
		return False


def _number(value):
	if isinstance(value, (int, float)):
		return float(value)
	cleaned = re.sub(r"[^\d.]", "", str(value).replace(",", "."))
	try:
		return float(cleaned) if cleaned else None
	except ValueError:
		return None


def _unit(value):
	number = _number(value)
	if number is None:
		return 0.5
	return max(0.0, min(1.0, number))


def _line_items(rows):
	"""Same entries as api._extract_line_items: item_name, qty, rate."""
	items = []
	for row in rows:
		name = str(row.get("item_name") or "").strip()
		if not name:
			continue
		qty, rate, amount = (_number(row.get(k)) for k in ("qty", "rate", "amount"))
		entry = {"item_name": name}
		if qty is None and rate and amount:
			qty = round(amount / rate, 2)
		if qty is not None:
			entry["qty"] = qty
		if rate is not None:
			entry["rate"] = rate
		elif amount is not None:
			entry["rate"] = amount / qty if qty else amount
			entry.setdefault("qty", 1)
		items.append(entry)
	return items
