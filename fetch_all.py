# -*- coding: utf-8 -*-
"""
fetch_all.py — 실측 수집 1회 실행으로 data.json 생성.
"""
import yfinance as yf, pandas as pd, numpy as np, json, io, subprocess, warnings
warnings.filterwarnings("ignore")
from lib_ind import *
from lib_ind import expected_edge, enh_gate, pick_metrics
import lib_ind as L_
import pick_engine as PE
import config as C

import sys as _sys, time as _time
ASOF_PIN = _sys.argv[1] if len(_sys.argv) > 1 else None
if ASOF_PIN:                     # ★v57 어댑터에 기준일 전달 — 비KR(간밤 US)을 D 미만으로 자동 절단
    import os as _os; _os.environ["YF_ASOF"] = ASOF_PIN

import lib_idx
FIXLOG = []

def _intraday_daily(t):
    for iv in ("5m", "1h"):
        try:
            x = yf.Ticker(t).history(period="7d", interval=iv, auto_adjust=False)
            if x is None or len(x) == 0:
                continue
            x = x.dropna(subset=["Close"])
            g = x.groupby(x.index.normalize())
            return pd.DataFrame({"Open": g["Open"].first(), "High": g["High"].max(),
                                 "Low": g["Low"].min(), "Close": g["Close"].last(),
                                 "Volume": g["Volume"].sum()})
        except Exception:
            continue
    return None

def _fill_lagging_session(t, d):
    try:
        agg = _intraday_daily(t)
        if agg is None or len(agg) == 0:
            return d
        last = d.index[-1].normalize()
        today = pd.Timestamp.now(tz=d.index.tz).normalize()
        add = agg[(agg.index > last) & (agg.index < today)]
        if len(add) == 0:
            return d
        for ts, r in add.iterrows():
            for col in d.columns:
                if col in ("Open", "High", "Low", "Close"):
                    d.loc[ts, col] = float(r[col])
                elif col == "Adj Close":
                    d.loc[ts, col] = float(r["Close"])
                elif col == "Volume":
                    d.loc[ts, col] = float(r["Volume"])
                else:
                    d.loc[ts, col] = 0.0
        d = d.sort_index()
        FIXLOG.append({"item": f"{t} 일봉 지연", "kind": "보정(동일 제공자 인트라데이)",
            "detail": f"<b>시도</b>: yfinance 일봉 {t} — 최종 유효 {last.strftime('%Y-%m-%d')}로 "
                      f"직전 확정 거래일 누락(개별 종목 일봉은 정상 → 지수 피드 지연). "
                      f"<b>반환</b>: 같은 yfinance 인트라데이(5분봉) 종료 세션 집계로 "
                      f"{', '.join(x.strftime('%m/%d') for x in add.index)} 봉 복원 "
                      f"(종가 {float(add['Close'].iloc[-1]):,.2f}). "
                      f"<b>대체</b>: 외부 사이트 값 이식 아님 — 동일 제공자 실측 재집계."})
        return d
    except Exception:
        return d

PREFETCH = {}

def prefetch(tickers, per="2y", chunk=50):
    tickers = [t for t in dict.fromkeys(tickers) if t not in PREFETCH]
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i+chunk]
        try:
            bulk = yf.download(part, period=per, group_by="ticker", threads=True,
                               auto_adjust=False, progress=False)
        except Exception:
            continue
        for t in part:
            try:
                d = bulk[t] if len(part) > 1 else bulk
                d = d.dropna(subset=["Close"])
                if len(d) > 120:
                    PREFETCH[t] = d
            except Exception:
                pass


def hist(t, per="2y", _tries=3):
    d = None
    _best = None
    for i in range(_tries):
        try:
            d = yf.Ticker(t).history(period=per, auto_adjust=False)
            if d is not None and len(d) > 0:
                if _best is None or len(d) > len(_best):
                    _best = d
                if per not in ("2y", "1y") or len(d) >= 100:
                    break
        except Exception:
            d = None
        _time.sleep(1.2 * (i + 1))
    d = _best if (_best is not None and (d is None or len(_best) > len(d))) else d
    if d is None or len(d) == 0:
        raise RuntimeError(f"[hist] {t} 빈 응답 — {_tries}회 재시도 실패(§8 기록 후 상위에서 대체 처리)")
    d = d[~d.index.duplicated()].dropna(subset=["Close"])
    d = _fill_lagging_session(t, d)
    d = lib_idx.reconcile(t, d, FIXLOG, ASOF_PIN)
    if ASOF_PIN:
        idx = pd.to_datetime(d.index).tz_localize(None).normalize()
        d = d[idx <= pd.Timestamp(ASOF_PIN)]
    return d

def ret(c, n):
    return float(c.iloc[-1]/c.iloc[-1-n] - 1) if len(c) > n else 0.0

OUT = {"log8": []}
if ASOF_PIN:
    OUT["log8"].append({"item": "기준일 고정(as-of)", "kind": "정상",
        "detail": f"<b>시도</b>: 모든 시계열을 <b>{ASOF_PIN}</b> 이하로 절단해 회차를 재현. "
                  f"<b>반환</b>: 정상. <b>대체</b>: 불필요 — 지난 회차 동일 조건 재현·검증용(v40 신설)."})

MACRO_PROXY = {"KOSPI200": "069500.KS"}

def hist_nocut(t, per="2y", _tries=3):
    _p = ASOF_PIN
    globals()["ASOF_PIN"] = None
    try:
        return hist(t, per, _tries)
    finally:
        globals()["ASOF_PIN"] = _p

