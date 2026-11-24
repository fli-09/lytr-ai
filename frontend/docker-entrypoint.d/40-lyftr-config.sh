#!/bin/sh
# Writes the runtime frontend config from env vars before nginx starts.
set -eu
escaped=$(printf '%s' "${API_BASE_URL:-}" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf 'window.__LYFTR_CONFIG__ = { apiBaseUrl: "%s" };\n' "$escaped" > /usr/share/nginx/html/config.js
echo "lyftr: API_BASE_URL=${API_BASE_URL:-<unset>}"
