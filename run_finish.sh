#!/usr/bin/env bash
# run_finish.sh D — [ME] 칸을 채운 research.json으로 마무리(preflight→build→render→gate).
#   예) bash run_finish.sh 2026-09-18
set -e
D="${1:?기준일 필요: YYYY-MM-DD}"
export BRIEF_QUIET=1
cd "$(dirname "$0")"
t0=$(date +%s)
python3 preflight.py research
python3 build.py;               t1=$(date +%s); echo "⏱ build   $((t1-t0))s"
python3 preflight.py text
python3 render.py "brief_${D}.pdf"; t2=$(date +%s); echo "⏱ render  $((t2-t1))s"
python3 gate.py "brief_${D}.pdf"    # 118/118 전면 통과 후에만 제시
