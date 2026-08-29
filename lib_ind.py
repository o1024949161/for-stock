import numpy as np, pandas as pd

def ema(s,n): return s.ewm(span=n, adjust=False).mean()
def sma(s,n): return s.rolling(n).mean()

def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up/dn.replace(0,np.nan)
    return 100 - 100/(1+rs)

def atr(df, n=14):
    h,l,c = df['High'], df['Low'], df['Close']
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def boll(s, n=20, k=2.0):
    m = sma(s,n); sd = s.rolling(n).std(ddof=0)
    return m+k*sd, m, m-k*sd, sd

def macd(s, f=12, sl=26, sig=9):
    m = ema(s,f)-ema(s,sl); g = ema(m,sig)
    return m, g, m-g

def ichimoku_raw(df):
    h,l = df['High'], df['Low']
    conv = (h.rolling(9).max()+l.rolling(9).min())/2
    base = (h.rolling(26).max()+l.rolling(26).min())/2
    spanA_raw = (conv+base)/2
    spanB_raw = (h.rolling(52).max()+l.rolling(52).min())/2
    return conv, base, spanA_raw, spanB_raw

def cloud_at_today(spanA_raw, spanB_raw):
    # 현재 시점의 구름 = 26봉 전 raw값
    a = spanA_raw.shift(26); b = spanB_raw.shift(26)
    return a, b

# ══════════════════════════════════════════════════════════════════
# ★v47 개편: 19신호 가중치 실측 재산출 (KOSPI 45종 × 8년 × 84,362표본)
#   근거 : 20일 후 «지수 대비 초과수익». 절대수익으로 재면 상승장 편향이 들어간다.
#   규칙 : 초과수익 ≤ 0 이거나 t < 1.0 → 가중치 0(제외). 나머지는 (평균 초과 × min(t,6))에
#          비례해 총점 100으로 배분. ★골든크로스·망치형·쌍바닥은 예측력 미확인 → 0점.
#   만점이 302 → 100으로 바뀐다. signals19() 조건식 본문은 손대지 않는다(정의 바뀌면 백테스트 무효).
# ══════════════════════════════════════════════════════════════════
WEIGHTS = {
 "전고점임박":12.5, "RSI반등":11.1, "구름대강세돌파":10.6, "주도주모멘텀":10.3,
 "삼역호전":8.9,   "MACD호전":6.6,  "양운":6.3,          "전고점돌파":6.0,
 "밴드타기":5.9,   "전환기준선호전":5.7, "상승장악형":4.9, "거래량급증":3.0,
 "적삼병":3.0,     "하단밴드반등":2.1, "스퀴즈돌파":1.8,  "구름대돌파":1.2,
 "골든크로스":0.0, "망치형":0.0,    "쌍바닥":0.0}
SCORE_MAX = 100
ZERO_SIGS = ["골든크로스", "망치형", "쌍바닥"]   # 조건식은 유지, 점수만 미반영
# 점수 해석 구간 (표본외 실측 기준) — 본문 판정 문구에 이 밴드를 쓴다
SCORE_BANDS = [
 (45, 999, "강",   "표본외 20일 초과수익 +2.08% · 승률 53.0%"),
 (30, 45,  "양",   "표본외 +0.98% · 승률 47.2%"),
 (10, 30,  "중립", "표본외 +0.1% 내외 — 점수만으로 진입 근거가 되지 않는다"),
 (0,  10,  "약",   "표본외 -0.34% · 승률 44.1% — 점수가 낮으면 사지 않는다"),
]