def _rebuild_from_proxy(k, t, d, stale=False):
    p = MACRO_PROXY.get(k)
    if not p:
        agg = _intraday_daily(t)
        if agg is not None and len(agg) >= 2:
            anchor = float(d["Close"].iloc[-1])
            agg = agg[agg.index.normalize() <= d.index[-1].normalize()]
            agg.loc[agg.index[-1], "Close"] = anchor
            FIXLOG.append({"item": f"{t} 일봉 이력 결손", "kind": "보정(동일 제공자 인트라데이 복원)",
                "detail": f"<b>시도</b>: yfinance {t} 일봉 요청 → 1행만 반환(이력 결손, 3회 재현). "
                          f"<b>반환</b>: 최신 실측 종가 {anchor:,.2f}는 유효. "
                          f"<b>대체</b>: 같은 yfinance 인트라데이(5분봉)에서 종료 세션 {len(agg)}개를 "
                          f"일봉으로 재집계해 직전 대비 등락률만 복원. "
                          f"20일선·52주 고점은 표본 부족 → 해당 칸 참고용."})
            return agg
        return d
    raw = hist_nocut(t, "2y")
    e_raw = hist_nocut(p, "2y")
    e = e_raw["Close"]
    ri, ei = raw.index.normalize(), e.index.normalize()
    common = [x for x in ri if (ei == x).any()]
    if not common:
        return d
    anchor_d = max(common)
    scale = float(raw["Close"][ri == anchor_d].iloc[0]) / float(e[ei == anchor_d].iloc[0])
    s = (e * scale).to_frame("Close")
    for col in ("Open", "High", "Low"):
        s[col] = s["Close"]
    s["Volume"] = 0.0
    if ASOF_PIN:
        _i = pd.to_datetime(s.index).tz_localize(None).normalize()
        s = s[_i <= pd.Timestamp(ASOF_PIN)]
    FIXLOG.append({"item": f"{t} 일봉 {'지연' if stale else '이력 결손'}", "kind": "보정(추종 ETF 스케일 복원)",
        "detail": f"<b>시도</b>: yfinance {t} 일봉 요청(6mo·2y·3회 재시도). <b>반환</b>: "
                  f"요청마다 <b>1행짜리 응답</b>과 <b>{anchor_d.strftime('%Y-%m-%d')}까지의 절단본</b>이 번갈아 반환되는 "
                  f"불안정 상태 — 이 티커만의 재현되는 결함이다. "
                  f"<b>대체</b>: 추종 ETF <b>KODEX200({p})</b> 실측 시계열에 "
                  f"공통 최종일 {anchor_d.strftime('%Y-%m-%d')} 기준 계수 {scale:.6f}를 곱해 전 구간 복원 "
                  f"(v37 「KODEX200 롤포워드」 규격의 확장). ETF 추적오차가 섞이므로 20일선·52주 고점은 참고용이며, "
                  f"등락률·야간선물 베이시스 판정에는 영향이 없다."})
    return s

mac = {}
for k, t in C.MACRO.items():
    try:
        d = hist(t, "6mo")
        if len(d) < 2:
            try:
                d2 = hist(t, "2y")
                if len(d2) >= 2:
                    d = d2.iloc[-130:]
            except Exception:
                pass
        if k in MACRO_PROXY and "코스피" in mac:
            _stale = (len(d) < 2) or (d.index[-1].strftime("%Y-%m-%d") < mac["코스피"]["date"])
            if _stale:
                d = _rebuild_from_proxy(k, t, d, stale=(len(d) >= 2))
        elif len(d) < 2:
            d = _rebuild_from_proxy(k, t, d)
        c = d["Close"]
        if len(d) < 2: raise ValueError("empty")
        mac[k] = {"ticker": t, "date": d.index[-1].strftime("%Y-%m-%d"),
                  "close": float(c.iloc[-1]), "prev": float(c.iloc[-2]),
                  "chg_pct": float(c.iloc[-1]/c.iloc[-2]-1)*100,
                  "ma20": float(c.rolling(20, min_periods=1).mean().iloc[-1]),
                  "hi252": float(d["High"].max())}
    except Exception as e:
        mac[k] = {"err": str(e)}
        OUT["log8"].append({"item": k, "kind": "실패", "detail": f"yfinance {t} → {e}"})
mac = lib_idx.macro_fix(mac, FIXLOG)
OUT["macro"] = mac

try:
    ks_date = mac["코스피"]["date"]
    if mac["KOSPI200"]["date"] != ks_date:
        last200 = mac["KOSPI200"]["date"]
        etf = hist("069500.KS", "6mo")["Close"]
        e_at = float(etf.loc[etf.index.strftime("%Y-%m-%d") == last200].iloc[0])
        e_now = float(etf.iloc[-1])
        est = mac["KOSPI200"]["close"] * (e_now / e_at)
        mac["KOSPI200"]["estimated"] = est
        mac["KOSPI200"]["stale_date"] = last200
        mac["KOSPI200"]["method"] = "KODEX200 롤포워드"
        OUT["log8"].append({"item": "^KS200", "kind": "보정(실측 ETF)",
            "detail": f"yfinance 최종 유효값 {last200}({mac['KOSPI200']['close']:,.2f}) — 갱신 지연. "
                      f"KODEX200(069500.KS) {e_at:,.0f}→{e_now:,.0f} 등락으로 롤포워드 → {est:,.2f}. "
                      f"추정이 아니라 ETF 실측 기반 보정."})
    else:
        mac["KOSPI200"]["estimated"] = mac["KOSPI200"]["close"]
