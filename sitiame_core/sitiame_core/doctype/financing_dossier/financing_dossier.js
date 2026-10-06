// Copyright (c) 2026, Sitiame Capital
// License: MIT

const SCORE_FIELDS = [
	"score_legal_fiscal",
	"score_experience_governance",
	"score_market",
	"score_financial_performance",
	"score_repayment_capacity",
	"score_debt",
	"score_payment_history",
	"score_contribution_guarantees",
];

const SCORE_MAX = { score_legal_fiscal: 10, score_experience_governance: 10, score_market: 15,
	score_financial_performance: 20, score_repayment_capacity: 20, score_debt: 10,
	score_payment_history: 10, score_contribution_guarantees: 5 };

function compute_total_score(frm) {
	var total = 0;
	SCORE_FIELDS.forEach(function (f) {
		var val = cint(frm.doc[f]) || 0;
		var max = SCORE_MAX[f];
		if (val > max) val = max;
		if (val < 0) val = 0;
		total += val;
	});
	frm.set_value("total_score", total);
}

frappe.ui.form.on("Financing Dossier", {
	refresh: function (frm) {
		frm.add_custom_button(__("Synchroniser depuis PME360"), function () {
			financing_dossier_sync(frm);
		});

		// Chargé d'affaires propose uniquement, le validateur donne l'avis final
		if (frappe.user.has_role("Charge d'affaires Sitiame")
			&& !frappe.user.has_role("System Manager") && !frappe.user.has_role("Analyste Credit Sitiame")) {
			var proposals = ["A examiner", "En cours d'analyse"];
			if (!frm.doc.status || proposals.indexOf(frm.doc.status) !== -1) {
				frm.set_df_property("status", "options", proposals.join("\n"));
			} else {
				frm.set_df_property("status", "read_only", 1);
			}
			frm.set_df_property("status", "description", __("L'avis (favorable, défavorable, ajourné) revient à un validateur."));
			// Masquer les champs d'analyse réservés à l'analyste crédit
			["credit_opinion", "approval_conditions", "analyst_opinion"].forEach(function (f) {
				frm.set_df_property(f, "read_only", 1);
			});
		}

		if (frm.doc.__islocal) return;

		// Afficher le score global avec une couleur selon le résultat
		var score = frm.doc.total_score || 0;
		var color = score >= 80 ? "green" : score >= 65 ? "orange" : "red";
		var label = score >= 80 ? __("Risque faible") : score >= 65 ? __("Risque modéré") : score >= 50 ? __("Risque élevé") : __("Risque très élevé");
		frm.dashboard.add_indicator(__("Score : {0}/100 — {1}", [score, label]), color);

		// Afficher l'écart plan de financement si non nul
		if (frm.doc.funding_gap && frm.doc.funding_gap !== 0) {
			frm.dashboard.add_indicator(__("Écart plan de financement : {0} XOF", [format_currency(frm.doc.funding_gap, "XOF")]), "red");
		}

		// Afficher le DSCR si présent
		if (frm.doc.dscr) {
			var dscr_color = frm.doc.dscr >= 1.25 ? "green" : "red";
			frm.dashboard.add_indicator(__("DSCR : {0}", [flt(frm.doc.dscr, 2)]), dscr_color);
		}
	},

	company: function (frm) {
		if (frm.doc.company && frm.is_new()) {
			financing_dossier_sync(frm);
		}
	},
});

// Recalcul du score à chaque changement de critère
SCORE_FIELDS.forEach(function (field) {
	frappe.ui.form.on("Financing Dossier", field, function (frm) {
		compute_total_score(frm);
	});
});

// Recalcul DSCR automatique
frappe.ui.form.on("Financing Dossier", {
	cash_available_for_debt: function (frm) { _compute_dscr(frm); },
	annual_debt_service: function (frm) { _compute_dscr(frm); },
});

function _compute_dscr(frm) {
	var debt = flt(frm.doc.annual_debt_service);
	var cash = flt(frm.doc.cash_available_for_debt);
	if (debt > 0) frm.set_value("dscr", flt(cash / debt, 2));
}

