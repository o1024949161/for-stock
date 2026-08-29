# -*- coding: utf-8 -*-
"""pick_engine.py — ★브리핑 종목 «선정» 엔진 (v48 실측 개편판)"""
import numpy as np, pandas as pd
import lib_ind as L

W_TREND = {"구름대강세돌파": 39.7, "삼역호전": 26.5, "RSI반등": 19.5, "MACD호전": 14.3}
W_REV   = {"RSI과매도": 47.8, "20일선하방이격": 43.7, "RSI과매도탈출": 8.5}

TREND_BANDS = [(66, 999, "강", "표본외 20일 초과수익 +4.14% · 승률 53.4%"),
               (26, 66, "양", "표본외 +2.35% · 승률 52.7%"),
               (0,  26, "약", "표본외 +0.45% · 승률 48.2%")]
REV_BANDS   = [(50, 999, "강", "표본외 +2.50% · 승률 51.8%"),
               (20, 50, "양", "표본외 +0.76% · 승률 47.5%"),
               (0.1, 20, "중립", "표본외 +0.38%"),
               (0, 0.1, "약", "표본외 -0.52% · 승률 45.1% — 되돌림 조건 없음")]
TREND_WARN  = [(70, 999, "표본외 -1.33% · 승률 44.1%"),
               (40, 70,  "표본외 -0.66%"),
               (0,  40,  "표본외 -0.2% 내외")]
CHAR_TH = -0.02

LIQ_MIN    = 100e8
LIQ_MIN_US = 5e7
AMP_MIN   = 1.5
RR_MIN    = 1.5
EVENT_DAYS = 5
TAX_RT, FEE_RT = 0.0018, 0.00015


def _naive(obj):
    o = obj.copy()
    idx = pd.to_datetime(o.index)
    try:
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    o.index = idx.normalize()
    return o[~o.index.duplicated(keep="last")]


def band_of(score, bands):
    for lo, hi, lab, note in bands:
        if lo <= score < hi: return lab, note
    return bands[-1][2], bands[-1][3]


def rev_signals_series(df):
    c, h, l, o, v = df["Close"], df["High"], df["Low"], df["Open"], df["Volume"]
    ub, mb, lb, sd = L.boll(c); r = L.rsi(c); ml, ms, mh = L.macd(c)
    pb = (c - lb) / (ub - lb); ma20 = L.sma(c, 20)
    hi60, lo60 = h.rolling(60).max(), l.rolling(60).min()
    S = {"RSI과매도": r < 30,
         "RSI과매도탈출": (r.shift(1) < 32) & (r > r.shift(1)),
         "밴드하단이탈": pb < 0.05,
         "밴드하단복귀": (pb.shift(1) < 0.10) & (pb > pb.shift(1)) & (pb < 0.5),
         "20일선하방이격": (c / ma20 - 1) < -0.07,
         "스윙하단권": ((c - lo60) / (hi60 - lo60)) < 0.20,
         "연속음봉소진": ((c.shift(1) < o.shift(1)) & (c.shift(2) < o.shift(2))
                          & (c.shift(3) < o.shift(3)) & (c > o)),
         "투매거래량": (v > v.rolling(20).mean() * 2.0) & (c < o),
         "52주저점근접": (c / l.rolling(252).min() - 1) < 0.07,
         "MACD바닥반전": (mh < 0) & (mh > mh.shift(1)) & (mh.shift(1) <= mh.shift(2))}
    return {k: s.fillna(False).astype(bool) for k, s in S.items()}


def trend_signals_series(df):
    c, h, l = df["Close"], df["High"], df["Low"]
    r = L.rsi(c); ml, ms, mh = L.macd(c)
    conv, base, sA, sB = L.ichimoku_raw(df)
    ca, cb = L.cloud_at_today(sA, sB)
    ctop = pd.concat([ca, cb], axis=1).max(axis=1)
    above, bull = c > ctop, ca > cb
    S = {"구름대강세돌파": above & bull,
         "삼역호전": above & (conv > base) & (c > c.shift(26)),
         "RSI반등": (r.rolling(10).min() < 35) & (r > r.shift(1)) & (r < 60),
         "MACD호전": (mh > 0) & (mh > mh.shift(1))}
    return {k: s.fillna(False).astype(bool) for k, s in S.items()}


def character(close, bench_close, fwd=20):
    b = bench_close.reindex(close.index, method="ffill")
    past = close / close.shift(fwd) - 1
    ex = (close.shift(-fwd) / close - 1) - (b.shift(-fwd) / b - 1)
    d = pd.DataFrame({"p": past, "e": ex}).dropna()
    return None if len(d) < 120 else float(np.corrcoef(d.p, d.e)[0, 1])


