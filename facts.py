# -*- coding: utf-8 -*-
"""
facts.py — ★v62 병렬 작성용 «사실 요약서» 생성 (A)

왜: 분석 서술을 나눠 쓰는 작성자(서브에이전트) 여러 명이 data.json(수 MB)을 각자 읽으면 토큰이 폭발하고,
    메인 대화가 웹검색 결과·로그를 계속 들고 다니면 매 호출마다 그 전체를 다시 읽는다.
    → 작성에 필요한 «숫자·신호·규칙 판정»만 한 장(facts.md, 약 4~6천 토큰)으로 압축해 모두가 이것만 읽게 한다.

실행: python3 facts.py  → facts.md
"""
import json, datetime as dt
import config as C

D = json.load(open("data.json", encoding="utf-8"))
R = json.load(open("research.json", encoding="utf-8"))
EX = D.get("extra") or {}
try:
    BS = json.load(open("brief_state.json", encoding="utf-8"))
except Exception:
    BS = {}
import build_plus as BP

K, mac = D["kospi"], D["macro"]
out = []
P = out.append


def f(v, d=2):
    try:
        return f"{v:,.{d}f}"
    except Exception:
        return str(v)


def X(n):
    return D["kr"].get(n) or D["us"].get(n) or D.get("holdings", {}).get(n)


M = R["meta"]
P(f"# 사실 요약서 — 기준일 {D['asof']} ({M['mode']}) · 발행 {M['pub']} · 간밤 미국장 {mac['S&P500']['date']}")
P(f"포지션: {M['position_line']}  (국장 전량 매도 · 관찰 카드 = 매도 기준가 대비 추적)")
P("")
P("## 1. 코스피")
P(f"- 종가 {f(K['close'])} ({K['chg']:+.2f}%) · 주간 {K['ret5']:+.2f}% · 월간 {K['ret20']:+.2f}% · RSI {K['rsi']:.1f} · %b {K['pb']:.2f}")
P("- 레벨: " + " · ".join(f"{k} {f(v,0)}({(v/K['close']-1)*100:+.1f}%)" for k, v in
      [("10일", K['ma10']), ("20일", K['ma20']), ("60일", K['ma60']), ("전환", K['conv']), ("기준", K['base']),
       ("구름상단", K['ctop']), ("구름하단", K['cbot']), ("볼린저하단", K['bb_low']), ("22봉저점", K['lo22']), ("52주고점", K['hi252'])]))
P("- 최근 10봉: " + " ".join(f"{r['d']} {r['c']:,.0f}({r['p']:+.1f})" for r in K["recent"]))
P(f"- 레짐: {(D.get('regime') or {}).get('state')} · 권장 상한 {(D.get('regime') or {}).get('size_pct')}% · {(D.get('regime') or {}).get('note')}")
P("")
P("## 2. 지수·매크로 (간밤 US = " + mac['S&P500']['date'] + ")")
for k in ["코스닥", "S&P500", "나스닥", "필라델피아반도체(SOX)", "VIX", "VIX3M", "원/달러", "달러/엔", "WTI", "브렌트", "미국채10년", "비트코인", "EWY"]:
    v = mac.get(k) or {}
    if v.get("close"):
        P(f"- {k}: {f(v['close'], 3 if k=='미국채10년' else 2)} ({v.get('chg_pct',0):+.2f}%) [{v.get('date')}]")
fr = D.get("fred", {})
P(f"- 하이일드 {fr.get('하이일드스프레드',{}).get('val')} ({fr.get('하이일드스프레드',{}).get('date')}) · 장단기차 {fr.get('장단기금리차',{}).get('val')}")
nf = D.get("night_futures") or {}
P(f"- 야간선물 Tier{nf.get('tier')} ≈{f(nf.get('value') or 0)} ({(nf.get('chg') or 0):+.2f}%) — {nf.get('note')}")
P("")
P("## 3. 선행 신호판(자동 신호 g=초록 y=노랑 r=빨강)")
for k, v, chg, c, mean, how in BP.lead_rows(D):
    import re
    strip = lambda s: re.sub(r"<[^>]+>", "", str(s))
    P(f"- [{c}] {k}: {strip(v)} | {strip(chg)}")
