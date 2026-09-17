#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prefill.py — «골격은 재사용, 값·판단만 갈아끼운다» (2026-09-17 신설)

용도: 매 회차 build.py «앞»에서 1회 실행.
  research.skeleton.json (v59 코드와 1:1 대응하는 고정 골격) + data.json + config
  → research.json 을 만든다.
  · [AUTO] 블록: data.json/config에서 계산 가능한 것 = prefill이 전부 채운다(손 안 댐).
  · [ME]   블록: 트레이딩 분석·멘트·판단 = 빈칸("")으로 남긴다 → 사람이 그 칸만 채운다.

실행:  python3 asof.py 마감 → D 확정 → fetch_all → mkchart →
       python3 prefill.py 마감   (또는 장전)   → research.json 자동블록 채움
       → [ME] 칸 분석 작성 → build → render → gate
"""
import json, sys, datetime as dt
import config

MODE = sys.argv[1] if len(sys.argv) > 1 else "마감"
D = json.load(open("data.json", encoding="utf-8"))
ASOF = D["asof"]
K = D["kospi"]; KR = D["kr"]; US = D["us"]
MAC = D["macro"]; SEC = D.get("sector", {}); PERF = D.get("perf", {})
HEDGE = D.get("hedge", {}); ADR = D.get("adr", {}); NFP = D.get("night_futures_proxy", {})
POS = config.POSITIONS

def nxt_trading_day(iso):
    d = dt.date.fromisoformat(iso)
    FIX = {(1,1),(3,1),(5,5),(6,6),(8,15),(10,3),(10,9),(12,25)}
    while True:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and (d.month, d.day) not in FIX:
            return d.isoformat()

def f(n, dec=0):
    try: return f"{n:,.{dec}f}"
    except Exception: return str(n)

def dist(cur, ref):
    return (cur/ref - 1) * 100

def pos_side(cur, ref):
    return "위" if ref > cur else "아래"

def hold_ccy(name):
    return POS.get(name, {}).get("ccy", "₩")

sk = json.load(open("research.skeleton.json", encoding="utf-8"))

# ══════════════ [AUTO] meta ══════════════
pub = nxt_trading_day(ASOF)  # 발행일 = 다음 거래일 (신선도 게이트: pub > asof)
d0 = dt.date.fromisoformat(ASOF)
wd = "월화수목금토일"[d0.weekday()]
lines = []
for n, p in POS.items():
    c = hold_ccy(n)
    if c == "$": lines.append(f"{n} ${p['avg']:g}×{p['qty']}")
    else: lines.append(f"{n} {p['avg']:,}원×{p['qty']}")
kr_h = [n for n in POS if hold_ccy(n) == "₩"]
us_h = [n for n in POS if hold_ccy(n) == "$"]
sk["meta"].update({
 "mode": MODE, "pub": pub, "asof": ASOF,
 "asof_label": f"{ASOF}({wd}) 한국장 마감 + 간밤 미국장",
 "next": f"{pub} 한국장 " + ("개장 전" if MODE == "마감" else "개장 전"),
 "position": f"보유 {len(POS)}종 — 국장 {len(kr_h)} + 미장 {len(us_h)}",
 "position_line": "포지션: " + " / ".join(lines) + ". 통화 분리 계산.",
 "position_note": f"보유 {len(POS)}종 — 국장 원화 {len(kr_h)}·미장 달러 {len(us_h)}"
})

# ══════════════ [AUTO] levels (코스피) ══════════════
c = K["close"]
LV = [
 ("코스피 종가", c, None, f"{ASOF} 확정({K['chg']:+.2f}%). 야후 v8 실측 = 마감시황 종가 대조(§8 G17)."),
 ("20일선", K["ma20"], None, "단기 추세 기준선. 종가 회복·이탈이 이 회차 최대 분기점."),
 ("기준선", K["base"], None, "일목 기준선."),
 ("10일선", K["ma10"], None, "단기 이평."),
 ("전환선", K["conv"], None, "일목 전환선."),
 ("60일선", K["ma60"], None, "중기 추세선."),
 ("일목 구름 상단", K["ctop"], None, "중기 상단 저항."),
 ("일목 구름 하단", K["cbot"], None, "구름 하단, 이탈 시 추세 훼손 경계."),
 ("볼린저 하단", K["bb_low"], None, "밴드 하단 지지."),
 ("최근 22봉 저점", K["lo22"], None, "최후 지지."),
]
lev = {}
for name, val, _, desc in LV:
    if name == "코스피 종가":
        lev[name] = f"<b>{f(val,2)}</b> — {desc}"
    else:
        dd = dist(c, val); side = pos_side(c, val)
        lev[name] = f"<b>{f(val,2)}</b> — 현재가 대비 <b>{dd:+.2f}% {side}</b>. {desc}"
sk["levels"] = lev

# ══════════════ [AUTO] log8 (그대로 복사) ══════════════
sk["log8"] = D.get("log8", [])

# ══════════════ [AUTO] baseline (보유 종목 기준선 검증) ══════════════
bl = {}
for n in POS:
    b = KR.get(n) or US.get(n)
    if not b: continue
    a = POS[n]["avg"]; cc = b["close"]; ccy = hold_ccy(n)
    plv = dist(cc, a)
    ma20 = b["ma20"]; d20 = dist(cc, ma20); s20 = pos_side(cc, ma20)
    unit = "$" if ccy == "$" else ""
    fmt = 2 if ccy == "$" else 0
    trig = f"신호 {b['nsig']}개 · score {b['score']}"
    verify = (f"평단 {unit}{f(a,fmt)} 대비 <b>{plv:+.2f}%</b>. "
              f"현재가는 20일선 {unit}{f(ma20,fmt)} " + ("위" if d20>=0 else "아래") + f"({d20:+.1f}%). "
              f"120일선 대비 {b['vs_ma120']:+.1f}%.")
    bl[n] = {"base": a, "avg": a, "qty": POS[n]["qty"], "trigger": trig, "verify": verify}
sk["baseline"] = bl

# ══════════════ [AUTO] sector_notes (RS·대표주) ══════════════
sn = {}
sd = SEC.get("data", {})
ranked = sorted(sd.items(), key=lambda kv: kv[1].get("rs_w", 0), reverse=True)
for i, (name, v) in enumerate(ranked, 1):
    rsw = v.get("rs_w", 0); rep = v.get("rep", "")
    tag = "상위" if rsw > 1 else ("중립" if rsw > -1 else "열위")
    sn[name] = f"<b>RS {rsw:+.1f}</b>(주간 {i}위·{tag}) — {rep}."
sk["sector_notes"] = sn

# ══════════════ [AUTO] calendar_range ══════════════
end = dt.date.fromisoformat(pub) + dt.timedelta(days=12)
sk["calendar_range"] = f"{pub} ~ {end.isoformat()}"

# ══════════════ [AUTO] dashboard 고정노트 + reason ══════════════
sk["dashboard"]["note_a"] = f"기준 <b>{ASOF} 종가</b> · <b>국장=원화(₩)·미장=달러($) 각 통화 계산</b>"
rc = HEDGE.get("items", {})
reason = {}
for n in POS:
    b = KR.get(n) or US.get(n)
    if not b: continue
    a = POS[n]["avg"]; plv = dist(b["close"], a)
    hint = ""
    if n in rc: hint = f" · 상관 {rc[n].get('corr60',0):+.2f}(헤지)"
    reason[n] = f"보유 {POS[n]['qty']}주 · 평가 <b>{plv:+.2f}%</b>{hint}"
sk["dashboard"]["reason"] = reason

# ══════════════ [AUTO] index_notes 숫자 골격 ══════════════
def mac_line(key, dec=2, unit=""):
    v = MAC.get(key, {})
    cl = v.get("close"); cp = v.get("chg_pct", v.get("chg"))
    if cl is None: return ""
    s = f"<b>{unit}{f(cl,dec)} ({cp:+.2f}%)</b> — {v.get('date','')} 종가."
    return s
IN = sk["index_notes"]
IN["코스피"] = f"<b>{f(c,2)} ({K['chg']:+.2f}%)</b> — {ASOF} 종가. 20일선 {dist(c,K['ma20']):+.1f}%·60일선 {dist(c,K['ma60']):+.1f}%. RSI {K['rsi']:.1f}."
kd = MAC.get("코스닥", {})
IN["코스닥"] = f"<b>{f(kd.get('close',0),2)} ({kd.get('chg_pct',0):+.2f}%)</b> — {ASOF} 종가."
IN["KOSPI200"] = f"<b>{f(MAC.get('KOSPI200',{}).get('close',0),2)}</b> — {ASOF}. ※ KODEX200 스케일 복원(§8)."
IN["야간선물"] = f"<b>≈{f(NFP.get('value',0),2)} ({NFP.get('chg',0):+.2f}%) · Tier2 프록시</b> — {NFP.get('note','')}"
for k in ["S&P500","나스닥","필라델피아반도체(SOX)","VIX","VIX3M","원/달러","달러/엔","WTI","브렌트","미국채10년","비트코인"]:
    dec = 3 if k == "미국채10년" else (0 if k == "비트코인" else 2)
    unit = "$" if k == "비트코인" else ""
    ln = mac_line(k, dec, unit)
    if ln: IN[k] = ln


# ══════════════ [AUTO 골격 + 숫자] watch (position-driven) ══════════════
# 분석 칸(why/action/danger/read/trigger/avoid/concl/risk/tgt/tgt_detail/
#          earnings/valuation/hold_read)은 빈칸("") → 사람이 채운다.
# 숫자 앵커(t_tech/t_cons/pos_note)와 off_why({})는 자동.
WATCH_ANALYSIS = ["why","action","danger","read","trigger","avoid","concl",
                  "risk","tgt","tgt_detail","earnings","valuation","hold_read"]
wt = {}
for n in POS:
    b = KR.get(n) or US.get(n)
    if not b: continue
    ccy = hold_ccy(n); unit = "$" if ccy == "$" else ""
    fmt = 2 if ccy == "$" else 0
    a = POS[n]["avg"]; plv = dist(b["close"], a)
    ent = {"badge": "홀드"}
    ent["t_tech"] = round(b.get("bb_up", b["close"]))       # 근접 기술 저항
    ent["t_cons"] = round(b.get("tgt_px", b["close"]))       # 모델 목표
    for k in WATCH_ANALYSIS:
        ent[k] = ""                                          # ← 사람이 채움
    ent["news"] = [["", ""], ["", ""]]                       # ← 사람이 채움(날짜·문구)
    ent["off_why"] = {}                                      # preflight 자동보충
    ent["pos_note"] = (f"평단 {unit}{f(a,fmt)}×{POS[n]['qty']}주 · 평가 {plv:+.2f}%"
                       + (f" · 헤지(상관 {HEDGE.get('items',{}).get(n,{}).get('corr60',0):+.2f})"
                          if n in HEDGE.get("items", {}) else ""))
    wt[n] = ent
sk["watch"] = wt

json.dump(sk, open("research.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

auto = ["meta","levels","log8","baseline","sector_notes","calendar_range","dashboard.note_a","dashboard.reason","index_notes(숫자)","enhance"]
me = [k for k,v in sk.items() if (isinstance(v,str) and v=="") ]
print(f"■ prefill 완료 (mode={MODE} · asof={ASOF} · pub={pub})")
print(f"  [AUTO 채움] {', '.join(auto)}")
print(f"  [ME 빈칸(분석 작성 필요)] 문자열 블록 중 빈칸: {me}")
