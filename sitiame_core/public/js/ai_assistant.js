// Floating AI assistant widget for ERPNext desk, ported from PME360's
// "Assistant IA Admin" (Google Gemini) -- see gemini_assistant.py and
// api.py::chat_with_assistant. Only shown to System Manager / Accounts
// Manager (server also enforces this on every call).
(function () {
	var QUICK_ACTIONS = [
		"Resume de la situation aujourd'hui",
		"Analyse comptable rapide",
		"Actions prioritaires",
	];

	function allowed() {
		var roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
		return roles.indexOf("System Manager") !== -1 || roles.indexOf("Accounts Manager") !== -1;
	}

	function buildWidget() {
		if (document.getElementById("sitiame-ai-toggle")) return;

		var toggle = document.createElement("button");
		toggle.id = "sitiame-ai-toggle";
		toggle.innerHTML = "&#128172;";
		toggle.style.cssText =
			"position:fixed;bottom:24px;right:24px;z-index:9999;width:52px;height:52px;border-radius:50%;" +
			"background:#2563eb;color:#fff;border:none;font-size:22px;box-shadow:0 4px 14px rgba(37,99,235,.4);cursor:pointer;";

		var panel = document.createElement("div");
		panel.id = "sitiame-ai-panel";
		panel.style.cssText =
			"position:fixed;bottom:88px;right:24px;z-index:9999;width:360px;max-width:90vw;height:480px;" +
			"max-height:70vh;background:#fff;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.2);" +
			"display:none;flex-direction:column;overflow:hidden;border:1px solid #e2e8f0;";

		panel.innerHTML =
			"<div style='padding:14px 16px;background:#2563eb;color:#fff;display:flex;justify-content:space-between;align-items:center;'>" +
			"<div><div style='font-weight:700;font-size:14px;'>Assistant IA Admin</div>" +
			"<div style='font-size:11px;opacity:.85;'>Google Gemini</div></div>" +
			"<span id='sitiame-ai-close' style='cursor:pointer;font-size:18px;'>&times;</span></div>" +
			"<div id='sitiame-ai-messages' style='flex:1;overflow-y:auto;padding:12px;font-size:13px;background:#f8fafc;'></div>" +
			"<div id='sitiame-ai-quick' style='display:flex;gap:6px;flex-wrap:wrap;padding:8px 12px;border-top:1px solid #e2e8f0;'></div>" +
			"<div style='display:flex;gap:6px;padding:10px;border-top:1px solid #e2e8f0;'>" +
			"<input id='sitiame-ai-input' type='text' placeholder=\"Ex: Que dois-je traiter en priorite ?\" " +
			"style='flex:1;border:1px solid #cbd5e1;border-radius:8px;padding:8px 10px;font-size:13px;'>" +
			"<button id='sitiame-ai-send' style='background:#2563eb;color:#fff;border:none;border-radius:8px;padding:8px 14px;font-size:13px;cursor:pointer;'>Envoyer</button>" +
			"</div>";

		document.body.appendChild(toggle);
		document.body.appendChild(panel);

		var history = [];
		var $messages = panel.querySelector("#sitiame-ai-messages");
		var $input = panel.querySelector("#sitiame-ai-input");
		var $quick = panel.querySelector("#sitiame-ai-quick");

		function addBubble(role, text) {
			var bubble = document.createElement("div");
			var isUser = role === "user";
			bubble.style.cssText =
				"max-width:85%;margin-bottom:8px;padding:8px 12px;border-radius:10px;white-space:pre-wrap;line-height:1.4;" +
				(isUser
					? "background:#2563eb;color:#fff;margin-left:auto;"
					: "background:#fff;border:1px solid #e2e8f0;color:#0f172a;");
			bubble.textContent = text;
			$messages.appendChild(bubble);
			$messages.scrollTop = $messages.scrollHeight;
		}

		addBubble("assistant", "Bonjour. Je suis ton copilote admin ERPNext. Pose une question sur les erreurs, les paiements, le classement financier ou les priorites.");

		QUICK_ACTIONS.forEach(function (label) {
			var btn = document.createElement("button");
			btn.textContent = label;
			btn.style.cssText =
				"font-size:11px;border:1px solid #cbd5e1;background:#fff;border-radius:20px;padding:5px 10px;cursor:pointer;color:#334155;";
			btn.addEventListener("click", function () {
				send(label);
			});
			$quick.appendChild(btn);
		});

		function send(text) {
			text = (text || $input.value).trim();
			if (!text) return;
			$input.value = "";
			addBubble("user", text);
			history.push({ role: "user", content: text });

			var loading = document.createElement("div");
			loading.textContent = "...";
			loading.style.cssText = "color:#94a3b8;font-size:12px;margin-bottom:8px;";
			$messages.appendChild(loading);
			$messages.scrollTop = $messages.scrollHeight;

			frappe
				.call({
					method: "sitiame_core.api.chat_with_assistant",
					args: { message: text, history: JSON.stringify(history) },
				})
				.then(function (r) {
					loading.remove();
					var data = r.message || {};
					if (data.ok) {
						addBubble("assistant", data.answer);
						history.push({ role: "assistant", content: data.answer });
					} else {
						addBubble("assistant", data.error || "Erreur inconnue.");
					}
				})
				.catch(function () {
					loading.remove();
					addBubble("assistant", "Erreur de connexion a l'assistant.");
				});
		}

		toggle.addEventListener("click", function () {
			panel.style.display = panel.style.display === "flex" ? "none" : "flex";
		});
		panel.querySelector("#sitiame-ai-close").addEventListener("click", function () {
			panel.style.display = "none";
		});
		panel.querySelector("#sitiame-ai-send").addEventListener("click", function () {
			send();
		});
		$input.addEventListener("keydown", function (e) {
			if (e.key === "Enter") send();
		});
	}

	function init() {
		if (!window.frappe || !frappe.boot || !frappe.session || frappe.session.user === "Guest") return;
		if (!allowed()) return;
		buildWidget();
	}

	$(document).on("app_ready", init);
	setTimeout(init, 1500);
})();
