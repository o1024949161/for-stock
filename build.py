# -*- coding: utf-8 -*-
"""
build.py — data.json(실측) + research.json(그날의 리서치·해석) → briefing.html (14코너)
구조·계산·레이아웃은 전부 여기 고정. 매일 바뀌는 건 research.json 뿐이다.
실행: python3 build.py
"""
import json, base64, os
from style import CSS
from lib_ind import (WEIGHTS, stop_tiers, chart_levels, k_of,
                     band_of, next_signals, SCORE_BANDS, ZERO_SIGS)
import config as C

def dual_html(x):
    d = x.get("dual")
    if not d: return ""
    t = "회귀형" if d["is_rev"] else "추세형"
    s = (f'· <b>적용 모델</b> — {d["model"]} <b>{d["used"]:.1f}점({d["band"]})</b> · '
         f'<b>종목 성격</b> 상관 {d["char"]:+.2f}({t}) · '
         f'<span style="font-size:8.8px;">{d["band_note"]}</span>')
    if d.get("is_warn"):
        s += (f'<br><b class="warn">⚠ 역방향 경고</b> — 회귀형인데 추세점수 {d["trend_score"]:.1f} → '
              f'추세점수가 높은 건 매수가 아니라 «경고»다(표본외 {d["trend_warn"]}).')
    return s

# ════════════════════════════════════════════════════════════
# ★v55/v56 수치 플레이스홀더 (2026-08-30 신설 · 기존 로직 무수정)
#   research.json 서술에 실측 숫자를 «손으로» 적다가 2026-08-30 신선도 게이트 탈락.
#   («코스피 종가 6,803.36» — 10일선 값을 코스피 종가 옆에 적었다.)
#   서술은 자리표시자만 쓰고, 숫자는 여기서 data.json으로부터 주입한다.
#
#   {{kospi.close}}            → D["kospi"]["close"]        (기본 서식 ,.2f)
#   {{macro.코스피.chg_pct:+.2f}}
#   {{kr.삼성전자.ma20:,.0f}}  → D["kr"]["삼성전자"]["ma20"]
#   {{us.샌디스크.close:,.2f}}
#   {{pct:kospi.ma20|kospi.close}}   → (ma20/close-1)*100 → «-2.5%»  (★v56 파생 수치)
#   해석 실패 시 «치환하지 않고» 그대로 두고 경고 — 조용히 틀린 값이 들어가지 않게 한다.
# ════════════════════════════════════════════════════════════
def _pick(D, path, _miss, token):
    cur = D
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            _miss.append(token); return None
    return cur


def _inject(obj, D, _miss):
    import re as _re

    def pct(m):
        """★v56 — «현재가 대비 −2.5%» 류의 파생 수치도 손타이핑하지 않는다.
        {{pct:kospi.ma20|kospi.close}} → (a/b-1)*100 을 +.1f%% 로."""
        a = _pick(D, m.group(1), _miss, m.group(0))
        b = _pick(D, m.group(2), _miss, m.group(0))
        fmt = m.group(3) or "+.1f"
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not b:
            _miss.append(m.group(0)); return m.group(0)
        return format((a / b - 1) * 100, fmt) + "%"

    def one(m):
        path, fmt = m.group(1), (m.group(2) or ",.2f")
        cur = D
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                _miss.append(m.group(0)); return m.group(0)
        try:
            return format(cur, fmt) if isinstance(cur, (int, float)) else str(cur)
        except Exception:
            _miss.append(m.group(0)); return m.group(0)
    if isinstance(obj, str):
        obj = _re.sub(r"\{\{pct:([A-Za-z0-9_가-힣.]+)\|([A-Za-z0-9_가-힣.]+)(?::([^}]+))?\}\}", pct, obj)
        return _re.sub(r"\{\{([A-Za-z0-9_가-힣.]+)(?::([^}]+))?\}\}", one, obj)
    if isinstance(obj, dict):
        return {k: _inject(v, D, _miss) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_inject(v, D, _miss) for v in obj]
    return obj


D = json.load(open("data.json"))
R = json.load(open("research.json"))
_miss = []
R = _inject(R, D, _miss)
if _miss:
    print("  ⚠ ★v56 플레이스홀더 해석 실패 " + str(len(_miss)) + "건(원문 유지):", _miss[:5])
else:
    print("  ✔ ★v56 수치 플레이스홀더 주입 완료")
kr, us, mac, K = D["kr"], D["us"], D["macro"], D["kospi"]
sec, fred = D["sector"], D["fred"]

def _fresh_guard(R, D):
    import sys, datetime as _dt
    M = R.get("meta", {})
    d_asof = D.get("asof")
    r_asof = M.get("asof")
    errs, warns = [], []

    if not d_asof:
        errs.append("data.json에 asof가 없다")
    if r_asof != d_asof:
        errs.append(f"기준일 불일치 — research.meta.asof={r_asof} vs data.asof={d_asof}. "
                    f"서술이 다른 회차의 것이다")
    try:
        if M.get("pub") and d_asof and _dt.date.fromisoformat(M["pub"]) <= _dt.date.fromisoformat(d_asof):
            errs.append(f"발행일({M['pub']})이 기준일({d_asof}) 이전이거나 같다")
    except Exception:
        errs.append(f"발행일 형식 오류: {M.get('pub')}")

    import re, json as _json
    ks = D.get("kospi", {}).get("close")
    if ks:
        body = _json.dumps({k: v for k, v in R.items() if k != "log8"}, ensure_ascii=False)
        cand = set()
        for m in re.finditer(r"코스피[^0-9]{0,12}([0-9]{1,2},[0-9]{3}\.[0-9]{2})", body):
            cand.add(float(m.group(1).replace(",", "")))
        bad = [c for c in cand if abs(c / ks - 1) > 0.001]
        if bad:
            errs.append("서술 본문의 코스피 종가가 실측과 다르다 — "
                        f"실측 {ks:,.2f} vs 서술 {', '.join(f'{b:,.2f}' for b in sorted(bad))}")

    if not (R.get("headline") or []):
        errs.append("headline이 비어 있다 — 이 회차 서술이 아직 작성되지 않았다")

    if D.get("log8"):
        _lg = [l for l in D["log8"] if l.get("kind") in ("실패", "경고")]
        if _lg:
            warns.append("§8 실패/경고 " + str(len(_lg)) + "건: "
                         + ", ".join(l["item"] for l in _lg[:4]))
    for w in warns:
        print("  ⚠", w)
    if errs:
        print("\n" + "=" * 68)
        print("❌ 신선도 게이트 탈락 — 조립을 중단한다 (★v50)")
        for e in errs:
            print("   ·", e)
        print("=" * 68)
        print("조치: 이 회차의 research.json을 실측 기준일에 맞춰 새로 작성한 뒤 다시 실행한다.")
        print("      (RUNBOOK §2 리서치 8종 이행 → research.json 작성 → build.py)")
        sys.exit(2)
    print(f"  ✔ 신선도 게이트 통과 — 서술·실측 모두 기준일 {d_asof}")


_fresh_guard(R, D)
M = R["meta"]
FX  = mac["원/달러"]["close"]
BTC = mac["비트코인"]
ALL = {**C.KR_UNIVERSE, **C.US_UNIVERSE,
       **{k: v["ticker"] for k, v in D.get("kr", {}).items()},
       **{k: v["ticker"] for k, v in D.get("us", {}).items()}}
ENH = D["enhance_kr"] + D["enhance_us"]
CUR = {n: c for n, _, _, c in C.WATCH}
CODE = {n: c for n, c, _, _ in C.WATCH}

H = [CSS]; A = H.append
def b64(p): return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()
def pct(v, d=2):
    return f'<span class="{"up" if v>0 else ("dn" if v<0 else "")}">{v:+.{d}f}%</span>'
def num(v, d=0): return f"{v:,.{d}f}"
def sig(c): return f'<span class="d d{c}">●</span>'
def money(cur, v): return f"{v:,.0f}원" if cur == "₩" else f"${v:,.2f}"
hold = D.get("holdings", {})
def X(n): return kr[n] if n in kr else (us[n] if n in us else hold[n])
def cur_of(n): return CUR.get(n, "₩" if n in kr else "$")
def m_amt(cur, v):
    cl = "up" if v > 0 else ("dn" if v < 0 else ""); sgn = "+" if v >= 0 else "-"
    body = f"{abs(v):,.0f}원" if cur == "₩" else f"${abs(v):,.2f}"
    return f'<span class="{cl}"><b>{sgn}{body}</b></span>'
def m_neg(cur, v): return "−" + money(cur, abs(v))

POS = {n: dict(p) for n, p in getattr(C, "POSITIONS", {}).items()}
def held(n): return n in POS and POS[n]["qty"] > 0
def pnl(n):
    p, x = POS[n], X(n)
    cost, val = p["avg"]*p["qty"], x["close"]*p["qty"]
    return {"avg": p["avg"], "qty": p["qty"], "since": p.get("since", "-"),
            "cost": cost, "val": val, "amt": val-cost,
            "rate": (x["close"]/p["avg"]-1)*100,
            "day": x["close"]*p["qty"] - (x["prev"] if "prev" in x else x["close"])*p["qty"]}
def krw(v): return f"{v:,.0f}원"
def signed(v, unit="원"):
    c = "up" if v > 0 else ("dn" if v < 0 else "")
    return f'<span class="{c}"><b>{v:+,.0f}{unit}</b></span>'
def acct_of(n):
    if cur_of(n) == "₩": return C.ACCOUNT_KR
    return C.ACCOUNT_US or C.ACCOUNT_KR
HELD = [n for n in POS if held(n)]
WATCHONLY = [n for n, _, _, _ in C.WATCH if not held(n)]
HELD_KRW = [n for n in HELD if cur_of(n) == "₩"]
HELD_USD = [n for n in HELD if cur_of(n) == "$"]
def _tot(names):
    cost = sum(pnl(n)["cost"] for n in names); val = sum(pnl(n)["val"] for n in names)
    return cost, val, val-cost, ((val/cost-1)*100 if cost else 0.0)
KRW_COST, KRW_VAL, KRW_AMT, KRW_RATE = _tot(HELD_KRW)
USD_COST, USD_VAL, USD_AMT, USD_RATE = _tot(HELD_USD)

def stop_of(n):
    x, q = X(n), POS[n]["qty"]; a = POS[n]["avg"]
    S = stop_tiers(x, a, C.STOP_CAP, C.ATR_K_TABLE, C.STOP_FRAC, C.STOP_QTY, C.STOP_SNAP)
    rows, risk = [], 0.0
    for lab, nm2, v, fr in S["tiers"]:
        cut = q * fr
        loss = (x["close"] - v) * cut
        risk += loss
        rows.append({"lab": lab, "src": nm2, "lv": v, "pct": (v/x["close"]-1)*100,
                     "qty": cut, "loss": loss})
    S.update({"rows": rows, "risk": risk, "risk_wide": risk, "rule2": None,
              "risk_single": (x["close"]-S["s3"])*q,
              "adopt": f'3단 분할 · 캡 {C.STOP_CAP*100:.0f}% · 동적배수 {S["k"]:g}xATR'})
    return S

def plan_of(n, tech, cons):
    x = X(n); Cp, At = x["close"], x["atr"]
    pull = max(x["bb_low"], x["cloud_bot"])
    if pull >= Cp*0.995: pull = min(x["bb_low"], Cp*0.97)
    brk = min(x["cloud_top"], x["ma20"])
    if brk <= Cp: brk = max(x["cloud_top"], x["ma20"])
    out = {}
    for nm, e in [("눌림 대기(권장)", pull), ("돌파 추격", brk)]:
        kk = k_of(x["atr_pct"], C.ATR_K_TABLE)
        sf, sv = e*(1-C.STOP_CAP), e - kk*At
        st = max(sf, sv)
        out[nm] = {"entry": e, "e_pct": (e/Cp-1)*100, "stop": st, "s_fix": sf, "s_vol": sv,
                   "s_pct": (st/e-1)*100, "t_tech": tech, "t_cons": cons,
                   "rr": (tech-e)/(e-st) if e > st else 0,
                   "rr_cons": (cons-e)/(e-st) if e > st else 0}
    return out
PLAN = {n: plan_of(n, R["watch"][n]["t_tech"], R["watch"][n]["t_cons"]) for n, _, _, _ in C.WATCH}

def plan_enh(n):
    x = X(n); Cp, At = x["close"], x["atr"]
    pull = max(x["bb_low"], x["cloud_bot"], x["ma20"]*0.94)
    if pull >= Cp*0.995: pull = Cp*0.965
    brk = x["hi22"] if x["gap_hi60"] > -6 else min(x["ma20"], x["cloud_top"])
    if brk <= Cp: brk = max(x["hi22"], Cp*1.02)
    o = {}
    for nm, e in [("눌림 대기(권장)", pull), ("신고가 돌파", brk)]:
        kk = k_of(x["atr_pct"], C.ATR_K_TABLE)
        s = max(e*(1-C.STOP_CAP), e - kk*At)
        t = x["hi60"] if x["hi60"] > e*1.05 else e*1.18
        o[nm] = {"entry": e, "e_pct": (e/Cp-1)*100, "stop": s, "s_pct": (s/e-1)*100,
                 "s_fix": e*(1-C.STOP_CAP), "s_vol": e-kk*At, "t": t, "rr": (t-e)/(e-s) if e > s else 0}
    return o
PLAN_E = {n: plan_enh(n) for n in ENH}

