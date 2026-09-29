// Copyright (c) 2026, Sitiame Capital
// License: MIT

// Client-side live preview mirroring the standalone HTML mockup's
// calculate()/update() logic: recomputes score/grade on every change
// without requiring a save, then the server (credit_scoring_dossier.py)
// recomputes the same thing authoritatively on save.
const CREDIT_SCORING_CRITERIA = [
	"capacite_remboursement",
	"structure_financiere",
	"rentabilite",
	"historique_paiement",
	"marche_clientele",
	"direction_organisation",
	"qualite_informations",
	"projet_financement",
	"liquidite_generale",
	"garanties_recouvrement",
];

function credit_scoring_recompute(frm) {
	var total_weight = 0;
	var sum_score = 0;
	var count = 0;
	var valid = true;

	CREDIT_SCORING_CRITERIA.forEach(function (fname) {
		var weight = frm.doc[fname + "_weight"];
		weight = weight === undefined || weight === null || weight === "" ? 0 : parseInt(weight, 10);
		if (isNaN(weight) || weight < 0 || weight > 100) valid = false;
		total_weight += weight;

		var note = frm.doc[fname + "_note"];
		if (note !== undefined && note !== null && note !== "") {
			note = parseInt(note, 10);
			if (isNaN(note) || note < 0 || note > 5) {
				valid = false;
			} else {
				count += 1;
				sum_score += (weight * note) / 5;
			}
		}
	});

	var ready = valid && total_weight === 100 && count === CREDIT_SCORING_CRITERIA.length;

	frm.set_value("criteria_evaluated_count", count);
	frm.set_value("ready", ready ? 1 : 0);

	if (ready) {
		var score = Math.round(sum_score * 10) / 10;
		frm.set_value("score", score);
		frm.set_value("grade", score >= 80 ? "A" : score >= 65 ? "B" : score >= 50 ? "C" : "D");
	} else {
		frm.set_value("score", null);
		frm.set_value("grade", null);
	}

	frm.dashboard.clear_headline();
	frm.dashboard.set_headline(
		__("{0}/10 criteres evalues - Poids : {1}/100{2}", [
			count,
			total_weight,
			!valid ? " - Poids invalides" : total_weight !== 100 ? " - Corriger les ponderations" : "",
		])
	);
}

// Pré-remplit les infos entreprise depuis la fiche d'inscription (Company
// Signup) dès qu'une société est choisie, pour éviter de ressaisir ce qui a
// déjà été collecté à l'inscription. Ne touche jamais un champ déjà rempli
// manuellement, pour ne pas écraser une correction de l'analyste.
function credit_scoring_prefill_company_info(frm) {
	if (!frm.doc.company) return;

	frappe.call({
		method: "sitiame_core.api.get_company_signup_info",
		args: { company: frm.doc.company },
	}).then(function (r) {
		var info = r.message || {};
		var map = {
			contact_name: "contact_name",
			phone: "phone_from_signup",
			rccm: "rccm_from_signup",
			address: "address_from_signup",
			city: "city_from_signup",
			sector: "sector",
		};
		Object.keys(map).forEach(function (sourceKey) {
			var targetField = map[sourceKey];
			if (info[sourceKey] && !frm.doc[targetField]) {
				frm.set_value(targetField, info[sourceKey]);
			}
		});
	});
}

