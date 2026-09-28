# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Installable app: manifest + service worker served at the site root
(sitiame_core.pwa), icons, and their hooks."""

import json
import re
from pathlib import Path

import pytest
from PIL import Image

from sitiame_core import hooks, pwa

PUBLIC = Path(__file__).resolve().parents[1] / "sitiame_core" / "public"


def _get(path):
	renderer = pwa.PWARenderer(path)
	assert renderer.can_render()
	return renderer.render()


@pytest.mark.parametrize("path", ["desk", "login", "sw.js", "manifest.json", "api/method/x", ""])
def test_other_paths_are_left_to_frappe(path):
	assert not pwa.PWARenderer(path).can_render()


def test_manifest_is_served_as_a_web_app_manifest():
	response = _get("/manifest.webmanifest")
	assert response.mimetype == "application/manifest+json"
	assert response.headers["Cache-Control"] == "no-cache"
	manifest = json.loads(response.get_data(as_text=True))
	assert manifest["start_url"] == "/desk" and manifest["scope"] == "/"
	assert manifest["display"] == "standalone"
	assert manifest["theme_color"] == "#05157c"


def test_manifest_icons_exist_at_their_declared_size():
	purposes = set()
	for icon in pwa.MANIFEST["icons"]:
		path = PUBLIC / icon["src"].removeprefix("/assets/sitiame_core/")
		width, height = Image.open(path).size
		assert f"{width}x{height}" == icon["sizes"]
		purposes.add(icon["purpose"])
	assert {"any", "maskable"} <= purposes
	assert any(icon["sizes"] == "512x512" for icon in pwa.MANIFEST["icons"])


def test_service_worker_is_served_for_the_whole_site():
	response = _get("sitiame-sw.js")
	assert response.mimetype == "application/javascript"
	assert response.headers["Service-Worker-Allowed"] == "/"
	assert response.headers["Cache-Control"] == "no-cache"
	assert response.get_data(as_text=True) == pwa.SERVICE_WORKER


def test_service_worker_never_touches_business_data():
	sw = pwa.SERVICE_WORKER
	assert 'request.method !== "GET"' in sw
	assert "url.origin !== self.location.origin" in sw
	assert "/api/" not in sw


def test_unversioned_assets_are_left_to_the_browser_cache():
	"""Measured 2026-09-28 (4G + phone CPU): routing the unversioned Sitiame
	scripts through the worker network-first made the desk load slower
	(median 6.4s vs 5.0s without the worker) -- the browser's own HTTP
	cache served them without a round trip. Only navigations and versioned
	assets are intercepted now."""
	sw = pwa.SERVICE_WORKER
	assert 'if (!url.pathname.startsWith("/assets/") || !VERSIONED.test(url.pathname)) return;' in sw
	assert "network first" not in sw.lower()


@pytest.mark.parametrize(
	"path, cached_first",
	[
		("/assets/frappe/dist/js/frappe-web.bundle.B64X257C.js", True),
		("/assets/frappe/dist/css/website.bundle.ABCD1234.css", True),
		("/assets/frappe/fonts/inter.woff2", True),
		# unversioned Sitiame files must always be re-fetched after a deploy
		("/assets/sitiame_core/js/list_download.js", False),
		("/assets/sitiame_core/js/sitiame-assistant.js", False),
		("/assets/sitiame_core/pwa/icon-192.png", False),
	],
)
def test_only_versioned_assets_are_served_cache_first(path, cached_first):
	pattern, flags = re.search(r"const VERSIONED = /(.+)/(\w*);", pwa.SERVICE_WORKER).groups()
	assert bool(re.search(pattern, path, re.IGNORECASE if "i" in flags else 0)) is cached_first


def test_offline_page_is_precached_and_exists():
	assert pwa.OFFLINE_URL in pwa.SERVICE_WORKER
	assert (PUBLIC / pwa.OFFLINE_URL.removeprefix("/assets/sitiame_core/")).is_file()


def test_desk_home_scrolls_to_its_last_row_on_a_phone():
	"""2026-09-28, reproduced in phone emulation: Frappe's desk scroller
	(.main-section) is 100vh -- behind a phone's address bar, the last row
	of tiles was unreachable -- and an open folder had a fixed height with
	scrolling off."""
	css = (PUBLIC / "css" / "sitiame_mobile.css").read_text(encoding="utf-8")
	assert re.search(r"\.main-section\s*{\s*height:\s*100dvh;", css)
	folder_rules = re.findall(r"\.desktop-modal-body\s*{([^}]*)}", css)
	assert any("overflow-y: auto !important" in rule and "height: auto !important" in rule for rule in folder_rules)


def test_hooks_wire_the_pwa():
	assert "sitiame_core.pwa.PWARenderer" in hooks.page_renderer
	assert "/assets/sitiame_core/js/pwa.js" in hooks.app_include_js
	assert "/assets/sitiame_core/js/pwa.js" in hooks.web_include_js
	assert "/assets/sitiame_core/css/sitiame_mobile.css" in hooks.app_include_css