def axis6(x):
    Cp = x["close"]
    a1 = ("구름 위","g","강세대") if Cp > x["cloud_top"] else (("구름 아래","r","약세대") if Cp < x["cloud_bot"] else ("구름 안","y","중립대"))
    pb = x["pb"]
    a2 = (f"{pb:.2f}","g","밴드 중상단") if .5<=pb<=.8 else ((f"{pb:.2f}","y","밴드 하중단") if .2<=pb<.5 else (f"{pb:.2f}","r","밴드 하단 이탈권" if pb<.2 else "밴드 상단 밖"))
    r = x["rsi"]
    a3 = (f"{r:.0f}","g","중립~강세") if 50<=r<=70 else ((f"{r:.0f}","y","약세 or 과열") if (40<=r<50 or 70<r<=80) else (f"{r:.0f}","r","과매도" if r<40 else "과열"))
    g = x["gap_hi60"]
    a4 = (f"{g:+.1f}%","g","여유 있음") if -20<=g<=-5 else ((f"{g:+.1f}%","y","전고 근접") if -5<g<=3 else (f"{g:+.1f}%","r","과열" if g>3 else "전고와 너무 멂"))
    h, hp = x["macd_hist"], x["macd_hist_prev"]
    a5 = ("호전","g","양전환·상승") if (h>0 and h>hp) else (("개선 중","y","음전이나 축소") if h>hp else ("약화","r","하락"))
    v = x["vs_ma20"]
    a6 = (f"{v:+.1f}%","g","20일선 위") if v>0 else ((f"{v:+.1f}%","y","20일선 접점") if v>-2 else (f"{v:+.1f}%","r","20일선 아래"))
    return [("일목(구름 위치)",)+a1, ("%b (밴드 위치)",)+a2, ("RSI(일)",)+a3,
            ("전고 이격(60봉)",)+a4, ("MACD",)+a5, ("캔들/20일선",)+a6]

def ceiling(x):
    Cp = x["close"]
    b6 = [("주봉 RSI ≥ 75", x["rsi_w"]>=75, f'{x["rsi_w"]:.1f}'),
          ("볼린저 상단 종가 돌파", Cp > x["bb_up"], f'종가 {Cp:,.0f} vs 상단 {x["bb_up"]:,.0f}'),
          ("전고점(52주) 도달", x["gap_hi252"]>=-1, f'{x["gap_hi252"]:+.1f}%'),
          ("일봉 RSI ≥ 70", x["rsi"]>=70, f'{x["rsi"]:.1f}'),
          ("거래량 급증 ×2", x["vol_ratio"]>=2, f'{x["vol_ratio"]:.2f}배'),
          ("60일선 이탈", Cp < x["ma60"], f'{x["vs_ma60"]:+.1f}%')]
    p4 = [("볼린저 상단 밖 종가", Cp > x["bb_up"], f'%b {x["pb"]:.2f}'),
          ("단기선 이격 과대(>3ATR)", (Cp-x["ema9"]) > 3*x["atr"], f'이격 {Cp-x["ema9"]:,.0f} vs 3ATR {3*x["atr"]:,.0f}'),
          ("RSI 하락 다이버전스", x["rsi_div"], "점등" if x["rsi_div"] else "없음"),
          ("클라이맥스 거래량(×3)", x["vol_ratio"]>=3, f'{x["vol_ratio"]:.2f}배')]
    return b6, p4

A(f'''<div class="banner"><h1>데일리 마켓 브리핑 · {M["mode"]}</h1><div class="sub">
<span class="pill">발행 {M["pub"]}</span><span class="pill">기준일 {M["asof_label"]}</span>
<span class="pill">대상 {M["next"]}</span><span class="pill">데이터 yfinance + FRED + 웹검색</span>
<span class="pill">{M["position"]}</span>{("".join(f'<span class="pill">{n} {pnl(n)["qty"]}주 @ {money(cur_of(n),pnl(n)["avg"])}</span>' for n in HELD))}{(f'<span class="pill" style="background:#C0392B;">국장 {KRW_AMT:+,.0f}원 ({KRW_RATE:+.2f}%)</span>' if HELD_KRW else "")}{(f'<span class="pill" style="background:#1F6F43;">미장 {"+" if USD_AMT>=0 else "−"}${abs(USD_AMT):,.2f} ({USD_RATE:+.2f}%)</span>' if HELD_USD else "")}</div></div>
<div class="box-navy pb-avoid"><div style="font-size:12.5px;font-weight:bold;margin-bottom:4px;">📌 오늘 한 줄 요약</div>
<div style="line-height:1.65;">{"<br>".join("· "+s for s in R["headline"])}</div></div>
<div class="box box-a pb-avoid"><span class="chip c-amber">📖 용어 박스 (1회 정의 — 이후 재정의 금지)</span>
<div style="font-size:9.6px;line-height:1.6;margin-top:3px;">
<b>RSI</b> 과열·과매도 온도계(70↑ 과열/30↓ 과매도) · <b>일목균형표</b> 전환선(9)·기준선(26)·<b>구름</b>(미래 지지·저항대: 위=강세, 안=중립, 아래=약세) ·
<b>볼린저밴드(20,±2σ)</b> 평균선 위아래 변동폭 띠 · <b>%b</b> 밴드 안 위치(0=하단,1=상단) · <b>ATR</b> 하루 평균 변동폭 ·
<b>R:R</b> 손실 1을 걸었을 때 기대 이익 배수(2 이상이면 유리) · <b>손절 규격</b> 고정(앵커×0.92)과 변동성(앵커−3×ATR) 중 <b>넓은 쪽</b>을 그대로 채택 ·
<b>리스크 노출</b> 손절선까지 밀렸을 때의 손실 금액(<b class="warn">판정이 아니라 실측 표기</b>) · <b>6%룰</b> 월 누적 손실 6%면 그 달 매매 중단 ·
<b>국고채 3년물</b> 한국 통화정책 기대를 가장 민감하게 반영하는 시장금리 · <b>이동평균(10·20·60일)</b> 단기·중기·중장기 추세선.</div></div>''')

nf = D.get("night_futures_proxy", {})
k200 = mac["KOSPI200"].get("estimated", mac["KOSPI200"]["close"])
vixr = mac["VIX"]["close"] / mac["VIX3M"]["close"]
IN = R["index_notes"]
rows = [("코스피", num(K["close"],2), K["chg"], IN["코스피"]),
        ("코스닥", num(mac["코스닥"]["close"],2), mac["코스닥"]["chg_pct"], IN["코스닥"]),
        ("KOSPI200(추정)", num(k200,2), K["chg"], IN["KOSPI200"]),
        ("코스피200 야간선물(프록시)", f'≈{num(nf.get("value",0),2)}', nf.get("chg",0), IN["야간선물"])]
for k in ["S&P500","나스닥","필라델피아반도체(SOX)","VIX","VIX3M","원/달러","WTI","브렌트","미국채10년"]:
    v = mac[k]
    rows.append((k, num(v["close"],2) + ("%" if k=="미국채10년" else ""), v["chg_pct"], IN[k]))
rows.append(("비트코인(BTC-USD)", "$"+num(BTC["close"],0), BTC["chg_pct"], IN["비트코인"]))
for e in R.get("index_extra", []):
    rows.append((e["name"], e["value"], e.get("chg"), e["note"]))
A('<table><caption class="corner-cap">① 지수 · 선물 · 시황표 (16종 실측)</caption><thead><tr>'
  '<th style="width:16%">항목</th><th style="width:12%">종가</th><th style="width:9%">등락</th><th>비고 (맥락)</th></tr></thead><tbody>')
for n, v, c, note in rows:
    cell = pct(c) if isinstance(c, (int, float)) else (c or "—")
    A(f'<tr><td class="tl"><b>{n}</b></td><td class="tr">{v}</td><td class="tc">{cell}</td><td class="tl">{note}</td></tr>')
A('</tbody></table>')
A(f'<div class="box box-b" style="font-size:9.6px;">➡ <b>그래서 지금</b> — {R["index_sogo"]}</div>')

MB = R["macro_2x2"]
A('<div class="corner">매크로 한눈에</div><table class="g2 pb-avoid"><tr>')
for key, col, bg, ttl in [("호재","#1E8449","#F1FAF3","🟢 호재"), ("반락","#C0392B","#FDF2F1","🔴 반락 요인")]:
    A(f'<td style="border-left-color:{col};background:{bg};"><div class="t" style="color:{col};">{ttl}</div><div>{MB[key]}</div></td>')
A('</tr><tr>')
for key, col, bg, ttl in [("미국장","#245DA3","#F0F5FF","🔵 미국장 (간밤)"), ("정책","#E08A00","#FFF9EE","🟠 정책 / 이벤트")]:
    A(f'<td style="border-left-color:{col};background:{bg};"><div class="t" style="color:{col};">{ttl}</div><div>{MB[key]}</div></td>')
A(f'</tr></table><div class="box box-b" style="font-size:9.6px;">➡ <b>그래서 지금</b> — {MB["sogo"]}</div>')

A(f'''<div class="corner pgnew">★ KOSPI 일봉 차트</div>
<table class="chartwrap"><tr><td>
<div class="ct">📈 KOSPI 일봉 — 6개월(126봉) + 일목 구름 26봉 미래투영 · 이평 3중(10·20·60) · 볼린저(20,2σ) · 전환/기준선 · <b>MACD(12·26·9)</b> · <b>★v45 레벨 보드 + 매물대 패널</b></div>
<img src="{b64("charts/kospi.png")}">
<div class="cap"><b>캡션</b> — {R["kospi_caption"]}<br><b>현재 위치 해석</b> — {R["kospi_read"]}</div>
</td></tr></table>''')

LEVEL_SRC = [("20일선", K["ma20"]), ("일목 구름 상단", K["ctop"]), ("60일선", K["ma60"]),
             ("일목 구름 하단", K["cbot"]), ("볼린저 하단", K["bb_low"]), ("최근 22봉 저점", K["lo22"])]
above = sorted([t for t in LEVEL_SRC if t[1] >  K["close"]], key=lambda t:  t[1])
below = sorted([t for t in LEVEL_SRC if t[1] <= K["close"]], key=lambda t: -t[1])
LV = [(f"저항{i+1}", nm, v) for i, (nm, v) in enumerate(above)][::-1] \
   + [("현재", "코스피 종가", K["close"])] \
   + [(f"지지{i+1}", nm, v) for i, (nm, v) in enumerate(below)]
A('<div class="corner pgnew">② 코스피 시나리오 (3분할)</div><div class="sub2">① 레벨 표 (전부 실측 계산값 · 구분은 현재가 기준 자동 부여)</div>')
A('<table class="pb-avoid"><thead><tr><th style="width:11%">구분</th><th style="width:15%">지표</th><th style="width:13%">지수</th>'
  '<th style="width:11%">현재가 대비</th><th>의미 (실측 병기)</th></tr></thead><tbody>')
for lab, nm, v in LV:
    gap = (v/K["close"]-1)*100
    hl = ' style="background:#FFF6D6;"' if lab == "현재" else ""
    col = "#C0392B" if lab.startswith("저항") else ("#245DA3" if lab.startswith("지지") else "#12325B")
    A(f'<tr{hl}><td class="tc"><b style="color:{col}">{lab}</b></td><td class="tc"><b>{nm}</b></td>'
      f'<td class="tr"><b>{num(v,2)}</b></td>'
      f'<td class="tc">{pct(gap,1) if lab!="현재" else "—"}</td><td class="tl">{R["levels"][nm]}</td></tr>')
A('</tbody></table>')
A('<div class="cap">※ <b>구분(저항/지지)은 라벨 고정이 아니라 현재가와 비교해 매 회차 자동 부여</b>된다 — 숫자가 위면 저항, 아래면 지지. '
  '가까운 쪽이 1번이다. 구름 하단처럼 현재가 위에 있으면 「지지대」가 아니라 <b class="warn">저항</b>으로 표기된다.</div>')
S = R["scenario"]
A(f'''<table class="g2 pb-avoid"><tr>
<td style="border-left-color:#1E8449;background:#F1FAF3;"><div class="t" style="color:#1E8449;">② 상방 시나리오</div>
<div>{S["up"]}<div style="margin-top:4px;padding:4px 6px;background:#fff;border-radius:3px;border:1px dashed #1E8449;">
<b>▶ 관찰 4종 대응</b> — {S["up_watch"]}</div></div></td>
<td style="border-left-color:#C0392B;background:#FDF2F1;"><div class="t" style="color:#C0392B;">③ 조정 시나리오</div>
<div>{S["dn"]}<div style="margin-top:4px;padding:4px 6px;background:#fff;border-radius:3px;border:1px dashed #C0392B;">
<b>▶ 관찰 4종 대응</b> — {S["dn_watch"]}</div></div></td></tr></table>
<div class="box-navy pb-avoid"><span class="chip" style="background:#FFE14D;color:#16243F;">④ 개장 후 체크포인트</span>
<div style="margin-top:4px;line-height:1.6;">{"<br>".join(f"<b>{i+1}.</b> {c}" for i,c in enumerate(S["checkpoints"]))}</div></div>''')

A('<div class="corner pgnew">②-2 탑다운 신호등 — 3층 (L0 수급 최우선)</div>')
A('''<div class="box box-a pb-avoid" style="font-size:9.6px;"><b>📖 보는 법</b> — 위에서 아래로 <b>L0 수급 → L1 매크로 → L2 반도체 사이클</b>.
<b>수급(L0)이 가장 중요하다</b>(사용자 원칙). ● <span class="dg">초록</span>=호재 · ● <span class="dy">노랑</span>=보통 · ● <span class="dr">빨강</span>=악재 ·
● <span class="dgr">회색</span>=검색·계산을 실제로 하고도 못 구한 항목(§8 기록). 각 층 아래 "종합" 1줄, 맨 아래 <b>최종 판정 → 종목 카드 진입 판단</b>으로 연결.</div>''')
for layer, title, boxcls in [("L0","레이어 0 — 수급 (맨 위 · 최우선)","box-r"),
                             ("L1","레이어 1 — 범용 매크로","box-g"),
                             ("L2","레이어 2 — 반도체 / 메모리 사이클 (관찰 4종 직결)","box-a")]:
    A(f'<div class="sub2">{title}</div>')
    A('<table class="pb-avoid"><thead><tr><th style="width:16%">지표</th><th style="width:26%">오늘 값 (실측)</th>'
      '<th style="width:6%">신호</th><th>쉬운 말 한 줄</th></tr></thead><tbody>')
    for row in R["topdown"][layer]:
        A(f'<tr><td class="tl"><b>{row["k"]}</b></td><td class="tl">{row["v"]}</td>'
          f'<td class="tc">{sig(row["c"])}</td><td class="tl">{row["e"]}</td></tr>')
    A('</tbody></table>')
    A(f'<div class="box {boxcls}"><b class="sogo">▶ {layer} 종합</b> — {R["topdown"][layer+"_sum"]}</div>')
