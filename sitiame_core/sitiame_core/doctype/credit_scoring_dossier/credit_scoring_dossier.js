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

var handlers = {
	refresh: credit_scoring_recompute,
	company: credit_scoring_prefill_company_info,
};
CREDIT_SCORING_CRITERIA.forEach(function (fname) {
	handlers[fname + "_weight"] = credit_scoring_recompute;
	handlers[fname + "_note"] = credit_scoring_recompute;
});

frappe.ui.form.on("Credit Scoring Dossier", handlers);