except Exception as e:
    OUT["log8"].append({"item": "^KS200", "kind": "실패", "detail": str(e)})

try:
    if mac["VIX3M"]["date"] != mac["VIX"]["date"]:
        OUT["log8"].append({"item": "^VIX3M", "kind": "지연값",
            "detail": f"최종 유효값 {mac['VIX3M']['date']} ({mac['VIX3M']['close']:.2f}) — 최근 행 NaN(알려진 현상). "
                      f"기간구조 비율에 '지연' 꼬리표 병기"})
except Exception:
    pass

fred = {}
for name, fid in C.FRED.items():
    try:
        r = subprocess.run(["curl", "-sL", "--max-time", "60",
                            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fid}"],
                           capture_output=True, text=True)
        df = pd.read_csv(io.StringIO(r.stdout)); df.columns = ["date", "val"]
        df["val"] = pd.to_numeric(df["val"], errors="coerce"); df = df.dropna()
        fred[name] = {"id": fid, "date": str(df["date"].iloc[-1]),
                      "val": float(df["val"].iloc[-1]), "prev": float(df["val"].iloc[-2]),
                      "m1": float(df["val"].iloc[-22]) if len(df) > 22 else None}
    except Exception as e:
        fred[name] = {"err": str(e)}
        OUT["log8"].append({"item": f"FRED {fid}", "kind": "실패", "detail": str(e)})
OUT["fred"] = fred

ks  = hist("^KS11"); spx = hist("^GSPC")
ks_r20, spx_r20 = ret(ks["Close"], 20), ret(spx["Close"], 20)

def analyze(name, tk, bench20, bench_close=None):
    d = hist(tk)
    if len(d) < 130: return None
    c, h, l, o, v = d["Close"], d["High"], d["Low"], d["Open"], d["Volume"]
    sc, on, det = signals19(d, bench20)
    dual = dual_score(d, bench_close, on) if bench_close is not None else None
    _pm = pick_metrics(d)
    _mk = "KR" if tk.endswith(".KS") else "US"
    _edge = expected_edge(dual)
    _pgate = enh_gate(dual, _pm, market=_mk)
    ub, mb, lb, _ = boll(c); r = rsi(c); a = atr(d)
    ml, ms, mh = macd(c); conv, base, sA, sB = ichimoku_raw(d)
    ca, cb = cloud_at_today(sA, sB)
    C_ = float(c.iloc[-1]); A = float(a.iloc[-1])
    hi22 = float(h.iloc[-22:].max()); hi60 = float(h.iloc[-60:].max()); hi252 = float(h.iloc[-252:].max())
    wk = c.resample("W").last().dropna()
    va20 = float(v.iloc[-20:].mean())
    try:
        _stp = stop_tiers({"close": C_, "atr": A, "atr_pct": A / C_ * 100,
                           "hi22": hi22, "bb_low": float(lb.iloc[-1]),
                           "conv": float(conv.iloc[-1]), "base": float(base.iloc[-1]),
                           "ma20": float(sma(c, 20).iloc[-1]), "cloud_bot": cb})
        _stop_px = float(min(v for _, _, v in _stp["tiers"]))
    except Exception:
        _stop_px = float(lb.iloc[-1])
    _tgt_px = float(hi252) if C_ < hi252 else float(C_ * (1 + 2 * A / C_))

    w = d.iloc[-60:]; ph = float(w["Close"].iloc[:30].max()); pr = float(r.iloc[-60:-30].max())
    return {
      "name": name, "ticker": tk, "date": d.index[-1].strftime("%Y-%m-%d"),
      "close": C_, "prev": float(c.iloc[-2]), "chg": float(C_/c.iloc[-2]-1)*100,
      "score": sc, "nsig": sum(1 for x in on.values() if x), "on": on, "det": det,
      "dual": dual, "edge": round(_edge, 2), "pick_gate": _pgate,
      "tgt_px": _tgt_px, "stop_px": _stop_px,
      "vs_ma120": round(_pm["vs120"], 1), "sl120": round(_pm["sl120"], 2),
      "turnover": _pm["turn20"], "turn_ratio": round(_pm["turn_ratio"], 2),
      "ma10": float(sma(c,10).iloc[-1]), "ma20": float(sma(c,20).iloc[-1]), "ma60": float(sma(c,60).iloc[-1]),
      "ema9": float(ema(c,9).iloc[-1]),
      "bb_up": float(ub.iloc[-1]), "bb_mid": float(mb.iloc[-1]), "bb_low": float(lb.iloc[-1]),
      "pb": float((C_-lb.iloc[-1])/(ub.iloc[-1]-lb.iloc[-1])),
      "rsi": float(r.iloc[-1]), "rsi_prev": float(r.iloc[-2]), "rsi_w": float(rsi(wk).iloc[-1]),
      "rsi_div": bool(C_ >= ph*0.99 and float(r.iloc[-1]) < pr - 3),
      "atr": A, "atr_pct": A/C_*100,
      "macd": float(ml.iloc[-1]), "macd_sig": float(ms.iloc[-1]),
      "macd_hist": float(mh.iloc[-1]), "macd_hist_prev": float(mh.iloc[-2]),
      "conv": float(conv.iloc[-1]), "base": float(base.iloc[-1]),
      "cloud_top": float(max(ca.iloc[-1], cb.iloc[-1])), "cloud_bot": float(min(ca.iloc[-1], cb.iloc[-1])),
      "bull_cloud": bool(ca.iloc[-1] > cb.iloc[-1]),
      "hi22": hi22, "hi60": hi60, "hi252": hi252,
      "gap_hi60": (C_/hi60-1)*100, "gap_hi252": (C_/hi252-1)*100,
      "vol": float(v.iloc[-1]), "vol_avg20": va20, "vol_ratio": float(v.iloc[-1])/va20 if va20 else 0,
      "ret5": ret(c,5), "ret20": ret(c,20), "ret60": ret(c,60),
      "vs_ma20": (C_/float(sma(c,20).iloc[-1])-1)*100,
      "vs_ma60": (C_/float(sma(c,60).iloc[-1])-1)*100,
    }