V = R["topdown"]["verdict"]
A(f'''<div class="box-navy pb-avoid" style="border-left-color:#E0A800;">
<div style="font-size:13px;font-weight:bold;margin-bottom:5px;">🚦 탑다운 종합 판정 — <span style="color:#FFD54A;">{V["label"]}</span></div>
<div style="line-height:1.65;"><b>① 신호 집계</b> — {V["tally"]}<br>
<b>② 행동 지침</b> — <span class="hl">{V["action"]}</span><br>
<b>③ 카드 연결</b> — {V["link"]}</div></div>''')

def judge(rw, rm):
    if rw>5 and rm>5:   return ("주도", "#C0392B")
    if rw>0 and rm>0:   return ("우위", "#E08A00")
    if rw>0 or rm>0:    return ("중립", "#5A6570")
    if rw>-5 and rm>-5: return ("약세", "#245DA3")
    return ("열위", "#2f6fed")
A('<div class="corner pgnew">③ 섹터 RS 보드 (12섹터)</div>')
A('<table class="pb-avoid"><thead><tr><th style="width:15%">섹터 (대표주)</th><th>주간%</th><th>RS(주)</th>'
  '<th>월간%</th><th>RS(월)</th><th style="width:9%">판정</th><th style="width:38%">해설</th></tr></thead><tbody>')
for k, v in sorted(sec["data"].items(), key=lambda x: -x[1]["rs_w"]):
    j, col = judge(v["rs_w"], v["rs_m"])
    A(f'<tr><td class="tl"><b>{k}</b><br><span style="font-size:8.4px;color:#6B7680;">{v["rep"]}</span></td>'
      f'<td class="tc">{pct(v["w"],1)}</td><td class="tc">{pct(v["rs_w"],1)}</td>'
      f'<td class="tc">{pct(v["m"],1)}</td><td class="tc">{pct(v["rs_m"],1)}</td>'
      f'<td class="tc"><b style="color:{col}">{j}</b></td><td class="tl">{R["sector_notes"].get(k,"")}</td></tr>')
A(f'</tbody></table><div class="cap">RS = 섹터 수익률 − 코스피 수익률. 코스피 기준: 주간 {sec["ks_w"]:+.2f}% / 월간 {sec["ks_m"]:+.2f}%. '
  f'섹터 수익률은 대표주 2종 <b>동일가중 평균 프록시</b>(각주).</div>')
A(f'''<div class="box box-b pb-avoid"><span class="chip c-blue">🏆 PICK 상위 3</span> {R["sector_pick"]}
<div style="margin-top:5px;padding:6px 8px;background:#fff;border:1px dashed #245DA3;border-radius:4px;">
<b>▶ 재진입 분산 관점 — "현금 100%에서 첫 진입을 어느 섹터부터 설계할 것인가"</b><br>{R["sector_diversify"]}</div></div>''')

A(f'<div class="corner pgnew">④ 핵심 종목 4종 — 9블록 카드 (보유 {len(HELD)}종 · 관찰 {len(WATCHONLY)}종 · 동일 강도)</div>')
A(f'<div class="box box-b" style="font-size:9.6px;">★ {R["watch_intro"]}</div>')
BADGE_COL = {"진입 검토": "#1E8449", "진입 검토(조건부)": "#1E8449", "관망": "#E08A00", "회피": "#C0392B",
             "홀드": "#1E8449", "홀드(손절선 엄수)": "#186A3B", "분할 익절": "#00897B",
             "추가매수 검토": "#245DA3", "손절": "#C0392B", "보유·관망": "#E08A00"}