def score_stock(df, bench_close):
    T = trend_signals_series(df); R = rev_signals_series(df)
    sT_s = sum(T[k].astype(float) * W_TREND[k] for k in W_TREND)
    sR_s = sum(R[k].astype(float) * W_REV[k] for k in W_REV)
    ch = character(df["Close"], bench_close)
    is_rev = (ch is not None and ch < CHAR_TH)
    sT, sR = round(float(sT_s.iloc[-1]), 1), round(float(sR_s.iloc[-1]), 1)
    if is_rev:
        lab, note = band_of(sR, REV_BANDS)
        warn = next((n for lo, hi, n in TREND_WARN if lo <= sT < hi), None) if sT >= 40 else None
        model, used = "되돌림 모델", sR
    else:
        lab, note = band_of(sT, TREND_BANDS)
        warn, model, used = None, "추세 모델", sT
    return {"model": model, "used": used, "band": lab, "band_note": note,
            "trend": sT, "rev": sR, "char": None if ch is None else round(ch, 3),
            "is_rev": bool(is_rev), "trend_warn": warn,
            "on": {k: bool(T[k].iloc[-1]) for k in W_TREND},
            "on_rev": {k: bool(R[k].iloc[-1]) for k in W_REV},
            "_sT": sT_s, "_sR": sR_s}


def validate_stock(df, bench_close, sT_s, sR_s, is_rev, fwd=20):
    c = df["Close"]; b = bench_close.reindex(c.index, method="ffill")
    ex = ((c.shift(-fwd) / c - 1) - (b.shift(-fwd) / b - 1)) * 100
    s = sR_s if is_rev else sT_s
    d = pd.DataFrame({"s": s, "ex": ex}).dropna()
    bands = REV_BANDS if is_rev else TREND_BANDS
    cur, out = float(s.iloc[-1]), []
    for lo, hi, lab, _ in bands:
        x = d[(d.s >= lo) & (d.s < hi)]
        out.append({"lab": f"{lo:g}~{'' if hi > 900 else int(hi)} {lab}", "n": int(len(x)),
                    "mean": float(x.ex.mean()) if len(x) >= 20 else None,
                    "hit": float((x.ex > 0).mean() * 100) if len(x) >= 20 else None,
                    "cur": bool(lo <= cur < hi)})
    hi_ = d[d.s >= bands[0][0]]; lo_ = d[d.s < bands[-1][1]]
    works = bool(len(hi_) >= 20 and len(lo_) >= 20 and hi_.ex.mean() > lo_.ex.mean())
    return {"n_total": int(len(d)), "bands": out, "works": works}


def tradability(df, tgt=None, stop=None, dday=None, liq_min=None, market="KR"):
    c, h, l, o, v = df["Close"], df["High"], df["Low"], df["Open"], df["Volume"]
    px = float(c.iloc[-1])
    amt20 = float((c * v).tail(20).mean())
    rng20 = float(((h - l) / c * 100).tail(20).mean())
    gap20 = float(((o / c.shift(1) - 1) * 100).tail(20).abs().mean())
    _lim = liq_min if liq_min is not None else (LIQ_MIN if market == "KR" else LIQ_MIN_US)
    _big = 5e10 if market == "KR" else 5e8
    _mid = 1e10 if market == "KR" else 1e8
    slip = 0.10 if amt20 >= _big else (0.25 if amt20 >= _mid else 0.60)
    cost = ((TAX_RT if market == "KR" else 0.0) + FEE_RT * 2) * 100 + slip * 2
    rr = ((tgt - px) / max(px - stop, 1e-9)) if (tgt and stop and px > stop) else None
    fails = []
    _u = "억" if market == "KR" else "억$"
    if amt20 < _lim: fails.append(f"유동성 {amt20/1e8:,.1f}{_u} < {_lim/1e8:,.1f}{_u}")
    if rng20 < AMP_MIN: fails.append(f"진폭 {rng20:.2f}% < {AMP_MIN}%")
    if rr is not None and rr < RR_MIN: fails.append(f"손익비 {rr:.2f} < {RR_MIN}")
    if dday is not None and 0 <= dday <= EVENT_DAYS: fails.append(f"실적 D-{dday} 이벤트 창")
    exp = None
    if rr is not None and tgt: exp = (tgt / px - 1) * 100
    if exp is not None and exp <= cost: fails.append(f"기대수익 {exp:.1f}% ≤ 왕복비용 {cost:.2f}%")
    return {"px": px, "amt20": amt20, "rng20": rng20, "gap20": gap20,
            "slip": slip, "cost": cost, "rr": rr, "pass": not fails, "fails": fails}