OUT["kr"], OUT["us"] = {}, {}
import universe as _UNI
UKR, UUS, ULOG, USRC = _UNI.load(n_kr=getattr(C, "UNIVERSE_N_KR", 150),
                                 n_us=getattr(C, "UNIVERSE_N_US", 150))
UMETA = _UNI.load_meta(list(UKR.values()) + list(UUS.values()), ULOG)
print(f"■ 유니버스[{USRC}] KR {len(UKR)}종 · US {len(UUS)}종")
for _l in ULOG:
    print("   ·", _l)
prefetch(list(UKR.values()) + list(UUS.values()))
print(f"■ 배치 프리페치 {len(PREFETCH)}종")
if USRC == "legacy":
    OUT["log8"].append({"item": "유니버스 폴백(legacy)", "kind": "경고",
        "detail": "<b>시도</b>: 시총 상위 150+150 조회. <b>반환</b>: 실패. "
                  "<b>대체</b>: 레거시 13+13종. <b class='warn'>이 회차 강화 선정은 신뢰도가 낮다.</b>"})

for n, t in UKR.items():
    x = analyze(n, t, ks_r20, ks["Close"])
    if x: OUT["kr"][n] = x
for n, t in UUS.items():
    x = analyze(n, t, spx_r20, spx["Close"])
    if x: OUT["us"][n] = x

OUT["holdings"] = {}
for _n, _p in getattr(C, "POSITIONS", {}).items():
    if _p.get("ccy") == "$" and _n not in OUT["us"]:
        _x = analyze(_n, _p.get("ticker", _n), spx_r20, spx["Close"])
        if _x: OUT["holdings"][_n] = _x
        else: OUT["log8"].append({"item": f"보유종목 {_n}", "kind": "실패", "detail": f"yfinance {_p.get('ticker')} 데이터 부족"})

c = ks["Close"]; ub, mb, lb, _ = boll(c); conv, base, sA, sB = ichimoku_raw(ks)
ca, cb = cloud_at_today(sA, sB); K = float(c.iloc[-1])
OUT["kospi"] = {
  "close": K, "chg": float(K/c.iloc[-2]-1)*100,
  "ma10": float(sma(c,10).iloc[-1]), "ma20": float(sma(c,20).iloc[-1]), "ma60": float(sma(c,60).iloc[-1]),
  "bb_up": float(ub.iloc[-1]), "bb_mid": float(mb.iloc[-1]), "bb_low": float(lb.iloc[-1]),
  "pb": float((K-lb.iloc[-1])/(ub.iloc[-1]-lb.iloc[-1])), "rsi": float(rsi(c).iloc[-1]),
  "conv": float(conv.iloc[-1]), "base": float(base.iloc[-1]),
  "ctop": float(max(ca.iloc[-1], cb.iloc[-1])), "cbot": float(min(ca.iloc[-1], cb.iloc[-1])),
  "hi60": float(ks["High"].iloc[-60:].max()), "hi252": float(ks["High"].iloc[-252:].max()),
  "lo22": float(ks["Low"].iloc[-22:].min()),
  "ret5": ret(c,5)*100, "ret20": ret(c,20)*100,
  "recent": [{"d": ks.index[i].strftime("%m/%d"), "c": float(c.iloc[i]),
              "p": float(c.iloc[i]/c.iloc[i-1]-1)*100} for i in range(-10, 0)],
}

ks_w, ks_m = ret(c,5)*100, ret(c,20)*100
sec = {}
for s, mem in C.SECTORS.items():
    ws, ms = [], []
    for nm, tk in mem:
        try:
            d = hist(tk, "6mo")["Close"]
            if len(d) > 25: ws.append(ret(d,5)*100); ms.append(ret(d,20)*100)
        except Exception: pass
    if ws:
        w, m = float(np.mean(ws)), float(np.mean(ms))
        sec[s] = {"rep": ", ".join(x[0] for x in mem), "w": w, "m": m,
                  "rs_w": w-ks_w, "rs_m": m-ks_m}
OUT["sector"] = {"ks_w": ks_w, "ks_m": ks_m, "data": sec}

