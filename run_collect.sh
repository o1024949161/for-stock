#!/usr/bin/env bash
# run_collect.sh D MODE — 수집 단계(fetch→mkchart→prefill)를 조용히·병렬로 한 번에.
# 이걸 백그라운드로 돌려두고 그 사이 마감시황/FOMC/촉매/휴장 웹조사를 «병렬»로 진행한다.
# 끝나면 research.json의 [ME] 분석칸만 채우고 run_finish.sh 로 마무리한다.
#   예) nohup bash run_collect.sh 2026-09-18 마감 > _collect.log 2>&1 &
set -e
D="${1:?기준일 필요: YYYY-MM-DD}"; MODE="${2:-마감}"
export BRIEF_QUIET=1                 # 대용량 진단 print 억제(토큰 절감·내용 무관)
export YF_CONC="${YF_CONC:-8}"       # 동시 수집 스레드
export YF_MIN_GAP="${YF_MIN_GAP:-0.08}"
cd "$(dirname "$0")"
t0=$(date +%s)
python3 fetch_all.py "$D";  t1=$(date +%s); echo "⏱ fetch_all $((t1-t0))s"
python3 mkchart.py;         t2=$(date +%s); echo "⏱ mkchart  $((t2-t1))s"
python3 prefill.py "$MODE"; t3=$(date +%s); echo "⏱ prefill  $((t3-t2))s"
echo "✅ 수집 완료 총 $((t3-t0))s — 이제 research.json [ME] 칸 작성 → run_finish.sh $D"
