# -*- coding: utf-8 -*-
"""universe.py — ★v46 신설: 강화·스크리닝 유니버스를 「시총 상위 150위」로 동적 구성한다.

배경(2026-08-13 사용자 지적):
  기존 유니버스는 config.KR_UNIVERSE / US_UNIVERSE에 하드코딩된 13+13종이었다.
  미국은 반도체 8종을 제외하면 후보가 5종뿐이라, 애플이 '잘해서 2등'이 아니라
  '5개 중 2등'이라 뽑혔다. 후보에 없는 종목은 아무리 좋아도 절대 추천될 수 없었다.
  → 국장 KOSPI 시총 150위 · 미장 시총 150위로 유니버스를 넓힌다.

원칙:
  1) 시총 순위는 매일 바뀌지 않는다 → 7일 캐시(universe_cache.json). 매 회차 재조회하지 않는다.
  2) 조회가 실패해도 파이프라인이 죽으면 안 된다 → 캐시 → 레거시 순으로 폴백하고 §8에 남긴다.
  3) 보유·관찰 종목은 시총 순위와 무관하게 항상 포함한다(카드가 깨지면 안 되므로).
"""
import json, os, time, datetime as dt

CACHE = "universe_cache.json"
META  = "universe_meta.json"   # ★v46: 종목별 섹터·산업·시총 (대장주 판정용)
TTL_DAYS = 7

# 미장 시총 상위권인데 S&P500 구성종목이 아닌 미국 상장 종목(주로 ADR·최근 상장).
# S&P500만 쓰면 TSMC·ASML 같은 종목이 통째로 빠지므로 후보 풀에 더한다.
US_EXTRA = [
    "TSM", "ASML", "BABA", "NVO", "AZN", "SHOP", "ARM", "SNDK", "TM", "SAP",
    "HSBC", "RY", "MUFG", "SONY", "UL", "BHP", "RIO", "SNY", "TTE", "BUD",
    "INFY", "PDD", "SPOT", "MELI", "SE", "COIN", "APP", "SNPS", "CRWD", "DASH",
]


def _kospi_top(n, log):
    import pandas as pd
    import FinanceDataReader as fdr
    d = None
    for i in range(6):                       # 원격 엔드포인트가 간헐적으로 빈 응답을 준다
        try:
            d = fdr.StockListing("KOSPI")
            if d is not None and len(d) > 500:
                break
            d = None
        except Exception:
            d = None
        time.sleep(3 + i)
    if d is None:
        raise RuntimeError("FinanceDataReader KOSPI 리스팅 실패(6회)")
    pat = r"(?:우$|우B$|[0-9]우$|우선주)"       # 우선주는 본주와 중복이므로 제외
    d = d[~d["Name"].astype(str).str.contains(pat, regex=True, na=False)]
    d = d[~d["Name"].astype(str).str.contains(r"(?:스팩|리츠|리서치)", regex=True, na=False)]
    d = d.dropna(subset=["Marcap"]).sort_values("Marcap", ascending=False).head(n)
    out = {str(r["Name"]): f"{str(r['Code']).zfill(6)}.KS" for _, r in d.iterrows()}
    log.append(f"KOSPI 시총 상위 {len(out)}종 확보(컷 {float(d['Marcap'].iloc[-1])/1e12:.2f}조)")
    return out


def _us_top(n, log):
    import yfinance as yf
    import FinanceDataReader as fdr
    syms, names = [], {}
    for i in range(4):
        try:
            sp = fdr.StockListing("S&P500")
            if sp is not None and len(sp) > 400:
                syms = [str(s) for s in sp["Symbol"].tolist()]
                names = {str(r["Symbol"]): str(r["Name"]) for _, r in sp.iterrows()}
                break
        except Exception:
            pass
        time.sleep(3)
    if not syms:
        raise RuntimeError("S&P500 리스팅 실패(4회)")
    pool = list(dict.fromkeys(syms + US_EXTRA))
    caps = {}
    for s in pool:
        t = s.replace(".", "-")               # BRK.B → BRK-B (야후 표기)
        try:
            mc = yf.Ticker(t).fast_info["marketCap"]
            if mc:
                caps[t] = (float(mc), names.get(s, s))
        except Exception:
            continue
    if len(caps) < 200:
        raise RuntimeError(f"미장 시총 조회 부족({len(caps)}종)")
    top = sorted(caps.items(), key=lambda kv: -kv[1][0])[:n]
    out = {v[1]: k for k, v in top}
    log.append(f"미장 시총 상위 {len(out)}종 확보(후보 {len(caps)}종 · 컷 ${top[-1][1][0]/1e9:,.0f}B)")
    return out


