# -*- coding: utf-8 -*-
"""
fetch_kr_extra.py — ★v62 «웹검색으로 찾던 값»을 API로 직접 받고, 두 소스로 교차검증한다.

왜: 지금까지 수급·국고채·목표가를 마감시황 기사에서 읽었는데, 같은 날 기사끼리 숫자가 달랐다
    (2026-09-23 코스피 개인 순매매: 기사 A −1조4,397억 · 기사 B +620억 · 네이버 −1조4,649억 · 다음 −1조4,543억).
    기사는 장중 잠정치·오기가 섞인다 → 거래소 집계를 싣는 두 포털 API를 서로 대조해 쓴다.

모드
  python3 fetch_kr_extra.py xcheck D   # fetch_all «전» — 코스피·코스닥 확정 종가(네이버 OHLC × 다음 종가) → index_xcheck.json
  python3 fetch_kr_extra.py collect D  # fetch_all과 «병렬» — 수급·선물·프로그램·시장폭·금리·컨센서스 → extra.json
  python3 fetch_kr_extra.py merge      # fetch_all «후» — 야후 실측과 대조(EWY·10년물) + 후보 종목 컨센서스 → data.json["extra"]

원칙
  · 모든 값에 날짜·출처를 붙인다. 두 소스가 허용오차를 넘으면 값은 1차 소스로 쓰되 §8에 «불일치»로 남긴다.
  · 단일 소스 항목은 «단일 소스»라고 표시한다(검증된 척하지 않는다).
  · 단위 검증 기록: 네이버 K200 선물 투자자별 값은 억원이다
    (2026-09-21 +11,817 = 기사 «4,251계약 · 1조1,817억원»과 일치 → 계약당 ≈2.78억).
"""
import json, sys, os, time, datetime as dt, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0"}
DAUM_REF = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.daum.net/domestic"}
NV = "https://m.stock.naver.com"
NVW = "https://api.stock.naver.com"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
LOG = []            # §8 로그 (item/kind/detail)


def _get(url, headers=UA, tries=3, timeout=12, raw=False):
    last = None
    for i in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)
            b = r.read().decode("utf-8", "replace")
            return b if raw else json.loads(b)
        except Exception as e:
            last = e
            time.sleep(0.6 * (i + 1))
    raise RuntimeError(f"{url} → {last}")


