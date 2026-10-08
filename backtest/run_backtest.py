# -*- coding: utf-8 -*-
"""
backtest/run_backtest.py — ★v66 강화 카드 선정·운용 규칙 백테스트 (2주 점검 · 지수 200일선 가동 조건) (chart_pick.py의 «같은 함수»로 재현)

  python3 backtest/run_backtest.py                 (저장소 루트에서 · 10년 데이터 · 약 10분 · 2코어)
  1) 유니버스(data.json의 kr/us) 일봉 10년을 받아 캐시(backtest/px10y.pkl, 3일 유효 — 저장소에 올리지 않는다)
  2) 2주마다(금요일) 그 시점까지의 데이터만으로: 차트 망가짐 필터(chart_pick.weekly_flags·passes) + 합성 모멘텀(mom_features)
  3) 종목 성적: 상위 3종의 60거래일 지수 대비 초과수익 — 구간별(하락·횡보·급락반등·하락장·상승장)
  4) 포트 운용: 3종 · 버퍼 10위 · 점검 주기 2주/4주 · 비상 손절 −25% · 비용 반영 → 구간별 연수익·최대 낙폭, 국·미 50:50
  → backtest/summary.json (build.py ⑤ 페이지 근거) · backtest/report.txt
  규칙을 바꾸면(chart_pick.py·config.REBAL_WEEKS) 반드시 다시 돌려 «규칙을 정할 때 안 본 구간(2018~2022)»에서도 지수를 이기는지 확인한다.
  한계: 유니버스가 «현재» 시총 상위 → 과거 성적이 실제보다 좋게 나온다(생존 편향). 숫자는 상한선으로 읽는다.
"""
import os, sys, json, pickle, time, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import chart_pick as CP
import config as C

HERE = os.path.join(ROOT, "backtest")
CACHE = os.path.join(HERE, "px10y.pkl")
COST = {"kr": 0.0025, "us": 0.0010}          # 왕복 비용(세금·수수료·슬리피지 근사)
ERAS = [("2018-06~2019-12 하락·횡보", "2018-06-01", "2019-12-31"), ("2020 코로나 급락·반등", "2020-01-01", "2020-12-31"),
        ("2021 고점권", "2021-01-01", "2021-12-31"), ("2022 하락장", "2022-01-01", "2022-12-31"),
        ("2023~2026 상승장", "2023-01-01", "2026-12-31")]
DESIGN = ("2023-06-01", "2024-12-31")        # 규칙을 고른 구간(이 밖은 규칙이 본 적 없는 구간)


