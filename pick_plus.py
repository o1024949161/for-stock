# -*- coding: utf-8 -*-
"""
pick_plus.py — ★v62 추천 종목 카드 선정 «6기둥 점수» (선정 점수 v2)

기존(v49) 선정 점수 = 모델점수×0.6 + R:R×5 + 가점/감점. 이건 «차트 셋업»만 본다.
v62는 «앞으로 오를 종목»을 고르는 데 실증적으로 쓰이는 축을 더해 6기둥 100점으로 다시 줄 세운다.

  기둥                     만점  무엇을 보나(데이터)
  ① 셋업(이중모델)          25   종목 성격에 맞는 모델 점수(추세/되돌림) — 기존 엔진 그대로
  ② 손익비(R:R)             15   (목표−현재가) ÷ (현재가−손절) — 4배에서 만점
  ③ 주도성(RS 백분위)       20   3·6·9·12개월 수익률 가중(0.4·0.2·0.2·0.2)을 같은 시장 150종 안에서 순위 매김(1~99)
  ④ 수급                   15   국장: 외국인+기관 20일 누적 순매수 ÷ 시총 · 연속 순매수 / 미장: 상승일 거래량 ÷ 하락일 거래량(20일)
  ⑤ 촉매(컨센서스)          15   증권사 평균 목표가까지 여력 + 투자의견 — 네이버 금융(FnGuide·Refinitiv 집계)
  ⑥ 포트 적합성             10   지금 보유 종목과의 120일 상관 — 낮을수록 분산에 도움
  감점: 종목별 검증 미통과 −15 · 역방향 경고 −15 (v49 유지)

확신 등급: A = 70점↑ 그리고 «강» 기둥(만점의 60%↑) 4개↑ / B = 55점↑ / C = 그 외.
하드 필터(유동성·진폭·R:R 1.5·왕복비용)는 v49 그대로 «앞단»에서 적용한다 — 여기선 통과 종목만 다시 줄 세운다.
배합비는 설계값이다(백테스트 전). 그래서 기둥별 점수를 전부 표에 노출해 «왜 이 순위인가»를 검증 가능하게 둔다.
"""
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

MAXP = {"setup": 25, "rr": 15, "rs": 20, "flow": 15, "cat": 15, "fit": 10}
LABEL = {"setup": "셋업", "rr": "손익비", "rs": "주도성", "flow": "수급", "cat": "촉매", "fit": "포트적합"}


def rs_raw(c):
    """IBD식 상대강도 원점수 — 최근 3개월에 가중 0.4, 6·9·12개월 각 0.2."""
    def r(n):
        return float(c.iloc[-1] / c.iloc[-1 - n] - 1) if len(c) > n else None
    parts = [(0.4, r(63)), (0.2, r(126)), (0.2, r(189)), (0.2, r(252))]
    got = [(w, v) for w, v in parts if v is not None]
    if not got:
        return None
    return sum(w * v for w, v in got) / sum(w for w, _ in got) * 100


def add_rs_pct(pool):
    vals = {k: x.get("rs_raw") for k, x in pool.items() if x.get("rs_raw") is not None}
    if not vals:
        return
    s = pd.Series(vals).rank(pct=True)
    for k, p in s.items():
        pool[k]["rs_pct"] = int(max(1, min(99, round(p * 99))))


def ud_ratio(df, n=20):
    c, v = df["Close"], df["Volume"]
    ch = c.diff()
    t = pd.DataFrame({"ch": ch, "v": v}).tail(n)
    up, dn = t.loc[t.ch > 0, "v"].sum(), t.loc[t.ch < 0, "v"].sum()
    return float(up / dn) if dn > 0 else None


def _parse_cap(s):
    """네이버 «1,674조 9,588억» → 원."""
    if not s:
        return None
    s = str(s).replace(",", "")
    jo = eok = 0.0
    if "조" in s:
        a, s = s.split("조", 1)
        jo = float(a.strip() or 0)
    s = s.replace("억", "").strip()
    if s:
        try:
            eok = float(s)
        except Exception:
            pass
    return (jo * 1e12 + eok * 1e8) or None


def score_flow_kr(st):
    """국장 수급 기둥(15): 20일 외국인+기관 누적 ÷ 시총(%) + 연속 순매수 가점."""
    if not st or st.get("frn_20d_amt") is None:
        return 0.0, "수급 데이터 없음"
    net = (st.get("frn_20d_amt") or 0) + (st.get("inst_20d_amt") or 0)      # 억원
    cap = st.get("mcap")
    ratio = (net * 1e8 / cap * 100) if cap else None
    p = 0.0
    if ratio is not None:
        p = 12 if ratio >= 0.5 else 9 if ratio >= 0.2 else 6 if ratio > 0 else 2 if ratio > -0.2 else 0
    else:
        p = 8 if net > 0 else 0
    stk = max(st.get("frn_streak") or 0, st.get("inst_streak") or 0)
    if stk >= 3:
        p += 3
    txt = (f"외인+기관 20일 {net:+,.0f}억" + (f"(시총 대비 {ratio:+.2f}%)" if ratio is not None else "")
           + (f" · 연속 순매수 {stk}일" if stk >= 3 else ""))
    return float(min(p, 15)), txt