def vol_regime(df):
    c = df["Close"]; ub, mb, lb, sd = L.boll(c)
    bw = ((ub - lb) / mb).dropna()
    if len(bw) < 120: return None
    now = float(bw.iloc[-1]); p = float((bw.tail(252) < now).mean() * 100)
    return {"bw": now * 100, "pctl": p,
            "state": "스퀴즈(수축) — 방향 대기" if p < 25 else
                     ("확장 국면 — 추세 진행 중" if p > 75 else "보통")}


def behavior(df):
    c, h, l, o = df["Close"], df["High"], df["Low"], df["Open"]
    ma20 = L.sma(c, 20)
    touch = (l <= ma20) & (c.shift(1) > ma20.shift(1))
    tb = (c.shift(-5) / c - 1)[touch].dropna()
    gap = o / c.shift(1) - 1; gu = gap > 0.02
    filled = ((l <= c.shift(1)) & gu).fillna(False)
    win = float((tb > 0).mean() * 100) if len(tb) >= 10 else None
    return {"ma20_win": win, "ma20_n": int(len(tb)),
            "gap_fill": float(filled.sum() / gu.sum() * 100) if gu.sum() >= 10 else None,
            "style": ("눌림목형 — 20일선 지지에서 담는다" if (win or 0) >= 55
                      else "돌파형 — 저항 돌파를 확인하고 담는다")}


def market_regime(bench_close):
    c = bench_close.dropna(); px = float(c.iloc[-1])
    m20, m60, m120 = L.sma(c, 20), L.sma(c, 60), L.sma(c, 120)
    up = int(px > m20.iloc[-1]) + int(px > m60.iloc[-1]) + int(px > m120.iloc[-1]) \
         + int(m20.iloc[-1] > m60.iloc[-1])
    dd = float((px / c.tail(252).max() - 1) * 100)
    if up >= 4 and dd > -7: st, sz = "위험선호(Risk-On)", 100
    elif up >= 2:           st, sz = "중립", 70
    else:                   st, sz = "위험회피(Risk-Off)", 40
    return {"state": st, "size_pct": sz, "up_of4": up, "dd252": dd,
            "note": f"이평 4개 조건 중 {up}개 충족 · 52주 고점 대비 {dd:+.1f}%"}


def pick_rank(cands, bench_close, regime=None, market="KR"):
    bench_close = _naive(bench_close)
    regime = regime or market_regime(bench_close)
    out = []
    for cd in cands:
        df = _naive(cd["df"])
        sc = score_stock(df, bench_close)
        vl = validate_stock(df, bench_close, sc.pop("_sT"), sc.pop("_sR"), sc["is_rev"])
        tr = tradability(df, cd.get("tgt"), cd.get("stop"), cd.get("dday"), market=market)
        bh = behavior(df); vr = vol_regime(df)
        pts = 0.0; why = []
        pts += sc["used"] * 0.6
        why.append(f'{sc["model"]} {sc["used"]}점({sc["band"]})')
        if not vl["works"]:
            pts -= 15; why.append("종목별 검증 미통과")
        if sc["is_rev"] and sc["trend"] >= 40:
            pts -= 15; why.append(f'역방향 경고(추세 {sc["trend"]}점 · {sc["trend_warn"]})')
        if tr["rr"] is not None:
            pts += min(tr["rr"], 4.0) * 5
            why.append(f'R:R {tr["rr"]:.2f}')
        if tr["amt20"] >= (5e10 if market == "KR" else 5e8): pts += 5
        if tr["rng20"] >= 2.5: pts += 5
        if tr["gap20"] > 2.5: pts -= 5; why.append(f'갭 {tr["gap20"]:.1f}%')
        if vr and vr["pctl"] < 25: pts += 3; why.append("스퀴즈 — 확장 대기")
        out.append({"name": cd["name"], "rank_score": None if not tr["pass"] else round(pts, 1),
                    "excluded": not tr["pass"], "exclude_why": tr["fails"],
                    "why": " · ".join(why), "score": sc, "valid": vl,
                    "trade": tr, "behav": bh, "vol": vr,
                    "size_cap": regime["size_pct"]})
    ok = sorted([x for x in out if not x["excluded"]], key=lambda z: -z["rank_score"])
    ng = [x for x in out if x["excluded"]]
    return {"picks": ok, "excluded": ng, "regime": regime}
