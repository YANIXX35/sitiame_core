// Injects the left branding panel on the login page (see sitiame_login.css
// for the actual restyle) and adds an "eyebrow" line above the native
// "Sign In" heading -- same DOM-hook pattern as login_signup_link.js
// (detect via #page-login, not the URL, since the login form can render
// at "/" or "/login").
(function () {
	function inject() {
		if (!document.getElementById("page-login")) return;
		if (document.getElementById("sitiame-login-hero")) return;

		var hero = document.createElement("div");
		hero.id = "sitiame-login-hero";
		hero.innerHTML =
			'<img class="sitiame-hero-bg" src="https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800&h=1000&fit=crop" alt="">' +
			'<div class="sitiame-hero-overlay"></div>' +
			'<div class="sitiame-hero-content">' +
			'<div class="sitiame-hero-logo"><img src="/files/sitiame-capital-logo.png" alt="Logo Sitiame Capital"></div>' +
			"<h2>Sitiame Capital</h2>" +
			'<p class="sitiame-hero-tagline">Accedez a votre espace professionnel securise. Une plateforme moderne et performante pour gerer vos activites.</p>' +
			"</div>" +
			'<div class="sitiame-hero-features">' +
			"<div>" +
			'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>' +
			"<span>Authentification securisee</span>" +
			"</div><div>" +
			'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>' +
			"<span>Interface moderne et intuitive</span>" +
			"</div><div>" +
			'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>' +
			"<span>Support 24/7 disponible</span>" +
			"</div></div>";

		document.body.insertBefore(hero, document.body.firstChild);

		var headText = document.querySelector(".page-card-head-text");
		if (headText && !headText.querySelector(".sitiame-eyebrow")) {
			var eyebrow = document.createElement("span");
			eyebrow.className = "sitiame-eyebrow";
			eyebrow.textContent = "Veuillez entrer vos identifiants";
			headText.insertBefore(eyebrow, headText.firstChild);
		}
	}

	document.addEventListener("DOMContentLoaded", inject);
	setTimeout(inject, 300);
	setTimeout(inject, 1000);
})();
