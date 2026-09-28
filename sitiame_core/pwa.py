# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Installable app (PWA) for the ERPNext desk: the web app manifest and
the service worker, served at the site root through the page_renderer hook
-- a service worker only controls the pages under its own path, and
Frappe's static www pages refuse .js/.json files.

The service worker never caches business data: pages and API calls always
go to the network (an ERP must show live figures, and a lost phone must
not hold the books). It keeps versioned front-end files and an offline
page, nothing else.
"""

import json

from werkzeug.wrappers import Response

THEME_COLOR = "#05157c"
ICONS = "/assets/sitiame_core/pwa"
OFFLINE_URL = f"{ICONS}/offline.html"

MANIFEST = {
	"id": "/desk",
	"name": "Sitiame Capital",
	"short_name": "Sitiame",
	"description": "Comptabilité, facturation, stock et financement des PME",
	"lang": "fr",
	"start_url": "/desk",
	"scope": "/",
	"display": "standalone",
	"orientation": "any",
	"theme_color": THEME_COLOR,
	"background_color": "#ffffff",
	"icons": [
		{"src": f"{ICONS}/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
		{"src": f"{ICONS}/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
		{"src": f"{ICONS}/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
	],
}

SERVICE_WORKER = (
	"""// Sitiame Capital service worker (sitiame_core/pwa.py). Never caches
// business data: pages and API calls always go to the network.
const CACHE = "sitiame-v2";
const OFFLINE_URL = "%(offline)s";
// Files whose URL changes with their content -- Frappe's bundles carry an
// UPPERCASE hash (frappe-web.bundle.B64X257C.js), hence no "i" flag: a
// plain "sitiame-assistant.js" must not pass for one -- and fonts: safe
// to serve from the cache first.
const VERSIONED = /[.-][A-Z0-9]{8,}\\.(js|css)$|\\.(woff2?|ttf)$/;

self.addEventListener("install", (event) => {
	event.waitUntil(
		caches.open(CACHE).then((cache) => cache.addAll([OFFLINE_URL, "%(icon)s"])).then(() => self.skipWaiting())
	);
});

self.addEventListener("activate", (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
			.then(() => self.clients.claim())
	);
});

self.addEventListener("fetch", (event) => {
	const request = event.request;
	if (request.method !== "GET") return;
	const url = new URL(request.url);
	if (url.origin !== self.location.origin) return;

	if (request.mode === "navigate") {
		event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
		return;
	}
	// Anything else (API, unversioned scripts and images) is left to the
	// browser: its own HTTP cache serves unversioned assets without a round
	// trip, which routing them through here made slower on a phone.
	if (!url.pathname.startsWith("/assets/") || !VERSIONED.test(url.pathname)) return;

	event.respondWith(
		caches.open(CACHE).then((cache) =>
			cache.match(request).then(
				(hit) =>
					hit ||
					fetch(request).then((response) => {
						if (response.ok) cache.put(request, response.clone());
						return response;
					})
			)
		)
	);
});
"""
	% {"offline": OFFLINE_URL, "icon": f"{ICONS}/icon-192.png"}
)

_ROUTES = {
	"manifest.webmanifest": ("application/manifest+json", lambda: json.dumps(MANIFEST, ensure_ascii=False)),
	"sitiame-sw.js": ("application/javascript", lambda: SERVICE_WORKER),
}


class PWARenderer:
	"""page_renderer hook: Frappe tries it before its own renderers."""

	def __init__(self, path=None, http_status_code=None):
		self.path = (path or "").strip("/ ")
		self.http_status_code = http_status_code or 200

	def can_render(self):
		return self.path in _ROUTES

	def render(self):
		mimetype, body = _ROUTES[self.path]
		response = Response(body(), mimetype=mimetype)
		# a new manifest/worker must be picked up on the next deploy
		response.headers["Cache-Control"] = "no-cache"
		if self.path == "sitiame-sw.js":
			response.headers["Service-Worker-Allowed"] = "/"
		return response
