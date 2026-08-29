# -*- coding: utf-8 -*-
"""lib_idx.py — ★v51 지수 이중소스 대조 엔진 (yfinance × investing.com)"""
import json, os
import pandas as pd

XPATH = "index_xcheck.json"
TOL = 0.0005          # 종가 허용오차 0.05%
_X = None
LOG = []


def load(path=XPATH):
    global _X
    if _X is not None:
        return _X
    try:
        with open(path, encoding="utf-8") as f:
            _X = json.load(f)
    except Exception:
        _X = {}
    return _X


def asof(path=XPATH):
    return (load(path) or {}).get("asof")


def _bars(tk):
    b = (load() or {}).get("bars") or {}
    return b.get(tk) or []


def reconcile(tk, d, log=None, asof_pin=None):
    rows = _bars(tk)
    if d is None or len(d) == 0 or not rows:
        return d
    sink = LOG if log is None else log
    tz = getattr(d.index, "tz", None)
    have = {ts.strftime("%Y-%m-%d"): ts for ts in d.index}

    _rt = []
    for r in rows:
        ts0 = have.get(r.get("date"))
        iv = float(r.get("volume") or 0)
        if ts0 is not None and iv > 0:
            yv = float(d.at[ts0, "Volume"]) if "Volume" in d.columns else 0.0
            if yv > 0:
                _rt.append(yv / iv)
    vscale = sorted(_rt)[len(_rt) // 2] if _rt else 1.0

    fixed, added, shape, checked = [], [], [], 0
    for r in rows:
        ds = r.get("date")
        if not ds:
            continue
        if asof_pin and ds > str(asof_pin):
            continue
        px = float(r["close"])
        o, h, l = (float(r.get(k, px)) for k in ("open", "high", "low"))
        iv = float(r.get("volume") or 0)
        ts = have.get(ds)
        if ts is not None:
            checked += 1
            cur = float(d.at[ts, "Close"])
            bad_close = not cur or abs(cur / px - 1.0) > TOL
            bad_shape = False
            if not bad_close:
                for got, want in ((d.at[ts, "Open"], o), (d.at[ts, "High"], h), (d.at[ts, "Low"], l)):
                    if want and (not float(got) or abs(float(got) / want - 1.0) > TOL):
                        bad_shape = True
                if iv > 0 and "Volume" in d.columns and float(d.at[ts, "Volume"]) <= 0:
                    bad_shape = True
            if not bad_close and not bad_shape:
                continue
            if bad_close:
                fixed.append((ds, cur, px))
            else:
                shape.append(ds)
        else:
            ts = pd.Timestamp(ds, tz=tz) if tz is not None else pd.Timestamp(ds)
            added.append((ds, px))
        keep_vol = None
        if "Volume" in d.columns and ts in d.index:
            _v = float(d.at[ts, "Volume"] or 0)
            keep_vol = _v if _v > 0 else None
        for col in d.columns:
            if col == "Open":
                d.loc[ts, col] = o
            elif col == "High":
                d.loc[ts, col] = h
            elif col == "Low":
                d.loc[ts, col] = l
            elif col in ("Close", "Adj Close"):
                d.loc[ts, col] = px
            elif col == "Volume":
                _vv = keep_vol if keep_vol else iv * vscale
                d.loc[ts, col] = int(round(_vv)) if str(d[col].dtype).startswith("int") else float(_vv)
            else:
                d.loc[ts, col] = 0.0

    d = d.sort_index()
    if fixed or added or shape:
        det = []
        if fixed:
            det.append("종가 정정 " + " · ".join(
                f"{x[0]} {x[1]:,.2f}→{x[2]:,.2f}({(x[2]/x[1]-1)*100:+.2f}%)" for x in fixed))
        if added:
            det.append("결손 삽입 " + " · ".join(f"{x[0]} {x[1]:,.2f}" for x in added))
        if shape:
            det.append("봉 형태 복원(종가는 맞으나 시·고·저가 또는 거래량이 비어 있던 «껍데기 봉») "
                       + " · ".join(shape))
        sink.append({"item": f"{tk} 지수 이중소스 대조", "kind": "보정(investing.com 확정 종가)",
            "detail": f"<b>시도</b>: yfinance {tk} 일봉 — 직전 확정 거래일 봉이 없거나 "
                      f"인트라데이 재집계본(야후 ^KS11 인트라데이는 14:55에서 절단되어 "
                      f"종가가 아니라 장중 스냅샷이 잡힌다). "
                      f"<b>반환</b>: 대조 {checked}봉 중 불일치/결손/껍데기 {len(fixed)+len(added)+len(shape)}봉 — "
                      + " / ".join(det) + ". "
                      f"<b>대체</b>: 거래소 확정 종가를 싣는 <b>kr.investing.com 과거 데이터</b>로 "
                      f"해당 봉만 정정(허용오차 {TOL*100:.2f}%). 나머지 봉은 두 소스가 일치해 "
                      f"yfinance 원본을 그대로 유지 — 시세 정본은 여전히 yfinance다(계약2)."})
    elif checked:
        sink.append({"item": f"{tk} 지수 이중소스 대조", "kind": "정상",
            "detail": f"<b>시도</b>: yfinance {tk} 일봉 × kr.investing.com 확정 종가 {checked}봉 전수 대조. "
                      f"<b>반환</b>: 전 구간 일치(허용오차 {TOL*100:.2f}% 이내). "
                      f"<b>대체</b>: 불필요 — 정정 0건."})
    return d


def macro_fix(mac, log=None):
    sink = LOG if log is None else log
    ov = (load() or {}).get("macro") or {}
    for k, r in ov.items():
        m = mac.get(k)
        if not isinstance(m, dict) or "close" in m and m.get("err"):
            continue
        if not m or m.get("err"):
            continue
        px, ds = float(r["close"]), r.get("date")
        old, old_d = float(m.get("close", 0) or 0), m.get("date")
        if old and abs(old / px - 1.0) <= TOL and old_d == ds:
            sink.append({"item": f"{k} 이중소스 대조", "kind": "정상",
                "detail": f"<b>시도</b>: yfinance × kr.investing.com 대조. "
                          f"<b>반환</b>: {ds} {px:,.2f} 일치. <b>대체</b>: 불필요."})
            continue
        prev = float(r.get("prev") or m.get("prev") or 0)
        m["close"], m["date"] = px, ds
        if prev:
            m["prev"] = prev
            m["chg_pct"] = (px / prev - 1.0) * 100
        m["src"] = "investing.com 확정"
        sink.append({"item": f"{k} 이중소스 대조", "kind": "보정(investing.com 확정 종가)",
            "detail": f"<b>시도</b>: yfinance 계열(추종 ETF 스케일 복원 포함) → {old_d} {old:,.2f}. "
                      f"<b>반환</b>: 확정값과 {abs(old/px-1)*100:.2f}% 괴리. "
                      f"<b>대체</b>: kr.investing.com 확정 종가 {ds} <b>{px:,.2f}</b>로 정정. "
                      f"20일선·52주 고점은 기존 복원 계열 유지(참고용)."})
    return mac


def audit(data_asof=None):
    x = load() or {}
    if not x:
        return False, "index_xcheck.json 없음 — 지수 이중소스 대조를 수행하지 않았다"
    a = x.get("asof")
    if data_asof and a != data_asof:
        return False, f"index_xcheck.asof={a} vs data.asof={data_asof} — 직전 회차 대조 파일이다"
    n = sum(len(v) for v in (x.get("bars") or {}).values())
    return True, f"이중소스 대조 {n}봉 · 기준일 {a} · 출처 {x.get('source','?')}"
