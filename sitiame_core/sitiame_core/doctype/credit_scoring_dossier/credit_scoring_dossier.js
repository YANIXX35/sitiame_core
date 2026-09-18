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

var handlers = { refresh: credit_scoring_recompute };
CREDIT_SCORING_CRITERIA.forEach(function (fname) {
	handlers[fname + "_weight"] = credit_scoring_recompute;
	handlers[fname + "_note"] = credit_scoring_recompute;
});

frappe.ui.form.on("Credit Scoring Dossier", handlers);
