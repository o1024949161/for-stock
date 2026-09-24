# 회차 프롬프트 템플릿 (★v62) — 메인은 {D}·{NEXT}·{US} 세 값만 바꿔 그대로 붙인다

> 이 파일은 GitHub에 있다. 매 회차 프롬프트를 새로 쓰지 않는다(출력 토큰 절감).
> {D}=기준일(마지막 KR 세션) · {NEXT}=다음 KR 세션 · {US}=마지막 완결 미국 세션 — facts.md 첫 줄에 전부 있다.

## R. 리서치 에이전트 (model: sonnet · run_collect와 동시에 시작)
```
You are the research step of a Korean daily stock-market briefing pipeline. Last Korean session = {D}; next Korean session = {NEXT}; last completed US session = {US}.
User holds only Google Class C (GOOG); sold all Korean stocks. Core cards: Samsung Electronics, SK hynix, LS ELECTRIC, Google. Also tracked: POSCO Holdings, CrowdStrike (CRWD).
DO NOT look up prices, index levels, investor flows, yields, FX or consensus targets (APIs already verified them). Gather NEWS, CAUSES and the EVENT CALENDAR only.
Use WebSearch snippets (WebFetch only if a key fact is missing). Budget ≈12 searches, 3 fetches.
Write /root/w/notes.md in Korean (≤1,300 words) with sections:
## A. {D} 한국장 — 무엇이 지수를 움직였나 (원인·테마·종목 뉴스, 숫자 말고 이유)
## B. {US} 미국장 — 지수·금리(2년·10년)·유가·반도체·구글 움직임의 원인
## C. {NEXT} 한국장 전까지 남은 해외 일정·리스크
## D. 경제 캘린더 {NEXT}부터 약 2주 — 날짜 · KST 시각 · 이벤트 · 왜 중요한지 (미확정은 «미확정»)
## E. 종목 뉴스 — 삼성전자 / SK하이닉스 / LS ELECTRIC / 구글 / POSCO홀딩스 / 크라우드스트라이크 (최근 7일, 날짜 포함 · 앞 4종은 2~3줄, 뒤 2종은 1줄)
## F. 메모리 업황 — DRAM/NAND 가격·HBM·중국 경쟁
## G. 출처 (제목 + URL)
Reply only "done".
```

## A·B·C. 작성 에이전트 3명 (model: 기본 · 한 메시지에서 동시에 3개 호출)
공통 머리말(세 프롬프트 맨 앞에 붙인다):
```
You are writer {X} for a Korean daily stock-market briefing (PDF). Read ONLY: /root/w/me_spec.md (follow §0 and §{N}), /root/w/facts.md (the ONLY source of numbers),
/root/w/notes.md (causes/news/calendar — never copy its flow/price/FX numbers), /root/w/me_verdict.json (final verdict — stay consistent). Do NOT open data.json or code.
Write ONE UTF-8 JSON file {FILE}. Every judgement = condition (price/flow level) → action. Use the emphasis markers and placeholders from the spec.
Professional sell-side density, 2–4 sentences per field; do not shorten. Validate with python3 -c "import json;json.load(open('{FILE}'))". Reply only "done".
```
- **A (시장·매크로·수급)** — {X}=A · {N}=2 · {FILE}=/root/w/me_market.json · 덧붙임: `topdown L0≥5·L1≥6·L2≥5 rows, colors follow facts §3 auto signals, BTC row must contain «6만$», scenario.up/dn must contain KOSPI price levels.`
- **B (핵심 종목 카드 — facts §6 종목 전부)** — {X}=B · {N}=3 · {FILE}=/root/w/me_cards.json · 덧붙임: `trigger/avoid must contain price levels; if badge ≠ facts §6 rule verdict, explain in why's first sentence; badges must match me_verdict link.`
- **C (일정·행동·포트)** — {X}=C · {N}=4 · {FILE}=/root/w/me_plan.json · 덧붙임: `calendar 6–7 events with m1 & m2; traps exactly 6 incl. «물타기» «손절 미루기» «공포 전량매도»; perf_advice must contain «실행 순서» and 1단계/2단계/3단계.`
