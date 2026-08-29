# -*- coding: utf-8 -*-
"""
mkchart.py — 차트 11장(KOSPI + 관찰4 + 강화6) 일괄 생성.
공통 규격(2-4): 6개월 일봉 + 구름 26봉 미래투영 · 이평 3중 · 볼린저 · 일목 3요소 · ★MACD(12·26·9) 서브차트 · DPI≥150
※ 부록 C-1(구름 미래투영)·C-2(한글 폰트) 검증본 내장.
실행: python3 mkchart.py     (data.json의 enhance_kr/us를 읽어 자동으로 11장)
"""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib import font_manager as fm
import yfinance as yf, pandas as pd, numpy as np, json, os, warnings
import lib_idx                      # ★v51 본문(build)과 차트가 같은 대조를 통과해야 한다
warnings.filterwarnings("ignore")
from lib_ind import *
from lib_ind import stop_tiers, chart_levels
import config as C

# ── 부록 C-2: 한글 폰트 (외부 URL 다운로드 금지 — apt fonts-nanum 단일 페이스) ──
fm.fontManager.addfont(C.FONT_PATH)
plt.rcParams["font.family"] = "NanumGothic"
plt.rcParams["axes.unicode_minus"] = False

N, FUT = C.CHART_BARS, C.CHART_FUTURE

# ★v41: 차트도 data.json의 기준일(as-of)로 절단한다.
#   v40까지 차트만 실시간 봉을 물어와 "직전봉"이 당일 미완성 봉으로 찍히는 불일치가 있었다.
try:
    ASOF = json.load(open("data.json"))["asof"]
except Exception:
    ASOF = None

def _fill_lagging_session(tk, d):
    """★2026-08-13: fetch_all.py와 동일한 보정. 지수 일봉이 직전 확정 거래일을
       누락하면 같은 yfinance 인트라데이의 '종료된 세션'만 집계해 채운다.
       본문(build.py)은 data.json을, 차트는 yfinance를 각각 읽으므로
       이 보정을 양쪽에 똑같이 걸어야 숫자가 어긋나지 않는다."""
    try:
        for iv in ("5m", "1h"):
            x = yf.Ticker(tk).history(period="7d", interval=iv, auto_adjust=False)
            if x is None or len(x) == 0:
                continue
            x = x.dropna(subset=["Close"])
            g = x.groupby(x.index.normalize())
            agg = pd.DataFrame({"Open": g["Open"].first(), "High": g["High"].max(),
                                "Low": g["Low"].min(), "Close": g["Close"].last(),
                                "Volume": g["Volume"].sum()})
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
            return d.sort_index()
    except Exception:
        pass
    return d

def _volume_profile(H_, L_, V_, bins=46):
    """매물대(Volume Profile) — 표시구간의 거래량을 가격대별로 쌓는다.
       각 봉의 거래량을 그 봉의 고가~저가 구간에 균등 배분하는 표준 방식.
       반환: (구간 중심가 배열, 거래량 배열, POC, VAH, VAL)
       POC = 거래가 가장 많이 쌓인 가격대(= 가장 강한 지지/저항)
       VAH/VAL = 전체 거래량의 70%가 몰린 구간(Value Area)의 상·하단"""
    lo, hi = float(np.nanmin(L_)), float(np.nanmax(H_))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins + 1)
    mids = (edges[:-1] + edges[1:]) / 2.0
    vol = np.zeros(bins)
    for i in range(len(H_)):
        a, b = L_[i], H_[i]
        vv = float(V_[i]) if np.isfinite(V_[i]) else 0.0
        if vv <= 0:
            continue
        j0 = max(0, int(np.searchsorted(edges, a, "right") - 1))
        j1 = min(bins - 1, int(np.searchsorted(edges, b, "right") - 1))
        if j1 < j0:
            j0 = j1 = max(0, min(bins - 1, j0))
        vol[j0:j1 + 1] += vv / (j1 - j0 + 1)
    if vol.sum() <= 0:
        return None
    poc = int(np.argmax(vol))
    tot, target = vol.sum(), vol.sum() * 0.70
    lo_i = hi_i = poc; acc = vol[poc]
    while acc < target and (lo_i > 0 or hi_i < bins - 1):
        dn = vol[lo_i - 1] if lo_i > 0 else -1
        up = vol[hi_i + 1] if hi_i < bins - 1 else -1
        if up >= dn:
            hi_i += 1; acc += vol[hi_i]
        else:
            lo_i -= 1; acc += vol[lo_i]
    return mids, vol, float(mids[poc]), float(edges[hi_i + 1]), float(edges[lo_i])


