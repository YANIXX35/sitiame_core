frappe.pages["erp-plateforme-utilisateurs"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Utilisateurs de la plateforme"),
		single_column: true,
	});

	var $body = $("<div style='padding:0 15px;margin-top:15px;'></div>").appendTo(page.body);

	function statusLabel(user) {
		if (user.is_premium) return { text: __("Payant"), cls: "success" };
		if (user.premium_trial_ends_at && moment(user.premium_trial_ends_at).isAfter(moment())) {
			var days = moment(user.premium_trial_ends_at).diff(moment(), "days");
			return { text: __("Essai gratuit ({0} j restants)", [days]), cls: "warning" };
		}
		return { text: __("Expire"), cls: "secondary" };
	}

	function fmt(date) {
		return date ? frappe.datetime.str_to_user(frappe.datetime.convert_to_system_tz(date)) : "-";
	}

	function render() {
		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");

		frappe.call({ method: "sitiame_core.api.get_platform_users" })
			.then(function (r) {
				var users = (r.message || {}).users || [];

				if (!users.length) {
					$body.html("<p class='text-muted'>" + __("Aucune PME inscrite.") + "</p>");
					return;
				}

				var html =
					"<table class='table table-bordered bg-white'><thead><tr>" +
					"<th>" + __("Societe") + "</th>" +
					"<th>" + __("Email") + "</th>" +
					"<th>" + __("Statut") + "</th>" +
					"<th>" + __("Fin d'essai gratuit") + "</th>" +
					"<th>" + __("Fin d'abonnement") + "</th>" +
					"<th>" + __("Inscrit le") + "</th>" +
					"<th>" + __("Derniere connexion") + "</th>" +
					"</tr></thead><tbody>";

				users.forEach(function (u) {
					var status = statusLabel(u);
					html +=
						"<tr>" +
						"<td class='fw-bold'>" + frappe.utils.escape_html(u.erpnext_company_name || u.company_name || "-") + "</td>" +
						"<td>" + frappe.utils.escape_html(u.email) + "</td>" +
						"<td><span class='indicator-pill " + status.cls + "'>" + status.text + "</span></td>" +
						"<td>" + fmt(u.premium_trial_ends_at) + "</td>" +
						"<td>" + fmt(u.premium_ends_at) + "</td>" +
						"<td>" + fmt(u.registered_at) + "</td>" +
						"<td>" + (u.last_login_at ? fmt(u.last_login_at) : __("Jamais")) + "</td>" +
						"</tr>";
				});

				html += "</tbody></table>";
				$body.html(html);
			})
			.catch(function () {
				$body.html("<p class='text-danger'>" + __("Impossible de charger les utilisateurs (voir le journal des erreurs).") + "</p>");
			});
	}

	render();
};
