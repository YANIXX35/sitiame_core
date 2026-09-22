frappe.pages["erp-gerer-menu"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Gérer le menu"),
		single_column: true,
	});

	var $intro = $(
		"<p class='text-muted' style='padding:0 15px;'>" +
			__(
				"Masque des tuiles de la page d'accueil (/desk) et des liens du menu Organisation pour un utilisateur précis, indépendamment de son rôle. Prend effet à sa prochaine connexion."
			) +
			"</p>"
	).appendTo(page.body);

	var $filters = $(
		"<div style='padding:0 15px;max-width:480px;'>" +
			"<label class='control-label'>" + __("Utilisateur") + "</label>" +
			"<select class='form-control gm-user-select'><option value=''>" + __("— Choisir —") + "</option></select>" +
			"</div>"
	).appendTo(page.body);

	var $body = $("<div style='padding:0 15px;max-width:480px;'></div>").appendTo(page.body);

	var allIcons = [];
	var allItems = [];

	function loadUsers() {
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "User",
				filters: { enabled: 1, user_type: "System User" },
				fields: ["name", "full_name"],
				order_by: "full_name asc",
				limit_page_length: 0,
			},
		}).then(function (r) {
			var $select = $filters.find(".gm-user-select");
			(r.message || []).forEach(function (u) {
				$select.append(
					"<option value='" + frappe.utils.escape_html(u.name) + "'>" +
						frappe.utils.escape_html(u.full_name || u.name) + " (" + frappe.utils.escape_html(u.name) + ")" +
						"</option>"
				);
			});
		});
	}

	function loadStructure() {
		return frappe.call({ method: "sitiame_core.api.list_desktop_icons_for_menu_admin" }).then(function (r) {
			allIcons = r.message || [];
			return frappe.call({ method: "sitiame_core.api.list_sidebar_items_for_menu_admin" });
		}).then(function (r) {
			allItems = r.message || [];
		});
	}

	function checklistHtml(cssClass, dataAttr, list, labelKey, hiddenList) {
		var html = "<div>";
		list.forEach(function (row) {
			var value = row[labelKey];
			var checked = hiddenList.indexOf(value) === -1 ? "checked" : "";
			html +=
				"<div class='form-check'>" +
				"<input type='checkbox' class='form-check-input " + cssClass + "' " + dataAttr + "='" +
				frappe.utils.escape_html(value) + "' " + checked + ">" +
				"<label class='form-check-label'>" + frappe.utils.escape_html(row.label) + "</label>" +
				"</div>";
		});
		html += "</div>";
		return html;
	}

	function renderForUser(user) {
		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");

		Promise.all([
			frappe.call({ method: "sitiame_core.api.get_user_hidden_desktop_icons", args: { user: user } }),
			frappe.call({ method: "sitiame_core.api.get_user_hidden_sidebar_items", args: { user: user } }),
		]).then(function (results) {
			var hiddenIcons = results[0].message || [];
			var hiddenItems = results[1].message || [];

			var html = "<h6 style='margin-top:15px;'>" + __("Tuiles de la page d'accueil") + "</h6>";
			html += checklistHtml("gm-icon-checkbox", "data-label", allIcons, "label", hiddenIcons);

			html += "<h6 style='margin-top:20px;'>" + __("Liens du menu Organisation") + "</h6>";
			html += checklistHtml("gm-item-checkbox", "data-link-to", allItems, "link_to", hiddenItems);

			html += "<button class='btn btn-primary gm-save' style='margin-top:15px;'>" + __("Enregistrer") + "</button>";
			html += "<div class='gm-result' style='margin-top:10px;'></div>";

			$body.html(html);

			$body.find(".gm-save").on("click", function () {
				var hiddenIconsToSave = [];
				$body.find(".gm-icon-checkbox").each(function () {
					if (!$(this).is(":checked")) {
						hiddenIconsToSave.push($(this).data("label"));
					}
				});

				var hiddenLinksToSave = [];
				$body.find(".gm-item-checkbox").each(function () {
					if (!$(this).is(":checked")) {
						hiddenLinksToSave.push($(this).data("link-to"));
					}
				});

				Promise.all([
					frappe.call({
						method: "sitiame_core.api.set_user_hidden_desktop_icons",
						args: { user: user, hidden_labels: hiddenIconsToSave },
					}),
					frappe.call({
						method: "sitiame_core.api.set_user_hidden_sidebar_items",
						args: { user: user, hidden_links: hiddenLinksToSave },
					}),
				]).then(function () {
					$body.find(".gm-result").html(
						"<div class='alert alert-success'>" +
							__("Enregistré. Prend effet à la prochaine connexion de cet utilisateur.") +
							"</div>"
					);
				});
			});
		});
	}

	loadUsers();
	loadStructure().then(function () {
		$filters.find(".gm-user-select").on("change", function () {
			var user = $(this).val();
			if (user) {
				renderForUser(user);
			} else {
				$body.html("");
			}
		});
	});
};
