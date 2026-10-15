// Copyright (c) 2026, Sitiame Capital
// License: MIT

// "Configuration du compte": a PME account's starting position (products,
// opening stock, receivables, payables, cash) -- see onboarding.py. Shown
// on the desk until every step is done or declared empty; "Plus tard" hides
// it for the session only.
(function () {
	const API = "sitiame_core.onboarding.";
	const LATER_KEY = "sitiame_onboarding_later";
	const GREEN = "#22c55e";

	frappe.provide("sitiame");

	function later() {
		try { sessionStorage.setItem(LATER_KEY, "1"); } catch (e) {}
	}

	function isLater() {
		try { return sessionStorage.getItem(LATER_KEY) === "1"; } catch (e) { return false; }
	}

	function stepsHtml(steps) {
		const current = steps.findIndex((s) => s.state === "todo");
		return steps
			.map((s, i) => {
				const isCurrent = i === current;
				const finished = s.state !== "todo";
				const status = finished
					? s.state === "done" ? __("Terminé") : __("Sans objet")
					: isCurrent ? __("En cours") : __("Pas configuré");
				const bubble = finished || isCurrent ? GREEN : "#e5e7eb";
				const color = finished || isCurrent ? "#fff" : "#6b7280";
				const mark = finished ? "✓" : String(i);
				const line = i < steps.length - 1
					? `<div style="width:2px;height:22px;background:#e5e7eb;margin:2px 0 2px 13px"></div>`
					: "";
				return `
					<div class="sitiame-ob-step" data-key="${s.key}" style="display:flex;gap:14px;align-items:flex-start;cursor:pointer">
						<div style="flex:none;width:28px;height:28px;border-radius:50%;background:${bubble};color:${color};
							display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px">${mark}</div>
						<div>
							<div style="font-size:11px;color:${isCurrent || finished ? GREEN : "#9ca3af"}">${status}</div>
							<div style="font-weight:600;color:var(--text-color)">${frappe.utils.escape_html(s.label)}</div>
						</div>
					</div>${line}`;
			})
			.join("");
	}

	function showMain(status) {
		if (!status || !status.show) return;
		const current = status.steps.find((s) => s.state === "todo");
		const d = new frappe.ui.Dialog({
			title: __("Configuration du compte"),
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: __("Continuer") + " →",
			primary_action() {
				d.hide();
				openStep(current.key, status);
			},
			secondary_action_label: __("Plus tard"),
			secondary_action() {
				if (!status.preview) later();
				d.hide();
			},
		});
		d.fields_dict.body.$wrapper.html(`
			<p style="text-align:center;color:var(--text-muted);margin-bottom:18px">
				${__("Cliquez sur « Continuer » pour poursuivre la configuration de votre compte {0}", [
					`<b>${frappe.utils.escape_html(status.company)}</b>`,
				])}
			</p>
			<div style="padding:0 8px">${stepsHtml(status.steps)}</div>`);
		d.fields_dict.body.$wrapper.find(".sitiame-ob-step").on("click", function () {
			d.hide();
			openStep($(this).data("key"), status);
		});
		d.$wrapper.find(".modal-footer .standard-actions").css({ display: "flex", "flex-direction": "column", width: "100%", gap: "6px" });
		d.get_primary_btn().css({ order: 1, background: GREEN, "border-color": GREEN, width: "100%", padding: "10px", "font-size": "15px" });
		d.get_secondary_btn().css({ order: 2, background: "none", border: "none", color: "var(--text-muted)", width: "100%" });
		d.show();
	}

	// Preview (staff demo): steps move on screen only, nothing is sent.
	function previewDone(status, key, state) {
		status.steps.forEach((s) => { if (s.key === key) s.state = state; });
		status.show = status.steps.some((s) => s.state === "todo");
		frappe.show_alert({ message: __("Aperçu : rien n'a été enregistré"), indicator: "blue" });
		refresh(status);
	}

	function refresh(status) {
		if (status && status.show) showMain(status);
		else if (status) frappe.show_alert({ message: __("Configuration du compte terminée"), indicator: "green" });
	}

	function call(method, args, done) {
		frappe.call({
			method: API + method,
			args: args,
			freeze: true,
			freeze_message: __("Enregistrement..."),
			callback: (r) => r.message && done(r.message),
		});
	}

	function skipButton(d, key, status) {
		d.set_secondary_action_label(__("Je n'en ai pas"));
		d.set_secondary_action(() => {
			frappe.confirm(__("Confirmer que vous n'avez rien à déclarer pour cette étape ?"), () => {
				d.hide();
				if (status.preview) return previewDone(status, key, "skipped");
				call("skip_step", { step: key }, refresh);
			});
		});
	}

	const DATE_FIELD = {
		fieldtype: "Date",
		fieldname: "posting_date",
		label: __("Date de démarrage (date du solde)"),
		default: frappe.datetime.get_today(),
		reqd: 1,
	};

	const STEP_FORMS = {
		produits: {
			title: __("Créer les produits/services"),
			intro: __("Ajoutez ce que vous vendez. Cochez « Stocké » pour un produit physique dont vous suivez le stock."),
			fields: [
				{
					fieldtype: "Table",
					fieldname: "rows",
					label: __("Produits et services"),
					in_place_edit: true,
					data: [{}],
					fields: [
						{ fieldtype: "Data", fieldname: "item_name", label: __("Nom"), in_list_view: 1, reqd: 1, columns: 5 },
						{ fieldtype: "Check", fieldname: "is_stock_item", label: __("Stocké"), in_list_view: 1, columns: 1 },
						{ fieldtype: "Currency", fieldname: "rate", label: __("Prix de vente"), in_list_view: 1, columns: 3 },
					],
				},
			],
			method: "save_products",
			args: (v) => ({ rows: v.rows || [] }),
		},
		stocks: {
			title: __("Enregistrer les stocks disponibles"),
			intro: __("Quantités en stock aujourd'hui et leur coût unitaire d'achat."),
			fields: [
				DATE_FIELD,
				{
					fieldtype: "Table",
					fieldname: "rows",
					label: __("Stocks"),
					in_place_edit: true,
					data: [{}],
					fields: [
						{
							fieldtype: "Link", fieldname: "item_code", label: __("Article"), options: "Item",
							in_list_view: 1, reqd: 1, columns: 4,
							get_query: () => ({ filters: { is_stock_item: 1, disabled: 0 } }),
						},
						{ fieldtype: "Float", fieldname: "qty", label: __("Quantité"), in_list_view: 1, reqd: 1, columns: 2 },
						{ fieldtype: "Currency", fieldname: "valuation_rate", label: __("Coût unitaire"), in_list_view: 1, reqd: 1, columns: 3 },
					],
				},
			],
			method: "save_stock",
			args: (v) => ({ rows: v.rows || [], posting_date: v.posting_date }),
		},
		creances: {
			title: __("Enregistrer les créances en cours"),
			intro: __("Ce que vos clients vous doivent encore (factures non encaissées)."),
			fields: [DATE_FIELD, partyTable("Customer", __("Client"))],
			method: "save_receivables",
			args: (v) => ({ rows: v.rows || [], posting_date: v.posting_date }),
		},
		dettes: {
			title: __("Enregistrer les dettes en cours"),
			intro: __("Ce que vous devez encore à vos fournisseurs (factures non payées)."),
			fields: [DATE_FIELD, partyTable("Supplier", __("Fournisseur"))],
			method: "save_payables",
			args: (v) => ({ rows: v.rows || [], posting_date: v.posting_date }),
		},
		tresorerie: {
			title: __("Enregistrer le solde de votre trésorerie"),
			intro: __("L'argent disponible aujourd'hui : caisse, banque et autres cash (Mobile Money)."),
			fields: [
				DATE_FIELD,
				{ fieldtype: "Currency", fieldname: "caisse", label: __("Caisse (espèces)") },
				{ fieldtype: "Currency", fieldname: "banque", label: __("Banque") },
				{ fieldtype: "Currency", fieldname: "mobile_money", label: __("Mobile Money / autres cash") },
			],
			method: "save_cash",
			args: (v) => ({
				amounts: { caisse: v.caisse, banque: v.banque, mobile_money: v.mobile_money },
				posting_date: v.posting_date,
			}),
		},
	};

	function partyTable(doctype, label) {
		return {
			fieldtype: "Table",
			fieldname: "rows",
			label: label + "s",
			in_place_edit: true,
			data: [{}],
			fields: [
				{ fieldtype: "Link", fieldname: "party", label: label, options: doctype, in_list_view: 1, reqd: 1, columns: 3 },
				{ fieldtype: "Currency", fieldname: "amount", label: __("Montant restant dû"), in_list_view: 1, reqd: 1, columns: 2 },
				{ fieldtype: "Date", fieldname: "due_date", label: __("Échéance"), in_list_view: 1, columns: 2 },
				{ fieldtype: "Data", fieldname: "reference", label: __("Réf. facture"), in_list_view: 1, columns: 2 },
			],
		};
	}

	function openStep(key, status) {
		const form = STEP_FORMS[key];
		if (!form) return;
		const d = new frappe.ui.Dialog({
			title: form.title,
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "intro" }].concat(form.fields),
			primary_action_label: __("Enregistrer"),
			primary_action(values) {
				if (status.preview) {
					d.hide();
					return previewDone(status, key, "done");
				}
				call(form.method, form.args(values), (r) => {
					d.hide();
					refresh(r.status);
				});
			},
		});
		d.fields_dict.intro.$wrapper.html(`<p style="color:var(--text-muted)">${form.intro}</p>`);
		if (key !== "produits") skipButton(d, key, status);
		d.get_primary_btn().css({ background: GREEN, "border-color": GREEN });
		d.show();
	}

	sitiame.open_onboarding = function () {
		frappe.call({ method: API + "get_status", callback: (r) => showMain(r.message) });
	};

	$(document).on("app_ready", function () {
		if (frappe.session.user === "Administrator") return;
		frappe.call({
			method: API + "get_status",
			callback: (r) => {
				if (r.message && (r.message.preview || !isLater())) showMain(r.message);
			},
		});
	});
})();