def signals19(df, bench_ret20=0.0):
    c,h,l,o,v = df['Close'],df['High'],df['Low'],df['Open'],df['Volume']
    n = len(df)
    ub,mb,lb,sd = boll(c)
    r = rsi(c); a = atr(df)
    mline, msig, mhist = macd(c)
    conv, base, sA, sB = ichimoku_raw(df)
    ca, cb = cloud_at_today(sA, sB)
    ctop = pd.concat([ca,cb],axis=1).max(axis=1)
    cbot = pd.concat([ca,cb],axis=1).min(axis=1)
    ma10, ma20, ma60 = sma(c,10), sma(c,20), sma(c,60)
    i = n-1
    C = float(c.iloc[i])
    on = {}; det = {}
    hi60_prev = float(h.iloc[i-60:i].max()) if n>61 else float(h.max())
    hi60 = float(h.iloc[i-59:i+1].max())
    # 1 전고점임박
    ratio = C/hi60_prev
    on["전고점임박"] = (0.97 <= ratio < 1.0)
    det["전고점임박"] = f"전고 대비 {(ratio-1)*100:+.1f}%"
    # 2 전고점돌파
    on["전고점돌파"] = C > hi60_prev
    det["전고점돌파"] = f"60봉 전고 {hi60_prev:,.0f}"
    # 3 구름대돌파 (최근 5봉 내 구름 상단 상향 돌파)
    brk = False
    for k in range(max(1,i-4), i+1):
        if pd.notna(ctop.iloc[k]) and pd.notna(ctop.iloc[k-1]):
            if c.iloc[k] > ctop.iloc[k] and c.iloc[k-1] <= ctop.iloc[k-1]: brk = True
    on["구름대돌파"] = brk
    det["구름대돌파"] = "5봉내 구름상단 돌파" if brk else "돌파 없음"
    # 4 구름대강세돌파 : 구름 위 + 양운
    above = pd.notna(ctop.iloc[i]) and C > float(ctop.iloc[i])
    bull_cloud = pd.notna(ca.iloc[i]) and pd.notna(cb.iloc[i]) and float(ca.iloc[i])>float(cb.iloc[i])
    on["구름대강세돌파"] = bool(above and bull_cloud)
    det["구름대강세돌파"] = ("구름 위+양운" if (above and bull_cloud) else ("구름 위/음운" if above else "구름 아래·안"))
    # 5 삼역호전
    lag_ok = (i-26>=0) and (C > float(c.iloc[i-26]))
    cb_ok = pd.notna(conv.iloc[i]) and pd.notna(base.iloc[i]) and float(conv.iloc[i])>float(base.iloc[i])
    on["삼역호전"] = bool(above and cb_ok and lag_ok)
    det["삼역호전"] = f"구름{'○' if above else '×'}/전환>기준{'○' if cb_ok else '×'}/후행{'○' if lag_ok else '×'}"
    # 6 주도주모멘텀
    ret20 = C/float(c.iloc[i-20])-1 if i-20>=0 else 0
    on["주도주모멘텀"] = ret20 > bench_ret20
    det["주도주모멘텀"] = f"20일 {ret20*100:+.1f}% vs 지수 {bench_ret20*100:+.1f}%"
    # 7 스퀴즈돌파
    bw = ((ub-lb)/mb)
    bw_now = float(bw.iloc[i]) if pd.notna(bw.iloc[i]) else np.nan
    bw_hist = bw.iloc[max(0,i-119):i+1].dropna()
    sq = False
    if len(bw_hist)>30:
        q25 = float(bw_hist.quantile(0.25))
        was_sq = float(bw.iloc[max(0,i-10):i].min()) <= q25
        sq = was_sq and (C > float(mb.iloc[i])) and (bw_now > float(bw.iloc[i-1]))
    on["스퀴즈돌파"] = bool(sq)
    det["스퀴즈돌파"] = f"밴드폭 {bw_now*100:.1f}%"
    # 8 골든크로스
    gc = False
    for k in range(max(1,i-9), i+1):
        if pd.notna(ma20.iloc[k]) and pd.notna(ma60.iloc[k]) and pd.notna(ma20.iloc[k-1]):
            if ma20.iloc[k]>ma60.iloc[k] and ma20.iloc[k-1]<=ma60.iloc[k-1]: gc=True
    on["골든크로스"] = gc
    det["골든크로스"] = "10봉내 20>60 교차" if gc else ("20>60 유지" if (pd.notna(ma20.iloc[i]) and pd.notna(ma60.iloc[i]) and ma20.iloc[i]>ma60.iloc[i]) else "20<60")
    # 9 하단밴드반등
    hb = False
    for k in range(max(1,i-4), i+1):
        if pd.notna(lb.iloc[k]) and l.iloc[k] <= lb.iloc[k]: hb=True
    hb = hb and pd.notna(lb.iloc[i]) and C > float(lb.iloc[i])
    on["하단밴드반등"] = bool(hb)
    det["하단밴드반등"] = "5봉내 하단터치 후 회복" if hb else "하단터치 없음"
    # 10 RSI반등
    rl = r.iloc[max(0,i-9):i+1]
    on["RSI반등"] = bool(float(rl.min())<35 and float(r.iloc[i])>float(r.iloc[i-1]) and float(r.iloc[i])<60)
    det["RSI반등"] = f"RSI {float(r.iloc[i]):.0f}(10봉 최저 {float(rl.min()):.0f})"
    # 11 쌍바닥
    w = df.iloc[max(0,i-59):i+1]
    lows = w['Low'].values
    db = False
    if len(lows)>=40:
        h1 = lows[:len(lows)//2]; h2 = lows[len(lows)//2:]
        m1, m2 = h1.min(), h2.min()
        if m1>0 and abs(m2-m1)/m1 < 0.04 and C > m2*1.05: db=True
    on["쌍바닥"] = bool(db)
    det["쌍바닥"] = "쌍바닥 후 상승" if db else "패턴 없음"
    # 12 MACD호전
    mh_ok = pd.notna(mhist.iloc[i]) and float(mhist.iloc[i])>0 and float(mhist.iloc[i])>float(mhist.iloc[i-1])
    on["MACD호전"] = bool(mh_ok)
    det["MACD호전"] = f"히스토 {float(mhist.iloc[i]):+.2f}"
    # 13 적삼병
    up3 = all(float(c.iloc[i-k])>float(o.iloc[i-k]) for k in range(3)) and float(c.iloc[i])>float(c.iloc[i-1])>float(c.iloc[i-2])
    on["적삼병"] = bool(up3)
    det["적삼병"] = "3연속 양봉+고가경신" if up3 else "미충족"
    # 14 전환기준선호전
    cross = False
    for k in range(max(1,i-9), i+1):
        if pd.notna(conv.iloc[k]) and pd.notna(base.iloc[k]) and pd.notna(conv.iloc[k-1]):
            if conv.iloc[k]>base.iloc[k] and conv.iloc[k-1]<=base.iloc[k-1]: cross=True
    on["전환기준선호전"] = cross
    det["전환기준선호전"] = "10봉내 전환>기준 교차" if cross else ("전환>기준 유지" if cb_ok else "전환<기준")
    # 15 밴드타기
    pb_s = (c-lb)/(ub-lb)
    bt = all(pd.notna(pb_s.iloc[i-k]) and float(pb_s.iloc[i-k])>0.8 for k in range(2))
    on["밴드타기"] = bool(bt)
    det["밴드타기"] = f"%b {float(pb_s.iloc[i]):.2f}"
    # 16 거래량급증
    va = float(v.iloc[max(0,i-19):i+1].mean())
    vr = float(v.iloc[i])/va if va>0 else 0
    on["거래량급증"] = vr > 1.5
    det["거래량급증"] = f"평균 대비 {vr:.1f}배"
    # 17 상승장악형
    eng = (float(c.iloc[i-1])<float(o.iloc[i-1])) and (float(c.iloc[i])>float(o.iloc[i])) and (float(c.iloc[i])>=float(o.iloc[i-1])) and (float(o.iloc[i])<=float(c.iloc[i-1]))
    on["상승장악형"] = bool(eng)
    det["상승장악형"] = "전일 음봉 장악" if eng else "미충족"
    # 18 양운
    on["양운"] = bool(bull_cloud)
    det["양운"] = "양운" if bull_cloud else "음운"
    # 19 망치형
    body = abs(float(c.iloc[i])-float(o.iloc[i]))
    lower = min(float(c.iloc[i]),float(o.iloc[i])) - float(l.iloc[i])
    upper = float(h.iloc[i]) - max(float(c.iloc[i]),float(o.iloc[i]))
    ham = body>0 and lower >= body*2 and upper <= body*0.7
    on["망치형"] = bool(ham)
    det["망치형"] = "아래꼬리 긴 망치" if ham else "미충족"

    score = sum(WEIGHTS[k] for k,vv in on.items() if vv)
    return round(score, 1), on, det


# ══════════════════════════════════════════════════════════════════
# ★v47/v48 신설: 점수 밴드 + 이중 모델(추세/되돌림) 엔진
# ══════════════════════════════════════════════════════════════════
W_TREND = {"구름대강세돌파": 39.7, "삼역호전": 26.5, "RSI반등": 19.5, "MACD호전": 14.3}
W_REV   = {"RSI과매도": 47.8, "20일선하방이격": 43.7, "RSI과매도탈출": 8.5}
TREND_BANDS = [(66, 999, "강", "표본외 +4.14% · 승률 53.4%"),
               (26, 66, "양", "표본외 +2.35% · 승률 52.7%"),
               (0,  26, "약", "표본외 +0.45% · 승률 48.2%")]
REV_BANDS   = [(50, 999, "강", "표본외 +2.50% · 승률 51.8%"),
               (20, 50, "양", "표본외 +0.76% · 승률 47.5%"),
               (0.1, 20, "중립", "표본외 +0.38%"),
               (0, 0.1, "약", "표본외 -0.52% — 되돌림 조건 없음")]
TREND_WARN  = [(70, 999, "-1.33% · 승률 44.1%"), (40, 70, "-0.66%"), (0, 40, "-0.2% 내외")]
CHAR_TH = -0.02      # 성격 임계: 상관 < -0.02 → 회귀형 / 이상 → 추세형


def band_of(score, bands):
    for lo, hi, lab, note in bands:
        if lo <= score < hi:
            return lab, note
    return bands[-1][2], bands[-1][3]


def next_signals(on19, n=2):
    off = [k for k, vv in on19.items() if not vv and WEIGHTS.get(k, 0) > 0]
    return sorted(off, key=lambda k: -WEIGHTS[k])[:n]


def character(df, bench_close, fwd=20, look=20):
    if bench_close is None:
        return 0.0
    c = df["Close"].copy()
    c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    c = c[~c.index.duplicated(keep="last")]
    b = bench_close.copy()
    b.index = pd.to_datetime(b.index).tz_localize(None).normalize()
    b = b[~b.index.duplicated(keep="last")].reindex(c.index).ffill()
    past = c.pct_change(look)
    fwd_s = c.shift(-fwd) / c - 1
    fwd_b = b.shift(-fwd) / b - 1
    ex = fwd_s - fwd_b
    d = pd.concat([past.rename("p"), ex.rename("e")], axis=1).dropna()
    if len(d) < 60 or d["p"].std() == 0 or d["e"].std() == 0:
        return 0.0
    return float(np.corrcoef(d["p"].values, d["e"].values)[0, 1])


def rev_signals(df):
    c = df["Close"]
    r = rsi(c); ma20 = sma(c, 20)
    i = len(df) - 1
    R = float(r.iloc[i]) if pd.notna(r.iloc[i]) else 50.0
    Rp = float(r.iloc[i-1]) if pd.notna(r.iloc[i-1]) else R
    diverge = float(c.iloc[i] / ma20.iloc[i] - 1) if pd.notna(ma20.iloc[i]) else 0.0
    rl = r.iloc[max(0, i-5):i+1].dropna()
    rmin = float(rl.min()) if len(rl) else R
    on = {"RSI과매도": bool(R < 30),
          "20일선하방이격": bool(diverge < -0.07),
          "RSI과매도탈출": bool(rmin < 30 and R >= 30 and R > Rp)}
    det = {"RSI과매도": f"RSI {R:.0f}",
           "20일선하방이격": f"20일선 대비 {diverge*100:+.1f}%",
           "RSI과매도탈출": f"RSI {R:.0f}(5봉 최저 {rmin:.0f})"}
    return on, det


def dual_score(df, bench_close, on19, code=None):
    ch = character(df, bench_close)
    is_rev = ch < CHAR_TH
    trend_score = round(sum(W_TREND[k] for k in W_TREND if on19.get(k)), 1)
    rev_on, rev_det = rev_signals(df)
    rev_score = round(sum(W_REV[k] for k in W_REV if rev_on.get(k)), 1)
    if is_rev:
        model, used, band = "되돌림 모델", rev_score, band_of(rev_score, REV_BANDS)
    else:
        model, used, band = "추세 모델", trend_score, band_of(trend_score, TREND_BANDS)
    warn, is_warn = "", False
    if is_rev and trend_score >= 40:
        is_warn = True
        for lo, hi, txt in TREND_WARN:
            if lo <= trend_score < hi:
                warn = txt; break
    return {"model": model, "used": used, "band": band[0], "band_note": band[1],
            "char": round(ch, 3), "is_rev": bool(is_rev),
            "trend_score": trend_score, "rev_score": rev_score,
            "rev_on": {k: bool(v) for k, v in rev_on.items()}, "rev_det": rev_det,
            "trend_warn": warn, "is_warn": bool(is_warn)}


# ══════════════════════════════════════════════════════════════════
# ★v40 신설: 위험조정 성과 지표 (2-15B 코너 · 게이트 G12)
# ══════════════════════════════════════════════════════════════════
TD = 252   # 연환산 거래일

def ann_vol(r):
    return float(r.std(ddof=1) * np.sqrt(TD) * 100)

def ann_ret(r):
    if len(r) == 0: return 0.0
    return float((1 + r).prod() ** (TD / len(r)) - 1)

def beta_of(rp, rm):
    v = np.var(rm, ddof=1)
    return float(np.cov(rp, rm)[0, 1] / v) if v > 0 else 0.0

def sharpe(r, rf):
    s = r.std(ddof=1) * np.sqrt(TD)
    return float((ann_ret(r) - rf) / s) if s > 0 else 0.0

def sortino(r, rf):
    d = r[r < 0].std(ddof=1) * np.sqrt(TD)
    return float((ann_ret(r) - rf) / d) if d and d > 0 else 0.0

def mdd(level):
    return float((level / level.cummax() - 1).min() * 100)

def track_err(rp, rm):
    return float((rp - rm).std(ddof=1) * np.sqrt(TD) * 100)

def jensen_alpha(rp, rm, rf):
    b = beta_of(rp, rm)
    return float((ann_ret(rp) - (rf + b * (ann_ret(rm) - rf))) * 100)

def risk_contrib(vals, win=120):
    rr = vals.pct_change().dropna().tail(win)
    w = (vals.iloc[-1] / vals.iloc[-1].sum()).values
    cov = (rr.cov() * TD).values
    pv = float(np.sqrt(w @ cov @ w))
    if pv <= 0: return {}, 0.0
    mc = (cov @ w) * w / pv
    return {n: float(mc[i] / pv * 100) for i, n in enumerate(vals.columns)}, pv * 100

def vol_without(vals, drop, win=120):
    rr = vals.pct_change().dropna().tail(win)
    keep = [c for c in vals.columns if c != drop]
    if not keep: return 0.0
    w = (vals.iloc[-1][keep] / vals.iloc[-1][keep].sum()).values
    cov = (rr[keep].cov() * TD).values
    return float(np.sqrt(w @ cov @ w) * 100)

def roll_vol(r, win=60):
    return r.rolling(win).std(ddof=1) * np.sqrt(TD) * 100

def vol_beta_scenario(vals, rm, weights, win=120):
    rr = vals.pct_change().dropna().tail(win)
    cols = list(vals.columns)
    w = np.array([weights.get(c, 0.0) for c in cols])
    cov = (rr[cols].cov() * TD).values
    vol = float(np.sqrt(w @ cov @ w) * 100)
    m = rm.reindex(rr.index).fillna(0)
    port_r = (rr[cols] * w).sum(axis=1)
    return vol, beta_of(port_r, m)


# ════════════════════════════════════════════════════════════════════
# ★v42 신설: 손절 3단 엔진 + 차트 레벨 산출 (build.py·mkchart.py 공용)
# ════════════════════════════════════════════════════════════════════
def k_of(atr_pct, table):
    for lim, k in table:
        if atr_pct <= lim:
            return k
    return table[-1][1]

def stop_tiers(x, avg=None, cap=0.15, k_table=((4,3.0),(7,2.5),(10,2.0),(999,1.5)),
               frac=(0.50, 0.78, 1.00), qty_split=(1/3, 1/3, 1/3), snap_band=0.12):
    c, a, ap = x["close"], x["atr"], x["atr_pct"]
    k = k_of(ap, k_table)
    anchor = (max(avg, x["hi22"]) if (avg and c > avg) else (avg if avg else c))
    def _s3(anc): return anc - min(k * a, cap * anc)
    capped = (cap * anchor) <= (k * a)
    if _s3(anchor) >= c * 0.995:
        anchor = c
        capped = (cap * anchor) <= (k * a)
    s3 = _s3(anchor)
    D = c - s3
    cands = {"볼린저 하단": x.get("bb_low"), "일목 전환선": x.get("conv"),
             "일목 기준선": x.get("base"), "20일선": x.get("ma20"),
             "일목 구름 하단": x.get("cloud_bot")}
    cands = {n: v for n, v in cands.items() if v}
    def _snap(raw, lo, hi):
        best = None
        for n, v in cands.items():
            if lo <= v <= hi and (best is None or abs(v - raw) < abs(best[1] - raw)):
                best = (n, v)
        return best
    r1, r2 = c - frac[0] * D, c - frac[1] * D
    b1 = _snap(r1, c - (frac[0] + snap_band) * D, c - (frac[0] - snap_band) * D)
    n1, s1 = b1 if b1 else ("비율선(50%)", r1)
    b2 = _snap(r2, c - (frac[1] + snap_band) * D, min(c - (frac[1] - snap_band) * D, s1 - 1e-9))
    n2, s2 = b2 if b2 else ("비율선(78%)", r2)
    tiers = [("1차 경계선", n1, s1, qty_split[0]),
             ("2차 방어선", n2, s2, qty_split[1]),
             ("3차 최종선", ("변동성 상한(캡)" if capped else f"{k:g}×ATR"), s3, qty_split[2])]
    return {"anchor": anchor, "k": k, "cap": cap, "capped": capped, "D": D,
            "stop": s3, "s1": s1, "s2": s2, "s3": s3, "tiers": tiers,
            "mode": ("고점 앵커(트레일링)" if (avg and c > avg and anchor != c)
                     else ("평단 앵커(손실 한도)" if (avg and c <= avg and anchor == avg) else "현재가 앵커(즉시손절 방지)")),
            "s_pct": (s3 / c - 1) * 100}

def chart_levels(x, close=None):
    c = close if close is not None else x["close"]
    src = [("20일선", x.get("ma20")), ("60일선", x.get("ma60")),
           ("일목 구름 상단", x.get("cloud_top")), ("일목 구름 하단", x.get("cloud_bot")),
           ("볼린저 하단", x.get("bb_low")), ("22봉 고점", x.get("hi22"))]
    src = [(n, v) for n, v in src if v]
    up = sorted([t for t in src if t[1] > c], key=lambda t: t[1])
    dn = sorted([t for t in src if t[1] <= c], key=lambda t: -t[1])
    return [(f"저항{i+1}", n, v) for i, (n, v) in enumerate(up)] + \
           [(f"지지{i+1}", n, v) for i, (n, v) in enumerate(dn)]


# ══════════════════════════════════════════════════════════════════
# ★v49 신설: 강화 카드 «선정» 규격
# ══════════════════════════════════════════════════════════════════
TREND_EDGE = {"강": 4.14, "양": 2.35, "약": 0.45}
REV_EDGE   = {"강": 2.50, "양": 0.76, "중립": 0.38, "약": -0.52}
WARN_EDGE  = [(70, 999, -1.33), (40, 70, -0.66), (0, 40, -0.20)]


def expected_edge(dual):
    if not dual:
        return 0.0
    if dual.get("is_warn"):
        ts = dual.get("trend_score", 0)
        for lo, hi, e in WARN_EDGE:
            if lo <= ts < hi:
                return e
        return -1.33
    tbl = REV_EDGE if dual.get("is_rev") else TREND_EDGE
    return float(tbl.get(dual.get("band"), 0.0))


def pick_metrics(df):
    c = df["Close"]
    m120 = sma(c, 120)
    cur = float(c.iloc[-1])
    a120 = float(m120.iloc[-1]) if pd.notna(m120.iloc[-1]) else cur
    try:
        sl120 = (a120 / float(m120.iloc[-21]) - 1) * 100
    except Exception:
        sl120 = 0.0
    tv = df["Volume"] * c
    t20 = float(tv.iloc[-20:].mean())
    t60 = float(tv.iloc[-60:].mean())
    return {"cur": cur, "ma120": a120, "vs120": (cur / a120 - 1) * 100, "sl120": sl120,
            "turn20": t20, "turn60": t60, "turn_ratio": (t20 / t60 if t60 else 0.0)}


ENH_MIN_EDGE   = 0.50
ENH_MIN_TURN_KR = 1e10
ENH_MIN_TURN_US = 1e8
ENH_LONGTREND   = True


def enh_gate(dual, m, market="KR", min_edge=None, longtrend=None,
             turn_kr=None, turn_us=None):
    min_edge = ENH_MIN_EDGE if min_edge is None else min_edge
    longtrend = ENH_LONGTREND if longtrend is None else longtrend
    tk_ = (ENH_MIN_TURN_KR if turn_kr is None else turn_kr) if market == "KR" \
          else (ENH_MIN_TURN_US if turn_us is None else turn_us)
    f = []
    if not dual:
        return ["이중모델 미산출"]
    if dual.get("is_warn"):
        f.append(f"역방향 경고(회귀형+추세점수 {dual.get('trend_score')})")
    e = expected_edge(dual)
    if e < min_edge:
        f.append(f"기대수익 {e:+.2f}% < 하한 {min_edge:+.2f}%")
    if m["turn20"] < tk_:
        f.append("유동성 미달")
    if longtrend and (m["cur"] < m["ma120"]) and (m["sl120"] <= 0):
        f.append("장기 추세 이탈(120일선 아래·하락)")
    return f