// Suggère des notes de départ pour les critères déjà calculables depuis
// d'autres modules (Comptabilité pour 02/03/09, Documents KYC pour 07 et
// la case "Identité vérifiée"), au lieu de laisser l'analyste noter à
// l'aveugle. Ne touche jamais une note déjà saisie : c'est une suggestion,
// pas une décision automatique -- l'analyste garde la main.
function credit_scoring_apply_suggestions(frm) {
	if (!frm.doc.company) return;

	frappe.call({
		method: "sitiame_core.api.get_scoring_suggestions",
		args: { company: frm.doc.company },
	}).then(function (r) {
		var s = r.message || {};
		var noteFields = {
			capacite_remboursement: "capacite_remboursement_note",
			structure_financiere: "structure_financiere_note",
			rentabilite: "rentabilite_note",
			liquidite_generale: "liquidite_generale_note",
			historique_paiement: "historique_paiement_note",
			marche_clientele: "marche_clientele_note",
			qualite_informations: "qualite_informations_note",
		};
		var proofFields = {
			capacite_remboursement: "capacite_remboursement_proof",
			structure_financiere: "structure_financiere_proof",
			rentabilite: "rentabilite_proof",
			liquidite_generale: "liquidite_generale_proof",
			historique_paiement: "historique_paiement_proof",
			marche_clientele: "marche_clientele_proof",
			qualite_informations: "qualite_informations_proof",
		};
		var explanationKeys = {
			capacite_remboursement: "_comptabilite_note",
			structure_financiere: "_comptabilite_note",
			rentabilite: "_comptabilite_note",
			liquidite_generale: "_comptabilite_note",
			historique_paiement: "_historique_paiement_note",
			marche_clientele: "_marche_clientele_note",
			qualite_informations: "_kyc_note",
		};

		Object.keys(noteFields).forEach(function (key) {
			var noteField = noteFields[key];
			var proofField = proofFields[key];
			if (s[key] !== null && s[key] !== undefined && !frm.doc[noteField]) {
				frm.set_value(noteField, String(s[key]));
				var explanation = s[explanationKeys[key]];
				if (explanation && !frm.doc[proofField]) {
					frm.set_value(proofField, __("Suggestion automatique : ") + explanation);
				}
			}
		});

		if (s.identity_verified && !frm.doc.identity_verified) {
			frm.set_value("identity_verified", 1);
		}

		if (s._comptabilite_note || s._kyc_note) {
			frappe.show_alert({
				message: __("Suggestions de notation appliquées depuis la Comptabilité et les Documents KYC."),
				indicator: "blue",
			});
		}
	});
}

// Scoring 360 detail panel. Presentation only (French labels, display
// format, why a criterion can be non-computable): weights, thresholds and
// comparison direction all come from Scoring 360 Settings through the API
// -- nothing that decides the score is hardcoded here.
const SCORING360_BLOCKS = [
	{
		key: "bank",
		label: "Banque",
		criteria: [
			{ key: "dscr", label: "DSCR (capacite de remboursement)", format: "ratio", missing: "Aucune charge financiere (comptes 66) sur la periode." },
			{ key: "interest_coverage", label: "Couverture des interets", format: "ratio", missing: "Aucune charge financiere (comptes 66) sur la periode." },
			{ key: "current_ratio", label: "Liquidite generale", format: "ratio", missing: "Aucun passif circulant sur la periode." },
			{ key: "debt_asset", label: "Dettes financieres / actif", format: "pct", missing: "Aucun actif (immobilisations, stocks, creances, tresorerie)." },
			{ key: "bfr_days", label: "BFR en jours de CA", format: "days", missing: "Aucun chiffre d'affaires (classe 7) sur la periode." },
		],
	},
	{
		key: "investor",
		label: "Investisseur",
		criteria: [
			{ key: "revenue_growth", label: "Croissance du CA", format: "pct", missing: "Pas de chiffre d'affaires sur la periode precedente." },
			{ key: "ebitda_margin", label: "Marge EBITDA", format: "pct", missing: "Aucun chiffre d'affaires (classe 7) sur la periode." },
			{ key: "roe", label: "Rentabilite des capitaux propres", format: "pct", missing: "Capitaux propres nuls ou negatifs." },
			{ key: "fcf_margin", label: "Marge de tresorerie nette", format: "pct", missing: "Aucun chiffre d'affaires (classe 7) sur la periode." },
			{ key: "asset_turnover", label: "Rotation de l'actif", format: "ratio", missing: "Aucun actif (immobilisations, stocks, creances, tresorerie)." },
		],
	},
	{
		key: "internal",
		label: "Interne",
		criteria: [
			{ key: "net_margin", label: "Marge nette", format: "pct", missing: "Aucun chiffre d'affaires (classe 7) sur la periode." },
			{ key: "quick_ratio", label: "Liquidite reduite", format: "ratio", missing: "Aucun passif circulant sur la periode." },
			{ key: "receivable_days", label: "Delai clients (jours)", format: "days", missing: "Aucun chiffre d'affaires (classe 7) sur la periode." },
			{ key: "inventory_days", label: "Rotation des stocks (jours)", format: "days", missing: "Aucun achat (comptes 60/61) sur la periode." },
			{ key: "ebitda_growth", label: "Croissance de l'EBITDA", format: "pct", missing: "EBITDA nul ou negatif sur la periode precedente." },
		],
	},
];

const SCORING360_DECISION_COLORS = { strong: "green", medium: "orange", weak: "red" };
const SCORING360_LEVELS = {
	strong: { label: "Fort", color: "green" },
	medium: { label: "Moyen", color: "orange" },
	weak: { label: "Faible", color: "red" },
	missing: { label: "Non calculable", color: "gray" },
};

function scoring360_esc(value) {
	return frappe.utils.escape_html(value === null || value === undefined ? "" : String(value));
}

