#!/bin/sh
# Separate public-data model (Cricsheet IPL 2008-2026 + auction history 2013-2025). Kept apart from the SupeRR method:
# run it AFTER analysis/run_all.sh, because its last step only COMPARES its predictions with ours.
# usage: sh run_public_model.sh "<data pack dir>"
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PUB="$HERE/../public_data"
python -I "$HERE/pm1_parse.py" "$PUB/cricsheet/ipl_json.zip" "$HERE/out"
python -I "$HERE/pm2_link.py" "$1" "$HERE/out"
python -I "$HERE/pm3_model.py" "$HERE/out" "$PUB/auction" "$HERE/../analysis/out" > "$HERE/out/pm3_log.txt"
python -I "$HERE/../analysis/make_report.py" "$HERE/../analysis/out" "$HERE/../report/SupeRR_Pressure_Report.html"
python -I "$HERE/../analysis/build_dashboard.py" "$HERE/../analysis/out" "$HERE/../report/dashboard.html"