P("")
fl = (EX.get("flows") or {})
P("## 4. 수급 (억원, 다음×네이버 교차검증)")
for m in ("KOSPI", "KOSDAQ"):
    x = fl.get(m)
    if x:
        P(f"- {m}: 외국인 {x['frn']:+,.0f} · 기관 {x['inst']:+,.0f} · 개인 {x['ind']:+,.0f} | 외국인 5일 {x['frn_5d']:+,.0f} · 20일 {x['frn_20d']:+,.0f} · 연속 {x['frn_streak']:+d}일 | 기관 5일 {x['inst_5d']:+,.0f} · 연속 {x['inst_streak']:+d}일")
fu = EX.get("futures") or {}
if fu:
    P(f"- K200 선물 외국인 {fu['frn']:+,.0f}억(≈{fu['contracts']:+,}계약) · 5일 {fu['frn_5d']:+,.0f} · 연속 {fu['frn_streak']:+d}일 · 최근: "
      + " ".join(f"{r['date'][5:]} {r['frn']:+,.0f}" for r in fu["series"][:6]))
pg = (EX.get("program") or {}).get("KOSPI") or {}
if pg:
    P(f"- 프로그램(코스피) 차익 {pg['arb']:+,.0f} · 비차익 {pg['nonarb']:+,.0f} · 전체 등락 상승 {pg['up']:.0f}/하락 {pg['dn']:.0f}")
ad = D.get("adr") or {}
P(f"- 시장 폭(국장 150종): ADR {ad.get('today',0):.2f}(20일평균 {ad.get('ma20',0):.2f}) · 20일선 위 {ad.get('above20')}%(5일전 {ad.get('above20_5d')}·20일전 {ad.get('above20_20d')}) · 60일선 위 {ad.get('above60')}% · 신고가 {ad.get('nh')}/신저가 {ad.get('nl')}")
bu = D.get("breadth_us") or {}
P(f"- 시장 폭(미장 150종): 20일선 위 {bu.get('above20')}% · 60일선 위 {bu.get('above60')}% · 신고가 {bu.get('nh')}/신저가 {bu.get('nl')}")
P(f"- 외국인 현·선물 조합: {(EX.get('foreign_combo') or {}).get('label')} · EWY 새 정보분 {(EX.get('ewy') or {}).get('resid')}%")
rt = EX.get("rates") or {}
P("- 금리: " + " · ".join(f"{k} {v.get('val')}%({(v.get('chg_bp') or 0):+.1f}bp, {v.get('date')})" for k, v in rt.items()))
P("")
P("## 5. 섹터 RS(주간)")
sd = sorted(D["sector"]["data"].items(), key=lambda kv: -kv[1]["rs_w"])
P("- " + " · ".join(f"{k} {v['rs_w']:+.1f}/월{v['rs_m']:+.1f}" for k, v in sd))
P("")
P("## 6. 카드 4종 (보유/관찰) — 규칙 판정은 build 판단 매트릭스와 동일 로직")
stk = EX.get("stocks") or {}
for n, code, tk, cur in C.WATCH:
    x = X(n)
    if not x:
        continue
    held = n in C.POSITIONS
    ax, rule, ng, nr = BP.hmatrix(n, x, held, stk.get(n), BS, D["asof"])
    st = stk.get(n) or {}
    fm = (lambda v: f"${v:,.2f}") if cur == "$" else (lambda v: f"{v:,.0f}")
    P(f"### {n} ({'보유' if held else '관찰·매도완료'}) — 종가 {fm(x['close'])} ({x['chg']:+.2f}%) · 규칙 판정 **{rule}** (초록{ng}/빨강{nr})")
    if held:
        p = C.POSITIONS[n]
        P(f"- 평단 {fm(p['avg'])}×{p['qty']} · 평가 {(x['close']/p['avg']-1)*100:+.2f}%")
    else:
        e = (R.get("exits") or {}).get(n, {})
        P(f"- 매도 기준가 {fm(e.get('px') or x['close'])} ({e.get('date')}) 대비 {(x['close']/(e.get('px') or x['close'])-1)*100:+.2f}%")
    P(f"- 이평 10/20/60 {fm(x['ma10'])}/{fm(x['ma20'])}/{fm(x['ma60'])} (20일 {x['vs_ma20']:+.1f}% · 60일 {x['vs_ma60']:+.1f}%) · 볼린저 상/하 {fm(x['bb_up'])}/{fm(x['bb_low'])} · %b {x['pb']:.2f} · RSI {x['rsi']:.0f} · 주봉RSI {x['rsi_w']:.0f} · ATR {x['atr_pct']:.1f}% · σ20 {x.get('sig20',0):.2f}%")
    P(f"- 구름 {fm(x['cloud_bot'])}~{fm(x['cloud_top'])} · 전환/기준 {fm(x['conv'])}/{fm(x['base'])} · 22봉고 {fm(x['hi22'])} · 52주고 {fm(x['hi252'])}({x['gap_hi252']:+.1f}%) · 앵커VWAP(저점 {x.get('avwap_lo_d')}) {fm(x.get('avwap_lo') or 0)}")
    d = x.get("dual") or {}
    P(f"- 19신호 {x['score']}점 · 켜짐: {', '.join(k for k,v in x['on'].items() if v) or '없음'} · 이중모델 {d.get('model')} {d.get('used')}({d.get('band')}) 성격 {d.get('char')} · RS 백분위 {x.get('rs_pct')}")
    if st:
        P(f"- 컨센 목표가 {fm(st.get('target_mean') or 0)} (의견 {st.get('recomm')}, {st.get('cons_date')}) · PER {st.get('per')} · 추정PER {st.get('fwd_per')}"
          + (f" · 외국인 5/20일 {st.get('frn_5d_amt'):+,.0f}/{st.get('frn_20d_amt'):+,.0f}억 · 기관 5/20일 {st.get('inst_5d_amt'):+,.0f}/{st.get('inst_20d_amt'):+,.0f}억 · 외국인 연속 {st.get('frn_streak'):+d}일" if st.get("frn_5d_amt") is not None else ""))
        if st.get("reports"):
            P("- 최근 리포트: " + " / ".join(f"{r['date']} {r['broker']} «{r['title']}»" for r in st["reports"][:3]))
    P("- 4축: " + " · ".join(f"{a[0]}[{a[1]}] {BP.re.sub('<[^>]+>','',a[2])}" for a in ax))