for _wi, (nm, code, tk, cur) in enumerate(C.WATCH):
    x = X(nm); W = R["watch"][nm]; p = PLAN[nm]
    q1, q2 = p["눌림 대기(권장)"], p["돌파 추격"]
    b6, p4 = ceiling(x)
    npar = sum(1 for _, o, _ in p4 if o); nb6 = sum(1 for _, o, _ in b6 if o)
    hot = x["rsi_w"] >= 75 or x["close"] > x["bb_up"]; conf = x["nsig"] >= 6
    bcol = BADGE_COL.get(W["badge"], "#E08A00")
    bd = ('<span class="pillw bad-hot">과열</span>' if hot else '') + ('<span class="pillw bad-hi">고확신</span>' if conf else '')
    _pg = '' if _wi == 0 else ' pgnew'
    A(f'''<div class="card{_pg}"><div class="chead"><span class="nm">{nm}</span><span class="tk">{code}</span>
    <span class="rt"><span class="pillw">{money(cur,x["close"])}</span>
    <span class="pillw">{"▲" if x["chg"]>0 else "▼"} {abs(x["chg"]):.2f}%</span>
    <span class="pillw">19신호 {x["score"]:.1f}점</span>{bd}</span><div style="clear:both"></div></div><div class="cbody">''')

    A(f'''<div class="blk"><span class="chip c-navy">① 한눈에</span><div class="box-navy" style="margin-top:2px;">
    <div style="font-size:12px;"><b style="background:{bcol};color:#fff;padding:2px 9px;border-radius:10px;">진입 판단 : {W["badge"]}</b>
    <span style="margin-left:7px;font-size:9.6px;opacity:.85;">{W.get("pos_note", M["position_note"])}</span></div>
    {(f'<div style="margin-top:4px;font-size:11px;background:#0f1c33;border-radius:4px;padding:3px 7px;">'
      f'· <b>평가손익</b> — <b style="font-size:13px;color:{"#FF8A80" if pnl(nm)["amt"]<0 else "#7BE8A5"};">'
      f'{pnl(nm)["amt"]:+,.0f}원 ({pnl(nm)["rate"]:+.2f}%)</b> &nbsp;'
      f'<span style="opacity:.85;">평단 {money(cur,pnl(nm)["avg"])} × {pnl(nm)["qty"]}주 = 매입 {pnl(nm)["cost"]:,.0f}원 → 평가 {pnl(nm)["val"]:,.0f}원</span></div>'
      if held(nm) else "")}
    <div style="margin-top:5px;">· <b>근거</b> — {W["why"]}</div>
    <div style="margin-top:3px;">· <b>행동 지침</b> — <span class="hl">{W["action"]}</span></div>
    <div style="margin-top:3px;color:#FF8A80;">· <b>위험 지침</b> — {W["danger"]}</div></div></div>''')

    if held(nm):
        P, S = pnl(nm), stop_of(nm)
        rr_up = (R["watch"][nm]["t_cons"] - x["close"]) / (x["close"] - S["stop"]) if x["close"] > S["stop"] else 0
        A(f'''<div class="blk keep"><span class="chip c-gray">② 포지션 상태 — <b>보유 중</b> (실계산)</span>
        <table><thead><tr><th>평단</th><th>수량</th><th>매입금액</th><th>평가금액</th>
        <th>평가손익</th><th>수익률</th><th>손절선 (앵커)</th><th>손절 시 손실</th></tr></thead><tbody>
        <tr><td class="tr"><b>{money(cur,P["avg"])}</b></td><td class="tc">{P["qty"]}주</td>
        <td class="tr">{money(cur,P["cost"])}</td><td class="tr">{money(cur,P["val"])}</td>
        <td class="tr">{m_amt(cur,P["amt"])}</td>
        <td class="tc"><b class="{"vg" if P["rate"]>0 else "vr"}">{P["rate"]:+.2f}%</b></td>
        <td class="tr"><b class="warn">{money(cur,S["s1"])}</b><span style="font-size:8.4px;"> ← 1차</span><br>
        <b class="warn">{money(cur,S["s3"])}</b><span style="font-size:8.4px;"> ← 최종({S["s_pct"]:+.1f}%)<br>{S["mode"]} · {S["adopt"]}</span></td>
        <td class="tr"><b class="warn">{m_neg(cur,S["risk"])}</b><br><span style="font-size:8.4px;">3단 누적</span></td></tr></tbody></table>
        <div class="box box-r"><b>▶ 보유 판단</b> — {W["hold_read"]}</div></div>''')
        A('<div class="blk keep"><span class="chip c-red">② -2 손절 3단 분할 (v42 · 캡 '
          + f'{C.STOP_CAP*100:.0f}% · 동적 배수 {S["k"]:g}×ATR)</span>'
          + '<table><thead><tr><th style="width:13%">단계</th><th style="width:17%">근거</th><th>손절선</th>'
            '<th>현재가 대비</th><th>축소 수량</th><th>이 단계 손실</th><th style="width:27%">행동</th></tr></thead><tbody>')
        _ACT = ["종가 이탈 시 <b>1/3 축소</b> — 전량 아님",
                "종가 이탈 시 <b>추가 1/3 축소</b>",
                "종가 이탈 시 <b class='warn'>잔여 전량 정리</b>"]
        for _i, r in enumerate(S["rows"]):
            A(f'<tr><td class="tc"><b>{r["lab"]}</b></td><td class="tc">{r["src"]}</td>'
              f'<td class="tr"><b class="warn">{money(cur, r["lv"])}</b></td>'
              f'<td class="tc"><b class="vr">{r["pct"]:+.2f}%</b></td>'
              f'<td class="tc">{r["qty"]:.0f}주<br><span style="font-size:8.4px;">(1/3)</span></td>'
              f'<td class="tr">{m_neg(cur, r["loss"])}</td><td class="tl">{_ACT[_i]}</td></tr>')
        _save = (1 - S["risk"]/S["risk_single"])*100 if S["risk_single"] else 0
        A(f'''</tbody></table>
        <div class="box box-r"><b>▶ 손절 규격(1-3 · v42)</b> — 앵커 <b>{money(cur,S["anchor"])}</b>({S["mode"]}) ·
        ATR <b>{x["atr_pct"]:.1f}%</b> → 동적 배수 <b>{S["k"]:g}×</b> ·
        {"<b class='warn'>변동성 상한(캡) 적용</b>" if S["capped"] else "캡 미적용(변동성이 낮아 배수가 먼저 걸림)"} →
        최종선 <b class="warn">{money(cur,S["s3"])}</b>({S["s_pct"]:+.1f}%).<br>
        <span class="hl">3단을 전부 맞았을 때의 누적 손실 = {m_neg(cur,S["risk"])}</span> —
        같은 손절선을 한 번에 전량 적용했을 때({m_neg(cur,S["risk_single"])}) 대비 <b class="vg">{_save:.0f}% 절감</b>.<br>
        <b>▶ 시간 손절</b> — 진입 트리거가 꺼진 채 <b>1차 경계선 아래 {C.STOP_TIME_D}거래일</b> 지속 시 단계와 무관하게 축소 검토.<br>
        <b>▶ 재진입 규칙</b> — 축소 후 트리거가 다시 켜지면 <b>같은 비율로 되돌린다</b>(축소는 영구 청산이 아니다).<br>
        <b>▶ 목표(컨센 {money(cur,R["watch"][nm]["t_cons"])}) 기준 잔여 R:R</b> — <b>{rr_up:.2f}</b>
        (현재가에서 <b>최종선</b>까지의 손실 기준)</div></div>''')
    else:
        A(f'''<div class="blk"><span class="chip c-gray">② 포지션 상태 — <b>미보유(관찰)</b></span><div class="box">
        <b>{M["position_line"]}</b><br><b>재진입 조건 요약</b> — {W["trigger"]}</div></div>''')

    A(f'''<table class="chartwrap"><tr><td><span class="chip c-purple">③ 차트</span>
    <div class="ct">📈 {nm} 일봉 — 6개월 + 구름 26봉 미래투영 · 이평 3중 · 볼린저 · 전환/기준선 · <b>MACD(12·26·9)</b></div>
    <img src="{b64(f"charts/{code}.png")}">
    <div class="cap">{(f'<b class="warn">붉은 굵은 점선 = 평단 {money(cur,pnl(nm)["avg"])}</b> · <b class="warn">주황 음영 = 손절 구간 {money(cur,stop_of(nm)["s3"])}~{money(cur,stop_of(nm)["s1"])}</b>(3단선이 −1~2%에 밀집해 선 3개는 지웠다 — 단계별 숫자는 아래 ④ 손절 3단 분할 표에서 본다)'
       if held(nm) else f'평단선 없음(무포지션). <b>진입 후보선 = 20일선 {money(cur,x["ma20"])}</b> · <b>손절 후보선 = {money(cur,q1["stop"])}</b>(눌림 진입 기준)')}. ★v45 <b>레벨 보드</b> 신설 — 차트 오른쪽에 <b>이평(10·20·60)·볼린저(상/중/하)·일목(전환·기준·구름)·매물대(POC·VAH·VAL)·미충족 갭·직전 스윙 고점/눌림목</b>을 한데 모아 <b>저항 R1~R5 / 지지 S1~S5</b>로 정렬해 표기한다(현재가 ±25% 이내만). 가격 패널에는 <b>가장 가까운 R1·S1과 매물대 POC 3개 선만</b> 그려 캔들·이평·구름을 가리지 않는다. 우측 <b>매물대 패널</b>은 표시구간 거래량을 가격대별로 쌓은 것이며, 금색 막대가 <b>POC(거래가 가장 많이 쌓인 가격대)</b>다.</div>
    </td></tr></table>''')

    A('<div class="blk keep"><span class="chip c-blue">④ ★ 진입 실행표</span><table><thead><tr>'
      '<th style="width:17%">시나리오</th><th>진입가 (현재가 대비)</th><th>손절 (넓은 쪽 채택)</th>'
      '<th>목표 (기술 / 컨센)</th><th style="width:13%">R:R</th></tr></thead><tbody>')
    for sc in ["눌림 대기(권장)", "돌파 추격"]:
        q = p[sc]; rc = "vg" if q["rr"]>=2 else ("vy" if q["rr"]>=1 else "vr")
        A(f'''<tr><td class="tc"><b>{sc}</b></td>
        <td class="tc"><b>{money(cur,q["entry"])}</b><br><span style="font-size:8.8px;">({pct(q["e_pct"],1)})</span></td>
        <td class="tc"><b>{money(cur,q["stop"])}</b><br><span style="font-size:8.8px;">({pct(q["s_pct"],1)})</span></td>
        <td class="tc">{money(cur,q["t_tech"])}<br><span style="font-size:8.8px;">컨센 {money(cur,q["t_cons"])}</span></td>
        <td class="tc"><b class="{rc}">{q["rr"]:.2f}</b><br><span style="font-size:8.8px;">컨센 {q["rr_cons"]:.2f}</span></td></tr>''')
    A('</tbody></table>')
    A(f'''<table class="g2"><tr>
    <td style="border-left-color:#245DA3;background:#F0F5FF;"><div class="t">ⓐ 진입 존 — 무엇이 확인되면</div>
    {W["trigger"]}<br><b>눌림 존</b>: {money(cur,q1["entry"])} 부근(볼린저 하단·구름 하단 겹침). <b>돌파 존</b>: {money(cur,q2["entry"])} 종가 회복.</td>
    <td style="border-left-color:#245DA3;background:#F0F5FF;"><div class="t">ⓑ 분할 진입 방식</div>
    <b>{C.SPLIT[0]} / {C.SPLIT[1]} / {C.SPLIT[2]}</b> — 1차 {C.SPLIT[0]}%(트리거 점등), 2차 {C.SPLIT[1]}%(20일선 안착 3일), 3차 {C.SPLIT[2]}%(60일선 회복).
    <b class="warn">한 번에 다 사지 않는다.</b><br><span style="font-size:9px;">★v41: <b>2%룰 폐기</b>로 1회 투입 금액을 규칙이 정해주지 않는다 — 이 종목의 손절폭 <b>{abs(q1["s_pct"]):.0f}%</b>(ATR {x["atr_pct"]:.1f}%)를 보고 <b>본인이 감당할 손실 금액 ÷ 손절폭</b>으로 직접 정한다.</span></td>
    </tr><tr>
    <td style="border-left-color:#C0392B;background:#FDF2F1;"><div class="t">ⓒ 손절 후보 (둘 중 넓은 쪽)</div>
    ★v42 규격 — 상한식(진입가×{1-C.STOP_CAP:.2f}) = <b>{money(cur,q1["s_fix"])}</b> vs 변동성식(진입가−{k_of(x["atr_pct"],C.ATR_K_TABLE):g}×ATR) = <b>{money(cur,q1["s_vol"])}</b> → <b class="warn">좁은(높은) 쪽 {money(cur,q1["stop"])} 채택</b>.
    <br><span style="font-size:9px;">ATR {x["atr_pct"]:.1f}% → 동적 배수 <b>{k_of(x["atr_pct"],C.ATR_K_TABLE):g}×</b>. <b>손절폭은 어떤 경우에도 {C.STOP_CAP*100:.0f}%를 넘지 않는다</b> — 고정 3×ATR이 폭락기에 −40%까지 벌어지던 문제를 캡으로 막는다. 실제 청산은 <b>3단 분할</b>로 1/3씩.</span></td>
    <td style="border-left-color:#C0392B;background:#FDF2F1;"><div class="t">ⓓ 진입 회피 조건</div>
    · <b>포물선 천장 2개 이상 점등</b> (현재 <b class="{"vr" if npar>=2 else "vg"}">{npar}개</b>)<br>
    · <b>탑다운 회피 모드</b> 진입 (현재 {V["short"]})<br>
    · <b>L0 방어 모드 지속</b> (현재 {R["topdown"]["L0_short"]})<br>· {W["avoid"]}</td>
    </tr></table></div>''')

    A(f'''<div class="blk"><span class="chip c-teal">⑤ 맥락 (웹 리서치)</span>
    <div class="box box-g" style="font-size:9.8px;line-height:1.6;">
    <b>① 최근 뉴스</b><br>{"".join(f'&nbsp;&nbsp;· <b>{d}</b> — {t}<br>' for d,t in W["news"])}
    <b>② 목표가</b> — {W["tgt"]}<br>
    <b>③ 세부 (증권사 · 목표가 · 발간일)</b> — {W["tgt_detail"]}<br>
    <b>④ 실적 · 이벤트</b> — {W["earnings"]}<br>
    <b>⑤ 밸류에이션</b> — {W["valuation"]}<br>
    <b>⑥ 해석 (회사가 나빠졌나 vs 주가가 비싸졌나)</b> — {W["read"]}<br>
    <b>⑦ ★ 무엇이 확인되면 진입</b> — {W["trigger"]}</div></div>''')

    A('<div class="blk keep"><span class="chip c-red">⑥ 천장 / 과열 상시 감시</span><table><thead>'
      '<tr><th colspan="3" style="background:#FDECEA;">기본 6신호</th><th colspan="3" style="background:#FDECEA;">포물선 천장 4신호</th></tr>'
      '<tr><th style="width:16%">신호</th><th style="width:7%">상태</th><th style="width:14%">실측값</th>'
      '<th style="width:16%">신호</th><th style="width:7%">상태</th><th style="width:14%">실측값</th></tr></thead><tbody>')
    for i in range(6):
        n1, o1, v1 = b6[i]
        if i < 4:
            n2, o2, v2 = p4[i]
            c2 = (f'<td class="tl">{n2}</td><td class="tc">{"<span class=on>ON</span>" if o2 else "<span class=off>off</span>"}</td>'
                  f'<td class="tc">{v2}</td>')
        else:
            c2 = '<td colspan="3" style="background:#FAFBFC;"></td>'
        A(f'<tr><td class="tl">{n1}</td><td class="tc">{"<span class=on>ON</span>" if o1 else "<span class=off>off</span>"}</td>'
          f'<td class="tc">{v1}</td>{c2}</tr>')
    vd = "정상" if npar<=1 else ("과열 경계" if npar==2 else "천장 임박")
    vc = "vg" if npar<=1 else ("vy" if npar==2 else "vr")
    ma60_off = any(n=="60일선 이탈" and o for n,o,_ in b6)
    A(f'''</tbody></table><div class="box box-r" style="margin-top:3px;"><b>▶ 판정 (무포지션 관점)</b> —
    기본 6신호 <b>{nb6}개</b> ON · 포물선 <b class="{vc}">{npar}개</b> ON → <b class="{vc}">{vd}</b>.
    {'<span class="hl">포물선 2개↑ 점등 시 진입 보류</span> — 현재 미충족이므로 진입 자체를 막지는 않는다. 다만 ' +
      ('<b class="warn">60일선 이탈이 켜져 중기 추세가 깨진 상태</b>다.' if ma60_off else '<b>60일선은 지키고 있다</b> — 중기 추세는 살아있다.')
      if npar<2 else '<span class="hl warn">포물선 2개 이상 점등 — 신규 진입 보류.</span>'}</div></div>''')

    ons = [k for k, v in x["on"].items() if v]
    KEY_OFF = ["전고점임박","전고점돌파","구름대돌파","삼역호전","골든크로스","MACD호전","RSI반등","밴드타기"]
    offs = [k for k, v in x["on"].items() if not v and k in KEY_OFF]
    NEAR = {"RSI반등","MACD호전","전환기준선호전","하단밴드반등","구름대돌파","골든크로스"}
    _bd = band_of(x["score"], SCORE_BANDS)
    _bc = "vg" if _bd[0] in ("강", "양") else ("vy" if _bd[0] == "중립" else "vr")
    A(f'''<div class="blk"><span class="chip c-amber">⑦ 통과 신호 (켜짐 + 꺼짐)</span><div class="box box-a" style="font-size:9.7px;">
    <b>합산 점수 {x["score"]:.1f}점 / 100점 만점 · 켜진 신호 {x["nsig"]}개</b>
    <b class="{_bc}">({_bd[0]}) {_bd[1]}</b>{'<b class="vg"> · 고확신(6개↑)</b>' if conf else ''}<br>
    <div style="margin:3px 0;">{dual_html(x)}</div>
    <b style="color:#1E8449;">▶ 켜진 신호</b> — ''')
    A(" · ".join(f'{sig("g")}<b>{k}({WEIGHTS[k]:.1f})</b>{" <span class=warn>(참고·점수 미반영)</span>" if k in ZERO_SIGS else ""} <span style="font-size:8.8px;color:#5A6570;">{x["det"][k]}</span>' for k in ons) or "없음")
    A('<br><b style="color:#C0392B;">▶ 꺼진 핵심 신호 (언제 켜지나 / 왜 안 켜졌나)</b><br>')
    for k in offs:
        _zm = ' <span class="warn">(참고·점수 미반영)</span>' if k in ZERO_SIGS else ''
        A(f'&nbsp;&nbsp;{sig("y") if k in NEAR else sig("x")} <b>{k}({WEIGHTS[k]:.1f})</b>{_zm} — {W["off_why"].get(k, x["det"][k])}<br>')
    _ns = next_signals(x["on"], 2)
    _nxt = x["score"] + sum(WEIGHTS[k] for k in _ns)
    _ns_txt = " · ".join(f'<b>{k}</b>(실측 가중치 {WEIGHTS[k]:.1f}점 · {x["det"].get(k,"")})' for k in _ns) or "없음(핵심 신호 대부분 점등)"
    A(f'''<div style="margin-top:4px;padding:4px 6px;background:#fff;border:1px dashed #E08A00;border-radius:3px;">
    <b>▶ 가장 먼저 켜질 신호 (실측 가중치 순)</b> — {_ns_txt}. 이들이 켜지면
    <span class="hl">점수가 {x["score"]:.1f} → {_nxt:.1f}점으로 오른다</span>.
    <span style="font-size:8.6px;color:#6B7680;">(꺼진 신호 중 <b>실측 가중치</b>가 큰 순으로 자동 선택 — 실측 1.2점짜리 구름대돌파를 '트리거 근접'으로 오인하던 v46 버그를 v47에서 교정.)</span></div></div></div>''')

    ax = axis6(x)
    A('<div class="blk keep"><span class="chip c-purple">⑧ 차트 해석 6축 + 결론</span><table style="border-spacing:0;"><tr>')
    for an, av, ac, ad in ax:
        A(f'<td class="ax"><div class="an">{an}</div><div class="av">{sig(ac)} <span class="v{ac}">{av}</span></div><div class="ad">{ad}</div></td>')
    ngr = sum(1 for _,_,c,_ in ax if c=="g"); nrd = sum(1 for _,_,c,_ in ax if c=="r")
    A(f'''</tr></table><div class="concl">▶ <b>결론</b> — 6축 초록 {ngr} / 빨강 {nrd}.
    <b>진입 {money(cur,q1["entry"])}</b>(눌림·권장) · <b>손절 {money(cur,q1["stop"])}</b> ·
    <b>목표 {money(cur,q1["t_tech"])}</b>(기술) / {money(cur,q1["t_cons"])}(컨센) · <b>R:R {q1["rr"]:.2f}</b>
    → <b style="background:{bcol};color:#fff;padding:1px 8px;border-radius:9px;">{W["badge"]}</b>. {W["concl"]}</div></div>''')

    A(f'''<div class="blk"><span class="chip c-gray">⑨ 리스크</span><div class="box">{W["risk"]}<br>
    <b>회피 조건</b> — 탑다운이 <b>회피 모드</b>로 전환(빨강 4↑ / L2 빨강 2↑ / <b>BTC {C.BTC_ALERT:,}$ 이탈</b>) 또는
    §전량청산급 환경(지수 연속 급락 + VIX 30↑ + 섹터 동반 붕괴) 시 <b class="warn">진입 계획 전면 철회</b>.</div></div>
    </div></div>''')

A('<div class="corner pgnew">포지션 · 현금 대시보드</div>')
WN = [n for n, _, _, _ in C.WATCH]
if HELD:
    A('<div class="sub2">★ 보유 포지션 합산 (실계산 — 계약 9 / 절대원칙 1)</div>')
    A('<table class="pb-avoid keep"><thead><tr><th>종목</th><th>평단</th><th>수량</th><th>매입금액</th>'
      '<th>현재가</th><th>평가금액</th><th>평가손익</th><th>수익률</th><th>손절선</th><th>손절 시 손실</th></tr></thead><tbody>')
    for n in HELD:
        P, S, cur = pnl(n), stop_of(n), cur_of(n)
        A(f'<tr><td class="tl"><b>{n}</b></td><td class="tr">{money(cur,P["avg"])}</td>'
          f'<td class="tc">{P["qty"]}주</td><td class="tr">{money(cur,P["cost"])}</td>'
          f'<td class="tr"><b>{money(cur,X(n)["close"])}</b><br><span style="font-size:8.4px;">{pct(X(n)["chg"])}</span></td>'
          f'<td class="tr">{money(cur,P["val"])}</td><td class="tr">{m_amt(cur,P["amt"])}</td>'
          f'<td class="tc"><b class="{"vg" if P["rate"]>0 else "vr"}">{P["rate"]:+.2f}%</b></td>'
          f'<td class="tr"><b class="warn">{money(cur,S["stop"])}</b></td>'
          f'<td class="tr"><b class="warn">{m_neg(cur,S["risk"])}</b></td></tr>')
    TR_KRW = sum(stop_of(n)["risk"] for n in HELD_KRW)
    TR_USD = sum(stop_of(n)["risk"] for n in HELD_USD)
    if HELD_KRW:
        A(f'<tr style="background:#E9F0FB;"><td class="tl"><b>국장 소계(₩)</b></td><td colspan="2" class="tc">—</td>'
          f'<td class="tr"><b>{money("₩",KRW_COST)}</b></td><td class="tc">—</td><td class="tr"><b>{money("₩",KRW_VAL)}</b></td>'
          f'<td class="tr">{m_amt("₩",KRW_AMT)}</td>'
          f'<td class="tc"><b class="{"vg" if KRW_AMT>0 else "vr"}">{KRW_RATE:+.2f}%</b></td>'
          f'<td class="tc">—</td><td class="tr"><b class="warn">{m_neg("₩",TR_KRW)}</b></td></tr>')
    if HELD_USD:
        A(f'<tr style="background:#EAF4EE;"><td class="tl"><b>미장 소계($)</b></td><td colspan="2" class="tc">—</td>'
          f'<td class="tr"><b>{money("$",USD_COST)}</b></td><td class="tc">—</td><td class="tr"><b>{money("$",USD_VAL)}</b></td>'
          f'<td class="tr">{m_amt("$",USD_AMT)}</td>'
          f'<td class="tc"><b class="{"vg" if USD_AMT>0 else "vr"}">{USD_RATE:+.2f}%</b></td>'
          f'<td class="tc">—</td><td class="tr"><b class="warn">{m_neg("$",TR_USD)}</b></td></tr>')
    A('</tbody></table>')
    TR_USD_KRW = TR_USD * FX
    TR_TOTAL = TR_KRW + TR_USD_KRW
    over = (TR_TOTAL / C.ACCOUNT_TOTAL * 100) if C.ACCOUNT_TOTAL else 0.0
    A(f'<div class="box box-b pb-avoid"><b>▶ 리스크 노출 실측 (통합 시드 {C.ACCOUNT_TOTAL//100000000}억 · <span class="hl">2%룰 미적용</span>)</b> — '
      f'국장 <b>{m_neg("₩",TR_KRW)}</b> + 미장 <b>{m_neg("$",TR_USD)}</b>'
      f'(원화 환산 {m_neg("₩",TR_USD_KRW)} · 원/달러 {FX:,.2f}) = <b>총 {m_neg("₩",TR_TOTAL)}</b> = 통합 시드의 <b>{over:.1f}%</b>.<br>'
      f'<span style="font-size:9.2px;">이 숫자는 <b>"규격 손절선까지 전부 밀렸을 때의 최대 손실"</b>이며 <b class="warn">위반·초과 판정이 아니다</b>. '
      f'손절폭이 넓은 이유는 ATR(변동성)이 크기 때문이고, 넓은 손절폭은 <b>휩쏘에 안 털리는 대가</b>다. '
      f'축소 여부는 룰이 아니라 <b>본인이 감당 가능한 금액인가</b>로 판단한다.</span><br>'
      f'<span style="font-size:8.6px;color:#6B7680;">※ P&amp;L·손절선은 각 통화(원/달러) 표기, 노출 합산만 원화 환산.</span><br>'
      f'{R["dashboard"].get("risk_note","")}</div>')
    A('<div class="sub2">★ 4종 비교표 (보유 2 + 관찰 2 · 동일 강도)</div>')
