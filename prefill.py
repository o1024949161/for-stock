#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prefill.py — «골격은 재사용, 값·판단만 갈아끼운다» (2026-09-17 신설 · ★v62 확장)

용도: 매 회차 build.py «앞»에서 1회 실행.
  research.skeleton.json + data.json(+extra) + config + brief_state.json → research.json
  · [AUTO] 계산 가능한 칸 = prefill/build가 전부 채운다(사람·모델이 손대지 않는다).
  · [ME]   트레이딩 분석·멘트·판단 칸만 빈칸("")으로 남긴다 → me.json(분석 칸)으로 채운다.

★v62에서 AUTO로 넘어온 칸(모델이 매 회차 손으로 쓰던 «숫자 옮겨 적기»):
  levels · baseline · dashboard.reason · sector_notes · kospi_caption · watch.pos_note/t_tech/t_cons ·
  index_notes 숫자 머리(build) · index_extra(외국인 수급·국고채 3년 — build) · supply 표 숫자·출처(build) ·
  risk.modes 손절선 목록(build) · tracker_events(캘린더에서 build) · off_why(preflight) · 뉴스 첫 줄 등락(build)
  → 모델은 «해석»만 쓴다. 숫자는 전부 data.json에서 나온다(오기 원천 차단).

실행:  python3 prefill.py 마감   (또는 장전)
"""
import json, sys, datetime as dt
import config

MODE = sys.argv[1] if len(sys.argv) > 1 else "마감"
D = json.load(open("data.json", encoding="utf-8"))
ASOF = D["asof"]
K = D["kospi"]; KR = D["kr"]; US = D["us"]; HOLD = D.get("holdings", {})
MAC = D.get("macro", {}); SEC = D.get("sector", {})
EX = D.get("extra", {}) or {}
POS = config.POSITIONS
WATCH = [(n, code, tk, cur) for n, code, tk, cur in config.WATCH]                    # 분석 카드
TRACK = [(n, code, tk, cur) for n, code, tk, cur in getattr(config, "TRACK", config.WATCH)]   # 비교표·트래커(카드 + 추적 전용)
SOLD = getattr(config, "SOLD", set())
try:
    BS = json.load(open("brief_state.json", encoding="utf-8"))
except Exception:
    BS = {}

try:
    import asof as _A
    _HOL = _A.KR_HOLIDAYS
except Exception:
    _HOL = set()


def nxt_trading_day(iso):
    d = dt.date.fromisoformat(iso)
    while True:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in _HOL:
            return d.isoformat()


def f(n, dec=0):
    try:
        return f"{n:,.{dec}f}"
    except Exception:
        return str(n)


def dist(cur, ref):
    return (cur / ref - 1) * 100


def X(n):
    return KR.get(n) or US.get(n) or HOLD.get(n)


def ccy_of(n):
    return next((cur for nn, _, _, cur in TRACK if nn == n), POS.get(n, {}).get("ccy", "₩"))


def money(n, v):
    return f"${v:,.2f}" if ccy_of(n) == "$" else f"{v:,.0f}원"


sk = json.load(open("research.skeleton.json", encoding="utf-8"))

# ══════════════ [AUTO] meta ══════════════
pub = nxt_trading_day(ASOF)
d0 = dt.date.fromisoformat(ASOF)
wd = "월화수목금토일"[d0.weekday()]
kr_h = [n for n in POS if POS[n].get("ccy", "₩") == "₩"]
us_h = [n for n in POS if POS[n].get("ccy") == "$"]
lines = [f"{n} " + (f"${p['avg']:g}×{p['qty']}" if p.get("ccy") == "$" else f"{p['avg']:,}원×{p['qty']}")
         for n, p in POS.items()]
us_d = (MAC.get("S&P500") or {}).get("date", "")
sk["meta"].update({
    "mode": MODE, "pub": pub, "asof": ASOF,
    "asof_label": f"{ASOF}({wd}) 한국장 마감 + 간밤 미국장({us_d})",
    "next": f"{pub} 한국장 개장 전",
    "position": f"보유 {len(POS)}종 — 국장 {len(kr_h)} + 미장 {len(us_h)}",
    "position_line": ("포지션: " + " / ".join(lines) + ". 통화 분리 계산.") if lines else "포지션: 무포지션(현금 100%).",
    "position_note": f"보유 {len(POS)}종 — 국장 원화 {len(kr_h)}·미장 달러 {len(us_h)}",
})

# ══════════════ [AUTO] levels (코스피) ══════════════
c = K["close"]
LV = [
    ("코스피 종가", c, f"{ASOF} 확정({K['chg']:+.2f}%). 야후 실측 × 네이버·다음 확정 종가 대조(§8 G17)."),
    ("20일선", K["ma20"], "단기 추세 기준선. 종가 회복·이탈이 단기 방향을 가른다."),
    ("기준선", K["base"], "일목 기준선(26일 중간값) — 중기 균형가."),
    ("10일선", K["ma10"], "단기 이평."),
    ("전환선", K["conv"], "일목 전환선(9일 중간값) — 단기 균형가."),
    ("60일선", K["ma60"], "중기 추세선."),
    ("일목 구름 상단", K["ctop"], "구름 상단 — 위면 강세 국면."),
    ("일목 구름 하단", K["cbot"], "구름 하단 — 이탈 시 추세 훼손 경계."),
    ("볼린저 하단", K["bb_low"], "밴드 하단(20일 평균 −2σ) 지지."),
    ("최근 22봉 저점", K["lo22"], "최근 한 달 최저 — 최후 지지."),
]
lev = {}
for name, val, desc in LV:
    if name == "코스피 종가":
        lev[name] = f"<b>{f(val,2)}</b> — {desc}"
    else:
        dd = dist(val, c)
        lev[name] = f"<b>{f(val,2)}</b> — 현재가 대비 <b>{dd:+.2f}%</b>({'위' if val > c else '아래'}). {desc}"
sk["levels"] = lev

# ══════════════ [AUTO] kospi_caption (레벨 나열·보조지표 — 해석은 kospi_read가 한다) ══════════════
near = sorted([(nm, v) for nm, v, _ in LV if nm != "코스피 종가"], key=lambda t: abs(t[1] - c))[:5]
ups = [f"{nm} {f(v,0)}({dist(v,c):+.1f}%)" for nm, v in near if v > c]
dns = [f"{nm} {f(v,0)}({dist(v,c):+.1f}%)" for nm, v in near if v <= c]
sk["kospi_caption"] = (f"차트 <b>직전봉 = 기준일 {ASOF}({wd})</b> 종가 <b>{f(c,2)} ({K['chg']:+.2f}%)</b>. "
                       f"차트 우측 <b>레벨 보드</b>의 <b>R1·S1</b>과 본문 레벨표를 함께 본다 — "
                       f"가까운 저항: {' · '.join(ups) or '없음'} / 가까운 지지: {' · '.join(dns) or '없음'}. "
                       f"RSI {K['rsi']:.1f} · %b {K['pb']:.2f} · 주간 {K['ret5']:+.2f}% · 월간 {K['ret20']:+.2f}%.")

# ══════════════ [AUTO] log8 — fetch 단계 로그는 build가 data.json에서 직접 싣는다(중복 금지). 여기엔 웹조사 실패만.
sk["log8"] = []

# ══════════════ [AUTO] 기준가 — 매도 종목은 «매도 기준가», 새로 추적하는 종목은 «편입 기준가» ══════════════
exits = dict((BS.get("exits") or {}))
for n, code, tk, cur in TRACK:
    if n in POS:
        continue
    x = X(n)
    if x and n not in exits:
        sold = n in SOLD
        exits[n] = {"date": ASOF, "px": x["close"], "kind": "매도" if sold else "편입",
                    "note": "매도 고지 직후 첫 회차 종가(실제 체결가 미고지)" if sold else "추적 편입 첫 회차 종가"}
for n, e in exits.items():                      # 구버전 기록(kind 없음) 보정
    e.setdefault("kind", "매도" if n in SOLD else "편입")
sk["exits"] = exits

def base_lab(n):
    return "매도 기준가" if (exits.get(n) or {}).get("kind") == "매도" else "편입 기준가"

# ══════════════ [AUTO] baseline ══════════════
bl = {}
for n, code, tk, cur in TRACK:
    x = X(n)
    if not x:
        continue
    cc = x["close"]; d20 = dist(cc, x["ma20"])
    if n in POS:
        a = POS[n]["avg"]
        bl[n] = {"base": a, "avg": a, "qty": POS[n]["qty"],
                 "trigger": f"신호 {x['nsig']}개 · 19신호 {x['score']}점",
                 "verify": (f"평단 {money(n,a)} 대비 <b>{dist(cc,a):+.2f}%</b>. 20일선 {money(n,x['ma20'])} "
                            f"{'위' if d20 >= 0 else '아래'}({d20:+.1f}%). 120일선 대비 {x['vs_ma120']:+.1f}%.")}
    else:
        e = exits.get(n, {})
        b = e.get("px") or cc
        bl[n] = {"base": b, "avg": b, "qty": 0,
                 "trigger": f"신호 {x['nsig']}개 · 19신호 {x['score']}점",
                 "verify": (f"{base_lab(n)} {money(n,b)}({e.get('date', ASOF)}) 대비 <b>{dist(cc,b):+.2f}%</b> — "
                            + ((f"{'판 뒤 더 올랐다(재진입은 눌림에서)' if cc > b * 1.02 else ('판 뒤 내렸다(매도 판단 유효)' if cc < b * 0.98 else '판 가격 부근')}. ")
                               if base_lab(n) == "매도 기준가" else
                               (f"{'편입 후 상승' if cc > b * 1.02 else ('편입 후 하락' if cc < b * 0.98 else '편입 가격 부근')}. "))
                            + 
                            f"20일선 {'위' if d20 >= 0 else '아래'}({d20:+.1f}%).")}
sk["baseline"] = bl

# ══════════════ [AUTO] sector_notes ══════════════
sn = {}
ranked = sorted((SEC.get("data") or {}).items(), key=lambda kv: kv[1].get("rs_w", 0), reverse=True)
for i, (name, v) in enumerate(ranked, 1):
    rsw = v.get("rs_w", 0)
    tag = "상위" if rsw > 1 else ("중립" if rsw > -1 else "열위")
    sn[name] = f"<b>RS {rsw:+.1f}</b>(주간 {i}위·{tag}) — {v.get('rep','')}."
sk["sector_notes"] = sn

# ══════════════ [AUTO] calendar_range ══════════════
sk["calendar_range"] = f"{pub} ~ {(dt.date.fromisoformat(pub) + dt.timedelta(days=12)).isoformat()}"

# ══════════════ [AUTO] dashboard 고정노트 + reason ══════════════
sk["dashboard"]["note_a"] = f"기준 <b>{ASOF} 종가</b> · <b>국장=원화(₩)·미장=달러($) 각 통화 계산</b>"
reason = {}
for n, code, tk, cur in TRACK:
    x = X(n)
    if not x:
        continue
    if n in POS:
        reason[n] = f"보유 {POS[n]['qty']}주 · 평가 <b>{dist(x['close'], POS[n]['avg']):+.2f}%</b> · 20일선 {x['vs_ma20']:+.1f}%"
    else:
        b = (exits.get(n) or {}).get("px") or x["close"]
        reason[n] = (f"{'관찰(매도 완료)' if base_lab(n) == '매도 기준가' else '관찰'} · {base_lab(n)} 대비 "
                     f"<b>{dist(x['close'], b):+.2f}%</b> · 20일선 {x['vs_ma20']:+.1f}%")
sk["dashboard"]["reason"] = reason

# ══════════════ [ME] index_notes — 숫자 머리는 build가 붙인다. 여기엔 «맥락 해석»만 쓴다 ══════════════
sk["index_notes"] = {k: "" for k in ["코스피", "코스닥", "야간선물", "S&P500", "나스닥", "필라델피아반도체(SOX)", "VIX", "VIX3M",
                                     "원/달러", "달러/엔", "WTI", "브렌트", "미국채10년", "비트코인"]}
sk["index_extra"] = []                      # build가 extra(외국인 수급·국고채 3년)로 자동 생성

# ══════════════ [AUTO 골격 + 숫자] watch ══════════════
WATCH_ANALYSIS = ["why", "action", "danger", "read", "trigger", "avoid", "concl",
                  "risk", "tgt", "tgt_detail", "earnings", "valuation", "hold_read"]
stk = (EX.get("stocks") or {})
wt = {}
for n, code, tk, cur in WATCH:
    x = X(n)
    if not x:
        continue
    ent = {"badge": "홀드" if n in POS else "관망"}
    ent["t_tech"] = round(x.get("bb_up", x["close"]), 2 if cur == "$" else 0)
    tm = (stk.get(n) or {}).get("target_mean")
    ent["t_cons"] = round(tm if tm else x.get("tgt_px", x["close"]), 2 if cur == "$" else 0)
    for k in WATCH_ANALYSIS:
        ent[k] = ""
    ent["news"] = []                         # 모델은 «뉴스»만 2~3줄. 등락 줄은 build가 자동으로 맨 앞에 붙인다
    ent["off_why"] = {}                      # preflight research가 자동 보충
    if n in POS:
        a = POS[n]["avg"]
        ent["pos_note"] = f"평단 {money(n,a)}×{POS[n]['qty']}주 · 평가 {dist(x['close'], a):+.2f}%"
    else:
        b = (exits.get(n) or {}).get("px") or x["close"]
        ent["pos_note"] = (f"미보유(관찰{' · 매도 완료' if base_lab(n) == '매도 기준가' else ''}) · "
                           f"{base_lab(n)} {money(n,b)} 대비 {dist(x['close'], b):+.2f}%")
    wt[n] = ent
sk["watch"] = wt

# ══════════════ [AUTO] 추적 전용 종목(카드 없음) — 배지는 판단 매트릭스 규칙 판정, 목표는 컨센서스 ══════════════
try:
    import build_plus as _BP
except Exception:
    _BP = None
tr = {}
card_names = {n for n, _, _, _ in WATCH}
for n, code, tk, cur in TRACK:
    if n in card_names:
        continue
    x = X(n)
    if not x:
        continue
    tm = (stk.get(n) or {}).get("target_mean")
    rule = "관망"
    if _BP:
        try:
            _, rule, _, _ = _BP.hmatrix(n, x, n in POS, stk.get(n), BS, ASOF)
        except Exception:
            pass
    tr[n] = {"badge": rule, "auto": True,
             "t_tech": round(x.get("bb_up", x["close"]), 2 if cur == "$" else 0),
             "t_cons": round(tm if tm else x.get("tgt_px", x["close"]), 2 if cur == "$" else 0)}
sk["track"] = tr

# ══════════════ [ME] 신규 칸 ══════════════
sk["lead_sogo"] = ""                          # ①-2 선행 신호판 «그래서»
sk["supply"] = {"reads": {"외국인": "", "기관": "", "개인": "", "선물·프로그램": "", "시장 폭": ""}, "sogo": ""}
sk.setdefault("risk", {}).update({"modes": "", "events": ""})   # 비우면 build가 자동(손절선 목록·캘린더)
sk["tracker_events"] = ""
sk["hedge"] = {"read": ""}                    # 헤지 유효성 «그래서»
sk["stress"] = {"read": ""}                   # 스트레스 테스트 보는 법 뒤 한 줄
sk["shrink"] = ""

json.dump(sk, open("research.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

me_keys = []
def _walk(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            _walk(v, f"{p}.{k}" if p else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, f"{p}[{i}]")
    elif o == "":
        me_keys.append(p)
_walk(sk)
print(f"■ prefill 완료 (mode={MODE} · asof={ASOF} · pub={pub}) · 관찰 기준가 {len(exits)}종 · [ME] 빈칸 {len(me_keys)}개")