function scoring360_format(value, format) {
	if (value === null || value === undefined) return "n/c";
	if (format === "pct") return format_number(value * 100, null, 1) + " %";
	if (format === "days") return format_number(value, null, 0) + " j";
	return format_number(value, null, 2) + " x";
}

function scoring360_pill(label, color) {
	return "<span class='indicator-pill " + color + "'>" + scoring360_esc(label) + "</span>";
}

function scoring360_message(text) {
	return "<p class='text-muted' style='margin:10px 0;'>" + scoring360_esc(text) + "</p>";
}

// Saved period if both dates are set, otherwise 12 rolling months ending
// on the evaluation date (or today).
function credit_scoring_scoring360_period(frm) {
	if (frm.doc.scoring_period_from && frm.doc.scoring_period_to) {
		return { from: frm.doc.scoring_period_from, to: frm.doc.scoring_period_to };
	}
	var to = frm.doc.eval_date || frappe.datetime.get_today();
	return { from: frappe.datetime.add_days(frappe.datetime.add_months(to, -12), 1), to: to };
}

// Saves the default period with the dossier (credit decision traceability)
// -- only when the user can edit it; a read-only PME keeps the in-memory
// default.
function credit_scoring_prefill_period(frm) {
	if (!frm.doc.company || frm.doc.scoring_period_from || frm.doc.scoring_period_to) return;
	if (!frm.is_new() && !frm.has_perm("write")) return;
	var period = credit_scoring_scoring360_period(frm);
	frm.set_value({ scoring_period_from: period.from, scoring_period_to: period.to });
}

// Company + both dates changing together fire several events: render once.
function credit_scoring_schedule_scoring360(frm) {
	clearTimeout(frm._scoring360_timer);
	frm._scoring360_timer = setTimeout(function () {
		credit_scoring_render_scoring360(frm);
	}, 300);
}

function scoring360_header_html(data, period) {
	var composite = data.composite || {};
	var decision = composite.decision || {};
	var contributions = composite.contributions || {};
	var weights = ((data.config || {}).composite || {}).weights || {};

	var parts = SCORING360_BLOCKS.map(function (block) {
		return (
			scoring360_esc(block.label) + " <b>" + format_number(contributions[block.key] || 0, null, 1) +
			"</b> / " + format_number(weights[block.key] || 0, null, 0)
		);
	});

	return (
		"<div class='card' style='padding:15px;margin-bottom:15px;'>" +
		"<div class='text-muted' style='font-size:12px;'>" +
		scoring360_esc(__("Score composite - periode du {0} au {1}", [
			frappe.datetime.str_to_user(period.from),
			frappe.datetime.str_to_user(period.to),
		])) +
		"</div>" +
		"<div style='display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:6px 0;'>" +
		"<span style='font-size:28px;font-weight:600;'>" + format_number(composite.total || 0, null, 1) + " / 100</span>" +
		scoring360_pill(decision.label || "-", SCORING360_DECISION_COLORS[decision.level] || "gray") +
		"</div>" +
		"<div>" + scoring360_esc(decision.lecture || "") + "</div>" +
		"<div class='text-muted' style='margin-top:6px;'>" + __("Contributions") + " : " + parts.join(" &middot; ") + "</div>" +
		"</div>"
	);
}

