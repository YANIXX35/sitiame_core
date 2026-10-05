// Installable app (sitiame_core/pwa.py): head tags, service worker, and a
// one-time install banner for logged-in users -- the browser's own prompt
// on Android/desktop, a "Partager > Sur l'ecran d'accueil" hint on iPhone
// (Safari has no install prompt). Loaded on the desk and on the website
// pages (login), so it never relies on desk-only helpers.
(function () {
	if (window.sitiame_pwa_loaded) return;
	window.sitiame_pwa_loaded = true;

	var ICONS = "/assets/sitiame_core/pwa";
	var DISMISSED_KEY = "sitiame_install_prompt_dismissed";
	var t = window.__ || function (text) {
		return text;
	};

	function headTag(tag, key, attrs) {
		var el = document.head.querySelector(tag + "[" + key + "='" + attrs[key] + "']");
		if (!el) el = document.head.appendChild(document.createElement(tag));
		Object.keys(attrs).forEach(function (name) {
			el.setAttribute(name, attrs[name]);
		});
	}

	headTag("link", "rel", { rel: "manifest", href: "/manifest.webmanifest" });
	headTag("link", "rel", { rel: "apple-touch-icon", href: ICONS + "/apple-touch-icon.png" });
	headTag("meta", "name", { name: "theme-color", content: "#05157c" });
	headTag("meta", "name", { name: "apple-mobile-web-app-title", content: "Sitiame" });
	headTag("meta", "name", { name: "apple-mobile-web-app-capable", content: "yes" });

	if ("serviceWorker" in navigator) {
		navigator.serviceWorker.register("/sitiame-sw.js").catch(function () {});

		// When a new service worker activates it posts SW_UPDATED to all open
		// windows. Show a non-blocking "Mise à jour disponible" banner so
		// installed-PWA users get the new version without having to know why
		// the app looks stale. We reload immediately after the user confirms
		// (or after 60 s if they ignore it) -- the ERP saves everything
		// server-side, so a reload does not lose work.
		navigator.serviceWorker.addEventListener("message", function (event) {
			if (!event.data || event.data.type !== "SW_UPDATED") return;
			if (document.getElementById("sitiame-update-banner")) return;

			var wrap = document.createElement("div");
			wrap.id = "sitiame-update-banner";
			wrap.style.cssText =
				"position:fixed;left:0;right:0;top:0;z-index:9999;display:flex;align-items:center;gap:10px;" +
				"padding:10px 14px;background:#0a3d62;color:#fff;font-size:14px;line-height:1.35;" +
				"box-shadow:0 4px 14px rgba(0,0,0,.22);";

			var msg = document.createElement("span");
			msg.style.flex = "1";
			msg.textContent = t("Une mise à jour de Sitiame est disponible.");

			var btn = document.createElement("button");
			btn.type = "button";
			btn.textContent = t("Recharger");
			btn.style.cssText =
				"flex:none;border:none;border-radius:6px;padding:7px 14px;" +
				"background:#d4af37;color:#05157c;font-weight:700;font-size:13px;cursor:pointer;";
			btn.addEventListener("click", function () { window.location.reload(); });

			var close = document.createElement("button");
			close.type = "button";
			close.setAttribute("aria-label", t("Fermer"));
			close.innerHTML = "&times;";
			close.style.cssText =
				"flex:none;border:none;background:none;color:#fff;font-size:22px;line-height:1;padding:0 4px;cursor:pointer;";
			close.addEventListener("click", function () { wrap.remove(); });

			wrap.appendChild(msg);
			wrap.appendChild(btn);
			wrap.appendChild(close);
			document.body.appendChild(wrap);

			// Auto-reload after 60 s if the user ignores the banner — the
			// ERP is server-side so no unsaved work is lost.
			setTimeout(function () {
				if (document.getElementById("sitiame-update-banner")) {
					window.location.reload();
				}
			}, 60000);
		});
	}

	function dismissed() {
		try {
			return window.localStorage.getItem(DISMISSED_KEY) === "1";
		} catch (e) {
			return false;
		}
	}

	function standalone() {
		return (
			(window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
			window.navigator.standalone === true
		);
	}

	function loggedIn() {
		return !!(window.frappe && frappe.session && frappe.session.user && frappe.session.user !== "Guest");
	}

	var banner = null;

	function hide() {
		if (banner) banner.remove();
		banner = null;
		document.body.classList.remove("sitiame-install-banner-shown");
	}

	function dismiss() {
		try {
			window.localStorage.setItem(DISMISSED_KEY, "1");
		} catch (e) {
			// private browsing: the banner simply comes back next time
		}
		hide();
	}

	function show(text, actionLabel, onAction) {
		if (banner || dismissed() || standalone() || !loggedIn()) return;
		banner = document.createElement("div");
		banner.id = "sitiame-install-banner";
		// z-index under Frappe's dialogs (1050): it used to cover their buttons
		banner.style.cssText =
			"position:fixed;left:0;right:0;bottom:0;z-index:1041;display:flex;align-items:center;gap:10px;" +
			"padding:12px 14px;background:#05157c;color:#fff;font-size:14px;line-height:1.35;" +
			"box-shadow:0 -4px 14px rgba(0,0,0,.18);";

		var icon = document.createElement("img");
		icon.src = ICONS + "/icon-192.png";
		icon.alt = "";
		icon.style.cssText = "width:36px;height:36px;border-radius:8px;background:#fff;flex:none;";

		var text_el = document.createElement("span");
		text_el.style.cssText = "flex:1;";
		text_el.textContent = text;

		banner.appendChild(icon);
		banner.appendChild(text_el);

		if (actionLabel) {
			var action = document.createElement("button");
			action.type = "button";
			action.textContent = actionLabel;
			action.style.cssText =
				"flex:none;border:none;border-radius:6px;padding:8px 14px;background:#d4af37;color:#05157c;font-weight:700;font-size:14px;";
			action.addEventListener("click", onAction);
			banner.appendChild(action);
		}

		var close = document.createElement("button");
		close.type = "button";
		close.setAttribute("aria-label", t("Fermer"));
		close.innerHTML = "&times;";
		close.style.cssText = "flex:none;border:none;background:none;color:#fff;font-size:24px;line-height:1;padding:0 4px;";
		close.addEventListener("click", dismiss);
		banner.appendChild(close);

		document.body.appendChild(banner);
		document.body.classList.add("sitiame-install-banner-shown");
	}

	var deferredPrompt = null;

	function offerInstall() {
		if (deferredPrompt) {
			show(t("Installez Sitiame sur cet appareil pour l'ouvrir comme une application."), t("Installer"), function () {
				var promptEvent = deferredPrompt;
				deferredPrompt = null;
				promptEvent.prompt();
				promptEvent.userChoice.then(function (choice) {
					if (choice.outcome === "accepted") dismiss();
					else hide();
				});
			});
		} else if (/iphone|ipad|ipod/i.test(window.navigator.userAgent)) {
			show(t("Pour installer Sitiame : touchez Partager puis « Sur l'écran d'accueil »."));
		}
	}

	window.addEventListener("beforeinstallprompt", function (event) {
		event.preventDefault();
		deferredPrompt = event;
		offerInstall();
	});
	window.addEventListener("appinstalled", dismiss);

	// the session may not be ready yet when the prompt event fires
	if (window.jQuery) {
		window.jQuery(document).on("app_ready", function () {
			setTimeout(offerInstall, 3000);
		});
	}
	setTimeout(offerInstall, 4000);
})();