def _normalize(kr, us):
    """① config에 이름이 정의된 종목은 그 한글명을 쓴다(WATCH·POSITIONS 카드가 이름으로 조회되므로).
       ② 보유·관찰 종목은 시총 순위와 무관하게 반드시 포함한다.
       ③ 티커 중복은 제거한다(GOOGL/GOOG 같은 복수 클래스는 남긴다 — 티커가 다르므로)."""
    import config as C
    legacy = {**C.KR_UNIVERSE, **C.US_UNIVERSE}
    by_tk = {t: n for n, t in legacy.items()}          # 티커 → config 한글명
    def fix(dic, force_from):
        out, seen = {}, set()
        for nm, tk in dic.items():
            if tk in seen: continue
            seen.add(tk)
            out[by_tk.get(tk, nm)] = tk
        for nm, tk in force_from.items():              # 누락된 보유·관찰 종목 강제 편입
            if tk not in seen:
                out[nm] = tk; seen.add(tk)
        return out
    return fix(kr, C.KR_UNIVERSE), fix(us, C.US_UNIVERSE)


def load(n_kr=150, n_us=150, force=False, pin=None):
    """반환: (kr_dict, us_dict, log_list, source)
       source: 'fresh' | 'cache' | 'legacy'"""
    log = []
    if not force and os.path.exists(CACHE):
        try:
            c = json.load(open(CACHE, encoding="utf-8"))
            age = (dt.date.today() - dt.date.fromisoformat(c["date"])).days
            if age <= TTL_DAYS and len(c.get("kr", {})) >= 100 and len(c.get("us", {})) >= 100:
                log.append(f"유니버스 캐시 사용({c['date']} · {age}일 경과 · TTL {TTL_DAYS}일)")
                k, u = _normalize(c["kr"], c["us"]); return k, u, log, "cache"
        except Exception:
            pass
    try:
        kr = _kospi_top(n_kr, log)
        us = _us_top(n_us, log)
        json.dump({"date": dt.date.today().isoformat(), "kr": kr, "us": us},
                  open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        kr, us = _normalize(kr, us)
        log.append(f"보유·관찰 종목 강제 편입 후 KR {len(kr)}종 · US {len(us)}종")
        return kr, us, log, "fresh"
    except Exception as e:
        log.append(f"신규 조회 실패({e}) → 캐시/레거시 폴백")
        if os.path.exists(CACHE):
            try:
                c = json.load(open(CACHE, encoding="utf-8"))
                log.append(f"만료 캐시 사용({c['date']})")
                k, u = _normalize(c["kr"], c["us"]); return k, u, log, "cache"
            except Exception:
                pass
        import config as C
        log.append("레거시 13+13종으로 폴백 — 이 회차 강화 선정은 신뢰도가 낮다")
        return dict(C.KR_UNIVERSE), dict(C.US_UNIVERSE), log, "legacy"


def load_meta(tickers, log, force=False):
    """섹터·산업·시가총액을 채운다. 산업(industry)이 있어야 '변압기 대장주' 같은
       판정을 할 수 있다 — 2026-08-13 사용자 지적: "LS ELECTRIC처럼 섹터 대장주가
       탈락하는 건 의외다". 티커당 약 0.35초라 유니버스와 같은 7일 캐시를 쓴다."""
    import yfinance as yf
    meta = {}
    if not force and os.path.exists(META):
        try:
            c = json.load(open(META, encoding="utf-8"))
            age = (dt.date.today() - dt.date.fromisoformat(c["date"])).days
            if age <= TTL_DAYS:
                meta = c.get("meta", {})
        except Exception:
            meta = {}
    miss = [t for t in tickers if t not in meta]
    if miss:
        for t in miss:
            try:
                i = yf.Ticker(t).get_info()
                meta[t] = {"sector": i.get("sector") or "기타",
                           "industry": i.get("industry") or "기타",
                           "cap": float(i.get("marketCap") or 0)}
            except Exception:
                meta[t] = {"sector": "기타", "industry": "기타", "cap": 0.0}
        try:
            json.dump({"date": dt.date.today().isoformat(), "meta": meta},
                      open(META, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
        log.append(f"섹터·산업 메타 {len(miss)}종 신규 조회(전체 {len(meta)}종 캐시)")
    else:
        log.append(f"섹터·산업 메타 캐시 사용({len(meta)}종)")
    return meta


if __name__ == "__main__":
    kr, us, log, src = load()
    for l in log:
        print("·", l)
    print(f"source={src}  KR={len(kr)}  US={len(us)}")
    print("KR 상위15:", list(kr.items())[:15])
    print("US 상위15:", list(us.items())[:15])
