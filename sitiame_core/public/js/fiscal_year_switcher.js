/**
 * Sitiame — Sélecteur d'exercice fiscal global
 *
 * Affiche un badge "Exercice : 2026" dans la barre de navigation.
 * Quand l'utilisateur change d'année, toutes les listes et tous les
 * formulaires basculent sur cet exercice :
 *   - Les listes filtrées par posting_date sur la plage de l'exercice
 *   - Les nouveaux documents pré-remplis avec une date dans l'exercice
 *   - Le garde-fou fiscal_guard.py bloque si la date sort de l'exercice
 */

frappe.provide("sitiame.fiscal_year");

// Tous les doctypes dont la liste doit être filtrée par exercice
sitiame.fiscal_year.DATED_DOCTYPES = [
	"Purchase Invoice",
	"Sales Invoice",
	"Journal Entry",
	"Payment Entry",
	"Purchase Order",
	"Sales Order",
	"Purchase Receipt",
	"Delivery Note",
	"Stock Entry",
	"Expense Claim",
	"Asset",
	"Payment Reconciliation",
	"GL Entry",
	"Quotation",
	"Purchase Return",
	"Landed Cost Voucher",
];

// Champ date à filtrer selon le doctype
sitiame.fiscal_year.DATE_FIELD = {
	"Purchase Order": "transaction_date",
	"Sales Order": "transaction_date",
	"Quotation": "transaction_date",
	"Asset": "purchase_date",
};

sitiame.fiscal_year._fy = null; // exercice actif en mémoire

// ── Initialisation ──────────────────────────────────────────────────────────

sitiame.fiscal_year.init = function () {
	frappe.call({
		method: "sitiame_core.fiscal_year_api.get_active_fiscal_year",
		callback: function (r) {
			if (!r.message) return;
			sitiame.fiscal_year._fy = r.message;
			sitiame.fiscal_year._render_badge();
			sitiame.fiscal_year._setup_list_hook();
			sitiame.fiscal_year._setup_form_hook();
		},
	});
};

// ── Badge navbar ─────────────────────────────────────────────────────────────

sitiame.fiscal_year._render_badge = function () {
	const fy = sitiame.fiscal_year._fy;
	if (!fy) return;

	// Supprimer l'ancien badge s'il existe (re-render)
	$(".sitiame-fy-badge").remove();

	const $badge = $(`
		<li class="nav-item sitiame-fy-badge" title="Exercice fiscal actif — cliquez pour changer">
			<a class="nav-link sitiame-fy-link" href="#" style="
				display:flex; align-items:center; gap:6px;
				background: #1a7f5a; color:#fff;
				border-radius:20px; padding:4px 14px;
				font-weight:600; font-size:13px;
				margin: 6px 8px; white-space:nowrap;
			">
				<span style="font-size:15px;">📅</span>
				<span class="sitiame-fy-label">Exercice ${fy.label}</span>
			</a>
		</li>
	`);

	$badge.on("click", "a", function (e) {
		e.preventDefault();
		sitiame.fiscal_year._open_switcher();
	});

	// Insérer après le logo dans la navbar
	$(".navbar-nav.mr-auto, .navbar .navbar-nav").first().prepend($badge);
};

// ── Modal de sélection ───────────────────────────────────────────────────────

sitiame.fiscal_year._open_switcher = function () {
	frappe.call({
		method: "sitiame_core.fiscal_year_api.get_available_fiscal_years",
		callback: function (r) {
			const years = r.message || [];
			if (!years.length) {
				frappe.msgprint(__("Aucun exercice fiscal disponible."));
				return;
			}

			const current_name = (sitiame.fiscal_year._fy || {}).name;
			const buttons = years
				.map(
					(fy) => `
				<button class="btn ${fy.name === current_name ? "btn-primary" : "btn-default"}
					sitiame-fy-pick" data-fy="${fy.name}"
					style="margin:6px; min-width:90px; font-size:15px; font-weight:600;">
					${fy.label}${fy.is_current ? " ✓" : ""}
				</button>`
				)
				.join("");

			const d = new frappe.ui.Dialog({
				title: __("Changer d'exercice fiscal"),
				fields: [
					{
						fieldtype: "HTML",
						options: `
							<p style="margin-bottom:12px; color:#6c757d;">
								Toutes les listes et nouveaux documents basculeront sur l'exercice choisi.
							</p>
							<div style="text-align:center;">${buttons}</div>
						`,
					},
				],
			});

			d.show();

			d.$wrapper.on("click", ".sitiame-fy-pick", function () {
				const fy_name = $(this).data("fy");
				d.hide();
				sitiame.fiscal_year._switch_to(fy_name);
			});
		},
	});
};