A('<table class="pb-avoid"><thead><tr><th style="width:13%">구분</th>' +
  "".join(f'<th>{n}</th>' for n in WN) + '<th style="width:22%">비고</th></tr></thead><tbody>')
DB = R["dashboard"]
A('<tr><td class="tl"><b>ⓐ 현재가 · 등락</b></td>' + "".join(
  f'<td class="tc"><b>{money(cur_of(n), X(n)["close"])}</b><br>{pct(X(n)["chg"])}</td>' for n in WN) +
  f'<td class="tl">{DB["note_a"]}</td></tr>')
A('<tr><td class="tl"><b>ⓑ 진입 후보가</b><br><span style="font-size:8.6px;">(눌림 기준)</span></td>' + "".join(
  f'<td class="tc"><b>{money(cur_of(n), PLAN[n]["눌림 대기(권장)"]["entry"])}</b><br>'
  f'<span style="font-size:8.6px;">{pct(PLAN[n]["눌림 대기(권장)"]["e_pct"],1)}</span></td>' for n in WN) +
  f'<td class="tl">{DB["note_b"]}</td></tr>')
A('<tr><td class="tl"><b>ⓒ 손절 후보가</b></td>' + "".join(
  f'<td class="tc"><b class="warn">{money(cur_of(n), PLAN[n]["눌림 대기(권장)"]["stop"])}</b><br>'
  f'<span style="font-size:8.6px;">{pct(PLAN[n]["눌림 대기(권장)"]["s_pct"],1)}</span></td>' for n in WN) +
  '<td class="tl">★v42: 동적 배수 vs 상한(캡 15%) 중 <b>좁은 쪽</b> 채택 · 실제 청산은 3단 분할</td></tr>')
A('<tr><td class="tl"><b>ⓓ 목표가</b><br><span style="font-size:8.6px;">(컨센 / 기술)</span></td>' + "".join(
  f'<td class="tc">{money(cur_of(n), R["watch"][n]["t_cons"])}<br>'
  f'<span style="font-size:8.6px;">기술 {money(cur_of(n), R["watch"][n]["t_tech"])}</span></td>' for n in WN) +
  f'<td class="tl">{DB["note_d"]}</td></tr>')
A('<tr><td class="tl"><b>ⓔ 기술 위치</b><br><span style="font-size:8.6px;">(20일선·구름)</span></td>' + "".join(
  f'<td class="tc">20일선 <b class="{"vg" if X(n)["vs_ma20"]>0 else "vr"}">{X(n)["vs_ma20"]:+.1f}%</b><br>'
  f'<span style="font-size:8.6px;">{"구름 위" if X(n)["close"]>X(n)["cloud_top"] else ("구름 안" if X(n)["close"]>X(n)["cloud_bot"] else "구름 아래")} · '
  f'{"양운" if X(n)["bull_cloud"] else "음운"}</span></td>' for n in WN) +
  f'<td class="tl">{DB["note_e"]}</td></tr>')
A('<tr><td class="tl"><b>ⓕ 진입 판단</b></td>' + "".join(
  f'<td class="tc"><b style="background:{BADGE_COL.get(R["watch"][n]["badge"],"#E08A00")};color:#fff;padding:1.5px 6px;'
  f'border-radius:9px;font-size:9px;">{R["watch"][n]["badge"]}</b><br>'
  f'<span style="font-size:8.5px;">{DB["reason"][n]}</span></td>' for n in WN) +
  f'<td class="tl">{DB["note_f"]}</td></tr></tbody></table>')
A(f'''<table class="g2 pb-avoid"><tr>
<td style="border-left-color:#245DA3;background:#F0F5FF;"><div class="t" style="color:#245DA3;">① 현금 상태</div>{DB["cash"]}</td>
<td style="border-left-color:#C0392B;background:#FDF2F1;"><div class="t" style="color:#C0392B;">⚠ ② 쏠림 재발 방지</div>{DB["concentration"]}</td>
</tr></table>
<div class="box-navy pb-avoid stick" style="border-left-color:#FFE14D;">
<div style="font-size:12.5px;font-weight:bold;margin-bottom:4px;">💡 ③ 오늘의 재진입 지침</div>
<div style="line-height:1.65;">{DB["guide"]}</div></div>''')

SCN = getattr(C, "SCREEN_N", 5)
CORE = {w[0] for w in C.WATCH}
def cloudpos(x):
    if x["close"] > x["cloud_top"]: return '<b class="vg">위</b>'
    if x["close"] < x["cloud_bot"]: return '<b class="vr">아래</b>'
    return '<b class="vy">안</b>'
def buy_strength(x):
    hot = x["rsi_w"] >= 75 or x["close"] > x["bb_up"]
    up20 = x["vs_ma20"] > 0; s = x["nsig"]
    if hot:                       return ("과열 주의", "#C0392B", "추격 자제")
    if s >= 6 and up20:           return ("적극 매수", "#1E8449", "다신호+20일선 위")
    if s >= 5 or (s >= 4 and up20): return ("매수", "#2E9E5B", "신호 우위")
    if s >= 3:                    return ("관심", "#E08A00", "일부 점등")
    if s >= 2:                    return ("중립", "#8A939C", "관망")
    return ("회피", "#245DA3", "신호 부족")
def next_trigger(x):
    ns = next_signals(x["on"], 1)
    if not ns: return "—"
    k = ns[0]
    return f'{k} <span style="font-size:8px;color:#6B7680;">(실측 {WEIGHTS[k]:.1f}점 · {x["det"].get(k,"")})</span>'
PICKD = D.get("pick", {})
REG = D.get("regime") or {}

A('<div class="corner pgnew">⑤ 종목 선정 — 선정 점수 (구 「19신호 매수강도」 폐기)</div>')
if REG:
    _rc = {"위험선호(Risk-On)": "#1E8449", "중립": "#E08A00"}.get(REG.get("state"), "#C0392B")
    A(f'<div class="box box-b pb-avoid" style="font-size:10px;border-left-color:{_rc};">'
      f'🌐 <b>시장 레짐</b> — <b style="background:{_rc};color:#fff;padding:2px 9px;border-radius:10px;">{REG.get("state")}</b>'
      f' · <b>권장 포지션 상한 {REG.get("size_pct")}%</b><br>'
      f'<span style="font-size:9px;color:#5A6570;">{REG.get("note")}</span><br>'
      f'<span class="hl">좋은 셋업도 나쁜 시장에서는 깨진다. 아래 선정 점수와 무관하게 <b>전 종목 진입 수량에 이 상한을 곱한다</b>.</span></div>')

A('<div class="box box-a pb-avoid" style="font-size:9.2px;">📖 <b>선정 점수</b> = 성격에 맞는 모델 점수 × 0.6 '
  '+ R:R(최대 4로 캡) × 5 + 거래대금 가점 + 진폭 가점 − 갭 감점 + 스퀴즈 가점 '
  '<b class="warn">− 종목별 검증 미통과 15 − 역방향 경고 15</b>. '
  '감점이 −15인 이유는 <b>틀린 자를 쓰는 것이 점수가 조금 낮은 것보다 훨씬 나쁘기</b> 때문이다.<br>'
  '<b>적용 모델</b> — 종목 성격(과거20일↔이후20일 초과수익 상관, 임계 −0.02)이 양수면 <b>추세 모델</b>, '
  '음수면 <b>되돌림 모델</b>. <b class="warn">회귀형 종목에서 추세점수가 높은 것은 매수 신호가 아니라 경고다</b>(표본외 −1.33%).<br>'
  '<b>종목별 검증</b> — 그 종목 «과거»에서 고점수 구간이 저점수 구간보다 실제로 나았는가. '
  '✕면 「이 종목에서는 점수를 근거로 쓰지 말라」는 뜻이다. '
  '<b class="warn">핵심 보유 4종은 제외</b> — 별도 카드로 관리.</div>')

for _mk, _pool, _title in [("kr", kr, "코스피 선정 상위"), ("us", us, "미국 선정 상위")]:
    _P = PICKD.get(_mk, {})
    _rows = [r for r in _P.get("picks", []) if r["name"] not in CORE][:SCN]
    A(f'<div class="sub2">{_title} {SCN}</div><table class="pb-avoid"><thead><tr>'
      '<th style="width:13%">종목</th><th style="width:8%">선정 점수</th>'
      '<th style="width:16%">적용 모델 · 종목 성격</th><th style="width:8%">검증</th>'
      '<th style="width:7%">R:R</th><th style="width:14%">진입 방식</th>'
      '<th style="width:9%">19신호(참고)</th><th>산출 근거</th></tr></thead><tbody>')
    for r in _rows:
        _x = _pool.get(r["name"], {})
        _sc = r["score"]; _vl = r["valid"]; _tr = r["trade"]
        _ch = "회귀형" if _sc["is_rev"] else "추세형"
        _cc = "vy" if _sc["is_rev"] else "vg"
        _wb = ('<br><b class="vr" style="font-size:8px;">⚠ 역방향 경고</b>' if _sc.get("trend_warn") else '')
        _vv = ('<b class="vg">○ 통과</b>' if _vl["works"]
               else '<b class="vr">✕ 미통과</b><br><span style="font-size:7.6px;color:#8A939C;">점수 근거 금지</span>')
        _rr = ("%.2f" % _tr["rr"]) if _tr.get("rr") else "—"
        A(f'<tr><td class="tl"><b>{r["name"]}</b></td>'
          f'<td class="tc"><b style="font-size:12px;">{r["rank_score"]:.1f}</b></td>'
          f'<td class="tc"><b>{_sc["model"]}</b> {_sc["used"]:.1f}점({_sc["band"]})<br>'
          f'<span style="font-size:8px;">성격 <b class="{_cc}">{_ch}</b> {_sc["char"]}</span>{_wb}</td>'
          f'<td class="tc">{_vv}</td><td class="tc">{_rr}</td>'
          f'<td class="tl" style="font-size:8.6px;">{r["behav"]["style"]}</td>'
          f'<td class="tc"><span style="color:#8A94A0;">{_x.get("score", 0):.1f}점</span></td>'
          f'<td class="tl" style="font-size:8.4px;">{r["why"]}</td></tr>')
    if not _rows:
        A('<tr><td colspan="8" class="tc">하드 필터를 통과한 후보 없음</td></tr>')
    A('</tbody></table>')

    _ex = _P.get("excluded", [])
    if _ex:
        _show = sorted(_ex, key=lambda z: -(_pool.get(z["name"], {}).get("score") or 0))[:8]
        A(f'<div class="sub2">⛔ 하드 필터 탈락 — {_title.split()[0]} {len(_ex)}종 중 19신호 상위 {len(_show)}종</div>'
          '<table class="pb-avoid"><thead><tr><th style="width:16%">종목</th>'
          '<th style="width:10%">19신호</th><th style="width:12%">20일 거래대금</th>'
          '<th style="width:10%">일중 진폭</th><th style="width:11%">왕복비용</th>'
          '<th>탈락 사유</th></tr></thead><tbody>')
        for r in _show:
            _t = r["trade"]; _u = "억" if _mk == "kr" else "억$"
            A(f'<tr><td class="tl"><b>{r["name"]}</b></td>'
              f'<td class="tc">{(_pool.get(r["name"], {}).get("score") or 0):.1f}점</td>'
              f'<td class="tc">{_t["amt20"]/1e8:,.1f}{_u}</td>'
              f'<td class="tc">{_t["rng20"]:.2f}%</td>'
              f'<td class="tc">{_t["cost"]:.2f}%</td>'
              f'<td class="tl"><b class="vr">{" / ".join(r["exclude_why"])}</b></td></tr>')
        A('</tbody></table>')

A('<div class="box box-a pb-avoid" style="font-size:9.2px;">⛔ <b>탈락 표를 반드시 읽어야 하는 이유</b> — '
  '점수가 좋아도 <b>못 사고 못 파는 종목</b>이 있다. 실측 사례: 거래대금 42억 종목은 스윙 물량을 실으면 내가 시장을 밀고, '
  '목표가와 현재가 차이가 왕복비용보다 작은 종목은 <b class="warn">이겨도 비용으로 다 나간다</b>. '
  '<b>선정은 「좋은 종목」이 아니라 「지금 매매해서 남는 종목」을 고르는 일이다.</b> '
  '하드 필터: 20일 거래대금 ≥ 100억(미장 $5,000만) · 일중 진폭 ≥ 1.5% · 손익비 ≥ 1.5 · '
  '기대수익 &gt; 왕복비용 · 실적 D-5 제외.</div>')
A(f'<div class="box box-a pb-avoid"><b>▶ 해석</b><br>{R["screen_read"]}</div>')

