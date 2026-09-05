#!/usr/bin/env bash
# fetch_all_usage() treats an existing cache file as authoritative forever --
# it never re-fetches on its own. Since Pikalytics' own data refreshes
# monthly, this wrapper clears the raw cache before each scheduled run so the
# timer actually pulls fresh numbers instead of reporting 100% cache hits.
set -euo pipefail
cd /opt/pikarag
rm -rf data/raw_pikalytics
.venv/bin/python -m pipeline.refresh_pikalytics_job