_T2G = {tk: nm for nm, tks in getattr(C, "THEMES", {}).items() for tk in tks}
for _pool in (OUT["kr"], OUT["us"]):
    byg = {}
    for k, x in _pool.items():
        mt = UMETA.get(x["ticker"], {})
        x["sector"] = mt.get("sector", "기타")
        x["industry"] = mt.get("industry", "기타")
        x["mcap"] = mt.get("cap", 0.0)
        x["group"] = _T2G.get(x["ticker"]) or x["industry"]
        byg.setdefault(x["group"], []).append(k)
    for g, mem in byg.items():
        if g == "기타" or len(mem) < 3:
            for k in mem:
                _pool[k]["leader"] = ""
            continue
        rc = sorted(mem, key=lambda k: -_pool[k]["mcap"])
        re_ = sorted(mem, key=lambda k: -(_pool[k].get("edge") or 0))
        for k in mem:
            ic, ir = rc.index(k) + 1, re_.index(k) + 1
            _pool[k]["leader"] = (f"{g} 대장주(시총{ic}위·기대수익{ir}위)"
                                  if (ic <= 3 and ir <= 3) else "")
            _pool[k]["group_n"] = len(mem)


def _cands(pool):
    out = []
    for nm, x in pool.items():
        d = PREFETCH.get(x["ticker"])
        if d is None:
            try:
                d = hist(x["ticker"])
            except Exception:
                continue
        if d is None or len(d) < 130:
            continue
        out.append({"name": nm, "df": d, "tgt": x.get("tgt_px"),
                    "stop": x.get("stop_px"), "dday": None})
    return out


PICK = {}
for _mk, _pool, _bench in (("kr", OUT["kr"], ks["Close"]), ("us", OUT["us"], spx["Close"])):
    try:
        PICK[_mk] = PE.pick_rank(_cands(_pool), _bench, market=_mk.upper())
    except Exception as _e:
        PICK[_mk] = {"picks": [], "excluded": [], "regime": None, "err": str(_e)}
        OUT["log8"].append({"item": f"선정 엔진({_mk})", "kind": "실패", "detail": str(_e)})
    for _r in PICK[_mk].get("picks", []) + PICK[_mk].get("excluded", []):
        _x = _pool.get(_r["name"])
        if _x is None:
            continue
        _x["pick"] = {k: _r[k] for k in ("rank_score", "excluded", "exclude_why", "why",
                                         "score", "valid", "trade", "behav", "vol", "size_cap")}
OUT["pick"] = {mk: {"picks": [{k: r[k] for k in ("name", "rank_score", "excluded",
                                                 "exclude_why", "why", "score", "valid",
                                                 "trade", "behav", "vol", "size_cap")}
                              for r in v.get("picks", [])],
                    "excluded": [{k: r[k] for k in ("name", "rank_score", "excluded",
                                                    "exclude_why", "why", "score", "valid",
                                                    "trade", "behav", "vol", "size_cap")}
                                 for r in v.get("excluded", [])],
                    "regime": v.get("regime")}
               for mk, v in PICK.items()}
OUT["regime"] = PICK.get("kr", {}).get("regime")


def pick(pool, exclude, secmap, n=3):
    mk = "kr" if pool is OUT["kr"] else "us"
    order = [r["name"] for r in PICK.get(mk, {}).get("picks", [])]
    ok = [k for k in order if k in pool and k not in exclude]
    return ok[:n]
kr_secmap = {}
for s, mem in C.SECTORS.items():
    for nm, _ in mem:
        if s in sec: kr_secmap[nm] = sec[s]["rs_w"]
OUT["enhance_kr"] = pick(OUT["kr"], C.EXCLUDE_KR, kr_secmap, n=getattr(C,"ENHANCE_N",3))
OUT["enhance_us"] = pick(OUT["us"], C.EXCLUDE_US, {}, n=getattr(C,"ENHANCE_N",3))

OUT["watchlist_rev"] = {
  mk: sorted([{"name": k, "edge": x.get("edge"),
               "rev_score": (x.get("dual") or {}).get("rev_score"),
               "trend_score": (x.get("dual") or {}).get("trend_score"),
               "score19": x.get("score"), "band": (x.get("dual") or {}).get("band"),
               "band_note": (x.get("dual") or {}).get("band_note"),
               "char": (x.get("dual") or {}).get("char"),
               "rev_on": [s for s, v in ((x.get("dual") or {}).get("rev_on") or {}).items() if v],
               "leader": x.get("leader", ""), "gate": x.get("pick_gate", [])}
              for k, x in pool.items()
              if (x.get("dual") or {}).get("is_rev")
                 and (x.get("edge") or 0) >= getattr(L_, "ENH_MIN_EDGE", 0.5)
                 and not (x.get("dual") or {}).get("is_warn")
                 and "유동성 미달" not in (x.get("pick_gate") or [])],
             key=lambda d: -(d["edge"] or 0))[:6]
  for mk, pool in (("kr", OUT["kr"]), ("us", OUT["us"]))}

try:
    _fx = mac["원/달러"]["close"]
    _hr, _hw = {}, {}
    for _n, _p in C.POSITIONS.items():
        _x = OUT["kr"].get(_n) or OUT["us"].get(_n) or OUT["holdings"].get(_n)
        _s = hist(_x["ticker"], "1y")["Close"]
        _s.index = pd.to_datetime(_s.index).tz_localize(None).normalize()
        _hr[_n] = _s
        _hw[_n] = _x["close"] * _p["qty"] * (_fx if _p.get("ccy") == "$" else 1)
    _hdf = pd.DataFrame(_hr).dropna().pct_change().dropna().tail(120)
    _tot = sum(_hw.values())
    _pr = sum(_hdf[k] * (_hw[k] / _tot) for k in _hw)
    _base = float(_pr.std() * np.sqrt(252) * 100)
    EM = {"port_vol": round(_base, 1), "win": int(len(_pr)), "items": {}}
    for _n in OUT["enhance_kr"] + OUT["enhance_us"]:
        _x = OUT["kr"].get(_n) or OUT["us"].get(_n)
        _s = hist(_x["ticker"], "1y")["Close"]
        _s.index = pd.to_datetime(_s.index).tz_localize(None).normalize()
        _j = pd.concat([_pr.rename("p"), _s.pct_change().rename("s")], axis=1).dropna().tail(120)
        _c = float(np.corrcoef(_j["p"], _j["s"])[0, 1])
        _new = float((_j["p"] * 0.9 + _j["s"] * 0.1).std() * np.sqrt(252) * 100)
        EM["items"][_n] = {"corr": round(_c, 2),
                           "vol": round(float(_j["s"].std() * np.sqrt(252) * 100), 1),
                           "port_after": round(_new, 1), "delta": round(_new - _base, 1)}
    OUT["enhance_meta"] = EM
