# 분석 칸 작성 규격 (me_*.json) — ★v62 병렬 작성용

> 작성자(메인·서브에이전트)는 **facts.md(숫자·신호) + notes.md(뉴스·일정) + me_verdict.json(최종 판정)** 만 읽는다.
> data.json·코드를 열지 않는다. 결과는 **JSON 파일 하나**로 /root/w 에 저장한다(Write 한 번).

## 0. 공통 규칙 (위반 시 lint_me / gate 탈락)
1. **숫자 출처** — 시세·지표·수급·금리·컨센서스 숫자는 **facts.md 값만** 쓴다. notes.md(기사)에 있는 수급·종가·환율 숫자는
   기사 잠정치·오기가 섞여 있으므로 **절대 옮기지 않는다**(2026-09-23 실측: 기사 3곳의 외국인 순매수가 모두 달랐다).
   notes.md에서는 «왜 움직였나(원인)»·«일정»·«뉴스 사실»만 가져온다.
2. **자리표시자 권장** — data.json 값은 `{{kospi.close}}` `{{kospi.ma20:,.0f}}` `{{kr.삼성전자.ma20:,.0f}}` `{{us.구글 Class C.close:,.2f}}`
   `{{macro.원/달러.close:,.2f}}` `{{pct:kospi.ma20|kospi.close}}`(현재가 대비 %) 형태로 쓰면 build가 정확한 값을 넣는다.
   facts.md에 적힌 숫자를 그대로 적어도 되지만, 코스피 종가를 손으로 적을 땐 facts와 **소수점까지** 같아야 한다(G16).
3. **강조(경량 표기)** — `++호재++`(초록) `--악재--`(빨강) `!!경고!!`(빨강 볼드) `^^중립^^`(노랑) `==행동 지침==`(노란 형광) `**볼드**`.
   부호 숫자(+1.2%, −3억)는 build가 자동으로 빨강/파랑 칠한다 — 감싸지 않는다. HTML 태그도 그대로 통과한다.
   **문단마다 최소 1개 강조**, 행동 지침에는 반드시 `==…==`.
4. **판단 = 조건 → 행동** — 「무엇을 보면(가격·수급 레벨, 숫자)」→「무엇을 한다」. 레벨 없는 «관망» 한 줄 금지.
5. **중복 금지(C)** — 다른 칸과 같은 문장을 다시 쓰지 말고 `"=topdown.verdict.action"` 처럼 **«=경로» 문자열 하나**로 참조.
   토큰 `{{@stops}}`(손절선 목록) `{{@events}}`(캘린더 요약) `{{@verdict}}`(판정 라벨) 사용 가능.
6. 포지션 전제(★v67, 정본 = config.POSITIONS): **보유 = 국장 삼성전자 + 미장 구글 Class C·코어위브·어플라이드 머티어리얼즈·이튼**. 보유 카드 = 보유 판단, SK하이닉스 = 재진입 판단(매도 완료), LS ELECTRIC = 신규 진입 판단. POSCO홀딩스·크라우드스트라이크는 추적 전용(자동, 서술 불필요).
   관찰 카드 배지는 진입 판단(진입 검토 / 진입 검토(조건부) / 관망 / 회피), 보유 카드는 보유 판단(홀드 / 홀드(손절선 엄수) / 분할 익절 / 추가매수 검토 / 손절).
7. 분량 — 기존 브리핑과 같은 밀도(칸당 2~4문장). **줄이지 않는다.** 대신 숫자 나열은 자동 칸이 하므로 «해석»에 집중.

## 1. me_verdict.json (메인이 먼저 — 다른 작성자가 읽는다)
```json
{"topdown": {"verdict": {"label": "🟠 …", "short": "…", "tally": "L0 … · L1 … · L2 …", "action": "① … ② … ③ … ④ …", "link": "관찰 카드 …"}},
 "headline": ["지수 한 줄", "수급·선행 한 줄", "간밤 미국장 한 줄", "업황/종목 한 줄", "다음 장의 자리 + 행동 한 줄"]}
```

## 2. me_market.json (작성자 A — 시장·매크로·수급)
- `index_notes` 14칸(코스피·코스닥·야간선물·S&P500·나스닥·필라델피아반도체(SOX)·VIX·VIX3M·원/달러·달러/엔·WTI·브렌트·미국채10년·비트코인)
  — **숫자 머리는 build가 붙인다**. 여기엔 «맥락 해석» 1~2문장만.
