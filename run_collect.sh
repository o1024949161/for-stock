#!/usr/bin/env bash
# run_collect.sh D MODE — ★v62 수집 단계 전체(조용히·병렬). 백그라운드로 돌리고 그 사이 웹조사 에이전트를 돌린다.
#   예) nohup bash run_collect.sh 2026-09-23 마감 > _collect.log 2>&1 &
#   순서: ① 2차 소스 대조 파일(지수·환율·유가) → ② fetch_all ∥ API 수집(수급·선물·금리·컨센) → ③ 병합·야후 대조
#         → ④ 차트 → ⑤ prefill(자동 칸) → ⑥ facts.md(작성자용 사실 요약서)
set -e
D="${1:?기준일 필요: YYYY-MM-DD}"; MODE="${2:-마감}"
cd "$(dirname "$0")"
export BRIEF_QUIET=1
export YF_CONC="${YF_CONC:-8}" YF_MIN_GAP="${YF_MIN_GAP:-0.08}"
export YF_ASOF="$D"
export YF_US_CUT="${YF_US_CUT:-$(python3 asof.py uscut 2>/dev/null)}"   # 간밤 US 절단일(휴장일 저녁 대응)
t0=$(date +%s)
python3 fetch_kr_extra.py xcheck "$D"
python3 fetch_kr_extra.py collect "$D" > _extra.log 2>&1 &
EXP=$!
python3 fetch_all.py "$D";   t1=$(date +%s); echo "⏱ fetch_all $((t1-t0))s"
wait $EXP || { echo "⚠ API 수집 실패 — _extra.log 확인(브리핑은 계속, §8 기록)"; }
cat _extra.log | grep -v "^\s*\[adapter" || true
python3 fetch_kr_extra.py merge
python3 mkchart.py;          t2=$(date +%s); echo "⏱ mkchart  $((t2-t1))s"
python3 prefill.py "$MODE"
python3 facts.py;            t3=$(date +%s); echo "⏱ prefill+facts $((t3-t2))s"
echo "✅ 수집 완료 총 $((t3-t0))s — 다음: me_*.json 작성(병렬) → bash run_finish.sh $D"