except Exception as e:
    OUT["enhance_meta"] = {"err": str(e)}
    OUT["log8"].append({"item": "강화 후보 분산 효과", "kind": "실패", "detail": str(e)})

print("■ ★v49 강화 선정(기대수익 기준):")
for _mk, _lab in (("kr", "국내"), ("us", "미국")):
    _p = OUT["kr"] if _mk == "kr" else OUT["us"]
    _pk = OUT["enhance_kr"] if _mk == "kr" else OUT["enhance_us"]
    _n_ok = sum(1 for v in _p.values() if not v.get("pick_gate"))
    print(f"   {_lab}: {_pk}  (게이트 통과 {_n_ok}/{len(_p)}종)")
    for _k in _pk:
        _x = _p[_k]; _d = _x.get("dual") or {}
        print(f"     - {_k}: 기대 {_x['edge']:+.2f}% · {_d.get('model')} {_d.get('used')}점({_d.get('band')})"
              f" · 19신호 {_x['score']} · 성격 {_d.get('char')} · {_x.get('leader') or '-'}")

k200 = mac["KOSPI200"].get("estimated", mac["KOSPI200"]["close"])
nf = {"tier": None, "value": None, "chg": None, "note": ""}
try:
    r = subprocess.run(["curl", "-sL", "--max-time", "25", C.NF_TIER1], capture_output=True, text=True)
    j = json.loads(r.stdout)
    q, ss = j.get("quote", {}), j.get("session", {})
    px, vol = float(q["price"]), float(q.get("volume", 0))
    basis = abs(px / k200 - 1) * 100
    fails = []
    if ss.get("holiday_suspended") or ss.get("status") not in ("OPEN", "CLOSED_REGULAR", "CLOSED"):
        fails.append(f"세션={ss.get('status')}/휴장플래그={ss.get('holiday_suspended')}")
    if vol <= 0: fails.append("거래량 0(시드·플레이스홀더 의심)")
    if basis > C.NF_BASIS_MAX: fails.append(f"베이시스 {basis:.1f}% > {C.NF_BASIS_MAX}%")
    if not fails:
        nf = {"tier": 1, "value": px, "chg": float(q["change_pct"]), "src": "nfutures API",
              "basis": basis, "note": f"Tier1 실측 (베이시스 {basis:+.1f}%)"}
    else:
        OUT["log8"].append({"item": "코스피200 야간선물", "kind": "Tier1 게이트 탈락",
            "detail": f"<b>시도</b>: Tier1 정본 API 호출 성공(price {px:,.1f}, vol {vol:.0f}, "
                      f"session {ss.get('session_key')}). <b>반환</b>: 정합성 게이트 탈락 — {' / '.join(fails)}. "
                      f"현물 K200 {k200:,.2f} 대비 괴리 {basis:.1f}%. <b>대체</b>: Tier2 프록시."})
except Exception as e:
    OUT["log8"].append({"item": "코스피200 야간선물", "kind": "Tier1 호출 실패",
        "detail": f"<b>시도</b>: {C.NF_TIER1}. <b>반환</b>: {e}. <b>대체</b>: Tier2 프록시."})

if nf["tier"] is None:
    imp = (0.5*mac["필라델피아반도체(SOX)"]["chg_pct"] + 0.3*mac["나스닥"]["chg_pct"]
           + 0.2*mac["S&P500"]["chg_pct"])
    nf = {"tier": 2, "value": k200*(1+imp/100), "chg": imp, "src": "프록시",
          "note": "Tier2 프록시 추정 (0.5·SOX + 0.3·나스닥 + 0.2·S&P500)"}
OUT["night_futures"] = nf
OUT["night_futures_proxy"] = nf

try:
    px = pd.DataFrame({n: hist(t, "6mo")["Close"] for n, t in UKR.items()})
    px = px.loc[:, px.notna().sum() >= max(60, int(len(px) * 0.8))].dropna()
    ch = px.pct_change().dropna()
    up = (ch > 0).sum(axis=1); dn = (ch < 0).sum(axis=1)
    adr = (up / dn.replace(0, np.nan)).fillna(float(len(UKR)))
    OUT["adr"] = {"today": float(adr.iloc[-1]), "ma20": float(adr.rolling(20).mean().iloc[-1]),
                  "up": int(up.iloc[-1]), "dn": int(dn.iloc[-1]), "n": int(px.shape[1]),
                  "note": "표본 ADR(코스피 유니버스 13종) · 20일 이동평균 동시 산출"}
except Exception as e:
    OUT["log8"].append({"item": "표본 ADR", "kind": "실패", "detail": str(e)})