def enh_card(nm, first=False):
    x = X(nm); cur = cur_of(nm); p = PLAN_E[nm]
    _EM  = D.get("enhance_meta", {}).get("items", {}).get(nm, {})
    _PV  = D.get("enhance_meta", {}).get("port_vol")
    _DU  = x.get("dual") or {}
    _PK  = x.get("pick") or {}
    _ld  = x.get("leader", "")
    _def = {"sector": f'{x.get("group","—")} — 시총 상위 유니버스 자동 선정' + (f' · <b class="vg">{_ld}</b>' if _ld else ''),
            "diversify": (f'보유 포트와 <b>상관 {_EM.get("corr")}</b> · 개별 σ {_EM.get("vol")}% — '
                          f'10% 편입 시 포트 변동성 <b class="vg">{_PV}% → {_EM.get("port_after")}%'
                          f'({_EM.get("delta")}%p)</b>.' if _EM else "분산 효과 실측 실패(§8 참조)."),
            "diversify_short": (f'상관 {_EM.get("corr")} · 10% 편입 시 포트 σ {_EM.get("delta")}%p'
                                if _EM else "분산 후보."),
            "select": (f'<b>★v49 선정 규격</b> — 순위는 19신호 점수가 아니라 <b>선정 점수</b>다. '
                       f'선정 점수 <b class="vg">{(_PK.get("rank_score") if _PK else 0) or 0:.1f}점</b> · '
                       f'적용 모델 <b>{_DU.get("model")}</b> {_DU.get("used")}점({_DU.get("band")}) · '
                       f'종목 성격 <b>{"회귀형" if _DU.get("is_rev") else "추세형"}</b>({_DU.get("char")}) · '
                       f'종목별 검증 <b class="{"vg" if (_PK.get("valid") or {}).get("works") else "vr"}">'
                       f'{"통과" if (_PK.get("valid") or {}).get("works") else "미통과(점수 근거 금지)"}</b> · '
                       f'실행 가능성 <b class="vg">하드 필터 통과</b>. '
                       f'19신호 {x["score"]}점은 <b>참고값</b>이며 순위에 쓰이지 않는다. '
                       f'산출 근거: {_PK.get("why","—")}'),
            "news": f'기준일 종가 {money(cur, x["close"])} ({pct(x["chg"])}) · 20일선 {x["vs_ma20"]:+.1f}% · 60일선 {x["vs_ma60"]:+.1f}%.',
            "read": f'19신호 {x["score"]}점 · RSI {x["rsi"]:.1f} · %b {x["pb"]:.2f} — 실측 기준 판단.',
            "risk": f'ATR <b>{x["atr_pct"]:.2f}%</b> · 주봉RSI {x["rsi_w"]:.1f}.'}
    E = {**_def, **R["enhance"].get(nm, {})}
    ons = [k for k, v in x["on"].items() if v]
    conf = x["nsig"] >= 6; hot = x["rsi_w"] >= 75 or x["close"] > x["bb_up"]
    bd = ('<span class="pillw bad-hot">과열</span>' if hot else '') + ('<span class="pillw bad-hi">고확신</span>' if conf else '')
    img = f'charts/{ALL[nm].replace(".","_")}.png'
    _pg = '' if first else ' pgnew'
    A(f'''<div class="card{_pg}"><div class="chead en"><span class="nm">{nm}</span><span class="tk">{ALL[nm]}</span>
    <span class="rt"><span class="pillw">{money(cur,x["close"])}</span>
    <span class="pillw">{"▲" if x["chg"]>0 else "▼"} {abs(x["chg"]):.2f}%</span>
    <span class="pillw">19신호 {x["score"]:.1f}점 · {x["nsig"]}개</span>{bd}</span><div style="clear:both"></div></div><div class="cbody">
    <div class="blk"><span class="chip c-navy">① 한눈에</span><div class="box-navy" style="margin-top:2px;">
    <b>섹터·모멘텀</b> — {E["sector"]} · 20일선 대비 <b>{x["vs_ma20"]:+.1f}%</b> · 60일선 대비 <b>{x["vs_ma60"]:+.1f}%</b><br>
    <b>관찰 4종 대비 분산 효과</b> — {E["diversify"]}<br>
    <b>교체(선정) 사유</b> — {E["select"]}</div>
    <table style="margin-top:5px;"><thead><tr>
    <th style="width:12%">유니버스</th><th style="width:10%">선정 점수</th><th style="width:13%">성격</th>
    <th style="width:15%">적용 모델</th><th style="width:9%">검증</th><th style="width:7%">R:R</th>
    <th style="width:9%">19신호(참고)</th><th style="width:11%">거래대금</th><th>진입 방식</th></tr></thead><tbody><tr>
    <td class="tc">{("코스피 시총 " + str(len(D["kr"])) + "종") if ALL[nm].endswith(".KS") else ("미장 시총 " + str(len(D["us"])) + "종")}</td>
    <td class="tc"><b style="font-size:12px;">{(_PK.get("rank_score") or 0):.1f}</b></td>
    <td class="tc"><b class="{'vy' if _DU.get("is_rev") else 'vg'}">{"회귀형" if _DU.get("is_rev") else "추세형"}</b> ({_DU.get("char")})</td>
    <td class="tc"><b>{_DU.get("model")}</b> {_DU.get("used")}점 <b class="{'vg' if _DU.get("band")=="강" else 'vy'}">{_DU.get("band")}</b></td>
    <td class="tc"><b class="{"vg" if (_PK.get("valid") or {}).get("works") else "vr"}">{"○" if (_PK.get("valid") or {}).get("works") else "✕"}</b></td>
    <td class="tc">{("%.2f" % (_PK.get("trade") or {}).get("rr")) if (_PK.get("trade") or {}).get("rr") else "—"}</td>
    <td class="tc">{x["score"]}점</td>
    <td class="tc">{(x.get("turnover") or 0)/1e8:,.0f}{"억" if ALL[nm].endswith(".KS") else "억$"}</td>
    <td class="tc" style="font-size:8.4px;">{(_PK.get("behav") or {}).get("style","—")}</td></tr></tbody></table>
    <div class="cap"><b>진입 게이트 4종</b> — <b>[검증]</b> ①역방향 경고 배제(회귀형인데 추세점수 40↑ = 실측 −0.66~−1.33%)
    ②기대 초과수익 ≥ +0.50%(추세형 '약' +0.45 · 회귀형 '약' −0.52 배제) / <b>[미검증·위생]</b> ③유동성(국장 100억·미장 1억달러)
    ④장기 추세 이탈 배제(종가&lt;120일선 <b>이고</b> 120일선 하락). 넷을 통과한 종목만 후보이며, 순위는 <b>기대 초과수익</b> 순이다.
    <b class="warn">19신호 점수는 순위에 쓰이지 않는다</b> — 19신호는 전부 추세추종 계열이라 회귀형 종목에서는 점수가 높을수록 성적이 나빴다(v48 실측).
    편입 크기는 위 「분산 효과」의 상관·σ 변화를 보고 정한다.</div></div>
    <table class="chartwrap"><tr><td><span class="chip c-purple">② 차트</span>
    <div class="ct">📈 {nm} 일봉 — 6개월 + 구름 26봉 미래투영 · 이평 3중 · 볼린저 · 전환/기준선 · <b>MACD(12·26·9)</b></div>
    <img src="{b64(img)}"><div class="cap">공통 규격 전부 적용(6개월+26봉 투영·이평 3중·볼린저·일목 3요소·<b>MACD(12·26·9) 서브차트</b>). ★v45 <b>레벨 보드</b> 신설 — 차트 오른쪽에 <b>이평(10·20·60)·볼린저(상/중/하)·일목(전환·기준·구름)·매물대(POC·VAH·VAL)·미충족 갭·직전 스윙 고점/눌림목</b>을 한데 모아 <b>저항 R1~R5 / 지지 S1~S5</b>로 정렬해 표기한다(현재가 ±25% 이내만). 가격 패널에는 <b>가장 가까운 R1·S1과 매물대 POC 3개 선만</b> 그려 캔들·이평·구름을 가리지 않는다. 우측 <b>매물대 패널</b>은 표시구간 거래량을 가격대별로 쌓은 것이며, 금색 막대가 <b>POC(거래가 가장 많이 쌓인 가격대)</b>다.</div></td></tr></table>
    <div class="blk keep"><span class="chip c-blue">③ 실행 디테일 표</span><table><thead><tr>
    <th style="width:18%">시나리오</th><th>진입가(현재가 대비)</th><th>손절(넓은 쪽)</th><th>목표</th><th style="width:10%">R:R</th></tr></thead><tbody>''')
    for sc, q in p.items():
        rc = "vg" if q["rr"]>=2 else ("vy" if q["rr"]>=1 else "vr")
        A(f'''<tr><td class="tc"><b>{sc}</b></td>
        <td class="tc"><b>{money(cur,q["entry"])}</b> <span style="font-size:8.8px;">({pct(q["e_pct"],1)})</span></td>
        <td class="tc"><b>{money(cur,q["stop"])}</b> <span style="font-size:8.8px;">({pct(q["s_pct"],1)})</span><br>
        <span style="font-size:8.4px;color:#6B7680;">고정 {money(cur,q["s_fix"])} / 변동성 {money(cur,q["s_vol"])}</span></td>
        <td class="tc">{money(cur,q["t"])}</td><td class="tc"><b class="{rc}">{q["rr"]:.2f}</b></td></tr>''')
    A(f'''</tbody></table></div>
    <div class="blk"><span class="chip c-teal">④ 맥락</span><div class="box box-g">
    <b>뉴스</b> — {E["news"]}<br><b>해석</b> — {E["read"]}</div></div>''')
    KEY = ("전고점돌파","구름대돌파","삼역호전","골든크로스","MACD호전","밴드타기","RSI반등")
    offs = [k for k, v in x["on"].items() if not v and k in KEY]
    _ens = next_signals(x["on"], 2)
    _ens_txt = " · ".join(f'<b>{k}</b>(실측 가중치 {WEIGHTS[k]:.1f}점)' for k in _ens) or "없음"
    A(f'<div class="blk"><span class="chip c-amber">⑤ 통과 신호 (켜짐 + 꺼짐 + 왜)</span><div class="box box-a" style="font-size:9.6px;">'
      + (f'{dual_html(x)}<br>' if x.get("dual") else '')
      + '<b style="color:#1E8449;">▶ 켜짐</b> — ' + (" · ".join(f'{sig("g")}<b>{k}({WEIGHTS[k]:.1f})</b>{" <span class=warn>(참고·점수 미반영)</span>" if k in ZERO_SIGS else ""}' for k in ons) or "없음") +
      '<br><b style="color:#C0392B;">▶ 꺼짐</b> — ' + " · ".join(
        f'{sig("y") if k in ("MACD호전","구름대돌파","전환기준선호전") else sig("x")}<b>{k}({WEIGHTS[k]:.1f})</b>'
        f'{" <span class=warn>(참고·점수 미반영)</span>" if k in ZERO_SIGS else ""} '
        f'<span style="font-size:8.8px;color:#5A6570;">({x["det"][k]})</span>' for k in offs) +
      f'<br><span style="font-size:9px;">→ <b>가장 먼저 켜질 신호(실측 가중치 순)</b> — {_ens_txt}.</span></div></div>')
    ax = axis6(x); q1 = list(p.values())[0]
    A('<div class="blk keep"><span class="chip c-purple">⑥ 6축 색판정 + 결론</span><table style="border-spacing:0;"><tr>')
    for an, av, ac, ad in ax:
        A(f'<td class="ax"><div class="an">{an}</div><div class="av">{sig(ac)} <span class="v{ac}">{av}</span></div><div class="ad">{ad}</div></td>')
    A(f'''</tr></table><div class="concl">▶ <b>결론</b> — <b>진입 {money(cur,q1["entry"])}</b> · <b>손절 {money(cur,q1["stop"])}</b> ·
    <b>목표 {money(cur,q1["t"])}</b> · <b>R:R {q1["rr"]:.2f}</b>. <b>분산 1줄</b> —
    <span style="color:#FFE14D;">{E["diversify_short"]}</span></div></div>
    <div class="blk"><span class="chip c-gray">⑦ 모니터링 · ⑧ 리스크</span><div class="box">
    <b>모니터링</b> — 진입가 {money(cur,q1["entry"])} 도달 여부 · 20일선({money(cur,x["ma20"])}) 유지 여부 ·
    MACD 히스토그램 {x["macd_hist"]:+,.1f}(직전 {x["macd_hist_prev"]:+,.1f} → {"확대" if x["macd_hist"]>x["macd_hist_prev"] else "축소"}) 추이.<br><b>리스크</b> — {E["risk"]}</div></div>
    </div></div>''')

_RULE49 = ('★ <b>v49 선정 규격</b> — ① 유니버스 <b>코스피 시총 상위 {a}종 · 미장 상위 {b}종</b> '
           '② 관찰 4종과 같은 하위섹터 제외 ③ <b>실행 가능성 하드 필터</b>(유동성·진폭·손익비·왕복비용·이벤트 창) 통과 '
           '④ 순위 = <b>선정 점수</b>(성격에 맞는 모델 ×0.6 + R:R×5 + 가점 − 검증 미통과 15 − 역방향 경고 15). '
           '<b class="warn">19신호 점수 순이 아니다</b> — 19신호는 전부 추세추종 계열이라 회귀형 종목에서 높을수록 성적이 나빴다(표본외 −1.33%). '
           '하드 필터 통과 국장 <b>{c}종</b> / 미장 <b>{d}종</b>.'
           ).format(a=len(D["kr"]), b=len(D["us"]),
                    c=len(D.get("pick", {}).get("kr", {}).get("picks", [])),
                    d=len(D.get("pick", {}).get("us", {}).get("picks", [])))
A('<div class="corner pgnew">⑥ 강화 카드 — 국내 2종 (기대 초과수익 기준 선정)</div>')
A(f'<div class="box box-b" style="font-size:9.6px;">{_RULE49}</div>')
A(f'<div class="box box-b" style="font-size:9.6px;">★ <b>선정 규칙</b> — 관찰 4종과 같은 하위섹터(제외: {", ".join(sorted(C.EXCLUDE_KR))})를 '
  f'스캔에서 뺀 뒤, 19신호 점수 상위 → 동점 시 섹터 RS 우선. <b>특정 종목 고정 없음 — 매 회차 재계산.</b> '
  f'이번 회차 선정: <b>{" · ".join(D["enhance_kr"])}</b></div>')