function financing_dossier_sync(frm) {
	if (!frm.doc.company) {
		frappe.msgprint(__("Choisissez d'abord une société."));
		return;
	}

	frappe.call({
		method: "sitiame_core.api.get_financing_dossier_from_pme360",
		args: { company: frm.doc.company },
		freeze: true,
		freeze_message: __("Récupération depuis PME360..."),
	}).then(function (r) {
		var data = r.message || {};

		if (data.status === "ignored") {
			frappe.show_alert({
				message: __("PME360 : ") + (data.reason || __("aucune donnée trouvée")),
				indicator: "orange",
			});
			return;
		}

		if (data.status !== "ok") {
			frappe.show_alert({ message: __("PME360 injoignable ou erreur."), indicator: "red" });
			return;
		}

		// Mapping des champs API PME360 → ERPNext
		var syncFields = [
			// Étape 1 — Demande
			"financing_type", "financing_purpose", "amount_requested", "currency",
			"desired_term_months", "grace_period_months", "repayment_frequency",
			"promoter_contribution", "desired_disbursement_date",
			"financing_summary", "repayment_source",
			// Étape 2 — Entreprise
			"legal_name", "trade_name", "legal_form", "rccm_number", "taxpayer_number",
			"incorporation_date", "registered_office", "city_country",
			"business_sector", "main_activity", "employee_count", "website",
			"company_history", "share_capital", "major_shareholders",
			"beneficial_owners", "authorized_representative",
			// Étape 3 — Promoteurs
			"manager_full_name", "manager_role", "manager_birth_date", "manager_nationality",
			"manager_phone", "manager_email", "manager_experience_years", "manager_education",
			"manager_background", "management_team", "succession_controls",
			// Étape 4 — Projet
			"project_name", "project_location", "project_start_date", "implementation_months",
			"total_project_cost", "contingency_amount", "project_problem", "project_solution",
			"expected_results", "cost_breakdown_json", "project_risks", "mitigation_measures",
			// Étape 5 — Marché
			"market_description", "target_customers", "customer_need", "market_trends",
			"competitors", "competitive_advantage", "pricing_strategy", "sales_channels",
			"top_customers", "customer_concentration", "orders_contracts",
			// Étape 6 — Finances historiques
			"current_revenue_ytd", "bank_balance", "customer_receivables", "supplier_payables",
			"inventory_value", "tax_social_debt", "financial_history_json",
			"existing_loans_json", "payment_incidents",
			// Étape 7 — Prévisions
			"sales_assumptions", "cost_assumptions", "working_capital_assumptions",
			"forecast_scenarios", "annual_debt_service", "cash_available_for_debt",
			"dscr", "break_even_revenue", "forecast_json",
			// Étape 8 — Plan de financement
			"total_uses", "total_sources", "funding_gap", "funding_uses_json", "funding_sources_json",
			// Étape 9 — Garanties
			"collateral_details", "insurer_name", "insurance_policy",
			"estimated_collateral_value", "guarantee_coverage", "collateral_json",
			// Pièces justificatives (URLs de fichiers)
			"company_statutes", "rccm_document", "tax_document", "manager_id",
			"clearance_certificates", "historical_financial_statements",
			"current_trial_balance", "bank_statements", "existing_loan_schedules",
			"supplier_quotes", "business_plan", "commercial_evidence", "collateral_documents",
		];

		var apiToDoctypeField = {
			reference: "pme360_reference",
			dossier_status: "pme360_status",
		};

		// Appliquer les champs statut/référence
		["reference", "dossier_status"].forEach(function (key) {
			if (data[key] !== undefined) {
				frm.set_value(apiToDoctypeField[key], data[key]);
			}
		});

		// Appliquer tous les champs synchronisés
		syncFields.forEach(function (field) {
			if (data[field] !== undefined && data[field] !== null) {
				frm.set_value(field, data[field]);
			}
		});

		frm.set_value("last_synced_at", frappe.datetime.now_datetime());

		// Recalculer le DSCR et le score après sync
		_compute_dscr(frm);
		compute_total_score(frm);

		frappe.show_alert({ message: __("Dossier synchronisé depuis PME360."), indicator: "green" });
	});
}