P("")
P("## 7. 추천 후보(6기둥 v2 순) — 강화 카드: 국내 " + ", ".join(D["enhance_kr"]) + " / 미국 " + ", ".join(D["enhance_us"]))
for mk in ("kr", "us"):
    for r in (D.get("pick", {}).get(mk, {}).get("picks") or [])[:6]:
        v = r.get("v2") or {}
        P(f"- [{mk}] {r['name']}: v2 {v.get('total')} {v.get('grade')} · " + " · ".join(f"{k}:{(v.get('why') or {}).get(k,'')}" for k in ("setup", "rs", "flow", "cat")))
P("")
pf = D.get("perf") or {}
if pf.get("ok"):
    w = pf["windows"]["120"]
    P(f"## 8. 포트(원화 환산) — σ {w['vol_p']:.1f}% vs 코스피 {w['vol_m']:.1f}% · β {w['beta']:.2f} · 샤프 {w['sharpe_p']:.2f} vs {w['sharpe_m']:.2f} · 60일 샤프 {pf['windows']['60']['sharpe_p']:.2f}")
hg = D.get("hedge") or {}
if hg.get("ok"):
    P("- 헤지: " + " · ".join(f"{h} corr60 {v['corr60']} corr20 {v['corr20']} β {v['beta']}" for h, v in hg["items"].items())
      + (" (비교 대상 = SOX 지수)" if hg.get("vs_index") else ""))
P(f"- 현금·시드: 통합 {C.ACCOUNT_TOTAL:,}원 · 스트레스 시나리오: " + " / ".join(s["name"] for s in C.STRESS_SCENARIOS))
sc = D.get("scorecard") or {}
P(f"- 채점표: {sc.get('sum') or '기록 시작 회차'}")
P("")
P("## 9. 작성 규칙(요약) — 자세한 건 RUNBOOK §4")
P("- 숫자는 data.json 값이면 {{kospi.close}} · {{kr.삼성전자.ma20:,.0f}} · {{us.구글 Class C.close:,.2f}} · {{pct:kospi.ma20|kospi.close}} 자리표시자. 웹 수치는 손으로(출처는 log8).")
P("- 강조: ++호재++ --악재-- !!경고!! ^^중립^^ ==행동(형광)== **볼드**. 부호 숫자(+1.2% / −3억)는 자동 색 — 따로 감쌀 필요 없음.")
P("- 참조: 다른 칸과 같은 문장이면 \"=topdown.verdict.action\" 처럼 «=경로»만 쓴다. {{@stops}} {{@events}} {{@verdict}} 토큰 사용 가능.")
P("- 모든 판단은 «무엇을 보면(가격·수급 레벨) → 무엇을 한다(행동)» 형태. 레벨 없는 한 줄 판단 금지(G18).")
open("facts.md", "w", encoding="utf-8").write("\n".join(out))
print(f"■ facts.md {len(chr(10).join(out)):,}자")