function scoring360_block_html(block, data) {
	var result = (data.blocks || {})[block.key] || {};
	var decision = result.decision || {};
	var criteria = result.criteria || {};
	var cfg = (data.config || {})[block.key] || {};
	var weights = cfg.weights || {};
	var thresholds = cfg.thresholds || {};

	var rows = block.criteria.map(function (crit) {
		var c = criteria[crit.key] || { value: null, score: 0, level: "missing" };
		var t = thresholds[crit.key] || {};
		var op = t.direction === "lte" ? "&le;" : "&ge;";
		var level = SCORING360_LEVELS[c.level] || SCORING360_LEVELS.missing;
		var value = scoring360_format(c.value, crit.format);
		var valueCell = c.value === null || c.value === undefined
			? "<span title='" + scoring360_esc(crit.missing) + "' style='cursor:help;border-bottom:1px dotted;'>" + value + "</span>"
			: value;

		return (
			"<tr>" +
			"<td>" + scoring360_esc(crit.label) + "</td>" +
			"<td class='text-end'>" + valueCell + "</td>" +
			"<td class='text-end text-muted' style='white-space:nowrap;'>" +
			op + " " + scoring360_format(t.strong, crit.format) + " / " + op + " " + scoring360_format(t.medium, crit.format) +
			"</td>" +
			"<td>" + scoring360_pill(level.label, level.color) + "</td>" +
			"<td class='text-end' style='white-space:nowrap;'>" +
			format_number(c.score || 0, null, 1) + " / " + format_number(weights[crit.key] || 0, null, 0) +
			"</td>" +
			"</tr>"
		);
	});

	return (
		// Full width, stacked: the form column is too narrow for 3 cards side
		// by side (Niveau/Points columns ended up clipped behind a scrollbar).
		"<div class='col-12' style='margin-bottom:15px;'>" +
		"<div class='card' style='padding:12px;'>" +
		"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;'>" +
		"<b>" + scoring360_esc(__("Bloc {0}", [block.label])) + "</b>" +
		"<span><b>" + format_number(result.total || 0, null, 1) + "</b> / 100 " +
		scoring360_pill(decision.label || "-", SCORING360_DECISION_COLORS[decision.level] || "gray") + "</span>" +
		"</div>" +
		"<div class='table-responsive' style='margin-top:8px;'>" +
		"<table class='table table-sm' style='font-size:12px;margin:0;'><thead><tr>" +
		"<th>" + __("Critere") + "</th>" +
		"<th class='text-end'>" + __("Valeur") + "</th>" +
		"<th class='text-end'>" + __("Seuils fort / moyen") + "</th>" +
		"<th>" + __("Niveau") + "</th>" +
		"<th class='text-end'>" + __("Points") + "</th>" +
		"</tr></thead><tbody>" + rows.join("") + "</tbody></table>" +
		"</div></div></div>"
	);
}

function credit_scoring_render_scoring360(frm) {
	var field = frm.get_field("scoring360_panel");
	if (!field) return;
	var $wrapper = field.$wrapper;

	if (!frm.doc.company) {
		$wrapper.html(scoring360_message(__("Choisissez une societe pour afficher l'analyse Scoring 360.")));
		return;
	}

	var period = credit_scoring_scoring360_period(frm);
	// A slow answer must never overwrite a more recent one.
	var requestId = (frm._scoring360_request || 0) + 1;
	frm._scoring360_request = requestId;
	$wrapper.html(scoring360_message(__("Calcul en cours...")));

	frappe.call({
		method: "sitiame_core.api.get_scoring360_score",
		args: { company: frm.doc.company, date_from: period.from, date_to: period.to },
		callback: function (r) {
			if (frm._scoring360_request !== requestId) return;
			var data = r.message || {};
			if (!data.entries_count) {
				$wrapper.html(scoring360_message(__("Donnees insuffisantes - aucune ecriture comptable sur la periode.")));
				return;
			}
			$wrapper.html(
				scoring360_header_html(data, period) +
				"<div class='row'>" +
				SCORING360_BLOCKS.map(function (block) {
					return scoring360_block_html(block, data);
				}).join("") +
				"</div>"
			);
		},
		error: function () {
			if (frm._scoring360_request !== requestId) return;
			$wrapper.html(scoring360_message(__("Analyse indisponible.")));
		},
	});
}

// A chargé d'affaires proposes, a validator decides (the server enforces
// it too: sitiame_core.portfolio.check_decision).
function credit_scoring_is_proposer() {
	return frappe.user.has_role("Charge d'affaires Sitiame")
		&& !frappe.user.has_role("System Manager") && !frappe.user.has_role("Analyste Credit Sitiame");
}

var handlers = {
	refresh: function (frm) {
		credit_scoring_recompute(frm);
		credit_scoring_schedule_scoring360(frm);
		if (credit_scoring_is_proposer()) {
			frm.set_df_property("decision", "read_only", 1);
			frm.set_df_property("validator", "read_only", 1);
			frm.set_df_property("decision", "description", __("La décision revient à un validateur : cochez « Prêt » quand le dossier est complet."));
		}
	},
	company: function (frm) {
		credit_scoring_prefill_company_info(frm);
		credit_scoring_apply_suggestions(frm);
		credit_scoring_prefill_period(frm);
		credit_scoring_schedule_scoring360(frm);
	},
	scoring_period_from: credit_scoring_schedule_scoring360,
	scoring_period_to: credit_scoring_schedule_scoring360,
	eval_date: function (frm) {
		// Only the in-memory default period depends on eval_date.
		if (!frm.doc.scoring_period_from || !frm.doc.scoring_period_to) {
			credit_scoring_schedule_scoring360(frm);
		}
	},
};
CREDIT_SCORING_CRITERIA.forEach(function (fname) {
	handlers[fname + "_weight"] = credit_scoring_recompute;
	handlers[fname + "_note"] = credit_scoring_recompute;
});

frappe.ui.form.on("Credit Scoring Dossier", handlers);