def _unfilled_gaps(O, H_, L_, Cl):
    """미충족 갭 — 메워지지 않은 갭은 그 자체가 지지(갭업)·저항(갭다운)으로 작동한다.
       갭업: 오늘 저가 > 어제 고가 → 그 사이 구간이 '빈 공간' = 되돌림 시 지지
       갭다운: 오늘 고가 < 어제 저가 → 그 사이 구간 = 반등 시 저항
       이후 봉이 그 구간을 통과했으면 '충족'된 것으로 보고 버린다."""
    out = []
    n = len(H_)
    for i in range(1, n):
        if L_[i] > H_[i - 1]:
            zl, zh, kind = H_[i - 1], L_[i], "up"
        elif H_[i] < L_[i - 1]:
            zl, zh, kind = H_[i], L_[i - 1], "dn"
        else:
            continue
        if (zh / zl - 1) < 0.008:          # 0.8% 미만은 노이즈
            continue
        later = slice(i + 1, n)
        filled = (np.nanmin(L_[later]) <= zl) if kind == "up" and i + 1 < n else \
                 ((np.nanmax(H_[later]) >= zh) if kind == "dn" and i + 1 < n else False)
        if not filled:
            out.append((kind, float(zl), float(zh), i))
    return out


def _pivots(H_, L_, w=5):
    """스윙 고점·눌림목(스윙 저점) — 좌우 w봉보다 높거나 낮은 지점.
       '눌림목'은 상승 중 되돌림이 멈췄던 자리이며, 재차 눌릴 때 지지로 쓰인다."""
    hs, ls = [], []
    n = len(H_)
    for i in range(w, n - w):
        seg_h, seg_l = H_[i - w:i + w + 1], L_[i - w:i + w + 1]
        if H_[i] >= np.nanmax(seg_h): hs.append((i, float(H_[i])))
        if L_[i] <= np.nanmin(seg_l): ls.append((i, float(L_[i])))
    return hs, ls


