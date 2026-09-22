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

var handlers = {
	refresh: credit_scoring_recompute,
	company: function (frm) {
		credit_scoring_prefill_company_info(frm);
		credit_scoring_apply_suggestions(frm);
	},
};
CREDIT_SCORING_CRITERIA.forEach(function (fname) {
	handlers[fname + "_weight"] = credit_scoring_recompute;
	handlers[fname + "_note"] = credit_scoring_recompute;
});

frappe.ui.form.on("Credit Scoring Dossier", handlers);
