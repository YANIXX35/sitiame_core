#!/usr/bin/env bash
# Deploy sitiame_core on the production VPS (run as root on the server:
#   bash /root/sitiame_core_deploy.sh
# after copying this file there).
#
# Why this exists: the stack runs on a local image (sitiame/erpnext:current)
# that already contains frappe, erpnext, hrms and sitiame_core. Updating the
# code with a plain `git pull` inside the containers would be lost the next
# time they are recreated, so every deploy bakes the new code into a new
# image and recreates all ERPNext services from it:
#   1. pull sitiame_core in the backend container
#   2. migrate + build assets + clear cache
#   3. commit the backend container as a new dated image, tag it :current
#   4. recreate every ERPNext service from :current
#   5. health check, and keep only the last 3 dated images
set -euo pipefail

PROJECT=sitiame-prod
COMPOSE=/root/sitiame-prod-compose.yml
SITE=erp.sitiame-capital.com
BACKEND=${PROJECT}-backend-1
BENCH=/home/frappe/frappe-bench
SERVICES="backend frontend websocket scheduler queue-short queue-long"

echo "== 1. git pull"
docker exec -w "$BENCH/apps/sitiame_core" "$BACKEND" bash -c \
	'm=$(git ls-files -m | grep "\.pyc$" || true); [ -n "$m" ] && git checkout -- $m; git pull --ff-only origin master'
REV=$(docker exec -w "$BENCH/apps/sitiame_core" "$BACKEND" git rev-parse --short HEAD)
echo "   sitiame_core at $REV"

echo "== 2. migrate + build"
docker exec -w "$BENCH" "$BACKEND" bench --site "$SITE" migrate
docker exec -w "$BENCH" "$BACKEND" bench build --app sitiame_core
# hooks.py is cached in Redis ("app_hooks") and migrate does not drop it:
# without this, a new hook (page_renderer, doctype_list_js...) stays
# inactive after deploy (seen 2026-09-28), and 404s cached before the
# deploy keep being served.
docker exec -w "$BENCH" "$BACKEND" bench --site "$SITE" clear-cache

echo "== 3. bake image"
TAG="sitiame/erpnext:$(date -u +%Y%m%d-%H%M)-$REV"
docker commit --pause=false -m "deploy sitiame_core $REV" "$BACKEND" "$TAG" >/dev/null
docker tag "$TAG" sitiame/erpnext:current
echo "   $TAG -> sitiame/erpnext:current"

echo "== 4. recreate services"
docker compose -p "$PROJECT" -f "$COMPOSE" up -d --force-recreate $SERVICES

echo "== 5. health check"
for i in $(seq 1 30); do
	if docker exec -w "$BENCH" "$BACKEND" bench --site "$SITE" execute frappe.ping >/dev/null 2>&1; then
		echo "   site OK"
		break
	fi
	[ "$i" = 30 ] && { echo "   SITE NOT RESPONDING - roll back: docker tag <previous image> sitiame/erpnext:current, then rerun step 4"; exit 1; }
	sleep 5
done
docker exec -w "$BENCH/apps/sitiame_core" "$BACKEND" git log --oneline -1

# keep the 3 most recent dated images (layers shared with :current stay)
docker image ls sitiame/erpnext --format '{{.Tag}}' | grep -E '^[0-9]{8}-' | sort -r | tail -n +4 \
	| xargs -r -I{} docker image rm "sitiame/erpnext:{}" >/dev/null 2>&1 || true
echo "== done ($REV)"