for _i, n in enumerate(D["enhance_kr"]): enh_card(n, first=(_i == 0))
A('<div class="corner pgnew">⑥-2 강화 카드 — 미국 2종 (기대 초과수익 기준 선정)</div>')
A(f'<div class="box box-b" style="font-size:9.6px;">{_RULE49}</div>')
A(f'<div class="box box-b" style="font-size:9.6px;">★ 제외: {", ".join(sorted(C.EXCLUDE_US))}. '
  f'잔여 후보 중 점수 상위 3종 → <b>{" · ".join(D["enhance_us"])}</b></div>')
for _i, n in enumerate(D["enhance_us"]): enh_card(n, first=(_i == 0))

_WR = D.get("watchlist_rev", {})
if True:   # ★코너는 항상 노출(빈 회차엔 '해당 종목 없음' 명시 — 게이트 G15/코너 일관성)
    A('<div class="corner pgnew">⑥-3 회귀형 되돌림 후보 — 19신호는 낮지만 되돌림 점수가 높은 자리</div>')
    A('<table><thead><tr><th style="width:6%">시장</th><th style="width:15%">종목</th>'
      '<th style="width:9%">19신호</th><th style="width:11%">되돌림 점수</th>'
      '<th style="width:11%">추세 점수</th><th style="width:10%">기대수익</th>'
      '<th style="width:10%">성격 상관</th><th>점등된 되돌림 신호 · 실측 근거</th></tr></thead><tbody>')
    if not (_WR.get("kr") or _WR.get("us")):
        A('<tr><td colspan="8" class="tc">이번 회차 해당 종목 없음 — <b class="warn">레거시 유니버스 폴백</b>(§8, FinanceDataReader 미설치). '
          '<b>되돌림 3신호(RSI과매도 47.8 · 20일선하방이격 43.7 · RSI과매도탈출 8.5)</b>를 충족하며 '
          '기대 초과수익 하한(+0.50%)을 넘는 회귀형 종목이 이 13+13 레거시 표본엔 없다. '
          '유니버스가 시총 상위 150종으로 정상 복구되는 회차에 다시 채워진다.</td></tr>')
    for _mk, _lab in (("kr", "국장"), ("us", "미장")):
        for _r in _WR.get(_mk, []):
            _bc = "vg" if _r["band"] == "강" else "vy"
            A(f'<tr><td class="tc">{_lab}</td><td class="tc"><b>{_r["name"]}</b></td>'
              f'<td class="tc"><span style="color:#8A94A0;">{_r["score19"]}점</span></td>'
              f'<td class="tc"><b class="{_bc}">{_r["rev_score"]}점 ({_r["band"]})</b></td>'
              f'<td class="tc">{_r["trend_score"]}점</td>'
              f'<td class="tc"><b class="vg">{_r["edge"]:+.2f}%</b></td>'
              f'<td class="tc">{_r["char"]:+.3f}</td>'
              f'<td class="tl" style="font-size:8.6px;">{", ".join(_r["rev_on"]) or "—"} · {_r["band_note"]}'
              + (f' <b class="warn">· 게이트: {" / ".join(_r["gate"])}</b>' if _r["gate"] else '') + '</td></tr>')
    A('</tbody></table>')
    A('<div class="cap"><b>읽는 법</b> — 이 표의 종목은 <b>19신호 점수가 낮다</b>. 그런데 기대수익은 높다. '
      '모순이 아니라 <b>19신호가 측정하지 못하는 종목</b>이라는 뜻이다 — 19신호는 전고점·구름·돌파 등 전부 추세추종 계열인데, '
      '이 종목들은 <b>과거 20일 수익률과 이후 20일 초과수익의 상관이 음수(회귀형)</b>라 오르면 되돌리고 빠지면 돌아온다. '
      '회귀형에 추세 점수를 매기면 <b class="warn">높을수록 성적이 나쁘다(추세점수 70↑ = 표본외 −1.33%)</b>. '
      '그래서 이들은 <b>되돌림 3신호(RSI과매도 47.8 · 20일선하방이격 43.7 · RSI과매도탈출 8.5)</b>로 다시 채점한다. '
      '<b class="warn">게이트 칸에 사유가 적혀 있으면 강화 카드에는 오르지 못한 종목</b>이며, 사유가 없으면 강화 후보와 같은 자격이다.</div>')

A(f'<table><caption class="corner-cap">(A) 수급 레이더 — 실측 순매매 ({M["asof"]} 확정)</caption><thead><tr>'
  '<th style="width:11%">주체</th><th style="width:14%">코스피 순매매</th><th style="width:14%">코스닥 순매매</th>'
  '<th style="width:13%">출처</th><th>해석 1줄</th></tr></thead><tbody>')
for s in R["supply"]["rows"]:
    A(f'<tr><td class="tl"><b>{s["who"]}</b></td><td class="tr">{s["kospi"]}</td><td class="tr">{s["kosdaq"]}</td>'
      f'<td class="tc" style="font-size:9px;">{s["src"]}</td><td class="tl">{s["read"]}</td></tr>')
A(f'</tbody></table><div class="box box-b"><b>➡ 그래서</b> — {R["supply"]["sogo"]}</div>')

A(f'<table><caption class="corner-cap">(B) 경제 캘린더 — {R["calendar_range"]}</caption><thead><tr>'
  '<th style="width:11%">확정 일시(한국시간)</th><th style="width:22%">이벤트</th><th style="width:8%">성격</th>'
  '<th style="width:34%">모드1 (중기 스윙) 대응</th><th>모드2 (단타) 대응</th></tr></thead><tbody>')
for e in R["calendar"]:
    A(f'<tr><td class="tc">{e["when"]}</td><td class="tl">{e["what"]}</td><td class="tc">{e["type"]}</td>'
      f'<td class="tl">{e["m1"]}</td><td class="tl">{e["m2"]}</td></tr>')
A(f'</tbody></table><div class="cap stick">※ 확정 박제 — {R["calendar_pin"]}</div>')

RK = R["risk"]
A(f'''<div class="corner pgnew">리스크 대시보드</div><table class="g2 pb-avoid"><tr>
<td style="border-left-color:#1E8449;background:#F1FAF3;"><div class="t">📊 VIX 게이지</div>
<b style="font-size:15px;" class="{"vg" if mac["VIX"]["close"]<20 else "vr"}">{mac["VIX"]["close"]:.2f}</b> ({pct(mac["VIX"]["chg_pct"])}) ·
VIX3M {mac["VIX3M"]["close"]:.2f} · 기간구조 <b class="{"vg" if vixr<0.9 else "vr"}">{vixr:.2f}</b><br>{RK["vix"]}</td>
<td style="border-left-color:#C0392B;background:#FDF2F1;"><div class="t">🛡 리스크 노출 (★v41: 2%룰 폐기 · 실측만 표기)</div>
<b>손절선까지 밀렸을 때의 손실 금액</b>을 종목별로 실측한다. <b class="warn">한도·초과 판정은 하지 않는다</b>(사용자 프로필 = 공격형).<br>''' +
"".join(f'· <b class="warn">[보유] {n}</b> 손절폭 {abs(stop_of(n)["s_pct"]):.1f}% → '
        f'<b>리스크 노출 {m_neg(cur_of(n),stop_of(n)["risk"])}</b> '
        f'{("(통합 시드의 %.2f%%)" % (stop_of(n)["risk"]/C.ACCOUNT_TOTAL*100)) if cur_of(n)=="₩" else ("(원화환산 통합 시드의 %.2f%%)" % (stop_of(n)["risk"]*FX/C.ACCOUNT_TOTAL*100))}<br>'
        for n in HELD) +
"".join(f'· [관찰] {n} 손절폭 {abs(PLAN[n]["눌림 대기(권장)"]["s_pct"]):.1f}% — 투입 금액은 본인 판단<br>'
        for n in WATCHONLY) +
f'''<b class="warn">{RK["sizing"]}</b><br><b>6%룰(유지)</b> — 월 누적 손실 6% 도달 시 그 달 매매 중단. <b>2%룰은 이번 버전에서 폐기</b>됐다.</td>
</tr><tr>
<td style="border-left-color:#245DA3;background:#F0F5FF;"><div class="t">⚙ 모드1 / 모드2 규칙</div>{RK["modes"]}</td>
<td style="border-left-color:#E08A00;background:#FFF9EE;"><div class="t">⚠ 이번 회차 리스크 이벤트</div>{RK["events"]}</td>
</tr></table>''')

A('''<div class="trapblk pb-avoid">
<div style="font-size:14px;font-weight:bold;color:#C0392B;margin-bottom:6px;">🚨 행동 함정 체크 — 독립 경고 블록 (보유 기준 6종)</div>
<table class="traptbl">''')
T = R["traps"]
for i in range(0, 6, 2):
    A('<tr>')
    for t in T[i:i+2]:
        badge = ' <span class="todaybadge">오늘 특히 위험</span>' if t.get("today") else ''
        A(f'<td><span class="nobadge">❌ 금지</span> <b>{t["name"]}</b>{badge}<br><b>당일 근거</b> — {t["why"]}</td>')
    A('</tr>')
A('''</table><div style="margin-top:5px;font-size:9.4px;color:#7B2418;"><b>※ 보유 복원(2026-07-13)</b> —
함정 세트가 <b>물타기 남발 · 손절 미루기 · 공포 전량매도</b> 중심으로 전환됐다(v38 · 레지스트리 규약).</div></div>''')

A(f'<div class="corner pgnew">성과 추적</div><div class="box box-b pb-avoid"><b>▶ 직전 회차 시나리오 적중 검증</b> — {R["perf_prev"]}</div>')
A('<div class="sub2">★ 청산 기준선 대비 관찰 4종 추적</div>')
A('<table class="pb-avoid"><thead><tr><th>종목</th><th>청산 기준선</th><th>현재가</th><th>기준선 대비</th>'
  '<th>청산 직전 평단</th><th>진입 트리거</th><th style="width:34%">검증 (자책 아님 — 트리거 검증 목적)</th></tr></thead><tbody>')
for n in WN:
    x = X(n); cur = cur_of(n); B = R["baseline"][n]
    gap = (x["close"]/B["base"]-1)*100
    A(f'''<tr><td class="tl"><b>{n}</b></td><td class="tr">{money(cur,B["base"])}</td>
    <td class="tr"><b>{money(cur,x["close"])}</b></td><td class="tc">{pct(gap,2)}</td>
    <td class="tr">{money(cur,B["avg"])}<br><span style="font-size:8.6px;">{B["qty"]}주</span></td>
    <td class="tc">{B["trigger"]}</td><td class="tl">{B["verify"]}</td></tr>''')
A(f'</tbody></table><div class="box box-a">{R["perf_note"]}</div>')

