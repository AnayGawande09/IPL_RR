#!/bin/sh
# Reproduce the full pipeline (pure Python 3 standard library, ~4 minutes).
# usage: sh run_all.sh "<data folder: the data pack with the updated ball_by_ball.csv>"
set -e
DATA="$1"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/out"
python -I "$HERE/step1_preprocess.py" "$DATA" "$OUT"
python -I "$HERE/step2_winprob.py" "$OUT"
python -I "$HERE/step3_pressure.py" "$OUT"
for m in main ipl recent alt li2; do python -I "$HERE/step4_ratings.py" "$OUT" $m > "$OUT/run_$m.txt"; done
python -I "$HERE/step5_final.py" "$OUT"
python -I "$HERE/step6_rr_fit.py" "$DATA" "$OUT"
for m in pre25 min40 min100; do python -I "$HERE/step4_ratings.py" "$OUT" $m > "$OUT/run_$m.txt"; done
python -I "$HERE/step7_audit.py" "$DATA" "$OUT" > "$OUT/run_audit.txt"
python -I "$HERE/step8_rr_backlist.py" "$OUT" > "$OUT/run_backlist.txt"
(cd "$HERE" && python -I compare.py > "$OUT/run_compare.txt")
python -I "$HERE/make_report.py" "$OUT" "$HERE/../report/SupeRR_Pressure_Report.html"
python -I "$HERE/make_summary.py" "$OUT" "$HERE/../report/SupeRR_Judges_Summary.html"
python -I "$HERE/build_dashboard.py" "$OUT" "$HERE/../report/dashboard.html"
cd "$HERE" && python -I evidence.py "$DATA"
