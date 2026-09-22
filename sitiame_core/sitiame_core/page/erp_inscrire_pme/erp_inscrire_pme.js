frappe.pages["erp-inscrire-pme"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Inscrire une PME"),
		single_column: true,
	});

	var $intro = $(
		"<p class='text-muted' style='padding:0 15px;'>" +
			__(
				"Crée directement un compte entreprise sur PME360 (comme si la PME s'inscrivait elle-même), avec provisionnement automatique de sa société sur ERPNext."
			) +
			"</p>"
	).appendTo(page.body);

	var $body = $(
		"<div style='padding:0 15px;max-width:640px;'>" +
			"<div class='row g-3'>" +
			"<div class='col-sm-6'><label class='control-label'>" + __("Nom du contact") + " *</label>" +
			"<input class='form-control pme-name' required></div>" +
			"<div class='col-sm-6'><label class='control-label'>" + __("E-mail") + " *</label>" +
			"<input type='email' class='form-control pme-email' required></div>" +
			"<div class='col-sm-6'><label class='control-label'>" + __("Téléphone") + "</label>" +
			"<input class='form-control pme-phone'></div>" +
			"<div class='col-sm-6'><label class='control-label'>" + __("Société") + " *</label>" +
			"<input class='form-control pme-company-name' required></div>" +
			"<div class='col-sm-6'><label class='control-label'>" + __("NIF") + "</label>" +
			"<input class='form-control pme-tax-id'></div>" +
			"<div class='col-sm-6'><label class='control-label'>" + __("RCCM") + "</label>" +
			"<input class='form-control pme-rccm'></div>" +
			"<div class='col-sm-6'><label class='control-label'>" + __("Ville") + "</label>" +
			"<input class='form-control pme-city'></div>" +
			"<div class='col-sm-6'><label class='control-label'>" + __("Mot de passe (optionnel)") + "</label>" +
			"<input type='password' class='form-control pme-password' placeholder='" + __("défaut : SITIAME2026!") + "'></div>" +
			"</div>" +
			"<button class='btn btn-primary pme-submit' style='margin-top:18px;'>" + __("Inscrire la PME") + "</button>" +
			"<div class='pme-result' style='margin-top:15px;'></div>" +
			"</div>"
	).appendTo(page.body);

	$body.find(".pme-submit").on("click", function () {
		var payload = {
			name: $body.find(".pme-name").val(),
			email: $body.find(".pme-email").val(),
			phone: $body.find(".pme-phone").val(),
			company_name: $body.find(".pme-company-name").val(),
			company_tax_id: $body.find(".pme-tax-id").val(),
			rccm: $body.find(".pme-rccm").val(),
			city: $body.find(".pme-city").val(),
			password: $body.find(".pme-password").val(),
		};

		if (!payload.name || !payload.email || !payload.company_name) {
			frappe.show_alert({ message: __("Nom, e-mail et société sont obligatoires."), indicator: "orange" });
			return;
		}

		var $btn = $body.find(".pme-submit");
		$btn.prop("disabled", true).text(__("Inscription en cours..."));
		$body.find(".pme-result").html("");

		frappe.call({
			method: "sitiame_core.api.register_pme_from_erpnext",
			args: payload,
		}).then(function (r) {
			var data = r.message || {};
			$body.find(".pme-result").html(
				"<div class='alert alert-success'>" +
					"<b>" + __("PME inscrite avec succès.") + "</b><br>" +
					__("E-mail") + " : " + frappe.utils.escape_html(data.email || payload.email) + "<br>" +
					__("Mot de passe") + " : <code>" + frappe.utils.escape_html(data.password || "") + "</code><br>" +
					"<span class='text-muted'>" + __("Transmettez ces identifiants à la PME ; le mot de passe devra être changé à la première connexion.") + "</span>" +
					"</div>"
			);
			$body.find("input").val("");
		}).catch(function () {
			// L'erreur est déjà affichée par frappe.call via son propre dialogue.
		}).always(function () {
			$btn.prop("disabled", false).text(__("Inscrire la PME"));
		});
	});
};
