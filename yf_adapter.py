# -*- coding: utf-8 -*-
"""
sitecustomize.py — ★환경 어댑터 (클라우드 컨테이너 전용, 2026-08-22)

yfinance(curl_cffi)가 야후 egress에서 리셋/429로 죽는다. 야후 v8 차트 API를
브라우저 UA + urllib로 직접 호출해 동일 DataFrame을 돌려준다. 파이프라인 코드는 무수정.
전송 계층만 바꾼다(시세 정본은 여전히 야후 v8 = yfinance가 부르던 그 엔드포인트).

이 환경 최적화 3종:
 1) 디스크 캐시(.yfcache) — 같은 (심볼,기간,간격)은 재호출 안 함(회차 반복·중단복구 대비).
 2) 인트라데이(5m/1h) 스킵 — as-of 확정 일봉이 완결이면 _fill_lagging_session이 부를
    5분봉 보정은 불필요하다. 공용 IP에 대한 호출량을 절반으로 줄이는 핵심.
 3) 글로벌 페이싱 — 버스트를 막아 429 페널티를 피한다(단발 호출은 0.2초/건으로 전부 200).
"""
import json, time, urllib.request, urllib.error, random, os, hashlib, pickle
import pandas as pd, numpy as np

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_MEM = {}
_CDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".yfcache")
os.makedirs(_CDIR, exist_ok=True)
_RANGE = {"1d": "1d", "5d": "5d", "7d": "5d", "1mo": "1mo", "3mo": "3mo",
          "6mo": "6mo", "1y": "1y", "2y": "2y", "5y": "5y", "10y": "10y",
          "ytd": "ytd", "max": "max"}
_INTRADAY = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
# 야후가 «일봉을 1행만» 주는 지수는 5분봉으로 일봉을 재구성해야 한다(^VIX3M 실증).
# 나머지는 확정 일봉이 완결이라 인트라데이 스킵(호출량 절감).
_INTRA_OK = {"^VIX3M", "^VXV"}
_last = [0.0]
_PACE = 0.25


def _cpath(symbol, rng, interval):
    h = hashlib.md5(f"{symbol}|{rng}|{interval}".encode()).hexdigest()[:16]
    return os.path.join(_CDIR, f"{h}.pkl")


def _get(url, tries=5):
    last = None
    for i in range(tries):
        dt = time.time() - _last[0]
        if dt < _PACE:
            time.sleep(_PACE - dt)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=18) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 999, 500, 502, 503):
                time.sleep(1.2 * (i + 1) + random.random())
                continue
            if e.code == 404:
                return None
            time.sleep(0.8 + i)
        except Exception as e:
            last = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"chart API 실패({url.split('/chart/')[-1][:40]}): {last}")


def _chart(symbol, rng="2y", interval="1d"):
    if interval in _INTRADAY and str(symbol) not in _INTRA_OK:  # 인트라데이 스킵(허용목록 제외)
        return pd.DataFrame()
    key = (symbol, rng, interval)
    if key in _MEM:
        return _MEM[key].copy()
    cp = _cpath(symbol, rng, interval)
    if os.path.exists(cp):
        try:
            df = pickle.load(open(cp, "rb"))
            _MEM[key] = df
            return df.copy()
        except Exception:
            pass
    r = _RANGE.get(rng, rng)
    sym = urllib.request.quote(str(symbol), safe="")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?range={r}&interval={interval}&includePrePost=false&events=div%2Csplit")
    j = _get(url)
    if not j or not j.get("chart", {}).get("result"):
        df = pd.DataFrame()
        _MEM[key] = df
        return df.copy()
    res = j["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    tzname = res.get("meta", {}).get("exchangeTimezoneName") or "UTC"
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert(tzname)
    if interval == "1d":
        idx = idx.normalize()
    df = pd.DataFrame({
        "Open": q.get("open"), "High": q.get("high"), "Low": q.get("low"),
        "Close": q.get("close"), "Volume": q.get("volume")}, index=idx)
    adj = ((res.get("indicators", {}).get("adjclose") or [{}])[0]).get("adjclose")
    df["Adj Close"] = adj if adj is not None else df["Close"]
    df = df[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]
    df = df[df["Close"].notna()]
    df["Volume"] = df["Volume"].fillna(0)
    if not df.empty:
        _MEM[key] = df.copy()
        try:
            pickle.dump(df, open(cp, "wb"))
        except Exception:
            pass
    return df


def _install():
    import yfinance as yf

    def history(self, period="1mo", interval="1d", start=None, end=None,
                auto_adjust=False, actions=True, prepost=False, **kw):
        sym = getattr(self, "ticker", None) or getattr(self, "_ticker", None)
        df = _chart(sym, period or "1mo", interval)
        if df.empty:
            return df
        if auto_adjust and "Adj Close" in df.columns:
            f = (df["Adj Close"] / df["Close"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
            for c in ("Open", "High", "Low", "Close"):
                df[c] = df[c] * f
        return df.copy()

    yf.Ticker.history = history

    class _FI(dict):
        def __getitem__(self, k):
            raise KeyError(k)
        def get(self, k, d=None):
            return d
    try:
        yf.Ticker.fast_info = property(lambda self: _FI())
    except Exception:
        pass
    yf.Ticker.get_info = lambda self, *a, **k: {}
    try:
        yf.Ticker.info = property(lambda self: {})
    except Exception:
        pass

    def download(tickers, period="1mo", interval="1d", group_by="column",
                 auto_adjust=False, threads=True, progress=False, **kw):
        if isinstance(tickers, str):
            tickers = tickers.replace(",", " ").split()
        tickers = [t for t in tickers if t]
        frames = {}
        for t in tickers:
            try:
                d = _chart(t, period, interval)
            except Exception:
                d = pd.DataFrame()
            if auto_adjust and not d.empty and "Adj Close" in d.columns:
                f = (d["Adj Close"] / d["Close"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
                for c in ("Open", "High", "Low", "Close"):
                    d[c] = d[c] * f
            frames[t] = d
        if len(tickers) == 1:
            return frames[tickers[0]]
        good = {t: d for t, d in frames.items() if not d.empty}
        if not good:
            return pd.DataFrame()
        return pd.concat(good, axis=1)

    yf.download = download
    print("  [adapter] yfinance → 야후 v8 차트 API 직접호출(디스크캐시·인트라데이스킵·페이싱)")


try:
    _install()
except Exception as _e:
    print(f"  [adapter] 설치 실패(무시): {_e}")