def load_px():
    if os.path.exists(CACHE) and (time.time() - os.path.getmtime(CACHE)) < 3 * 86400:
        return pickle.load(open(CACHE, "rb"))
    import yfinance as yf
    D = json.load(open(os.path.join(ROOT, "data.json"), encoding="utf-8"))
    tk = {mk: {n: x["ticker"] for n, x in D[mk].items()} for mk in ("kr", "us")}
    px = {}
    for t in list(tk["kr"].values()) + list(tk["us"].values()) + ["^KS11", "^GSPC"]:
        try:
            d = yf.Ticker(t).history(period="10y", auto_adjust=False)
            d = d[~d.index.duplicated()].dropna(subset=["Close"])
            idx = d.index.tz_localize(None) if getattr(d.index, "tz", None) is not None else d.index
            d.index = idx.normalize()
            px[t] = d[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            print("  ⚠ 받기 실패", t, e)
    B = {"px": px, "tk": tk}
    pickle.dump(B, open(CACHE, "wb"))
    return B


B = load_px(); PX, TK = B["px"], B["tk"]
BEN = {"kr": PX["^KS11"]["Close"], "us": PX["^GSPC"]["Close"]}
EXCL = {"kr": set(C.EXCLUDE_KR), "us": set(C.EXCLUDE_US)}
CL = {t: d["Close"] for t, d in PX.items()}


def at(s, t):
    return s.iloc[s.index.searchsorted(t, side="right") - 1]


def fwd(s, t, n):
    i = s.index.searchsorted(t, side="right") - 1
    return None if i < 0 or i + n >= len(s) else float(s.iloc[i + n] / s.iloc[i] - 1)


def one_date(t):
    rows = []
    for mk in ("kr", "us"):
        for nm, tk in TK[mk].items():
            if nm in EXCL[mk] or tk not in PX:
                continue
            dd = PX[tk].loc[:t]
            if len(dd) < 420:
                continue
            f = CP.mom_features(dd.iloc[-520:])
            if not f:
                continue
            try:
                wf = CP.weekly_flags(CP.to_weekly(dd.iloc[-520:]))
            except Exception:
                wf = None
            if not wf:
                continue
            ok, _ = CP.passes(f, wf)
            a, b = fwd(CL[tk], t, 60), fwd(BEN[mk], t, 60)
            rows.append({"t": t, "mk": mk, "name": nm, "ok": ok, **{k: f[k] for k in ("mom12_1", "mom6_1", "slope126")},
                         "x60": None if a is None or b is None else a - b})
    return pd.DataFrame(rows)


def portfolio(P, mk, step=1, N=None, buf=None, stop=CP.EMERGENCY, regime=None):
    """점검일마다: 보유 중 10위 안·필터 통과면 유지, 빈자리는 순위대로(통과 종목이 모자라면 그만큼 현금).
       점검일 사이 비상 손절(진입가 −25%) — 손절된 자리는 다음 점검일까지 현금."""
    N = N or CP.PICK_N; buf = buf or CP.WATCH_K
    regime = getattr(C, "REGIME_MA", 200) if regime is None else regime     # 0이면 가동 조건 없음
    bma = BEN[mk].rolling(regime).mean() if regime else None
    G = P[P.mk == mk]; ts = sorted(G.t.unique())[::step]
    hold, ent, rows = [], {}, []
    for a, c in zip(ts[:-1], ts[1:]):
        rk = G[(G.t == a) & G.ok].set_index("name")["rank"].dropna().sort_values()
        on = (not regime) or at(BEN[mk], a) > at(bma, a)                   # ★v66 지수가 이평 아래면 전략 정지(현금)
        keep = [h for h in hold if h in rk.index and rk[h] <= buf] if on else []
        new = (keep + [n for n in rk.index if n not in keep][:max(0, N - len(keep))]) if on else []
        for n in new:
            if n not in keep:
                ent[n] = at(CL[TK[mk][n]], a)
        cost = COST[mk] / 2 * len(set(new) ^ set(hold)) / N
        rets = []
        for n in new:
            s = CL[TK[mk][n]]; lo = PX[TK[mk][n]]["Low"].loc[a:c].iloc[1:]
            sp = ent[n] * (1 - stop)
            if stop and len(lo) and lo.min() <= sp:
                rets.append(min(sp, at(s, a)) / at(s, a) - 1)
            else:
                rets.append(at(s, c) / at(s, a) - 1)
        r = (sum(rets) / N if rets else 0.0) - cost            # 빈자리는 현금(0%)
        rows.append((c, r, at(BEN[mk], c) / at(BEN[mk], a) - 1, len(new)))
        hold = new
    return pd.DataFrame(rows, columns=["t", "r", "br", "n"]).set_index("t")


def stats(R, ppy):
    if len(R) < 3:
        return None
    eq, beq = (1 + R.r).cumprod(), (1 + R.br).cumprod()
    ann = lambda x: ((1 + x).prod() ** (ppy / len(x)) - 1) * 100
    return {"연수익%": round(ann(R.r), 1), "지수%": round(ann(R.br), 1), "초과%p": round(ann(R.r) - ann(R.br), 1),
            "최대낙폭%": round(float((eq / eq.cummax() - 1).min() * 100), 1), "지수낙폭%": round(float((beq / beq.cummax() - 1).min() * 100), 1),
            "평균보유": round(float(R.n.mean()), 1) if "n" in R else None}


def main(start="2018-06-01", end="2026-08-21"):
    k = BEN["kr"].index
    dates = sorted({k[k <= f][-1] for f in pd.date_range(start, end, freq="2W-FRI")})
    t0 = time.time()
    from multiprocessing import Pool
    with Pool(max(1, os.cpu_count() or 1)) as p:
        parts = p.map(one_date, dates, chunksize=4)
    P = pd.concat([x for x in parts if len(x)], ignore_index=True)
    P["comp"] = 0.0
    for col in ("mom12_1", "mom6_1", "slope126"):
        P["comp"] += P.groupby(["t", "mk"])[col].rank(pct=True) / 3
    P["rank"] = P[P.ok].groupby(["t", "mk"]).comp.rank(ascending=False)
    P.to_pickle(os.path.join(HERE, "panel.pkl"))
    L = [f"기간 {min(dates).date()} ~ {max(dates).date()} · 2주 간격 시점 {len(dates)} · 계산 {time.time()-t0:.0f}s",
         f"규칙을 고른 구간 {DESIGN[0]}~{DESIGN[1]} — 그 밖(특히 2018~2022)은 규칙이 본 적 없는 구간"]
    S = {"period": f"{min(dates):%Y-%m}~{max(dates):%Y-%m}", "n_dates": len(dates), "pick": {}, "port": {}}

    L.append("\n■ 종목 성적 — 시점마다 규칙 상위3의 60일 지수 대비 초과수익 평균% (괄호: 유니버스 평균)")
    for lab, a_, b_ in ERAS:
        row = {}
        for mk in ("kr", "us"):
            g = P[(P.mk == mk) & (P.t >= a_) & (P.t <= b_)]
            top = g[g["rank"] <= 3].x60.dropna(); allv = g.x60.dropna()
            row[mk] = {"top3": round(top.mean() * 100, 1) if len(top) else None, "all": round(allv.mean() * 100, 1) if len(allv) else None,
                       "win": round(float((top > 0).mean() * 100), 0) if len(top) else None}
        S["pick"][lab] = row
        L.append(f"  {lab:<22} 국장 {row['kr']['top3']}({row['kr']['all']}) · 미장 {row['us']['top3']}({row['us']['all']})")

    RW = getattr(C, "REBAL_WEEKS", 2); RM = getattr(C, "REGIME_MA", 200)
    VARIANTS = [(f"채택: {RW}주·지수 {RM}일선 가동 조건", RW // 2 or 1, None), (f"비교: 가동 조건 없음({RW}주)", RW // 2 or 1, 0),
                ("비교: 4주·가동 조건", 2, None)]
    for nm, step, rg in VARIANTS:
        ppy = 26 / step
        K, U = portfolio(P, "kr", step, regime=rg), portfolio(P, "us", step, regime=rg)
        U2 = U.reindex(K.index, method="nearest")
        M = pd.DataFrame({"r": 0.5 * K.r + 0.5 * U2.r, "br": 0.5 * K.br + 0.5 * U2.br, "n": K.n + U2.n})
        S["port"][nm] = {"전체": {"kr": stats(K, ppy), "us": stats(U, ppy), "50:50": stats(M, ppy)}}
        L.append(f"\n■ 포트(3종·버퍼10·비상손절 −25%·비용) — {nm}")
        L.append(f"  전체   국장 {S['port'][nm]['전체']['kr']}\n         미장 {S['port'][nm]['전체']['us']}\n         50:50 {S['port'][nm]['전체']['50:50']}")
        for lab, a_, b_ in ERAS:
            sel = lambda R: R[(R.index >= a_) & (R.index <= b_)]
            e = {"kr": stats(sel(K), ppy), "us": stats(sel(U), ppy), "50:50": stats(sel(M), ppy)}
            S["port"][nm][lab] = e
            f_ = lambda d: "—" if not d else f"{d['연수익%']:+.0f}%(지수 {d['지수%']:+.0f}%, 낙폭 {d['최대낙폭%']:.0f}%, 평균 {d['평균보유']}종)"
            L.append(f"  {lab:<22} 국장 {f_(e['kr'])}\n  {'':<22} 미장 {f_(e['us'])}\n  {'':<22} 50:50 {f_(e['50:50'])}")
    rw = VARIANTS[0][0]
    best = S["port"][rw]["전체"]; nog = S["port"][VARIANTS[1][0]]["전체"]
    unseen = [lab for lab, a_, b_ in ERAS if b_ < DESIGN[0]]
    beat = sum(1 for lab in unseen for mk in ("kr", "us") if ((S["port"][rw][lab][mk] or {}).get("초과%p", -1) > 0))
    S["evidence"] = (f"10년 백테스트({S['period']}): 필터+합성 모멘텀 3종·버퍼 10위·{RW}주 점검·지수 {RM}일선 가동 조건 포트 연수익 "
                     f"국장 {best['kr']['연수익%']:+.0f}%(지수 {best['kr']['지수%']:+.0f}%) · 미장 {best['us']['연수익%']:+.0f}%(지수 {best['us']['지수%']:+.0f}%) · "
                     f"국·미 50:50 {best['50:50']['연수익%']:+.0f}%(최대 낙폭 {best['50:50']['최대낙폭%']:.0f}%). "
                     f"가동 조건이 없으면 50:50 최대 낙폭 {nog['50:50']['최대낙폭%']:.0f}%(국장 2018~19 횡보·하락 구간 큰 손실). "
                     f"규칙을 정할 때 안 본 2018~2022 구간 {len(unseen)}개×2시장 중 {beat}건에서 지수 이상.")
    S["run_at"] = time.strftime("%Y-%m-%d %H:%M")
    json.dump(S, open(os.path.join(HERE, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    open(os.path.join(HERE, "report.txt"), "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L)); print("\n" + S["evidence"]); print("→ backtest/summary.json · report.txt")


if __name__ == "__main__":
    main(*sys.argv[1:3])