P = D.get("perf", {})
if P.get("ok"):
    def dot_ratio(v):
        return "g" if v < C.VOL_RATIO_Y else ("y" if v < C.VOL_RATIO_R else "r")
    def dot_sh(dp):
        return "g" if dp > 0 else ("y" if dp > -0.3 else "r")
    def f2(v, d=2): return f"{v:,.{d}f}"
    W120 = P["windows"][str(C.PERF_MCTR_WIN)]

    A('<div class="corner pgnew">⑮-B 위험조정 성과 — 내 포트폴리오 vs 시장(코스피) · '
      f'무위험수익률 {P["rf"]*100:.2f}%</div>')
    A('<div class="box box-a pb-avoid"><b>▶ 이 코너가 답하는 질문</b> — '
      '<b class="vg">"코스피를 그냥 산 사람보다 나는 얼마나 더 흔들리는 배를 탔고, 그 대가를 받고 있는가?"</b> '
      '수익률만 보면 답이 안 나온다. <b>같은 수익이라도 두 배로 흔들려서 얻었다면 절반짜리 성적</b>이기 때문이다.<br>'
      '<b>용어 3개만 기억하면 된다</b> — '
      '<b>변동성</b>: 1년 동안 값이 위아래로 얼마나 출렁이는지(%). '
      '<b>베타</b>: 코스피가 1% 움직일 때 내 계좌가 몇 % 움직이는지(1.0=시장과 같음). '
      '<b>샤프지수</b>: 감수한 흔들림 1단위당 벌어들인 초과수익(높을수록 잘 운용). '
      f'<span class="hl">무위험수익률은 {P["rf_src"]}를 썼다.</span></div>')

    A('<table class="pb-avoid"><caption class="corner-cap">① 기간별 위험·수익 비교 (전부 실측 계산)</caption>'
      '<thead><tr><th>지표</th><th>최근 60일</th><th>최근 120일</th><th>최근 252일(1년)</th>'
      '<th style="width:36%">읽는 법</th></tr></thead><tbody>')
    rows = [
      ("연환산 수익률 — 내 포트", lambda w: pct(w["ret_p"], 1), None,
       "현 보유 구성을 그 기간 내내 들고 있었다면의 성과."),
      ("연환산 수익률 — 코스피", lambda w: pct(w["ret_m"], 1), None,
       "같은 기간 시장에 그냥 참여했을 때."),
      ("변동성 — 내 포트", lambda w: f'<b>{f2(w["vol_p"],1)}%</b>', None,
       "숫자가 클수록 계좌가 심하게 출렁인다."),
      ("변동성 — 코스피", lambda w: f'{f2(w["vol_m"],1)}%', None,
       "시장의 기본 출렁임. 이게 비교 기준선이다."),
      ("<b>초과 위험 배수</b>", lambda w: f'{sig(dot_ratio(w["ratio"]))}<b>{f2(w["ratio"])}배</b>', None,
       "<b class='warn'>1.0 초과 = 시장보다 더 위험한 배를 탔다.</b> 1.3 넘으면 빨강."),
      ("<b>베타(β)</b>", lambda w: f'{sig(dot_ratio(w["beta"]))}<b>{f2(w["beta"])}</b>', None,
       "코스피 −1% 날 내 계좌는 평균 이만큼 더 빠진다."),
      ("<b>샤프지수 — 내 포트</b>", lambda w: f'{sig(dot_sh(w["sharpe_p"]-w["sharpe_m"]))}<b>{f2(w["sharpe_p"])}</b>', None,
       "<b>위험 1단위당 보상.</b> 아래 시장 샤프보다 높아야 '잘 운용'."),
      ("샤프지수 — 코스피", lambda w: f2(w["sharpe_m"]), None, "시장의 위험 대비 보상."),
      ("소르티노 — 내 포트", lambda w: f2(w["sortino_p"]), None,
       "샤프의 사촌. <b>손실 쪽 출렁임만</b>으로 계산(더 현실적)."),
      ("최대낙폭(MDD) — 내 포트", lambda w: f'<b class="dn">{f2(w["mdd_p"],1)}%</b>', None,
       "고점에서 최악의 순간까지 얼마나 깎였나."),
      ("최대낙폭(MDD) — 코스피", lambda w: f'<span class="dn">{f2(w["mdd_m"],1)}%</span>', None,
       "시장의 최악 구간. 내 것이 더 깊으면 초과 위험 실현."),
      ("코스피와의 상관계수", lambda w: f'{sig("r" if w["corr"]>C.CORR_R else "y")}<b>{f2(w["corr"])}</b>', None,
       "<b class='warn'>1에 가까울수록 분산이 안 된 상태</b> — 시장이 빠지면 같이 빠진다."),
      ("추적오차 / 젠센 알파", lambda w: f'{f2(w["te"],1)}% / {pct(w["alpha"],1)}', None,
       "알파 = 베타로 설명되지 않는 순수 실력분."),
    ]
    for lab, fn, _, expl in rows:
        A(f'<tr><td class="tl">{lab}</td>'
          + "".join(f'<td class="tc">{fn(P["windows"][str(w)])}</td>' for w in C.PERF_WINDOWS)
          + f'<td class="tl" style="font-size:9.2px">{expl}</td></tr>')
    A('</tbody></table>')

    r120 = W120["ratio"]; b120 = W120["beta"]
    dsh = W120["sharpe_p"] - W120["sharpe_m"]
    A('<div class="box box-navy pb-avoid"><b>▶ 한 문장 판정</b> — '
      f'내 계좌는 코스피보다 <b>{f2(r120)}배</b> 더 출렁이고(베타 {f2(b120)}), '
      f'그 대가로 120일 샤프 <b>{f2(W120["sharpe_p"])}</b> vs 시장 <b>{f2(W120["sharpe_m"])}</b>를 기록했다. '
      + ('<span class="hl">위험을 더 진 만큼 보상도 더 받았다 — 운용 자체는 시장을 이기고 있다.</span>'
         if dsh > 0 else
         '<span class="hl">더 위험한데 보상은 시장보다 못하다 — 위험 대비 성적이 열위다.</span>')
      + f' 다만 <b class="warn">최근 60일 샤프는 {f2(P["windows"]["60"]["sharpe_p"])}</b>로, '
      '<b class="warn">하락 국면에서는 초과 위험이 그대로 초과 손실이 된다</b>는 점이 실측으로 확인됐다.</div>')

    A(f'<table class="chartwrap pb-avoid"><caption class="corner-cap">📈 내 포트폴리오 vs 코스피 — 1년 누적 수익</caption>'
      f'<tr><td><img src="{b64("charts/perf_curve.png")}" style="width:100%"></td></tr></table>')
    A(f'<table class="chartwrap pb-avoid"><caption class="corner-cap">📈 60일 롤링 변동성 — 붉은 면적이 초과 위험</caption>'
      f'<tr><td><img src="{b64("charts/perf_vol.png")}" style="width:100%"></td></tr></table>')

    A('<table class="pb-avoid"><caption class="corner-cap">② 종목별 리스크 기여도 — '
      '<b>비중보다 위험 기여가 크면 그 종목이 위험의 주범</b></caption>'
      '<thead><tr><th>종목</th><th>평가 비중</th><th>리스크 기여도</th><th>기여/비중</th>'
      '<th>개별 변동성</th><th>개별 베타</th><th>이 종목을 빼면 포트 변동성</th><th style="width:24%">해석</th></tr></thead><tbody>')
    for n, Lg in sorted(P["legs"].items(), key=lambda kv: -kv[1]["mctr"]):
        k = Lg["mctr"]/Lg["w"] if Lg["w"] else 0
        kc = "r" if k > 1.2 else ("y" if k > 1.0 else "g")
        dv = Lg["whatif"] - P["pvol"]
        if k > 1.2:
            itp = "<b class='warn'>위험의 주범</b> — 비중보다 위험을 더 만든다. 축소 1순위."
        elif Lg["mctr"] < 3 and Lg["beta"] < 0.5:
            itp = "<b class='vg'>분산 기여</b> — 시장과 따로 움직여 전체 위험을 낮춘다."
        else:
            itp = "비중만큼의 위험. 중립."
        A(f'<tr><td class="tl"><b>{n}</b></td><td class="tc">{f2(Lg["w"],1)}%</td>'
          f'<td class="tc"><b>{f2(Lg["mctr"],1)}%</b></td>'
          f'<td class="tc">{sig(kc)}<b>{f2(k)}배</b></td>'
          f'<td class="tc">{f2(Lg["vol"],1)}%</td><td class="tc">{f2(Lg["beta"])}</td>'
          f'<td class="tc">{f2(Lg["whatif"],1)}% ({pct(dv,1)}p)</td>'
          f'<td class="tl" style="font-size:9.2px">{itp}</td></tr>')
    A(f'</tbody></table><div class="box box-g pb-avoid"><b>▶ 포트 전체 변동성 {f2(P["pvol"],1)}%</b> '
      f'(120일 기준) · 총 평가금액 {krw(P["value"])}. '
      '<b class="warn">비중 순위와 위험 순위가 다르다는 점이 이 표의 핵심</b>이다 — '
      '줄여야 할 것은 "많이 산 것"이 아니라 "위험을 많이 만드는 것"이다.</div>')

    A(f'<div class="box box-b pb-avoid"><b>▶ 실제 진입({P["since"]}) 이후 {P["since_days"]}거래일 실현 성과</b> — '
      f'내 포트 <b>{pct(P["since_p"],2)}</b> vs 코스피 <b>{pct(P["since_m"],2)}</b> '
      f'→ <b class="warn">시장 대비 {f2(abs(P["since_p"]-P["since_m"]),2)}%p '
      f'{"초과 손실" if P["since_p"] < P["since_m"] else "초과 수익"}</b>. '
      f'베타 {f2(b120)}를 감안하면 시장 {pct(P["since_m"],2)} 구간의 이론 손실은 '
      f'{pct(P["since_m"]*b120,2)} — <b>실제는 그보다 더 나빴다면 종목 선택이, 덜 나빴다면 방어가 기여한 것</b>이다.</div>')

    SC = P["scenario"]; sc = SC["scen"]
    A('<table class="pb-avoid"><caption class="corner-cap">③ ★위험 대비 수익을 개선하는 3가지 방법 — '
      '전부 실제 계산 결과다(느낌이 아니다)</caption>'
      '<thead><tr><th style="width:26%">방법</th><th>실행 시 포트 변동성</th><th>변화</th><th>베타</th>'
      '<th>시장 대비 배수</th><th style="width:38%">왜 / 언제</th></tr></thead><tbody>')
    adv = {
      "half_cash": ("<b class='warn'>가장 효과 큼.</b> 리스크 기여 1위 종목만 손대면 전체 위험이 급감한다. "
                    "<span class='hl'>손절이 아니라 '비중 관리'다 — 종목을 부정하는 게 아니라 크기를 줄이는 것.</span>"),
      "half_shift": ("축소분을 <b>시장과 따로 움직이는 자산</b>으로 옮기는 방식. 현금화보다 수익 기회를 덜 포기한다. "
                     "<b class='warn'>단 옮길 대상의 상관계수가 낮아야만 효과가 있다.</b>"),
      "cash20": ("종목 판단을 하지 않고 <b>전체를 균등 축소</b>하는 가장 단순한 방법. "
                 "<b class='warn'>효과는 가장 작다</b> — 쏠린 구조는 그대로 두기 때문."),
    }
    for k in ["half_cash", "half_shift", "cash20"]:
        v = sc[k]
        A(f'<tr><td class="tl"><b>{v["label"]}</b></td>'
          f'<td class="tc"><b>{f2(v["vol"],1)}%</b></td>'
          f'<td class="tc"><b class="up">{f2(v["d_vol"],1)}%p</b></td>'
          f'<td class="tc">{f2(v["beta"])}</td>'
          f'<td class="tc">{sig(dot_ratio(v["ratio"]))}<b>{f2(v["ratio"])}배</b></td>'
          f'<td class="tl" style="font-size:9.2px">{adv[k]}</td></tr>')
    A('</tbody></table>')
    A(f'<div class="box box-navy pb-avoid"><b>▶ 그래서 지금 무엇을 하라</b> — '
      + R.get("perf_advice", "") + '</div>')

A('<table><caption class="corner-cap">(C) 핵심 4종 트래커 (보유 2 · 관찰 2)</caption><thead><tr><th>종목</th><th>구분</th>'
  '<th>평단 / 수량</th><th>현재가</th><th>평가손익 / 기준선 대비</th><th>진입·추가 후보가</th><th>손절선</th>'
  '<th>목표(컨센)</th><th>20일선까지</th></tr></thead><tbody>')
for n in WN:
    x = X(n); cur = cur_of(n); q = PLAN[n]["눌림 대기(권장)"]
    if held(n):
        P, S = pnl(n), stop_of(n)
        c1 = '<b class="warn">보유</b>'
        c2 = f'{money(cur,P["avg"])}<br><span style="font-size:8.4px;">{P["qty"]}주</span>'
        c3 = f'{signed(P["amt"])}<br><span style="font-size:8.4px;">{P["rate"]:+.2f}%</span>'
        c5 = f'<b class="warn">{money(cur,S["stop"])}</b>'
    else:
        c1, c2 = '관찰', '—'
        c3 = f'<span style="font-size:8.6px;">기준선 대비 {pct((x["close"]/R["baseline"][n]["base"]-1)*100,2)}</span>'
        c5 = f'<b class="warn">{money(cur,q["stop"])}</b>'
    A(f'<tr><td class="tl"><b>{n}</b></td><td class="tc">{c1}</td><td class="tr">{c2}</td>'
      f'<td class="tr"><b>{money(cur,x["close"])}</b></td><td class="tr">{c3}</td>'
      f'<td class="tr">{money(cur,q["entry"])}</td><td class="tr">{c5}</td>'
      f'<td class="tr">{money(cur,R["watch"][n]["t_cons"])}</td>'
      f'<td class="tc"><b class="{"vg" if x["vs_ma20"]>0 else "vr"}">{x["vs_ma20"]:+.1f}%</b></td></tr>')
A(f'''</tbody></table><div class="box box-b">
<b>· 적용 환율</b> — <b>원/달러 {num(FX,2)}원</b> (yfinance KRW=X, {M["asof"]} 종가). 미장 종목 원화 환산에 사용.<br>
<b>· 임박 이벤트 3건</b> — {R["tracker_events"]}<br>
<b>· 현금 / 재진입 메모</b> — {R["tracker_memo"]}</div>''')

A('<table><caption class="corner-cap">(D) 맨 끝 메모 · §8 실패·미확인 로그</caption><thead><tr>'
  '<th style="width:18%">항목</th><th style="width:11%">구분</th><th>시도 소스 · 반환 · 대체 (§8 규약)</th></tr></thead><tbody>')
for g in D["log8"] + R["log8"]:
    KC = {"실패":"vr","추정":"vy","지연값":"vy","폴백(Tier2)":"vy","미확인":"vgr","해결":"vg","구값":"vy","규격 조정":"vy","불가":"vgr","1일값 대체":"vy"}
    A(f'<tr><td class="tl"><b>{g["item"]}</b></td><td class="tc"><b class="{KC.get(g["kind"],"vy")}">{g["kind"]}</b></td>'
      f'<td class="tl">{g["detail"]}</td></tr>')
A(f'</tbody></table><div class="box box-r"><b>▶ 축소 코너: {R["shrink"]}</b></div>')

A(f'''<div class="foot"><b>본 브리핑은 실데이터 기반 정보 제공 자료이며 투자 자문이 아님. 모든 매매 판단·책임은 사용자 본인에게 있음.</b><br>
데이터 출처: yfinance(시세·기술지표·19신호·섹터RS) · FRED(하이일드 BAMLH0A0HYM2 · 금리차 T10Y2Y) ·
웹검색(수급·뉴스·목표가·캘린더·반도체 사이클). 기준일 {M["asof_label"]}. 발행 {M["pub"]}.</div>''')

open("briefing.html", "w").write("\n".join(H))
print(f"→ briefing.html 생성 ({len(''.join(H))//1024}KB) · 카드 {len(C.WATCH)}+{len(ENH)}종 · 차트 {1+len(C.WATCH)+len(ENH)}장")

import json as _json
_state = {
  "asof": D["asof"], "pub": M["pub"],
  "kospi_close": D["kospi"]["close"],
  "levels": {"ma20": D["kospi"]["ma20"], "ma60": D["kospi"]["ma60"],
             "cloud_top": D["kospi"]["ctop"], "cloud_bot": D["kospi"]["cbot"],
             "bb_low": D["kospi"]["bb_low"], "lo22": D["kospi"]["lo22"]},
  "night_futures": D.get("night_futures"),
  "sector_pick": sorted(D["sector"]["data"].items(), key=lambda x: -x[1]["rs_w"])[:3],
  "screen_top": {"kr": sorted([(v["score"], k) for k, v in D["kr"].items()], reverse=True)[:5],
                 "us": sorted([(v["score"], k) for k, v in D["us"].items()], reverse=True)[:5]},
  "enhance": {"kr": D["enhance_kr"], "us": D["enhance_us"]},
  "watch": {n: {"close": {**kr, **us}[n]["close"], "ma20": {**kr, **us}[n]["ma20"],
                "score": {**kr, **us}[n]["score"], "badge": R["watch"][n]["badge"],
                "trigger": R["watch"][n].get("trigger", "")}
            for n, _, _, _ in C.WATCH if n in {**kr, **us}},
}
_json.dump(_state, open(f"state_{D['asof']}.json", "w"), ensure_ascii=False, indent=1)
print(f"→ state_{D['asof']}.json 기록 (다음 회차 성과 자동 검증용)")