def score_flow_us(x):
    u = x.get("ud20")
    if u is None:
        return 0.0, "거래량 데이터 없음"
    p = 15 if u >= 1.5 else 11 if u >= 1.2 else 7 if u >= 1.0 else 3 if u >= 0.8 else 0
    return float(p), f"상승일/하락일 거래량 {u:.2f}배(20일)"


def score_cat(st, px):
    if not st or not st.get("target_mean") or not px:
        return 0.0, "컨센서스 없음"
    up = (st["target_mean"] / px - 1) * 100
    p = 10 if up >= 30 else 7 if up >= 15 else 4 if up >= 5 else 0
    rc = st.get("recomm")
    if rc is not None and rc >= 4.0:
        p += 5
    elif rc is not None and rc >= 3.5:
        p += 2
    return float(min(p, 15)), f"목표가 여력 {up:+.1f}%" + (f" · 투자의견 {rc:.2f}/5" if rc is not None else "")


def score_fit(corr):
    if corr is None:
        return 10.0, "보유 없음 — 제약 없음"
    p = 10 if corr <= 0.3 else 5 if corr <= 0.6 else 0
    return float(p), f"보유 종목과 상관 {corr:+.2f}"


def rerank(picks, pool, market, dfs, held_ret, fetch_kr=None, fetch_us=None, topn=15):
    """picks: pick_rank 결과(하드필터 통과·rank_score 순). pool: OUT[kr|us]. dfs: 이름→일봉.
    held_ret: 보유 포트 일간수익률 Series(naive date index) 또는 None.
    fetch_kr(code)->dict / fetch_us(ticker)->dict : 컨센서스·수급 조회 함수(네트워크 실패 허용)."""
    top = picks[:topn]
    ext = {}
    def job(r):
        x = pool.get(r["name"]) or {}
        try:
            if market == "KR" and fetch_kr:
                return r["name"], fetch_kr(x["ticker"].split(".")[0])
            if market == "US" and fetch_us:
                return r["name"], fetch_us(x["ticker"])
        except Exception as e:
            return r["name"], {"err": str(e)}
        return r["name"], None
    with ThreadPoolExecutor(8) as ex:
        for n, v in ex.map(job, top):
            ext[n] = v
    out = []
    for r in top:
        n = r["name"]; x = pool.get(n) or {}; st = ext.get(n) or {}
        sc, tr = r["score"], r["trade"]
        P, why = {}, {}
        P["setup"] = min(max(sc["used"], 0), 100) / 100 * MAXP["setup"]
        why["setup"] = f'{sc["model"]} {sc["used"]}점({sc["band"]})'
        rr = tr.get("rr") or 0
        P["rr"] = min(rr, 4.0) / 4.0 * MAXP["rr"]; why["rr"] = f"R:R {rr:.2f}"
        rp = x.get("rs_pct")
        P["rs"] = (rp or 0) / 99 * MAXP["rs"]; why["rs"] = f"RS 백분위 {rp}" if rp else "RS 산출 불가"
        if x.get("rs_lead"):
            why["rs"] += " · RS 선행 신고가"
        P["flow"], why["flow"] = score_flow_kr(st) if market == "KR" else score_flow_us(x)
        P["cat"], why["cat"] = score_cat(st, x.get("close"))
        corr = None
        d = dfs.get(n)
        if held_ret is not None and d is not None:
            try:
                s = d["Close"].copy(); s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
                j = pd.concat([held_ret.rename("h"), s.pct_change().rename("s")], axis=1).dropna().tail(120)
                if len(j) > 30:
                    corr = float(np.corrcoef(j["h"], j["s"])[0, 1])
            except Exception:
                corr = None
        P["fit"], why["fit"] = score_fit(corr)
        pen, pen_why = 0.0, []
        if not r["valid"]["works"]:
            pen -= 15; pen_why.append("종목별 검증 미통과 −15")
        if sc["is_rev"] and sc["trend"] >= 40:
            pen -= 15; pen_why.append("역방향 경고 −15")
        tot = round(sum(P.values()) + pen, 1)
        strong = sum(1 for k, v in P.items() if v >= 0.6 * MAXP[k])
        grade = "A" if (tot >= 70 and strong >= 4) else ("B" if tot >= 55 else "C")
        r["v2"] = {"total": tot, "grade": grade, "strong": strong,
                   "pillars": {k: round(v, 1) for k, v in P.items()}, "why": why,
                   "penalty": pen, "penalty_why": pen_why, "corr_held": None if corr is None else round(corr, 2),
                   "cons": {k: st.get(k) for k in ("target_mean", "target_hi", "target_lo", "recomm", "cons_date",
                                                    "fwd_per", "per")} if st else None}
        out.append(r)
    out.sort(key=lambda z: -z["v2"]["total"])
    return out + picks[topn:]
