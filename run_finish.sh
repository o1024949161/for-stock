#!/usr/bin/env bash
# run_finish.sh D — ★v62 마무리: 분석 칸 병합 → 사전 린트 → 빌드 → 렌더 → 게이트
#   예) bash run_finish.sh 2026-09-23
set -e
D="${1:?기준일 필요: YYYY-MM-DD}"
cd "$(dirname "$0")"
export BRIEF_QUIET=1
export YF_ASOF="$D"
t0=$(date +%s)
python3 apply_pick.py                    # ★v63 차트 판독 선정(chart_pick.json) → data.json 강화 3+3 · me_pick.json
ls me_*.json >/dev/null 2>&1 && python3 merge_me.py me_*.json
python3 lint_me.py                       # 빈칸·앵커·자리표시자를 빌드 전에(1초) — 게이트 재실행 사이클 제거
python3 preflight.py research
python3 build.py;                   t1=$(date +%s); echo "⏱ build   $((t1-t0))s"
python3 preflight.py text
python3 render.py "brief_${D}.pdf"; t2=$(date +%s); echo "⏱ render  $((t2-t1))s"
python3 gate.py "brief_${D}.pdf"    # 전면 통과 후에만 제시
cp brief_state.json /mnt/user-data/outputs/ 2>/dev/null || true
echo "→ brief_state.json 을 프로젝트 지식에 저장(project_write)할 것 — 다음 회차 채점·리비전의 원천"