def draw(tk, title, path, avg=None, levels=None, annotate=False, stops=None):
    d = yf.Ticker(tk).history(period="2y", auto_adjust=False)
    d = d[~d.index.duplicated()].dropna(subset=["Close"])
    d = _fill_lagging_session(tk, d)
    d = lib_idx.reconcile(tk, d, None, ASOF)   # ★v51 fetch_all과 동일한 이중소스 대조
    if ASOF:
        _ix = d.index.tz_localize(None) if getattr(d.index, "tz", None) is not None else d.index
        d = d[_ix <= pd.Timestamp(ASOF)]
    c, h, l, o, v = d["Close"], d["High"], d["Low"], d["Open"], d["Volume"]
    ub, mb, lb, _ = boll(c)
    conv, base, sA, sB = ichimoku_raw(d)
    ma10, ma20, ma60 = sma(c,10), sma(c,20), sma(c,60)
    n = min(N, len(d)); idx = d.index[-n:]
    x = np.arange(n + FUT)

    # ── 부록 C-1: 구름 26봉 미래투영 (today 끊김 버그 봉쇄) ──
    A_, B_ = list(sA), list(sB); start = len(A_) - n
    sa, sb = [], []
    for p in range(n + FUT):
        j = start + p - 26
        sa.append(A_[j] if 0 <= j < len(A_) and pd.notna(A_[j]) else np.nan)
        sb.append(B_[j] if 0 <= j < len(B_) and pd.notna(B_[j]) else np.nan)
    sa, sb = np.array(sa, float), np.array(sb, float)

    O, Cl, H_, L_, V_ = (o[-n:].values, c[-n:].values, h[-n:].values,
                         l[-n:].values, v[-n:].values)
    CUR = float(Cl[-1])

    # ══ ★v45: 4분할 레이아웃 ══════════════════════════════════
    #   좌상 = 가격  /  우상 = 매물대  /  좌하 = MACD  /  우 전체하단 = 레벨 보드
    #   레벨 정보를 캔들 위가 아니라 '전용 패널'로 빼는 것이 이번 개정의 핵심이다.
    fig = plt.figure(figsize=(11.8, 7.05), dpi=190)
    gsp = fig.add_gridspec(2, 3, width_ratios=[4.85, 0.72, 1.92],
                           height_ratios=[3.10, 1.02], wspace=0.045, hspace=0.15)
    ax  = fig.add_subplot(gsp[0, 0])
    axP = fig.add_subplot(gsp[0, 1], sharey=ax)
    ax2 = fig.add_subplot(gsp[1, 0], sharex=ax)
    axL = fig.add_subplot(gsp[:, 2])
    for a in (fig, ax, axP, ax2, axL):
        try: a.set_facecolor("white")
        except AttributeError: a.patch.set_facecolor("white")

    def _fmt(val):
        return f"{val:,.0f}" if abs(val) >= 100 else f"{val:,.2f}"
    RTAG = []      # ★v45: 가격 패널 우측 태그는 전부 여기 모아 한 번에 배치(겹침 봉쇄)

    # ── 구름 + 캔들 + 곡선 ────────────────────────────────────
    ax.fill_between(x, sa, sb, where=sa >= sb, color="#bcd8ff", alpha=.40, interpolate=True, zorder=1)
    ax.fill_between(x, sa, sb, where=sa <  sb, color="#ffd6ac", alpha=.40, interpolate=True, zorder=1)
    for i in range(n):
        col = "#e8453c" if Cl[i] >= O[i] else "#2f6fed"   # red=상승 / blue=하락 (한국식)
        ax.vlines(i, L_[i], H_[i], color=col, lw=0.75, zorder=4)
        ax.add_patch(plt.Rectangle((i-0.32, min(O[i], Cl[i])), 0.64,
                     max(abs(Cl[i]-O[i]), (H_[i]-L_[i])*0.004),
                     facecolor=col, edgecolor=col, lw=0.4, zorder=4))
    xi = np.arange(n)
    ax.plot(xi, ma10[-n:].values, color="#0aa6b8", lw=1.2, label="10일선", zorder=5)
    ax.plot(xi, ma20[-n:].values, color="#f5a300", lw=1.2, label="20일선", zorder=5)
    ax.plot(xi, ma60[-n:].values, color="#7b3fe4", lw=1.2, label="60일선", zorder=5)
    ax.plot(xi, ub[-n:].values, color="#9aa5b1", lw=0.8, ls="--", alpha=.6, label="볼린저(20,2σ)", zorder=3)
    ax.plot(xi, lb[-n:].values, color="#9aa5b1", lw=0.8, ls="--", alpha=.6, zorder=3)
    ax.plot(xi, conv[-n:].values, color="#2e9e5b", lw=1.0, label="전환선(9)", zorder=5)
    ax.plot(xi, base[-n:].values, color="#e26aa5", lw=1.0, ls=":", label="기준선(26)", zorder=5)

    # ── 매물대 ────────────────────────────────────────────────
    VP = _volume_profile(H_, L_, V_)
    POC = VAH = VAL = None
    if VP:
        mids, vol, POC, VAH, VAL = VP
        bh = (mids[1] - mids[0]) * 0.92 if len(mids) > 1 else 1.0
        cols = ["#C9A227" if abs(m - POC) < 1e-9 else "#AEC3DC" for m in mids]
        axP.barh(mids, vol, height=bh, color=cols, alpha=.85, edgecolor="none")
        axP.axhspan(VAL, VAH, color="#C9A227", alpha=.07, zorder=0)
        # 가격 패널에도 Value Area를 아주 옅게 깔아 '거래가 몰린 띠'를 보이게 한다
        ax.axhspan(VAL, VAH, color="#C9A227", alpha=.055, zorder=0)
        ax.axhline(POC, color="#B8860B", lw=1.25, ls="-", alpha=.75, zorder=6)
        RTAG.append((POC, "POC", "#8A6508"))
    axP.invert_xaxis()
    axP.set_title("매물대", fontsize=10.2, color="#5A6570", pad=3)
    axP.tick_params(left=False, labelleft=False, bottom=False, labelbottom=False)
    for sp in ("top", "right", "bottom"): axP.spines[sp].set_visible(False)
    axP.spines["left"].set_color("#DCE5F0")
    axP.grid(False)

    # ── 미충족 갭 · 스윙 ──────────────────────────────────────
    GAPS = _unfilled_gaps(O, H_, L_, Cl)
    for kind, zl, zh, gi in GAPS[-2:]:
        ax.axhspan(zl, zh, color=("#1E8449" if kind == "up" else "#C0392B"), alpha=.09, zorder=2)
    PH, PL = _pivots(H_, L_)
    hi_i = int(np.argmax(H_)); hi_v = float(H_[hi_i])
    ax.plot([hi_i], [hi_v], marker="v", ms=7, color="#7B2418", zorder=9)
    if PL:
        _pi, _pv = PL[-1]
        ax.plot([_pi], [_pv], marker="^", ms=7, color="#12325B", zorder=9)

    # ── 보유 종목: 평단선 + 손절 '구간'(3선 → 밴드 1개) ────────
    #   ★v45: 손절 3단선은 앵커 규격상 −1~2%에 밀집해 차트에서 한 선으로 보였다.
    #          선 3개를 지우고 '손절 구간' 음영 1개 + 최종선만 남긴다. 숫자는 레벨 보드와 본문 표에.
    if stops:
        _sv = sorted([v for _, _, v in stops])
        ax.axhspan(_sv[0], _sv[-1], color="#E67E22", alpha=.16, zorder=2)
        ax.axhline(_sv[0], color="#E67E22", lw=1.15, ls=(0, (3, 2)), alpha=.9, zorder=6)
        RTAG.append((_sv[0], "손절", "#8C4A06"))
    if avg:
        ax.axhline(avg, color="#C0392B", lw=1.5, ls="--", alpha=.95, zorder=7)
        RTAG.append((float(avg), "평단", "#8E1B12"))

    # ══ 레벨 후보 집계 — 차트 전용 확장 세트 ═══════════════════
    CAND = [("20일선", float(ma20.iloc[-1])), ("10일선", float(ma10.iloc[-1])),
            ("60일선", float(ma60.iloc[-1])),
            ("볼린저 상단", float(ub.iloc[-1])), ("볼린저 중심", float(mb.iloc[-1])),
            ("볼린저 하단", float(lb.iloc[-1])),
            ("일목 전환선", float(conv.iloc[-1])), ("일목 기준선", float(base.iloc[-1]))]
    _ct, _cb = float(np.nanmax([sa[n-1], sb[n-1]])), float(np.nanmin([sa[n-1], sb[n-1]]))
    CAND += [("일목 구름 상단", _ct), ("일목 구름 하단", _cb)]
    if POC:
        CAND += [("매물대 POC", POC), ("매물대 상단", VAH), ("매물대 하단", VAL)]
    CAND += [("22봉 고점", float(np.nanmax(H_[-22:]))), ("22봉 저점", float(np.nanmin(L_[-22:]))),
             ("표시구간 고점", hi_v)]
    for kind, zl, zh, gi in GAPS[-3:]:
        CAND.append((f"미충족 갭 {'지지' if kind=='up' else '저항'}", zl if kind == "up" else zh))
    if PL: CAND.append(("직전 눌림목", PL[-1][1]))
    if PH: CAND.append(("직전 스윙 고점", PH[-1][1]))
    if avg: CAND.append(("평단", float(avg)))
    if stops: CAND.append(("손절 최종선", float(min(v for _, _, v in stops))))

    def _pick(above):
        # ★v45: 현재가 ±25% 밖의 레벨은 매매 판단에 쓰이지 않으므로 보드에서 제외한다.
        #   (2026-08-13 실증: SK하이닉스 지지 목록이 −42%·−47%로 채워져 실용성이 0이었다)
        out, seen = [], []
        pool = [(nm, vv) for nm, vv in CAND if np.isfinite(vv) and abs(vv/CUR - 1) <= 0.25 and
                ((vv > CUR) if above else (vv <= CUR))]
        pool.sort(key=lambda t: (t[1] if above else -t[1]))
        for nm, vv in pool:
            if any(abs(vv / s - 1) < 0.004 for s in seen):   # 0.4% 이내 중복은 접는다
                continue
            seen.append(vv); out.append((nm, vv))
            if len(out) >= 6: break
        return out
    RES, SUP = _pick(True), _pick(False)

    # ── 가격 패널에는 「가장 가까운 저항1·지지1」만 선으로 ────
    if RES:
        ax.axhline(RES[0][1], color="#C0392B", lw=1.25, ls=(0, (7, 3)), alpha=.8, zorder=6)
        RTAG.append((RES[0][1], "R1", "#C0392B"))
        ax.axhspan(CUR, RES[0][1], color="#1E8449", alpha=.05, zorder=0)
    if SUP:
        ax.axhline(SUP[0][1], color="#245DA3", lw=1.25, ls=(0, (7, 3)), alpha=.8, zorder=6)
        RTAG.append((SUP[0][1], "S1", "#245DA3"))
        ax.axhspan(SUP[0][1], CUR, color="#C0392B", alpha=.05, zorder=0)

    # ── 우측 태그 일괄 배치 — 값 순 정렬 후 최소 간격 강제 ──
    _lo2 = float(np.nanmin([np.nanmin(L_)] + [t[0] for t in RTAG])) if RTAG else float(np.nanmin(L_))
    _hi2 = float(np.nanmax([np.nanmax(H_)] + [t[0] for t in RTAG])) if RTAG else float(np.nanmax(H_))
    _sp2 = max(1e-9, _hi2 - _lo2)
    RTAG.sort(key=lambda t: t[0])
    _pv = None
    for _val, _txt, _col in RTAG:
        _yy = _val if _pv is None else max(_val, _pv + _sp2 * 0.052)
        _pv = _yy
        ax.annotate(_txt, xy=(n + FUT - 0.5, _yy), ha="right", va="center",
                    fontsize=9.0, color=_col, fontweight="bold", zorder=11,
                    bbox=dict(boxstyle="round,pad=0.16", fc="white", ec=_col, lw=0.6, alpha=.90))

    ax.axvline(n-1, color="#333", lw=0.9, ls="-.", alpha=.7, zorder=6)
    ax.annotate("today", xy=(n-1, 1.0), xycoords=("data", "axes fraction"),
                xytext=(2, -11), textcoords="offset points",
                fontsize=9.2, color="#555", fontweight="bold", va="top")

    # ══ 헤더 3단(제목 → 직전봉 실측 → 범례) — 전부 플롯 영역 '밖' ══
    ax.set_title(title, fontsize=15.0, fontweight="bold", color="#12325B", pad=40, loc="left")
    if annotate:
        chg = (Cl[-1]/Cl[-2]-1)*100 if n >= 2 else 0.0
        ccol = "#E8453C" if chg >= 0 else "#2F6FED"
        ax.text(0.0, 1.078,
                f"직전봉 {idx[-1].strftime('%Y-%m-%d')}   종가 {_fmt(CUR)} ({chg:+.2f}%)   "
                f"시 {_fmt(O[-1])} · 고 {_fmt(H_[-1])} · 저 {_fmt(L_[-1])}   "
                f"│  ▼표시구간 고점 {_fmt(hi_v)}({idx[hi_i].strftime('%m/%d')})"
                + (f"   │  ▲직전 눌림목 {_fmt(PL[-1][1])}({idx[PL[-1][0]].strftime('%m/%d')})" if PL else ""),
                transform=ax.transAxes, ha="left", va="bottom",
                fontsize=10.0, color="#12325B", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.28", fc="#FFFDF0", ec=ccol, lw=1.0, alpha=.96))
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.004), ncol=7,
              fontsize=9.2, frameon=False, handlelength=1.7, columnspacing=1.3)
    ax.grid(alpha=.12, lw=.55); ax.set_xlim(-1, n+FUT)
    ax.tick_params(labelsize=9.6, labelbottom=False)      # x라벨은 MACD 패널에만
    # ★v45: 백만 단위에서 matplotlib이 붙이는 '1e6' 오프셋 표기를 제거하고 천단위 콤마로 고정
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(
        lambda vv, _: f"{vv:,.0f}" if abs(vv) >= 100 else f"{vv:,.2f}"))

    # ══ ★v45 레벨 보드 — 캔들을 가리지 않는 전용 패널 ══════════
    axL.axis("off")
    rows = []
    rows.append(("hdr", "◆ 저항 (위쪽 · 가까운 순)", "", ""))
    for i, (nm, vv) in enumerate(RES[:5][::-1]):
        rows.append(("res", f"R{len(RES[:5])-i}", nm, f"{_fmt(vv)}  {(vv/CUR-1)*100:+.1f}%"))
    rows.append(("cur", "현재가", "", _fmt(CUR)))
    for i, (nm, vv) in enumerate(SUP[:5]):
        rows.append(("sup", f"S{i+1}", nm, f"{_fmt(vv)}  {(vv/CUR-1)*100:+.1f}%"))
    rows.append(("hdr", "◆ 지지 (아래쪽 · 가까운 순)", "", ""))
    # 지지 헤더를 목록 위로 올리기 위해 순서 재배치
    _h = rows.pop()
    _ci = [i for i, r in enumerate(rows) if r[0] == "cur"][0]
    rows.insert(_ci + 1, _h)

    axL.text(0.5, 0.985, "레벨 보드", ha="center", va="top", fontsize=12.4,
             fontweight="bold", color="#12325B", transform=axL.transAxes)
    axL.text(0.5, 0.955, "이평 · 볼린저 · 일목 · 매물대 · 갭 · 스윙 통합",
             ha="center", va="top", fontsize=8.4, color="#6B7680", transform=axL.transAxes)
    y = 0.930
    for kind, a1, a2, a3 in rows:
        if kind == "hdr":
            y -= 0.012
            axL.text(0.02, y, a1, ha="left", va="top", fontsize=9.6,
                     fontweight="bold", color="#5A6570", transform=axL.transAxes)
            y -= 0.038
        elif kind == "cur":
            axL.add_patch(plt.Rectangle((0.01, y - 0.042), 0.98, 0.046, transform=axL.transAxes,
                                        facecolor="#FFF6D6", edgecolor="#E0A800", lw=0.8, zorder=0))
            axL.text(0.04, y - 0.006, "현재가", ha="left", va="top", fontsize=11.0,
                     fontweight="bold", color="#12325B", transform=axL.transAxes)
            axL.text(0.96, y - 0.006, a3, ha="right", va="top", fontsize=11.0,
                     fontweight="bold", color="#12325B", transform=axL.transAxes)
            y -= 0.052
        else:
            col = "#C0392B" if kind == "res" else "#245DA3"
            axL.text(0.035, y, a1, ha="left", va="top", fontsize=9.4,
                     fontweight="bold", color=col, transform=axL.transAxes)
            axL.text(0.175, y, (a2[:9] + "…") if len(a2) > 10 else a2, ha="left", va="top", fontsize=9.0,
                     color="#1c2530", transform=axL.transAxes)
            axL.text(0.965, y, a3, ha="right", va="top", fontsize=9.0,
                     fontweight="bold", color=col, transform=axL.transAxes)
            y -= 0.041
    y -= 0.014
    axL.plot([0.02, 0.98], [y, y], color="#DCE5F0", lw=0.9, transform=axL.transAxes)
    y -= 0.026
    _notes = []
    if POC: _notes.append(f"매물대 POC {_fmt(POC)} — 거래가 가장 많이 쌓인 가격대")
    if GAPS:
        _k, _zl, _zh, _gi = min(GAPS, key=lambda g: abs((g[1]+g[2])/2 / CUR - 1))
        _notes.append(f"미충족 갭 {_fmt(_zl)}~{_fmt(_zh)} ({idx[_gi].strftime('%m/%d')}) "
                      f"— {'되돌림 시 지지' if _k=='up' else '반등 시 저항'}")
    if stops:
        _sv = sorted(v for _, _, v in stops)
        _notes.append(f"손절 구간 {_fmt(_sv[0])}~{_fmt(_sv[-1])} (3단 분할 · 종가 기준)")
    if avg:
        _notes.append(f"평단 {_fmt(avg)} — 현재가 대비 {(CUR/avg-1)*100:+.2f}%")
    _notes.append("음영: 초록=상방 여백 · 붉은색=하방 여백 · 금색 띠=매물대 밀집")
    for t in _notes:
        axL.text(0.035, y, "· " + t, ha="left", va="top", fontsize=8.2,
                 color="#5A6570", transform=axL.transAxes, wrap=True)
        y -= 0.046
    axL.add_patch(plt.Rectangle((0.005, 0.005), 0.99, 0.99, transform=axL.transAxes,
                                fill=False, edgecolor="#C9D8EC", lw=1.0))

    # ── 서브차트 = MACD 오실레이터(12·26·9) ───────────────────
    _c = d["Close"]
    _ef, _es = _c.ewm(span=12, adjust=False).mean(), _c.ewm(span=26, adjust=False).mean()
    _macd = _ef - _es
    _sig = _macd.ewm(span=9, adjust=False).mean()
    _hist = (_macd - _sig)[-n:].values
    _m, _s = _macd[-n:].values, _sig[-n:].values
    hc = ["#e8453c" if hh >= 0 else "#2f6fed" for hh in _hist]
    ax2.bar(xi, _hist, color=hc, alpha=.60, width=.72, label="히스토그램(MACD - 시그널)")
    ax2.plot(xi, _m, color="#12325B", lw=1.3, label="MACD(12,26)")
    ax2.plot(xi, _s, color="#E67E22", lw=1.1, ls="--", label="시그널(9)")
    ax2.axhline(0, color="#444", lw=.9, alpha=.75)
    ax2.axvline(n-1, color="#333", lw=.9, ls="-.", alpha=.7)
    _st = ("골든크로스(MACD>시그널)" if _m[-1] > _s[-1] else "데드크로스(MACD<시그널)")
    _tr = ("확대" if _hist[-1] > _hist[-2] else "축소") if n >= 2 else "—"
    ax2.text(1.0, 1.03,
             f"직전봉 MACD {_m[-1]:,.1f} · 시그널 {_s[-1]:,.1f} · 히스토 {_hist[-1]:+,.1f}({_tr}) → {_st}",
             transform=ax2.transAxes, ha="right", va="bottom",
             fontsize=9.0, color="#12325B", fontweight="bold")
    ax2.legend(loc="upper left", fontsize=8.6, ncol=3, framealpha=.85)
    ax2.grid(alpha=.12, lw=.55)
    ax2.tick_params(labelsize=9.6); ax2.set_xlim(-1, n+FUT)

    pos, labs, step = [], [], max(1, (n+FUT)//9)
    for p in range(0, n+FUT, step):
        pos.append(p); labs.append(idx[p].strftime("%m/%d") if p < n else "+%d" % (p-n+1))
    ax2.set_xticks(pos); ax2.set_xticklabels(labs, fontsize=9.2)
    plt.savefig(path, facecolor="white", bbox_inches="tight"); plt.close()
    return path

if __name__ == "__main__":
    os.makedirs("charts", exist_ok=True)
    D = json.load(open("data.json"))
    # ★v49: 유니버스가 시총 상위 150위로 동적 구성되므로 티커는 data.json에서 읽는다
    ALL = {**C.KR_UNIVERSE, **C.US_UNIVERSE,
           **{k: v["ticker"] for k, v in D.get("kr", {}).items()},
           **{k: v["ticker"] for k, v in D.get("us", {}).items()}}
    # ★v41: KOSPI 차트에 레벨 수평선·직전봉 주석·시나리오 밴드를 얹는다(사용자 피드백 3).
    K = D["kospi"]
    SRC = [("20일선", K["ma20"]), ("일목 구름 상단", K["ctop"]), ("60일선", K["ma60"]),
           ("일목 구름 하단", K["cbot"]), ("볼린저 하단", K["bb_low"]), ("최근 22봉 저점", K["lo22"])]
    _up = sorted([t for t in SRC if t[1] >  K["close"]], key=lambda t:  t[1])
    _dn = sorted([t for t in SRC if t[1] <= K["close"]], key=lambda t: -t[1])
    KLV = [(f"저항{i+1}", nm, v) for i, (nm, v) in enumerate(_up)] + \
          [(f"지지{i+1}", nm, v) for i, (nm, v) in enumerate(_dn)]
    json.dump(KLV, open("charts/kospi_levels.json", "w"), ensure_ascii=False)
    jobs = [("^KS11", "KOSPI 일봉 — 레벨 보드(이평·볼린저·일목·매물대·갭·스윙) + 직전봉 실측",
             "charts/kospi.png", None, KLV, None)]
    POS = getattr(C, "POSITIONS", {})
    ALLX = {**D["kr"], **D["us"], **D.get("holdings", {})}
    def _lv(nm):
        return chart_levels(ALLX[nm]) if nm in ALLX else None
    def _st(nm):
        """★v42: 보유 종목 차트에 손절 3단선을 얹는다(본문 표와 같은 숫자 — lib_ind 공용 엔진)."""
        if nm not in POS or nm not in ALLX:
            return None
        S = stop_tiers(ALLX[nm], POS[nm]["avg"], C.STOP_CAP, C.ATR_K_TABLE,
                       C.STOP_FRAC, C.STOP_QTY, C.STOP_SNAP)
        return [(lab, src, v) for lab, src, v, _ in S["tiers"]]
    for nm, code, tk, _ in C.WATCH:
        tag = "핵심 보유" if nm in POS else "핵심 관찰"
        jobs.append((tk, f"{nm}({code}) 일봉 — {tag} · 레벨 보드", f"charts/{code}.png",
                     POS.get(nm, {}).get("avg"), _lv(nm), _st(nm)))
    for nm in D["enhance_kr"] + D["enhance_us"]:
        jobs.append((ALLX and ALL[nm], f"{nm} 일봉 — 강화 카드 · 레벨 보드",
                     f"charts/{ALL[nm].replace('.','_')}.png", None, _lv(nm), None))
    for i, (tk, ti, p, av, lv, st) in enumerate(jobs):
        draw(tk, ti, p, av, levels=lv, annotate=True, stops=st)
        print(f"  [{i+1:2d}/{len(jobs)}] {p}")
        if i == 0:
            print("  ※ 첫 장 생성 — view 툴로 한글 육안 검증(두부 □ 없는지) 후 계속")
    # ── ★v40 신설: 위험조정 성과 차트 2장 (2-15B 코너) ──
    P = D.get("perf", {})
    if P.get("ok"):
        import matplotlib.dates as mdates
        def _d(a): return [pd.Timestamp(x) for x in a]
        # (1) 누적 수익 곡선 — 내 포트 vs 코스피 (1년 전 = 100)
        cv = P["curve"]; xs = _d(cv["idx"])
        fig, ax = plt.subplots(figsize=(11.2, 4.2), dpi=170)
        ax.plot(xs, cv["p"], color="#E8453C", lw=2.2, label="내 포트폴리오(현 보유 구성)")
        ax.plot(xs, cv["m"], color="#2F6FED", lw=1.9, label="코스피(시장에 그냥 참여)")
        ax.axhline(100, color="#8895a7", lw=1.0, ls="--")
        ax.fill_between(xs, cv["p"], cv["m"],
                        where=np.array(cv["p"]) >= np.array(cv["m"]),
                        color="#E8453C", alpha=0.10, interpolate=True)
        ax.fill_between(xs, cv["p"], cv["m"],
                        where=np.array(cv["p"]) < np.array(cv["m"]),
                        color="#2F6FED", alpha=0.12, interpolate=True)
        ax.set_title("내 포트폴리오 vs 코스피 — 1년 누적 수익 (시작=100)", fontsize=13, fontweight="bold")
        ax.set_ylabel("지수화(=100)", fontsize=9)
        ax.legend(fontsize=9, loc="upper left"); ax.grid(alpha=0.25)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
        plt.tight_layout(); plt.savefig("charts/perf_curve.png", facecolor="white", bbox_inches="tight"); plt.close()
        print(f"  [{len(jobs)+1:2d}/{len(jobs)+2}] charts/perf_curve.png")

        # (2) 60일 롤링 변동성 — 초과 위험이 '언제' 벌어졌는지
        rv = P["rollvol"]; xs2 = _d(rv["idx"])
        fig, ax = plt.subplots(figsize=(11.2, 4.0), dpi=170)
        ax.plot(xs2, rv["p"], color="#E8453C", lw=2.2, label="내 포트폴리오 변동성")
        ax.plot(xs2, rv["m"], color="#2F6FED", lw=1.9, label="코스피 변동성")
        ax.fill_between(xs2, rv["m"], rv["p"], where=np.array(rv["p"]) >= np.array(rv["m"]),
                        color="#E8453C", alpha=0.14, interpolate=True, label="초과 위험 구간")
        ax.set_title("60일 롤링 변동성(연환산 %) — 붉은 면적 = 시장보다 더 진 위험",
                     fontsize=13, fontweight="bold")
        ax.set_ylabel("연환산 변동성(%)", fontsize=9)
        ax.legend(fontsize=9, loc="upper left"); ax.grid(alpha=0.25)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
        plt.tight_layout(); plt.savefig("charts/perf_vol.png", facecolor="white", bbox_inches="tight"); plt.close()
        print(f"  [{len(jobs)+2:2d}/{len(jobs)+2}] charts/perf_vol.png")
        jobs = jobs + [None, None]

    # ★v50: 차트가 어느 기준일로 그려졌는지 사이드카에 기록한다.
    #   차트 기준일은 PNG 안에만 있어 PDF 텍스트로 검사할 수 없다 → 게이트가 이 파일을 본다.
    #   (2026-08-17 사고: 재수집 후 mkchart를 다시 안 돌리면 본문과 차트의 기준일이 갈라진다)
    import json as _j, datetime as _dt
    _j.dump({"asof": ASOF, "n": len(jobs),
             "built": _dt.datetime.now().isoformat(timespec="seconds")},
            open("charts/_meta.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n→ 차트 {len(jobs)}장 완료 (charts/)")