- `index_sogo`, `lead_sogo`(선행 신호판 «그래서 다음 장은» — EWY·외국인 선물·2년물·실질금리·시장 폭을 묶어 갭 방향과 대응)
- `macro_2x2`: {호재, 반락, 미국장, 정책, sogo}
- `kospi_read`(현재 위치 해석 — kospi_caption은 자동)
- `scenario`: {up, up_watch, dn, dn_watch, checkpoints[5]} — up/dn에 **가격 레벨 필수**, *_watch는 «핵심 종목 대응»(카드 종목별 행동)
- `topdown`: {L0[≥5행], L0_sum, L0_short, L1[≥6행], L1_sum, L1_short, L2[≥5행], L2_sum} — 각 행 {k, v, c(g/y/r), e}
  (L0 = 수급·선행: 외국인 현물·선물, 기관, 프로그램, 시장 폭, EWY, 환율 / L1 = 금리 2년·10년·실질·연준·유가·BTC / L2 = 메모리 사이클·반도체)
- `supply`: {reads: {외국인, 기관, 개인, 선물·프로그램, 시장 폭}(각 1~2문장 해석), sogo}
- `sector_pick`, `sector_diversify`(현금 비중이 큰 상태에서 «첫 진입을 어느 섹터부터»), (★v63 `screen_read`·강화 카드 서술은 차트 판독 에이전트가 chart_pick.json으로 쓴다 — 작성자 A는 쓰지 않는다)
- `hedge.read`(보유 종목 vs SOX 상관 해석 — 반도체 노출이 큰지), `stress.read`

## 3. me_cards.json (작성자 B — 핵심 종목 분석 카드: facts.md §6의 종목 전부)
`watch.<종목>`: {badge, why, action, danger, read, trigger, avoid, concl, risk, tgt, tgt_detail, earnings, valuation, hold_read, news[[날짜, 뉴스]…2~3개]}
- 종목명 키 = facts.md §6 제목의 종목명 그대로(현재 `삼성전자` `SK하이닉스` `LS ELECTRIC` `구글 Class C` `코어위브` `어플라이드 머티어리얼즈` `이튼` — config.WATCH가 바뀌면 따라 바뀐다). §6-2 추적 전용 종목은 카드를 쓰지 않는다(자동).
- `trigger`·`avoid`에는 **가격 레벨(숫자 또는 자리표시자) 필수**. 미보유 종목 trigger = «(재)진입 조건», 보유 종목 = «추가/보유 조건».
- facts.md의 **규칙 판정**(4축 매트릭스)과 배지가 다르면 `why` 첫 문장에 이유를 쓴다.
- `news`는 뉴스만(등락 줄은 build가 자동으로 맨 앞에 붙인다). `hold_read`는 보유 종목 = 보유 근거·손절 규율 / 매도한 종목 = «매도 판단 복기» 한 줄 / 신규 관찰 종목 = «왜 지금 추적하나» 한 줄.
- `tgt`·`tgt_detail`은 facts.md의 **컨센 목표가(평균·기준일)** + 최근 리포트 제목을 근거로.

## 4. me_plan.json (작성자 C — 일정·행동·포트)
- `calendar`: 5~7건 [{when, what, type, m1(스윙: 무엇을 보면→행동), m2(단타: 무엇을 보면→행동)}] — **확정 일시(한국시간)**, 미확정은 «미확정» 명기
- `calendar_pin`, `watch_intro`
- `traps`: 6종 [{name, today(bool), why}] — 보유 세트 필수 문구: **물타기 · 손절 미루기 · 공포 전량매도** 가 이름이나 설명에 들어갈 것
- `risk`: {vix, sizing} (modes·events는 자동 — 비워 둔다)
- `dashboard`: {cash, concentration, guide(짧은 오늘의 지침 — 또는 "=topdown.verdict.action"), risk_note}
- `perf_note`, `perf_advice`(**«실행 순서» 문구 + 1단계/2단계/3단계** 필수), `tracker_memo`
- `log8`: 웹조사로 못 구한 항목만 [{item, kind:"실패", detail:"<b>시도</b>: … <b>반환</b>: … <b>대체</b>: …"}] (없으면 [])