// ── Basculement ───────────────────────────────────────────────────────────────

sitiame.fiscal_year._switch_to = function (fy_name) {
	frappe.call({
		method: "sitiame_core.fiscal_year_api.set_active_fiscal_year",
		args: { fiscal_year_name: fy_name },
		callback: function (r) {
			if (!r.message) return;
			sitiame.fiscal_year._fy = r.message;
			// Mettre à jour le badge sans rechargement
			$(".sitiame-fy-label").text("Exercice " + r.message.label);
			frappe.show_alert(
				{
					message: __("Exercice {0} activé — les listes se mettent à jour.", [r.message.label]),
					indicator: "green",
				},
				3
			);
			// Recharger la page courante pour appliquer les filtres
			setTimeout(() => location.reload(), 800);
		},
	});
};

// ── Filtrage automatique des listes ──────────────────────────────────────────

sitiame.fiscal_year._setup_list_hook = function () {
	const DATED = sitiame.fiscal_year.DATED_DOCTYPES;
	const DATE_FIELD = sitiame.fiscal_year.DATE_FIELD;

	// Hook sur chaque changement de route Frappe
	$(document).on("page-change", function () {
		setTimeout(function () {
			const fy = sitiame.fiscal_year._fy;
			if (!fy || !frappe.pages) return;

			// Chercher si la page courante est une liste
			const page = frappe.get_route();
			if (!page || page[0] !== "List") return;
			const doctype = page[1];
			if (!DATED.includes(doctype)) return;

			const list_view = frappe.views && frappe.views.list_view;
			if (!list_view || !list_view.filter_area) return;

			const date_field = DATE_FIELD[doctype] || "posting_date";
			const existing = list_view.filter_area.get();
			const already = existing.some(
				(f) => f[1] === date_field && f[2] === "Between"
			);
			if (already) return;

			list_view.filter_area.add([
				[doctype, date_field, "Between", [fy.year_start_date, fy.year_end_date]],
			]);
			list_view.refresh();
		}, 400);
	});

	// Appliquer aussi via listview_settings pour chaque doctype listé
	sitiame.fiscal_year.DATED_DOCTYPES.forEach(function (doctype) {
		frappe.listview_settings[doctype] = frappe.listview_settings[doctype] || {};

		const original_onload = frappe.listview_settings[doctype].onload;
		frappe.listview_settings[doctype].onload = function (listview) {
			if (original_onload) original_onload(listview);

			const fy = sitiame.fiscal_year._fy;
			if (!fy) return;

			const date_field =
				sitiame.fiscal_year.DATE_FIELD[doctype] || "posting_date";
			const existing = listview.get_filters_for_args();
			const already =
				existing &&
				existing.some((f) => f[1] === date_field && f[2] === "Between");
			if (already) return;

			listview.filter_area.add([
				[doctype, date_field, "Between", [fy.year_start_date, fy.year_end_date]],
			]);
		};
	});
};

// ── Pré-remplissage des formulaires ──────────────────────────────────────────

sitiame.fiscal_year._setup_form_hook = function () {
	const DATED = sitiame.fiscal_year.DATED_DOCTYPES;
	const DATE_FIELD = sitiame.fiscal_year.DATE_FIELD;

	frappe.ui.form.on("*", {
		onload: function (frm) {
			if (!frm.is_new()) return;
			if (!DATED.includes(frm.doctype)) return;

			const fy = sitiame.fiscal_year._fy;
			if (!fy) return;

			const date_field = DATE_FIELD[frm.doctype] || "posting_date";
			if (!frm.fields_dict[date_field]) return;

			const current_val = frm.doc[date_field];
			if (current_val) {
				// Vérifier si la date est dans l'exercice sélectionné
				const d = frappe.datetime.str_to_obj(current_val);
				const start = frappe.datetime.str_to_obj(fy.year_start_date);
				const end = frappe.datetime.str_to_obj(fy.year_end_date);
				if (d >= start && d <= end) return; // déjà dans le bon exercice
			}

			// Pré-remplir avec la date de fin de l'exercice (ou aujourd'hui si exercice courant)
			const today = frappe.datetime.get_today();
			const today_obj = frappe.datetime.str_to_obj(today);
			const end_obj = frappe.datetime.str_to_obj(fy.year_end_date);
			const default_date = today_obj <= end_obj ? today : fy.year_end_date;

			frm.set_value(date_field, default_date);
		},
	});
};

// ── Démarrage ────────────────────────────────────────────────────────────────

$(document).ready(function () {
	// Attendre que Frappe soit prêt
	frappe.after_ajax(function () {
		if (frappe.session && frappe.session.user !== "Guest") {
			sitiame.fiscal_year.init();
		}
	});
});