import glob, os
try:
    files = sorted(glob.glob("state_*.json"))
    OUT["prev_state"] = json.load(open(files[-1])) if files else None
    if not files:
        OUT["log8"].append({"item": "직전 회차 성과 검증", "kind": "최초 회차",
            "detail": "state_*.json 없음 — v37 최초 산출. 이번 회차부터 state를 남기므로 다음 회차부터 자동 검증."})
except Exception as e:
    OUT["prev_state"] = None

def _px(t, period="2y"):
    d = hist(t, period)["Close"]
    d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
    return d[~d.index.duplicated(keep="last")]

OUT["perf"] = {"ok": False}
try:
    POS = getattr(C, "POSITIONS", {})
    if POS:
        tick = {n: (p.get("ticker") or {**UKR, **UUS}.get(n)) for n, p in POS.items()}
        cols = {n: _px(t) for n, t in tick.items()}
        cols["_KOSPI"] = _px("^KS11"); cols["_FX"] = _px("KRW=X")
        df = pd.concat(cols, axis=1).ffill().dropna()
        vals = pd.DataFrame({n: df[n] * POS[n]["qty"] * (df["_FX"] if POS[n].get("ccy") == "$" else 1.0)
                             for n in POS})
        V = vals.sum(axis=1)
        rr = pd.concat([V.pct_change().rename("p"), df["_KOSPI"].pct_change().rename("m")], axis=1).dropna()

        rf = C.RF_FALLBACK; rf_src = f"폴백 상수 {C.RF_FALLBACK*100:.2f}%"
        try:
            txt = subprocess.run(["curl", "-s", "--max-time", "25",
                f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={C.RF_FRED}"],
                capture_output=True, text=True).stdout.strip().split("\n")
            last = [l for l in txt if l and l[0].isdigit() and l.split(",")[-1] not in ("", ".")][-1]
            rf = float(last.split(",")[-1]) / 100
            rf_src = f"FRED {C.RF_FRED} {last.split(',')[0]} · 연 {rf*100:.2f}%"
        except Exception as e:
            OUT["log8"].append({"item": "무위험수익률(샤프 계산용)", "kind": "폴백",
                "detail": f"<b>시도</b>: FRED {C.RF_FRED}. <b>반환</b>: {e}. <b>대체</b>: 상수 {C.RF_FALLBACK*100:.1f}%."})

        wins = {}
        for w in C.PERF_WINDOWS:
            a, b = rr["p"].tail(w), rr["m"].tail(w)
            lv_p, lv_m = V.tail(w), df["_KOSPI"].tail(w)
            sp, sm = ann_vol(a), ann_vol(b)
            wins[str(w)] = {
                "n": int(len(a)), "ret_p": ann_ret(a)*100, "ret_m": ann_ret(b)*100,
                "vol_p": sp, "vol_m": sm, "ratio": sp/sm if sm else 0,
                "beta": beta_of(a, b), "corr": float(np.corrcoef(a, b)[0, 1]),
                "sharpe_p": sharpe(a, rf), "sharpe_m": sharpe(b, rf),
                "sortino_p": sortino(a, rf), "sortino_m": sortino(b, rf),
                "mdd_p": mdd(lv_p), "mdd_m": mdd(lv_m),
                "te": track_err(a, b), "alpha": jensen_alpha(a, b, rf)}

        mctr, pvol = risk_contrib(vals, C.PERF_MCTR_WIN)
        wts = (vals.iloc[-1] / vals.iloc[-1].sum() * 100).to_dict()
        rr120 = vals.pct_change().dropna().tail(C.PERF_MCTR_WIN)
        m120 = rr["m"].reindex(rr120.index).fillna(0)
        legs = {n: {"w": float(wts[n]), "mctr": mctr.get(n, 0.0),
                    "vol": ann_vol(rr120[n]), "beta": beta_of(rr120[n], m120),
                    "whatif": vol_without(vals, n, C.PERF_MCTR_WIN)} for n in vals.columns}

        base_w = {n: legs[n]["w"]/100 for n in legs}
        top = max(legs, key=lambda n: legs[n]["mctr"])
        hedge = min(legs, key=lambda n: legs[n]["mctr"])
        sc = {}
        w1 = dict(base_w); w1[top] = base_w[top]*0.5
        w2 = dict(base_w); w2[top] = base_w[top]*0.5; w2[hedge] = base_w[hedge] + base_w[top]*0.5
        w3 = {k: v*0.8 for k, v in base_w.items()}
        for key, ww, lab in [("half_cash", w1, f"{top} 비중 절반 축소 → 현금"),
                             ("half_shift", w2, f"{top} 절반을 {hedge}로 이동"),
                             ("cash20", w3, "전 종목 20% 균등 축소(현금 20%)")]:
            v, b = vol_beta_scenario(vals, rr["m"], ww, C.PERF_MCTR_WIN)
            sc[key] = {"label": lab, "vol": v, "beta": b,
                       "d_vol": v - pvol, "ratio": v / wins[str(C.PERF_MCTR_WIN)]["vol_m"]}
        OUT_SC = {"top": top, "hedge": hedge, "scen": sc}

        since = min(p.get("since", "1900-01-01") for p in POS.values())
        Vs, Ks = V[V.index >= since], df["_KOSPI"][df.index >= since]
        rc = roll_vol(rr["p"], C.PERF_ROLLVOL).dropna()
        rm_ = roll_vol(rr["m"], C.PERF_ROLLVOL).dropna()

        OUT["perf"] = {"ok": True, "scenario": OUT_SC, "rf": rf, "rf_src": rf_src, "windows": wins, "legs": legs,
            "pvol": pvol, "value": float(V.iloc[-1]), "since": since,
            "since_p": float((Vs.iloc[-1]/Vs.iloc[0]-1)*100) if len(Vs) > 1 else 0.0,
            "since_m": float((Ks.iloc[-1]/Ks.iloc[0]-1)*100) if len(Ks) > 1 else 0.0,
            "since_days": int(len(Vs)),
            "curve": {"idx": [d.strftime("%Y-%m-%d") for d in V.tail(252).index],
                      "p": list((V.tail(252)/V.tail(252).iloc[0]*100).round(2)),
                      "m": list((df["_KOSPI"].tail(252)/df["_KOSPI"].tail(252).iloc[0]*100).round(2))},
            "rollvol": {"idx": [d.strftime("%Y-%m-%d") for d in rc.tail(180).index],
                        "p": list(rc.tail(180).round(2)), "m": list(rm_.tail(180).round(2))}}
except Exception as e:
    OUT["log8"].append({"item": "위험조정 성과(샤프·베타)", "kind": "실패",
        "detail": f"<b>시도</b>: POSITIONS 평가금액 시계열 + ^KS11 비교. <b>반환</b>: {e}. <b>대체</b>: 코너 미표기."})

_seen, _fx = set(), []
for _e in FIXLOG:
    if _e["item"] in _seen: continue
    _seen.add(_e["item"]); _fx.append(_e)
OUT["log8"] = _fx + OUT["log8"]
OUT["asof"] = OUT["kr"]["삼성전자"]["date"]
json.dump(OUT, open("data.json", "w"), ensure_ascii=False, default=str)

print(f"■ 기준일 {OUT['asof']} · 코스피 {OUT['kospi']['close']:,.2f} ({OUT['kospi']['chg']:+.2f}%) "
      f"· 주간 {OUT['kospi']['ret5']:+.2f}% · 월간 {OUT['kospi']['ret20']:+.2f}%")
b = mac["비트코인"]
print(f"■ BTC ${b['close']:,.0f} ({b['chg_pct']:+.2f}%) · 6만$ 대비 {(b['close']/C.BTC_ALERT-1)*100:+.1f}% "
      f"· 고점 대비 {(b['close']/b['hi252']-1)*100:+.1f}%  → {'경보 아님' if b['close']>C.BTC_ALERT else '★유동성 경보★'}")
print(f"■ 원/달러 {mac['원/달러']['close']:,.2f} · VIX {mac['VIX']['close']:.2f}/{mac['VIX3M']['close']:.2f}")
for k, v in fred.items():
    print(f"■ {k}: {v.get('val')} ({v.get('date')})" if "val" in v else f"■ {k}: 실패")
print("■ KR 점수:", sorted([(v["score"], k) for k, v in OUT["kr"].items()], reverse=True))
print("■ US 점수:", sorted([(v["score"], k) for k, v in OUT["us"].items()], reverse=True))
print("■ 섹터 RS(주):", sorted([(round(v["rs_w"],1), k) for k, v in sec.items()], reverse=True))
print("■ ★강화 6종 자동 선정 → 국내:", OUT["enhance_kr"], "/ 미국:", OUT["enhance_us"])
print(f"■ 야간선물 [Tier{OUT['night_futures']['tier']}] {OUT['night_futures']['value']:,.2f} ({OUT['night_futures']['chg']:+.2f}%) — {OUT['night_futures']['note']}")
print(f"■ KOSPI200 {mac['KOSPI200'].get('estimated', 0):,.2f} ({mac['KOSPI200'].get('method','실측')})")
if "adr" in OUT: print(f"■ 표본ADR {OUT['adr']['today']:.1f} (20일평균 {OUT['adr']['ma20']:.2f}) · 상승 {OUT['adr']['up']}/하락 {OUT['adr']['dn']}")
if OUT.get("perf", {}).get("ok"):
    _w = OUT["perf"]["windows"]["120"]
    print(f"■ ★위험조정(120일) 포트 σ{_w['vol_p']:.1f}% vs 코스피 σ{_w['vol_m']:.1f}% "
          f"→ 초과위험 x{_w['ratio']:.2f} · β{_w['beta']:.2f} · 샤프 {_w['sharpe_p']:.2f} vs {_w['sharpe_m']:.2f}")
    print("■ ★리스크 기여도:", {k: f"비중{v['w']:.0f}%/위험{v['mctr']:.0f}%" for k, v in OUT["perf"]["legs"].items()})
print(f"■ 직전 state: {'로드됨' if OUT.get('prev_state') else '없음(최초)'}")
print(f"■ §8 자동 로그 {len(OUT['log8'])}건:", [x["item"] for x in OUT["log8"]])
print("\n→ data.json 저장 완료. 다음: 웹검색 8종 이행 후 research.json 작성 → build.py")

def _dl(pool):
    out = []
    for k, v in pool.items():
        d = v.get("dual") or {}
        out.append((v["score"], k, d.get("model", "-"), d.get("used"), d.get("band", "-"),
                    d.get("char"), "경고" if d.get("is_warn") else ""))
    return sorted(out, key=lambda t: -t[0])
print("■ ★이중모델 KR:", [(k, m, u, b, c, w) for _, k, m, u, b, c, w in _dl(OUT["kr"])])
print("■ ★이중모델 US:", [(k, m, u, b, c, w) for _, k, m, u, b, c, w in _dl(OUT["us"])])
