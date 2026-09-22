frappe.pages["erp-signalements"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Signalements"),
		single_column: true,
	});

	page.add_button(__("Vider les logs"), function () {
		frappe.confirm(
			__("Vider le fichier de log et supprimer les erreurs deja vues de plus de 7 jours ?"),
			function () {
				frappe.call({ method: "sitiame_core.api.clear_erp_logs" }).then(function () {
					frappe.show_alert({ message: __("Logs vides."), indicator: "green" });
					render();
				});
			}
		);
	});
	page.set_primary_action(__("Actualiser"), render, "refresh");

	var $body = $("<div style='padding:0 15px;'></div>").appendTo(page.body);

	function statCard(label, value, color) {
		return (
			"<div class='col-sm-3' style='margin-bottom:15px;'>" +
			"<div class='card' style='padding:15px;text-align:center;'>" +
			"<div style='font-size:22px;font-weight:600;color:" + (color || "inherit") + ";'>" + value + "</div>" +
			"<div class='text-muted' style='font-size:12px;'>" + label + "</div>" +
			"</div></div>"
		);
	}

	function render() {
		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");

		frappe.call({ method: "sitiame_core.api.get_erp_health_dashboard" }).then(function (r) {
			var data = r.message || {};
			var errors = data.errors || {};
			var db = data.db || {};
			var server = data.server || {};
			var logins = data.logins || {};

			var html = "<div class='row' style='margin-top:10px;'>";
			html += statCard(__("Erreurs non vues"), errors.open || 0, (errors.open || 0) > 0 ? "#d1382c" : "#2b8a3e");
			html += statCard(__("Erreurs (total)"), errors.total || 0);
			html += statCard(__("Connexions reussies"), logins.total_success || 0, "#2b8a3e");
			html += statCard(__("Connexions echouees"), logins.total_failed || 0, (logins.total_failed || 0) > 0 ? "#d1382c" : "inherit");
			html += "</div>";

			html +=
				"<div class='row'>" +
				"<div class='col-sm-6'>" +
				"<h6>" + __("Sante base de donnees") + "</h6>" +
				"<p>" +
				(db.connected
					? "<span class='indicator green'>" + __("Connectee") + "</span>"
					: "<span class='indicator red'>" + __("Deconnectee") + "</span>") +
				" &middot; " + __("Tables") + ": " + (db.table_count || 0) +
				" &middot; " + __("Ping") + ": " + (db.ping_ms || 0) + " ms" +
				(db.error ? "<br><span class='text-danger'>" + frappe.utils.escape_html(db.error) + "</span>" : "") +
				"</p>" +
				"</div>" +
				"<div class='col-sm-6'>" +
				"<h6>" + __("Sante serveur") + "</h6>" +
				"<p>Python " + (server.python_version || "?") +
				" &middot; " + __("Disque libre") + ": " + server.disk_free_gb + " Go / " + server.disk_total_gb + " Go" +
				"</p>" +
				"</div>" +
				"</div>";

			html += "<h6 style='margin-top:15px;'>" + __("Erreurs recentes") + "</h6>";
			if (!(errors.recent || []).length) {
				html += "<p class='text-muted'>" + __("Aucune erreur enregistree.") + "</p>";
			} else {
				html +=
					"<table class='table table-bordered'><thead><tr>" +
					"<th>" + __("Methode") + "</th><th>" + __("Date") + "</th><th>" + __("Statut") + "</th><th></th>" +
					"</tr></thead><tbody>";
				errors.recent.forEach(function (row) {
					html +=
						"<tr>" +
						"<td>" + frappe.utils.escape_html(row.method || "") + "</td>" +
						"<td>" + frappe.datetime.str_to_user(row.creation) + "</td>" +
						"<td>" +
						(row.seen
							? "<span class='indicator grey'>" + __("Vue") + "</span>"
							: "<span class='indicator orange'>" + __("Nouvelle") + "</span>") +
						"</td>" +
						"<td>" +
						"<a href='/app/error-log/" + encodeURIComponent(row.name) + "' class='btn btn-xs btn-default'>" +
						__("Ouvrir") + "</a>" +
						(row.seen
							? ""
							: " <button class='btn btn-xs btn-default erp-mark-seen' data-name='" + row.name + "'>" +
							  __("Marquer vue") + "</button>") +
						"</td>" +
						"</tr>";
				});
				html += "</tbody></table>";
			}

			html += "<h6 style='margin-top:15px;'>" + __("Connexions recentes") + "</h6>";
			if (!(logins.recent || []).length) {
				html += "<p class='text-muted'>" + __("Aucune connexion enregistree.") + "</p>";
			} else {
				html +=
					"<table class='table table-bordered'><thead><tr>" +
					"<th>" + __("Utilisateur") + "</th><th>" + __("Action") + "</th><th>" + __("Statut") + "</th><th>" + __("Date") + "</th>" +
					"</tr></thead><tbody>";
				logins.recent.forEach(function (row) {
					html +=
						"<tr>" +
						"<td>" + frappe.utils.escape_html(row.user || "") + "</td>" +
						"<td>" + frappe.utils.escape_html(row.operation || "") + "</td>" +
						"<td>" +
						(row.status === "Success"
							? "<span class='indicator green'>" + __("Succes") + "</span>"
							: "<span class='indicator red'>" + __("Echec") + "</span>") +
						"</td>" +
						"<td>" + frappe.datetime.str_to_user(row.creation) + "</td>" +
						"</tr>";
				});
				html += "</tbody></table>";
			}

			html +=
				"<h6 style='margin-top:15px;'>" + __("Journal applicatif") + "</h6>" +
				"<pre style='max-height:300px;overflow:auto;background:#f6f6f6;padding:10px;font-size:11px;'>" +
				frappe.utils.escape_html(data.log_tail || "") +
				"</pre>";

			$body.html(html);

			$body.find(".erp-mark-seen").on("click", function () {
				var name = $(this).data("name");
				frappe.call({ method: "sitiame_core.api.mark_error_log_seen", args: { name: name } }).then(render);
			});
		});
	}

	render();
};