def num(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    import re as _re
    m = _re.search(r"[-+]?\d+(?:\.\d+)?", str(s).replace(",", ""))
    return float(m.group(0)) if m else None


def log(item, kind, detail):
    LOG.append({"item": item, "kind": kind, "detail": detail})


def _near(a, b, rel=0.03, abs_=100.0):
    if a is None or b is None:
        return False
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


# ════════════════════════════════════════════════════════════
# 1) 지수 확정 종가 이중소스 → index_xcheck.json (G17)
# ════════════════════════════════════════════════════════════
def naver_index_bars(code, n=10):
    rows = _get(f"{NV}/api/index/{code}/price?pageSize={n}&page=1")
    return [{"date": r["localTradedAt"][:10], "close": num(r["closePrice"]), "open": num(r["openPrice"]),
             "high": num(r["highPrice"]), "low": num(r["lowPrice"])} for r in rows]


def daum_index_days(mkt, n=25):
    j = _get(f"https://finance.daum.net/api/market_index/days?page=1&perPage={n}&market={mkt}&pagination=true",
             DAUM_REF)
    return [{"date": r["date"][:10], "close": float(r["tradePrice"]),
             "ind": r["individualStraightPurchasePrice"] / 1e8,
             "frn": r["foreignStraightPurchasePrice"] / 1e8,
             "inst": r["institutionStraightPurchasePrice"] / 1e8} for r in j["data"]]


def cmd_xcheck(D):
    out = {"_README": "★v62 지수 이중소스 대조 — 네이버 금융(OHLC) × 다음 금융(종가) 자동 수집. "
                      "두 포털 모두 한국거래소 확정치를 싣는다. 종가가 0.05% 넘게 어긋나면 실패로 기록한다.",
           "asof": D, "source": "네이버 금융 지수 일별시세 × 다음 금융 지수 일별(자동 교차검증)",
           "fetched": dt.datetime.now().isoformat(timespec="seconds"), "bars": {}, "macro": {}, "agree": {}}
    ok_all = True
    for tk, nv_code, dm in (("^KS11", "KOSPI", "KOSPI"), ("^KQ11", "KOSDAQ", "KOSDAQ")):
        nb = [b for b in naver_index_bars(nv_code, 10) if b["date"] <= D]
        db = {b["date"]: b["close"] for b in daum_index_days(dm, 12)}
        rows, bad = [], []
        for b in nb[:5]:
            dc = db.get(b["date"])
            if dc is None or abs(dc / b["close"] - 1) > 0.0005:
                bad.append(f'{b["date"]} 네이버 {b["close"]:,.2f} / 다음 {dc}')
                continue
            rows.append(b)
        rows.sort(key=lambda r: r["date"])
        out["bars"][tk] = rows
        out["agree"][tk] = {"n": len(rows), "bad": bad}
        if not rows or rows[-1]["date"] != D:
            ok_all = False
        if bad:
            ok_all = False
    # ★v62 원/달러 — 야후 KRW=X 일봉은 런던 시간 기준이라 서울 종가와 하루 어긋난다
    #   (2026-09-23: 야후 «9/23» 1,350.36(−1.70%) vs 서울 1,366.70(+0.83%) — 야후 9/24 봉이 서울 9/23과 일치).
    #   네이버(은행 고시 종가) 1차 × 다음(최종 고시 매매기준율) 대조 → macro 정정(lib_idx.macro_fix).
    try:
        j = _get(f"{NV}/front-api/marketIndex/prices?category=exchange&reutersCode=FX_USDKRW&page=1&pageSize=10")
        rows = [r for r in j["result"] if r["localTradedAt"][:10] <= D]
        cur, prev = rows[0], rows[1]
        nv_c, nv_p = num(cur["closePrice"]), num(prev["closePrice"])
        dm = _get("https://finance.daum.net/api/exchanges/FRX.KRWUSD/days?page=1&perPage=5",
                  {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.daum.net/exchanges"})
        dmm = {r["date"][:10]: float(r["basePrice"]) for r in dm["data"]}
        dv = dmm.get(cur["localTradedAt"][:10])
        agree = dv is not None and abs(dv / nv_c - 1) <= 0.003
        out["macro"]["원/달러"] = {"date": cur["localTradedAt"][:10], "close": nv_c, "prev": nv_p,
                                 "src": "네이버(은행 고시 종가)", "daum": dv, "agree": agree}
        if not agree:
            print(f"   ⚠ 원/달러 네이버 {nv_c} / 다음 {dv} 불일치 — 네이버 값 사용")
    except Exception as e:
        print("   ⚠ 원/달러 서울 종가 수집 실패:", e)
    # ★v62 유가 — 야후 CL=F·BZ=F는 «연속 선물»이라 만기 교체(롤)일에 등락률이 가짜로 찍힌다
    #   (2026-09-23 WTI: 야후 −2.57% vs 새 근월물 기준 +1.81%). 네이버 원자재(근월물 기준 등락률)로 전일값을 역산해 정정.
    try:
        import asof as _A
        uc = os.environ.get("YF_US_CUT") or _A.us_cut()
        for key, code in (("WTI", "CLcv1"), ("브렌트", "LCOcv1")):
            j = _get(f"{NV}/front-api/marketIndex/prices?category=energy&reutersCode={code}&page=1&pageSize=10")
            rows = [r for r in j["result"] if r["localTradedAt"][:10] < uc]
            if not rows:
                continue
            c, rt = num(rows[0]["closePrice"]), num(rows[0]["fluctuationsRatio"])
            tcode = (rows[0].get("fluctuationsType") or {}).get("code")
            if tcode in ("4", "5"):          # 하락·하한 → 음수 보장
                rt = -abs(rt)
            elif tcode in ("1", "2"):        # 상승·상한 → 양수 보장
                rt = abs(rt)
            out["macro"][key] = {"date": rows[0]["localTradedAt"][:10], "close": c, "prev": c / (1 + rt / 100),
                                 "src": f"네이버 원자재({code}, 근월물 기준 등락)"}
    except Exception as e:
        print("   ⚠ 유가 롤 보정 수집 실패:", e)
    json.dump(out, open("index_xcheck.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    last = {k: (v[-1]["date"], v[-1]["close"]) if v else None for k, v in out["bars"].items()}
    last["원/달러"] = (out["macro"].get("원/달러") or {}).get("close")
    print(f"■ index_xcheck.json — {last} · {'두 소스 일치' if ok_all else '⚠ 불일치/누락 — §8 확인'}")
    for k, a in out["agree"].items():
        for b in a["bad"]:
            print("   ⚠", k, b)
    return 0


# ════════════════════════════════════════════════════════════
# 1-2) ★v62 KR 개별종목 «정규장 공식 종가» 검증
#   실측(2026-09-24): 포털(다음·네이버) 일별 «종가»는 넥스트레이드(NXT) 시간외(~20:00) 최종 체결가다
#   (삼성전자 9/23 다음 tradePrice 286,500 · 체결시각 19:59). 한국거래소 정규장 종가는 «다음 날 행의 전일종가»로만 나온다.
#   → 다음(prevClosingPrice)·네이버(종가−전일대비) 두 체인으로 «정규장 공식 종가»를 복원해 야후 .KS 종가를 검증한다.
#   2026-09-16~22 삼성전자·SK하이닉스·현대해상 전 봉에서 야후 = 공식 종가(일치). 야후가 다를 때만 종가를 정정한다.
# ════════════════════════════════════════════════════════════
def _official_daum(code, n=60):
    j = _get(f"https://finance.daum.net/api/quote/A{code}/days?symbolCode=A{code}&page=1&perPage={n}&pagination=true",
             DAUM_REF, tries=2, timeout=10)
    rows = [(r["date"][:10], float(r["prevClosingPrice"])) for r in j["data"]]   # 최신→과거
    return {rows[i + 1][0]: rows[i][1] for i in range(len(rows) - 1)}               # 전일 날짜 → 공식 종가


def _official_naver(code):
    r = _get(f"{NV}/api/stock/{code}/price?pageSize=60&page=1", tries=2, timeout=10)
    out = {}
    for i in range(len(r) - 1):
        c = num(r[i]["closePrice"]); ch = num(r[i]["compareToPreviousClosePrice"])
        tcode = (r[i].get("compareToPreviousPrice") or {}).get("code")
        if tcode in ("4", "5"):
            ch = -abs(ch)
        elif tcode in ("1", "2"):
            ch = abs(ch)
        if c and ch is not None and c - ch > 0:
            out[r[i + 1]["localTradedAt"][:10]] = c - ch
    return out


def kr_official(tickers, D, n=60):
    """→ {'bars': {tk: [{'date','close'}...]}, 'checked','agree','disagree','fail'} — close = 두 체인이 일치한 정규장 종가만."""
    codes = sorted({t for t in tickers if str(t).endswith(".KS")})
    out = {"bars": {}, "checked": 0, "agree": 0, "disagree": [], "fail": []}
    def one(t):
        c = t.split(".")[0]
        try:
            dm = _official_daum(c, n)
        except Exception as e:
            return t, None, None, str(e)
        try:
            nv = _official_naver(c)
        except Exception:
            nv = {}
        return t, dm, nv, None
    with ThreadPoolExecutor(10) as ex:
        for t, dm, nv, err in ex.map(one, codes):
            if err or not dm:
                out["fail"].append(t); continue
            rows, bad = [], 0
            for d, v in dm.items():
                if d > D or not v or v <= 0:
                    continue
                w = nv.get(d)
                if w is not None and w > 0 and abs(w / v - 1) > 0.0005:
                    bad += 1; continue                 # 두 체인이 다르면 그 봉은 쓰지 않는다
                rows.append({"date": d, "close": v})
            out["checked"] += 1
            if bad:
                out["disagree"].append(f"{t} {bad}봉")
            else:
                out["agree"] += 1
            out["bars"][t] = sorted(rows, key=lambda r: r["date"], reverse=True)
    return out


# ════════════════════════════════════════════════════════════
# 2) collect — 수급·선물·프로그램·시장폭·금리·컨센서스
# ════════════════════════════════════════════════════════════
def naver_trend(code, bizdate):
    j = _get(f"{NV}/api/index/{code}/trend?bizdate={bizdate}")
    return {"date": f'{j["bizdate"][:4]}-{j["bizdate"][4:6]}-{j["bizdate"][6:]}',
            "ind": num(j["personalValue"]), "frn": num(j["foreignValue"]), "inst": num(j["institutionalValue"])}


def _streak(vals):
    """최근부터 같은 부호가 몇 일 연속인가(+면 순매수 연속, −면 순매도 연속)."""
    if not vals:
        return 0
    s = 1 if vals[0] > 0 else -1
    n = 0
    for v in vals:
        if (v > 0 and s > 0) or (v < 0 and s < 0):
            n += 1
        else:
            break
    return n * s


def collect_flows(D):
    res = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        days = [r for r in daum_index_days(mkt, 25) if r["date"] <= D]
        if not days or days[0]["date"] != D:
            log(f"{mkt} 투자자별 수급", "실패",
                f"<b>시도</b>: 다음 금융 투자자별 일별. <b>반환</b>: 기준일 {D} 행 없음(최신 {days[0]['date'] if days else '없음'}). "
                f"<b>대체</b>: 네이버 단일 소스.")
        try:
            nv = naver_trend(mkt, D.replace("-", ""))
        except Exception as e:
            nv = None
            log(f"{mkt} 투자자별 수급(네이버)", "실패", f"<b>시도</b>: 네이버 trend. <b>반환</b>: {e}. <b>대체</b>: 다음 단일 소스.")
        d0 = days[0] if days and days[0]["date"] == D else None
        prim = d0 or nv
        if prim is None:
            continue
        agree = {k: _near(d0[k], nv[k]) for k in ("ind", "frn", "inst")} if (d0 and nv) else None
        ser = [r["frn"] for r in days]
        res[mkt] = {
            "date": D, "ind": prim["ind"], "frn": prim["frn"], "inst": prim["inst"],
            "src": "다음 금융(한국거래소 집계)" if d0 else "네이버 금융(한국거래소 집계)",
            "naver": nv, "daum": d0, "agree": agree,
            "frn_5d": sum(ser[:5]), "frn_20d": sum(ser[:20]),
            "inst_5d": sum(r["inst"] for r in days[:5]), "inst_20d": sum(r["inst"] for r in days[:20]),
            "frn_streak": _streak(ser), "inst_streak": _streak([r["inst"] for r in days]),
            "series": [{"date": r["date"], "frn": round(r["frn"], 1), "inst": round(r["inst"], 1),
                        "ind": round(r["ind"], 1)} for r in days[:20]],
        }
        if agree is not None:
            if all(agree.values()):
                log(f"{mkt} 투자자별 수급 이중소스 대조", "정상",
                    f"<b>시도</b>: 다음 × 네이버(둘 다 한국거래소 집계) {D}. <b>반환</b>: 개인·외국인·기관 모두 허용오차(3% 또는 100억) 이내 "
                    f"— 외국인 다음 {d0['frn']:+,.0f}억 / 네이버 {nv['frn']:+,.0f}억. <b>대체</b>: 불필요(표기값 = 다음).")
            else:
                log(f"{mkt} 투자자별 수급 이중소스 대조", "경고",
                    f"<b>시도</b>: 다음 × 네이버 {D}. <b>반환</b>: 불일치 — 다음 개인 {d0['ind']:+,.0f}/외국인 {d0['frn']:+,.0f}/기관 {d0['inst']:+,.0f}억 · "
                    f"네이버 {nv['ind']:+,.0f}/{nv['frn']:+,.0f}/{nv['inst']:+,.0f}억. <b>대체</b>: 다음 값을 표기하되 방향 해석만 쓴다(잠정치 가능성).")
    return res


def collect_futures(D, dates):
    """외국인 코스피200 선물 순매수(억원) — 네이버 단일 소스. 계약수는 선물 종가로 환산."""
    px = {r["date"]: r["close"] for r in naver_index_bars("FUT", 30)}
    rows = []
    def one(d):
        try:
            t = naver_trend("FUT", d.replace("-", ""))
            return t if t["date"] == d else None
        except Exception:
            return None
    with ThreadPoolExecutor(6) as ex:
        got = list(ex.map(one, dates[:10]))
    for t in got:
        if not t:
            continue
        p = px.get(t["date"])
        t["contracts"] = round(t["frn"] / (p * 250000 / 1e8)) if p else None
        t["fut_close"] = p
        rows.append(t)
    rows.sort(key=lambda r: r["date"], reverse=True)
    if not rows or rows[0]["date"] != D:
        log("외국인 K200 선물", "실패", f"<b>시도</b>: 네이버 FUT 투자자별 {D}. <b>반환</b>: 기준일 행 없음. <b>대체</b>: 코너 표기 생략.")
        return None
    ser = [r["frn"] for r in rows]
    log("외국인 K200 선물 순매수", "단일 소스",
        f"<b>시도</b>: 네이버 금융 K200 선물 투자자별(한국거래소 집계). <b>반환</b>: {D} 외국인 {rows[0]['frn']:+,.0f}억"
        f"(≈{rows[0]['contracts']:+,}계약). <b>대체</b>: 2차 소스 없음 — 단위(억원)는 9/21 기사(4,251계약=1조1,817억)로 검증.")
    return {"date": D, "frn": rows[0]["frn"], "contracts": rows[0]["contracts"], "ind": rows[0]["ind"],
            "inst": rows[0]["inst"], "fut_close": rows[0]["fut_close"],
            "frn_5d": sum(ser[:5]), "frn_streak": _streak(ser), "series": rows,
            "src": "네이버 금융(한국거래소 집계) · 단일 소스 · 단위 억원"}


def collect_program_breadth(D):
    out = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        try:
            j = _get(f"{NV}/api/index/{mkt}/integration")
            pg, ud = j.get("programTrendInfo") or {}, j.get("upDownStockInfo") or {}
            bd = pg.get("bizdate", "")
            bd = f"{bd[:4]}-{bd[4:6]}-{bd[6:]}" if bd else None
            if bd != D:
                log(f"{mkt} 프로그램·등락종목", "실패", f"<b>시도</b>: 네이버 integration. <b>반환</b>: 기준일 {bd}≠{D}. <b>대체</b>: 생략.")
                continue
            up = num(ud.get("riseCount")) + num(ud.get("upperCount"))
            dn = num(ud.get("fallCount")) + num(ud.get("lowerCount"))
            out[mkt] = {"date": D, "arb": num(pg.get("indexDifferenceReal")),
                        "nonarb": num(pg.get("indexBiDifferenceReal")), "prog": num(pg.get("indexTotalReal")),
                        "up": up, "dn": dn, "flat": num(ud.get("steadyCount")),
                        "adr": round(up / dn, 2) if dn else None,
                        "src": "네이버 금융(한국거래소 집계) · 단일 소스"}
        except Exception as e:
            log(f"{mkt} 프로그램·등락종목", "실패", f"<b>시도</b>: 네이버 integration. <b>반환</b>: {e}. <b>대체</b>: 생략.")
    return out


def naver_bond(code, n=10):
    j = _get(f"{NV}/front-api/marketIndex/prices?category=bond&reutersCode={urllib.parse.quote(code)}&page=1&pageSize={n}")
    return [{"date": r["localTradedAt"][:10], "close": num(r["closePrice"]), "chg": num(r["fluctuations"])}
            for r in j["result"]]


def fred(fid):
    """FRED CSV — urllib는 이 사이트에서 응답 대기로 멈춘 사례가 있어 fetch_all과 같은 curl 경로를 쓴다.
    최근 70일만 받는다(cosd) — 전체 이력(수십 년) 다운로드 낭비 제거."""
    import subprocess
    cosd = (dt.date.today() - dt.timedelta(days=70)).isoformat()
    txt = ""
    for i in range(3):
        txt = subprocess.run(["curl", "-sL", "--max-time", "25", f"{FRED}{fid}&cosd={cosd}"],
                             capture_output=True, text=True).stdout
        if txt.strip().count("\n") >= 2:
            break
        time.sleep(1.5 * (i + 1))
    if txt.strip().count("\n") < 2:
        raise RuntimeError("FRED 빈 응답")
    rows = []
    for l in txt.strip().splitlines()[1:]:
        d, v = l.split(",")[:2]
        if v not in ("", "."):
            rows.append((d, float(v)))
    return rows


def collect_rates(D, us_cut):
    out = {}
    # 미 2년·10년 = 네이버(로이터 17:05ET 종가) 1차 · FRED(재무부 CMT) 대조
    for key, code, fid in (("us2y", "US2YT=RR", "DGS2"), ("us10y", "US10YT=RR", "DGS10")):
        try:
            rows = [r for r in naver_bond(code, 10) if r["date"] < us_cut]
            cur, prev = rows[0], rows[1]
            ent = {"date": cur["date"], "val": cur["close"], "prev": prev["close"],
                   "chg_bp": round((cur["close"] - prev["close"]) * 100, 1),
                   "chg5_bp": round((cur["close"] - rows[min(5, len(rows)-1)]["close"]) * 100, 1),
                   "src": f"네이버 금융({code}, 뉴욕 17:05 종가)"}
            try:
                fr = dict(fred(fid)[-10:])
                fv = fr.get(cur["date"])
                ent["fred"] = {"id": fid, "val": fv, "date": cur["date"] if fv is not None else max(fr)}
                if fv is not None:
                    diff = (cur["close"] - fv) * 100
                    ok = abs(diff) <= 7
                    log(f"미 국채 {key[2:]} 이중소스 대조", "정상" if ok else "경고",
                        f"<b>시도</b>: 네이버({code}) × FRED {fid}(재무부 고시). <b>반환</b>: {cur['date']} {cur['close']:.3f}% vs {fv:.2f}% "
                        f"(차이 {diff:+.1f}bp — 집계 시각·방식 차). <b>대체</b>: {'불필요' if ok else '방향만 해석'}(표기값 = 네이버).")
                else:
                    # FRED는 하루 늦게 게시 → «직전일» 값끼리 대조해 소스 정합성만 확인
                    pv = fr.get(prev["date"])
                    pdiff = (prev["close"] - pv) * 100 if pv is not None else None
                    okp = pdiff is not None and abs(pdiff) <= 7
                    log(f"미 국채 {key[2:]} 이중소스 대조", "정상" if okp else "지연값",
                        f"<b>시도</b>: 네이버({code}) × FRED {fid}. <b>반환</b>: FRED는 하루 늦게 게시돼 {cur['date']} 값 미게시 → "
                        + (f"직전일 {prev['date']} 대조 {prev['close']:.3f}% vs {pv:.2f}%(차이 {pdiff:+.1f}bp). "
                           if pv is not None else f"직전일 값도 없음(최신 {max(fr)}). ")
                        + f"<b>대체</b>: {cur['date']} 값은 네이버로 표기{'(소스 정합성 확인됨)' if okp else ''}.")
            except Exception as e:
                log(f"FRED {fid}", "실패", f"<b>시도</b>: FRED. <b>반환</b>: {e}. <b>대체</b>: 네이버 단일 소스.")
            out[key] = ent
        except Exception as e:
            log(f"미 국채 {key}", "실패", f"<b>시도</b>: 네이버 {code}. <b>반환</b>: {e}. <b>대체</b>: 생략.")
    # 실질금리(10년 TIPS)·기대인플레(10년 BEI) — FRED 단일(하루 지연)
    for key, fid, lab in (("real10", "DFII10", "10년 실질금리(TIPS)"), ("bei10", "T10YIE", "10년 기대인플레(BEI)")):
        try:
            rows = [r for r in fred(fid) if r[0] < us_cut][-25:]
            (d0, v0), (d1, v1) = rows[-1], rows[-2]
            out[key] = {"date": d0, "val": v0, "prev": v1, "chg_bp": round((v0 - v1) * 100, 1),
                        "chg20_bp": round((v0 - rows[0][1]) * 100, 1),
                        "src": f"FRED {fid}(미 재무부·연준) · 하루 지연 게시"}
            log(lab, "정상" if d0 >= (out.get("us10y") or {}).get("date", d0) else "지연값",
                f"<b>시도</b>: FRED {fid}. <b>반환</b>: {d0} {v0:.2f}%. <b>대체</b>: "
                + ("불필요." if d0 >= (out.get("us10y") or {}).get("date", d0)
                   else f"미국 최신 세션({(out.get('us10y') or {}).get('date')}) 값은 아직 미게시 — 직전 게시일 값으로 표기(날짜 병기)."))
        except Exception as e:
            log(lab, "실패", f"<b>시도</b>: FRED {fid}. <b>반환</b>: {e}. <b>대체</b>: 생략.")
    # 당일 실질금리 추정 = 10년 명목(네이버, 당일) − 10년 기대인플레(BEI, 당일) — TIPS 게시 지연 보완
    try:
        b, n10 = out.get("bei10"), out.get("us10y")
        if b and n10 and b["date"] == n10["date"]:
            est = n10["val"] - b["val"]
            prev_est = (n10["prev"] - b["prev"]) if b.get("prev") is not None else None
            out["real10_est"] = {"date": n10["date"], "val": round(est, 3),
                                 "chg_bp": round((est - prev_est) * 100, 1) if prev_est is not None else None,
                                 "src": "10년 명목(네이버) − 10년 BEI(FRED T10YIE) · 같은 날짜"}
            if out.get("real10"):
                chk = (n10["prev"] - (b.get("prev") or 0)) if b.get("prev") is not None else None
                log("10년 실질금리 추정 검증", "정상",
                    f"<b>시도</b>: 당일 추정(명목−BEI) {n10['date']} {est:.2f}%. <b>반환</b>: 직전일 추정 {chk:.2f}% vs "
                    f"TIPS 실측 {out['real10']['date']} {out['real10']['val']:.2f}%. <b>대체</b>: 표에는 TIPS 실측(날짜 병기)과 당일 추정을 함께 적는다.")
    except Exception:
        pass
    # 국고채 3년 — 네이버 단일
    try:
        rows = [r for r in naver_bond("KR3YT=RR", 10) if r["date"] <= D]
        out["kr3y"] = {"date": rows[0]["date"], "val": rows[0]["close"], "prev": rows[1]["close"],
                       "chg_bp": round((rows[0]["close"] - rows[1]["close"]) * 100, 1),
                       "src": "네이버 금융(KR3YT=RR) · 단일 소스"}
        if rows[0]["date"] != D:
            log("국고채 3년물", "지연값", f"<b>시도</b>: 네이버 KR3YT. <b>반환</b>: 최신 {rows[0]['date']}. <b>대체</b>: 날짜 병기.")
    except Exception as e:
        log("국고채 3년물", "실패", f"<b>시도</b>: 네이버 KR3YT. <b>반환</b>: {e}. <b>대체</b>: 생략.")
    return out


def _ann_fin(code):
    """연간 실적 컨센서스(Y 표시 열) — 올해·내년 EPS/영업이익."""
    try:
        j = _get(f"{NV}/api/stock/{code}/finance/annual")
        fi = j["financeInfo"]
        cols = [t for t in fi["trTitleList"]]
        out = {}
        for row in fi["rowList"]:
            if row["title"] in ("영업이익", "EPS", "당기순이익", "매출액"):
                out[row["title"]] = {c["title"]: num((row["columns"].get(c["key"]) or {}).get("value"))
                                     for c in cols}
        return {"cols": [(c["title"], c["isConsensus"]) for c in cols], "rows": out}
    except Exception:
        return None


def kr_stock(code, D):
    j = _get(f"{NV}/api/stock/{code}/integration")
    ti = {x["code"]: x["value"] for x in j.get("totalInfos", [])}
    cs = j.get("consensusInfo") or {}
    tr = _get(f"{NV}/api/stock/{code}/trend?pageSize=20")
    ser = [{"date": f'{r["bizdate"][:4]}-{r["bizdate"][4:6]}-{r["bizdate"][6:]}',
            "frn": num(r["foreignerPureBuyQuant"]), "inst": num(r["organPureBuyQuant"]),
            "close": num(r["closePrice"]), "hold": num(r.get("foreignerHoldRatio"))} for r in tr]
    ser = [s for s in ser if s["date"] <= D]
    for s in ser:
        s["frn_amt"] = round(s["frn"] * s["close"] / 1e8, 1) if s["frn"] is not None else None
        s["inst_amt"] = round(s["inst"] * s["close"] / 1e8, 1) if s["inst"] is not None else None
    # 다음 교차검증(외국인 순매수 수량)
    agree = None
    try:
        dm = _get(f"https://finance.daum.net/api/investor/days?symbolCode=A{code}&page=1&perPage=3&pagination=true", DAUM_REF)
        dd = {r["date"][:10]: r for r in dm["data"]}
        if ser and ser[0]["date"] in dd:
            a, b = ser[0]["frn"], dd[ser[0]["date"]]["foreignStraightPurchaseVolume"]
            agree = {"naver": a, "daum": b, "ok": _near(a, b, rel=0.03, abs_=20000)}
    except Exception:
        pass
    reps = [{"broker": r.get("bnm"), "title": r.get("tit"), "date": r.get("wdt")} for r in (j.get("researches") or [])[:4]]
    from pick_plus import _parse_cap
    return {"code": code, "date": ser[0]["date"] if ser else None, "mcap": _parse_cap(ti.get("marketValue")),
            "target_mean": num(cs.get("priceTargetMean")), "recomm": num(cs.get("recommMean")),
            "cons_date": cs.get("createDate"),
            "per": num(ti.get("per")), "fwd_per": num(ti.get("cnsPer")), "pbr": num(ti.get("pbr")),
            "eps": num(ti.get("eps")), "fwd_eps": num(ti.get("cnsEps")), "div": num(ti.get("dividendYieldRatio")),
            "hi52": num(ti.get("highPriceOf52Weeks")), "lo52": num(ti.get("lowPriceOf52Weeks")),
            "frn_5d_amt": round(sum((s["frn_amt"] or 0) for s in ser[:5]), 1),
            "frn_20d_amt": round(sum((s["frn_amt"] or 0) for s in ser[:20]), 1),
            "inst_5d_amt": round(sum((s["inst_amt"] or 0) for s in ser[:5]), 1),
            "inst_20d_amt": round(sum((s["inst_amt"] or 0) for s in ser[:20]), 1),
            "frn_streak": _streak([s["frn"] or 0 for s in ser]), "inst_streak": _streak([s["inst"] or 0 for s in ser]),
            "frn_hold": ser[0]["hold"] if ser else None, "frn_hold_20": ser[-1]["hold"] if ser else None,
            "series": ser[:10], "agree": agree, "reports": reps, "annual": _ann_fin(code),
            "src": "네이버 금융(컨센서스=FnGuide 집계 · 수급=한국거래소) · 외국인 수량은 다음 금융과 대조"}


def us_stock(ric):
    j = _get(f"{NVW}/stock/{ric}/integration")
    cs = j.get("consensusInfo") or {}
    return {"ric": ric, "target_mean": num(cs.get("priceTargetMean")), "target_hi": num(cs.get("priceTargetHigh")),
            "target_lo": num(cs.get("priceTargetLow")), "recomm": num(cs.get("recommMean")),
            "cons_date": cs.get("createDate"), "src": "네이버 금융 해외(Refinitiv 컨센서스)"}


US_RIC = {"GOOG": "GOOG.O", "SNDK": "SNDK.O", "MU": "MU.O", "NVDA": "NVDA.O", "AAPL": "AAPL.O", "AMD": "AMD.O",
          "AVGO": "AVGO.O", "META": "META.O", "AMZN": "AMZN.O", "NFLX": "NFLX.O", "TSLA": "TSLA.O", "TSM": "TSM",
          "ASML": "ASML.O", "MSFT": "MSFT.O"}


def ric_of(t):
    if t in US_RIC:
        return US_RIC[t]
    return t  # NYSE 종목은 접미사 없음 — 실패하면 .O 재시도


def cmd_collect(D, us_cut):
    import config as C
    t0 = time.time()
    ex = {"asof": D, "us_cut": us_cut, "made": dt.datetime.now().isoformat(timespec="seconds")}
    ex["flows"] = collect_flows(D)
    dates = [s["date"] for s in (ex["flows"].get("KOSPI") or {}).get("series", [])] or [D]
    with ThreadPoolExecutor(4) as pool:
        f_fut = pool.submit(collect_futures, D, dates)
        f_pb = pool.submit(collect_program_breadth, D)
        f_rt = pool.submit(collect_rates, D, us_cut)
        f_kr = {n: pool.submit(kr_stock, c, D) for n, c, t, cur in C.WATCH if cur == "₩"}
        f_us = {n: pool.submit(us_stock, ric_of(c)) for n, c, t, cur in C.WATCH if cur == "$"}
        ex["futures"] = f_fut.result()
        ex["program"] = f_pb.result()
        ex["rates"] = f_rt.result()
        ex["stocks"] = {}
        for n, f in list(f_kr.items()) + list(f_us.items()):
            try:
                ex["stocks"][n] = f.result()
            except Exception as e:
                log(f"{n} 컨센서스·수급", "실패", f"<b>시도</b>: 네이버 금융. <b>반환</b>: {e}. <b>대체</b>: 생략.")
    ex["log8"] = LOG
    json.dump(ex, open("extra.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    f = ex["flows"].get("KOSPI") or {}
    print(f"■ extra.json ({time.time()-t0:.0f}s) — 코스피 외국인 {f.get('frn', 0):+,.0f}억 · "
          f"K200선물 외국인 {(ex['futures'] or {}).get('frn', 0):+,.0f}억 · §8 {len(LOG)}건")
    return 0


# ════════════════════════════════════════════════════════════
# 3) merge — 야후 실측과 대조 후 data.json["extra"]로
# ════════════════════════════════════════════════════════════
def cmd_merge():
    D = json.load(open("data.json", encoding="utf-8"))
    ex = json.load(open("extra.json", encoding="utf-8"))
    L = ex.get("log8", [])
    mac = D.get("macro", {})
    # (a) 10년물: 야후 ^TNX × 네이버
    r10 = (ex.get("rates") or {}).get("us10y")
    t = mac.get("미국채10년") or {}
    if r10 and t.get("close"):
        diff = (t["close"] - r10["val"]) * 100
        same = t.get("date") == r10["date"]
        L.append({"item": "미 국채 10년 야후×네이버 대조", "kind": "정상" if (abs(diff) <= 5 and same) else "경고",
                  "detail": f"<b>시도</b>: 야후 ^TNX {t.get('date')} {t['close']:.3f}% × 네이버 {r10['date']} {r10['val']:.3f}%. "
                            f"<b>반환</b>: 차이 {diff:+.1f}bp{'' if same else ' · 날짜 다름'}. "
                            f"<b>대체</b>: {'불필요' if abs(diff) <= 5 and same else '표·서술은 야후값, 해석은 방향만'}."})
    # (b) EWY: 야후 × 네이버 + «간밤 한국 갭 시사» 산출
    ewy = mac.get("EWY") or {}
    try:
        j = _get(f"{NVW}/stock/EWY/basic")
        nvp = num(j.get("closePrice"))
        nvd = str(j.get("localTradedAt", ""))[:10]
        if nvd and ewy.get("date") and nvd != ewy.get("date"):
            nvp = None                      # 네이버가 다음(진행 중) 세션이면 대조 생략 — 날짜가 달라 비교 불가
            L.append({"item": "EWY 야후×네이버 대조", "kind": "정상",
                      "detail": f"<b>시도</b>: 야후 EWY {ewy.get('date')} × 네이버. <b>반환</b>: 네이버는 {nvd} 세션(진행 중/다음 세션)이라 날짜 불일치. "
                                f"<b>대체</b>: 대조 생략 — 표기값 = 야후 확정 종가."})
        if ewy.get("close") and nvp:
            same = abs(ewy["close"] / nvp - 1) <= 0.003
            L.append({"item": "EWY 야후×네이버 대조", "kind": "정상" if same else "경고",
                      "detail": f"<b>시도</b>: 야후 EWY {ewy.get('date')} ${ewy['close']:.2f} × 네이버 ${nvp:.2f}. "
                                f"<b>반환</b>: {'일치' if same else '불일치(네이버는 최신 세션일 수 있음)'}. <b>대체</b>: 표기값 = 야후."})
    except Exception as e:
        L.append({"item": "EWY 네이버 대조", "kind": "실패", "detail": f"<b>시도</b>: 네이버. <b>반환</b>: {e}. <b>대체</b>: 야후 단일."})
    if ewy.get("close"):
        rec = {r["d"]: r for r in (D.get("kospi") or {}).get("recent", [])}
        e_d = ewy.get("date", "")
        k_same = rec.get(e_d[5:].replace("-", "/"))
        fx = mac.get("원/달러") or {}
        # EWY(달러) ≈ 코스피(원) ÷ 환율 → 같은 날 코스피·환율 변화로 설명 안 되는 부분 = 미국 시간 새 정보
        if k_same:
            resid = ewy["chg_pct"] - (k_same["p"] - (fx.get("chg_pct") or 0))
            ex["ewy"] = {"date": e_d, "close": ewy["close"], "chg": ewy["chg_pct"], "kospi_same": k_same["p"],
                         "fx_chg": fx.get("chg_pct"), "resid": round(resid, 2),
                         "note": f"EWY {e_d} {ewy['chg_pct']:+.2f}% − (같은 날 코스피 {k_same['p']:+.2f}% − 원/달러 {fx.get('chg_pct', 0):+.2f}%)"}
        else:
            ex["ewy"] = {"date": e_d, "close": ewy["close"], "chg": ewy["chg_pct"], "kospi_same": None,
                         "resid": round(ewy["chg_pct"], 2),
                         "note": f"EWY {e_d} {ewy['chg_pct']:+.2f}% — 같은 날 코스피 세션 없음(휴장) → 등락 전체가 다음 개장 갭 시사분"}
    # (c) 외국인 선물+현물 «합성 방향» — 둘 다 같은 방향이면 신뢰도 높음
    fu, fl = ex.get("futures") or {}, (ex.get("flows") or {}).get("KOSPI") or {}
    if fu and fl:
        s1 = 1 if fl.get("frn", 0) > 0 else -1
        s2 = 1 if fu.get("frn", 0) > 0 else -1
        ex["foreign_combo"] = {"spot": fl.get("frn"), "fut": fu.get("frn"),
                               "label": ("현·선물 동반 매수" if s1 > 0 and s2 > 0 else
                                         "현·선물 동반 매도" if s1 < 0 and s2 < 0 else
                                         "현물 매도·선물 매수(엇갈림)" if s1 < 0 else "현물 매수·선물 매도(엇갈림)")}
    # (d) 강화 후보 종목 컨센서스(선정 카드 설명용)
    ex.setdefault("stocks", {})
    for n in D.get("enhance_kr", []):
        x = (D.get("kr") or {}).get(n)
        if x and n not in ex["stocks"]:
            try:
                ex["stocks"][n] = kr_stock(x["ticker"].split(".")[0], D["asof"])
            except Exception as e:
                L.append({"item": f"{n} 컨센서스", "kind": "실패", "detail": f"<b>시도</b>: 네이버. <b>반환</b>: {e}. <b>대체</b>: 생략."})
    for n in D.get("enhance_us", []):
        x = (D.get("us") or {}).get(n)
        if x and n not in ex["stocks"]:
            for ric in (ric_of(x["ticker"]), x["ticker"] + ".O", x["ticker"] + ".N"):
                try:
                    s = us_stock(ric)
                    if s.get("target_mean"):
                        ex["stocks"][n] = s
                        break
                except Exception:
                    continue
    ex["log8"] = L
    D["extra"] = ex
    D["log8"] = D.get("log8", []) + [l for l in L if l.get("kind") != "정상"] + \
        [l for l in L if l.get("kind") == "정상"]
    json.dump(D, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, default=str)
    print(f"■ data.json[extra] 병합 — §8 +{len(L)}건 · EWY 시사 {(ex.get('ewy') or {}).get('resid')}% · "
          f"외국인 조합 {(ex.get('foreign_combo') or {}).get('label')}")
    return 0


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else ""
    if m == "xcheck":
        sys.exit(cmd_xcheck(sys.argv[2]))
    if m == "collect":
        import asof as _A
        sys.exit(cmd_collect(sys.argv[2], os.environ.get("YF_US_CUT") or _A.us_cut()))
    if m == "merge":
        sys.exit(cmd_merge())
    print(__doc__)
    sys.exit(1)
