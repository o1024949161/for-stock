# -*- coding: utf-8 -*-
"""
chart_pick.py — ★v65 강화 카드 선정 = «차트 망가짐 필터(주봉 먼저) → 합성 모멘텀 순위» (백테스트 채택 2026-10-07)
  ※ 아래 v64 감지기(analyze)는 판독·카드의 차트 맥락으로 계속 쓴다. 선정 규칙은 파일 끝 «★v65 선정 규칙» 블록.

  1단계  후보 풀       코스피 시총 상위 150 · 미장 상위 150 (universe.py — 그대로)
  2단계  주봉 점수     300종 주봉(일봉 2년 → 금요일 기준 주봉)을 채점 → 주봉 점수 W_MIN 이상 중 상위 WEEK_K종 «주봉 통과»
  3단계  일봉 점수     주봉 통과 종목만 일봉으로 «지금이 진입 자리인가»를 채점 → 주봉+일봉 합산 상위 CAND_K종 = 판독 후보
  4단계  차트 판독     판독 에이전트가 후보의 주봉 차트(추세·패턴)를 먼저 보고, 일봉 차트로 진입 시점을 정해 국내 3 + 미국 3
                       (prompts.md §D → chart_pick.json → apply_pick.py)
  컨센서스·수급·하드 필터·6기둥 v2는 선정에 쓰지 않는다. 제외 = 보유 종목뿐(★v68 fetch_all이 config.POSITIONS에서 자동 계산 · 같은 회사 다른 클래스는 EXCLUDE_ALIAS).

  ── 감지 신호와 가중치 (일봉 / 주봉) ───────────────────────────────────────
  이평·일목  20선×구름대 상향 돌파 22/18 · 전환선>기준선 상향 교차(호전) 10/12 · 골든크로스 5×20 8/10 · 20×60 12/16
             정배열(5>20>60·전부 상승) 6/14 · 구름 위+양운 —/10 · 종가 20선 상향 돌파 14/12
  볼린저     스퀴즈(밴드폭 하위 20%) 후 상단 돌파 14/14 · 상단 밴드 타기 6/8 · 하단 밴드 반등 10/—
  수평선     전고점 돌파(장기 120일·52주 18/20 · 단기 60일·26주 12/12) · 2회↑ 막힌 수평 저항선 돌파 18/16 · 박스권 상단 돌파 16/18
             상승 추세 눌림목 지지 14/10
  패턴       쌍바닥·역헤드앤숄더 넥라인 돌파 22/22 · 컵앤핸들 돌파 20/22 · 상승 삼각형 돌파 16/18 · 상승 깃발 돌파 16/14
             하락 쐐기 상향 이탈 14/14 · 바닥 반전(하락 추세선 돌파) 14/14
  대기       돌파 임박(레벨 3~5% 이내) 5~9
  확인       돌파 봉 거래량 평균 1.5배↑ +6 · 52주 신고가 +4/+6
  감점       20선 이격 과다(일 15%·주 25%) −8 · RSI 과열(일 78·주 80) −5 · 장기선 아래 하락 추세(일 120일선 −5 · 주 60주선 −12)
             쌍봉 넥라인 이탈 −12/−14 · 헤드앤숄더 넥라인 이탈 −14/−16
"""
import numpy as np, pandas as pd
import lib_ind as L

WEEK_K = 30         # 시장별 주봉 통과 상한
W_MIN = 20          # 주봉 통과 최소 점수
CAND_K = 8          # 시장별 판독 후보 수(주봉·일봉 차트 이미지 생성 대상)
PICK_N = 3          # 시장별 최종 선정 수(판독 에이전트)

TF = {
    "d": dict(u="일", bar="봉", piv=5, fresh=5, cross_n=10, gc_mid_n=15, hi_long=120, hi_short=60, pat=120, sep=10,
              boxes=(40, 30, 20), box_h=0.12, bb_hist=120, ext=0.15, rsi_hot=78, long_ma=120, long_slope=20,
              cup_min=30, cup_max=150, handle_max=25, handle_dd=0.15, pole_n=10, pole_min=0.15, flag_max=15,
              wedge_n=40, tri_n=40, dd=0.15, look=40, hi52=252),
    "w": dict(u="주", bar="주", piv=3, fresh=3, cross_n=6, gc_mid_n=8, hi_long=52, hi_short=26, pat=78, sep=4,
              boxes=(26, 20, 13), box_h=0.20, bb_hist=52, ext=0.25, rsi_hot=80, long_ma=60, long_slope=8,
              cup_min=12, cup_max=78, handle_max=10, handle_dd=0.20, pole_n=6, pole_min=0.25, flag_max=8,
              wedge_n=26, tri_n=26, dd=0.20, look=20, hi52=52),
}
WT = {  # key: (일봉, 주봉)
    "ma20_cloud": (22, 18), "tk_cross": (10, 12), "gc_short": (8, 10), "gc_mid": (12, 16), "ma_align": (6, 14),
    "cloud_above": (0, 10), "ma20_reclaim": (14, 12),
    "bb_squeeze": (14, 14), "bb_walk": (6, 8), "bb_lower": (10, 0),
    "hi_long": (18, 20), "hi_short": (12, 12), "resist": (18, 16), "box": (16, 18), "pullback": (14, 10),
    "dbl_bottom": (22, 22), "inv_hs": (22, 22), "cup_handle": (20, 22), "asc_tri": (16, 18), "bull_flag": (16, 14),
    "falling_wedge": (14, 14), "bottom_rev": (14, 14),
    "ma20_cloud_wait": (6, 6), "hi_wait": (5, 6), "neck_wait": (9, 9), "box_wait": (8, 8), "tri_wait": (8, 8), "cup_wait": (9, 9),
    "vol": (6, 6), "hi252": (4, 6),
    "ext": (-8, -8), "rsi_hot": (-5, -5), "longdown": (-5, -12), "dbl_top": (-12, -14), "hs_top": (-14, -16),
}
NON_PATTERN = ("vol", "hi252", "ext", "rsi_hot", "longdown", "dbl_top", "hs_top")


def label(key, tf):
    u = TF[tf]["u"]
    return {
        "ma20_cloud": f"20{u}선 구름대 상향 돌파", "tk_cross": "전환선 기준선 상향 돌파(호전)",
        "gc_short": f"골든크로스(5{u}×20{u})", "gc_mid": f"골든크로스(20{u}×60{u})",
        "ma_align": "이평 정배열(5>20>60·상승)", "cloud_above": "구름 위·양운(상승 추세대)",
        "ma20_reclaim": f"종가 20{u}선(볼린저 중심선) 상향 돌파",
        "bb_squeeze": "볼린저 스퀴즈 후 상단 돌파", "bb_walk": "볼린저 상단 밴드 타기", "bb_lower": "볼린저 하단 밴드 반등",
        "hi_long": ("120일 전고점 돌파" if tf == "d" else "52주 전고점 돌파"),
        "hi_short": ("60일 전고점 돌파" if tf == "d" else "26주 전고점 돌파"),
        "resist": "수평 저항선 돌파", "box": "박스권 상단 돌파", "pullback": "상승 추세 눌림목 지지",
        "dbl_bottom": "쌍바닥 넥라인 돌파", "inv_hs": "역헤드앤숄더 넥라인 돌파", "cup_handle": "컵앤핸들 돌파",
        "asc_tri": "상승 삼각형 돌파", "bull_flag": "상승 깃발형 돌파", "falling_wedge": "하락 쐐기 상향 이탈",
        "bottom_rev": "바닥 반전(하락 추세선 돌파)",
        "ma20_cloud_wait": f"20{u}선 구름 돌파 임박", "hi_wait": "전고점 돌파 대기", "neck_wait": "넥라인 돌파 대기",
        "box_wait": "박스 상단 이탈 대기", "tri_wait": "삼각형 상단 돌파 대기", "cup_wait": "컵 림(rim) 돌파 대기",
        "vol": "돌파 거래량 동반", "hi252": "52주 신고가", "ext": f"20{u}선 이격 과다(추격 위험)", "rsi_hot": "RSI 과열",
        "longdown": ("120일선 아래·하락 추세" if tf == "d" else "60주선 아래·하락 추세"),
        "dbl_top": "쌍봉 넥라인 이탈(천장)", "hs_top": "헤드앤숄더 넥라인 이탈(천장)",
    }[key]


def _pivots(h, l, w):
    n = len(h); hs, ls = [], []
    for i in range(w, n - w):
        if h[i] >= h[i - w:i + w + 1].max():
            hs.append((i, float(h[i])))
        if l[i] <= l[i - w:i + w + 1].min():
            ls.append((i, float(l[i])))
    return hs, ls


def _cross_up(c, lvl, i, n):
    """최근 n봉 안에서 종가가 lvl(스칼라 또는 배열)을 아래→위로 돌파한 봉(가장 최근)."""
    for k in range(i, max(0, i - n), -1):
        a = lvl[k] if hasattr(lvl, "__len__") else lvl
        b = lvl[k - 1] if hasattr(lvl, "__len__") else lvl
        if np.isfinite(a) and np.isfinite(b) and c[k] > a and c[k - 1] <= b:
            return k
    return None


def _cross_down(c, lvl, i, n):
    for k in range(i, max(0, i - n), -1):
        if c[k] < lvl and c[k - 1] >= lvl:
            return k
    return None


def _line_cross(a, b, i, n):
    """배열 a가 배열 b를 최근 n봉 안에 상향 교차한 봉."""
    for k in range(i, max(0, i - n), -1):
        if np.isfinite(a[k]) and np.isfinite(b[k]) and np.isfinite(a[k - 1]) and np.isfinite(b[k - 1]) \
                and a[k] > b[k] and a[k - 1] <= b[k - 1]:
            return k
    return None


def to_weekly(df):
    d = df.dropna(subset=["Close"]).copy()
    idx = pd.to_datetime(d.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    d.index = idx.normalize()
    w = d.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    w = w.dropna(subset=["Close"])
    w.attrs["partial"] = bool(len(d) and d.index[-1] < w.index[-1])
    w.attrs["last_day"] = d.index[-1].strftime("%Y-%m-%d") if len(d) else None
    return w


def analyze(df, tf="d"):
    """한 시간 프레임(일봉 d / 주봉 w) 차트를 같은 규칙으로 채점 → {"score","sig","main","levels","plan","bars_since"}."""
    P = TF[tf]; col = 0 if tf == "d" else 1; u = P["u"]
    df = df.dropna(subset=["Close"])
    need = 130 if tf == "d" else 80
    if len(df) < need:
        return None
    o, h, l, c, v = (df[k].values.astype(float) for k in ("Open", "High", "Low", "Close", "Volume"))
    cs = df["Close"]; n = len(c); i = n - 1; C = c[i]
    ma5, ma20, ma60 = (L.sma(cs, p).values for p in (5, 20, 60))
    malong = L.sma(cs, P["long_ma"]).values
    conv, base, sA, sB = L.ichimoku_raw(df)
    conv, base = conv.values, base.values
    ca, cb = L.cloud_at_today(sA, sB)
    ctop = np.fmax(ca.values, cb.values); cbot = np.fmin(ca.values, cb.values)
    ub, mb, lb, _ = L.boll(cs); ub, mb, lb = ub.values, mb.values, lb.values
    bw = (ub - lb) / mb
    rsi = L.rsi(cs).values
    atr = float(L.atr(df).iloc[-1])
    va = pd.Series(v).rolling(20).mean().values
    hs, ls = _pivots(h, l, P["piv"])
    fr = P["fresh"]
    dt = lambda j: df.index[j].strftime("%m/%d") if tf == "d" else df.index[j].strftime("%y/%m/%d")
    ago = lambda d_: ("기준 봉" if d_ == 0 else f"{d_}{P['bar']} 전")
    S = []

    def add(key, txt, k=None, lvl=None, stop=None, tgt=None):
        pts = WT[key][col]
        if pts == 0:
            return
        S.append({"key": key, "pts": pts, "txt": txt, "k": k, "label": label(key, tf),
                  "level": None if lvl is None or not np.isfinite(lvl) else float(lvl),
                  "stop": None if stop is None or not np.isfinite(stop) else float(stop),
                  "tgt": None if tgt is None or not np.isfinite(tgt) else float(tgt)})

    up_trend = ma20[i] > ma60[i] and C > ctop[i]

    # ── 이평·일목 ────────────────────────────────────────────────
    k = _line_cross(ma20, ctop, i, P["cross_n"])
    if k is not None and ma20[i] > ctop[i]:
        add("ma20_cloud", f"20{u}선이 {ago(i-k)} 구름 상단({ctop[k]:,.2f})을 상향 돌파 · 현재 20{u}선 {ma20[i]:,.2f}",
            k, ma20[i], stop=max(cbot[i], ma20[i] - 1.5 * atr))
    elif np.isfinite(ctop[i]) and ctop[i] * 0.97 <= ma20[i] <= ctop[i] and ma20[i] > ma20[i - 3]:
        add("ma20_cloud_wait", f"20{u}선({ma20[i]:,.2f})이 구름 상단({ctop[i]:,.2f}) 3% 이내·상승 중", None, ctop[i])
    k = _line_cross(conv, base, i, P["cross_n"])
    if k is not None and conv[i] > base[i]:
        add("tk_cross", f"전환선({conv[i]:,.2f})이 {ago(i-k)} 기준선({base[i]:,.2f})을 상향 돌파"
            + (" · 구름 위 호전(강)" if C > ctop[i] else (" · 구름 안" if C >= cbot[i] else " · 구름 아래(약)")), k, base[i],
            stop=min(base[i], cbot[i]) if np.isfinite(cbot[i]) else base[i])
    k = _line_cross(ma5, ma20, i, P["cross_n"])
    if k is not None and ma5[i] > ma20[i]:
        add("gc_short", f"5{u}선이 {ago(i-k)} 20{u}선을 상향 교차", k, ma20[i])
    k = _line_cross(ma20, ma60, i, P["gc_mid_n"])
    if k is not None and ma20[i] > ma60[i]:
        add("gc_mid", f"20{u}선이 {ago(i-k)} 60{u}선을 상향 교차(중기 추세 전환)", k, ma60[i])
    if ma5[i] > ma20[i] > ma60[i] and ma5[i] > ma5[i - 2] and ma20[i] > ma20[i - 3] and ma60[i] > ma60[i - 3]:
        add("ma_align", f"5{u}>20{u}>60{u} 정배열·세 선 모두 상승")
    if tf == "w" and C > ctop[i] and ca.values[i] > cb.values[i]:
        add("cloud_above", f"주가가 주봉 구름({cbot[i]:,.2f}~{ctop[i]:,.2f}) 위·양운")
    k = _cross_up(c, ma20, i, fr)
    if k is not None and C > ma20[i] and k - fr >= 1 and all(c[j] < ma20[j] for j in range(k - fr, k)):
        add("ma20_reclaim", f"{ago(i-k)} 종가가 20{u}선을 상향 돌파(직전 {fr}{P['bar']} 이상 아래)"
            + (f" · 20{u}선 상승 전환" if ma20[i] > ma20[i - 3] else ""), k, ma20[i], stop=min(l[k - 3:i + 1]) - 0.5 * atr)

    # ── 볼린저밴드 ───────────────────────────────────────────────
    bwh = bw[max(0, i - P["bb_hist"]):i + 1]; bwh = bwh[np.isfinite(bwh)]
    if len(bwh) > 30:
        q20 = np.quantile(bwh, 0.20)
        sq_recent = np.nanmin(bw[i - 10:i]) <= q20
        kb = _cross_up(c, ub, i, fr)
        if sq_recent and (kb is not None or (C > mb[i] and bw[i] >= np.nanmin(bw[i - 10:i]) * 1.2 and C >= h[i - 20:i].max())):
            add("bb_squeeze", f"밴드폭이 최근 {P['bb_hist']}{P['bar']} 하위 20%로 수축한 뒤 "
                + (f"{ago(i-kb)} 상단 밴드({ub[kb]:,.2f}) 돌파" if kb is not None else "확장하며 20봉 고점 돌파"),
                kb if kb is not None else i, mb[i], stop=mb[i] - 0.5 * atr)
    pb = (c - lb) / (ub - lb)
    if all(np.isfinite(pb[j]) and pb[j] >= 0.8 for j in range(i - 2, i + 1)) and mb[i] > mb[i - 3]:
        add("bb_walk", f"최근 3{P['bar']} %b {pb[i]:.2f} 이상 — 상단 밴드를 타는 강한 추세(중심선 상승)")
    if any(l[j] <= lb[j] for j in range(i - 4, i + 1)) and C > lb[i] and C > c[i - 1] and C > o[i] \
            and np.isfinite(ma60[i - 10]) and ma60[i] >= ma60[i - 10] * 0.98:
        add("bb_lower", f"5{P['bar']} 안 하단 밴드({lb[i]:,.2f}) 터치 후 양봉 반등(60{u}선 하락 아님)", i, lb[i],
            stop=l[i - 4:i + 1].min() - 0.3 * atr)

    # ── 전고점·수평 저항·박스 ────────────────────────────────────
    hl = h[max(0, i - P["hi_long"] - 5):i - fr + 1].max(); hsh = h[max(0, i - P["hi_short"] - 5):i - fr + 1].max()
    brk_hi = None
    for key, lv in (("hi_long", hl), ("hi_short", hsh)):
        k = _cross_up(c, lv, i, fr)
        if k is not None and C > lv:
            add(key, f"{label(key, tf).replace(' 돌파', '')} {lv:,.2f}을 {ago(i-k)} 종가 돌파", k, lv, stop=lv - atr,
                tgt=lv + (lv - l[max(0, i - P['hi_long']):i - fr + 1].min()) * 0.5)
            brk_hi = lv; break
    if brk_hi is None and hsh * 0.97 <= C < hsh and ma20[i] > ma20[i - 3]:
        add("hi_wait", f"전고점 {hsh:,.2f}까지 {(hsh/C-1)*100:.1f}% — 돌파 대기", None, hsh)
    if C >= h[max(0, i - P["hi52"]):i].max():
        add("hi252", "52주 신고가 경신")
    for Wn in P["boxes"]:
        if i - Wn - 3 < 0:
            continue
        top, bot = h[i - Wn - 3:i - 2].max(), l[i - Wn - 3:i - 2].min()
        hgt = top / bot - 1
        if hgt <= P["box_h"]:
            k = _cross_up(c, top, i, 3)
            if k is not None and C > top:
                add("box", f"{Wn}{P['bar']} 박스({bot:,.2f}~{top:,.2f}, 높이 {hgt*100:.1f}%) 상단 {ago(i-k)} 돌파",
                    k, top, stop=max(top - atr, (top + bot) / 2), tgt=top * (1 + hgt))
            elif top * 0.97 <= C <= top:
                add("box_wait", f"{Wn}{P['bar']} 박스({bot:,.2f}~{top:,.2f}) 상단까지 {(top/C-1)*100:.1f}% — 이탈 대기",
                    None, top, stop=(top + bot) / 2, tgt=top * (1 + hgt))
            break

    # ── 패턴: 쌍바닥 · 역헤드앤숄더 ──────────────────────────────
    pl = [(j, p) for j, p in ls if j >= i - P["pat"]]
    done = False
    if len(pl) >= 2:
        (a, L1), (b, L2) = pl[-2], pl[-1]
        if b - a >= P["sep"] and abs(L2 / L1 - 1) <= 0.04 and l[b:i + 1].min() >= min(L1, L2) * 0.99:
            neck = h[a:b + 1].max(); bot = min(L1, L2)
            if neck >= max(L1, L2) * 1.06 and h[max(0, a - P["look"]):a + 1].max() > neck:
                tgt = neck + (neck - bot); k = _cross_up(c, neck, i, fr + 2)
                if k is not None and C > neck:
                    add("dbl_bottom", f"쌍바닥({dt(a)} {L1:,.2f} · {dt(b)} {L2:,.2f}) 넥라인 {neck:,.2f}을 {ago(i-k)} 돌파 · "
                        f"측정 목표 {tgt:,.2f}", k, neck, stop=neck - atr, tgt=tgt); done = True
                elif neck * 0.95 <= C <= neck:
                    add("neck_wait", f"쌍바닥 넥라인 {neck:,.2f}까지 {(neck/C-1)*100:.1f}% — 돌파 대기", None, neck,
                        stop=bot, tgt=tgt); done = True
    if not done and len(pl) >= 3:
        (a, Ls), (m, Hd), (b, Rs) = pl[-3], pl[-2], pl[-1]
        if Hd < Ls * 0.97 and Hd < Rs * 0.97 and abs(Rs / Ls - 1) <= 0.06 and l[b:i + 1].min() >= Rs * 0.99:
            neck = max(h[a:m + 1].max(), h[m:b + 1].max()); tgt = neck + (neck - Hd)
            k = _cross_up(c, neck, i, fr + 2)
            if k is not None and C > neck:
                add("inv_hs", f"역헤드앤숄더(머리 {dt(m)} {Hd:,.2f}) 넥라인 {neck:,.2f}을 {ago(i-k)} 돌파 · 측정 목표 {tgt:,.2f}",
                    k, neck, stop=neck - atr, tgt=tgt)
            elif neck * 0.95 <= C <= neck:
                add("neck_wait", f"역헤드앤숄더 넥라인 {neck:,.2f}까지 {(neck/C-1)*100:.1f}% — 돌파 대기", None, neck,
                    stop=Rs, tgt=tgt)

    # ── 패턴: 컵앤핸들 ───────────────────────────────────────────
    for a, A in reversed([(j, p) for j, p in hs if i - P["cup_max"] <= j <= i - P["cup_min"]]):
        bi = a + int(np.argmin(l[a:i + 1])); B = l[bi]; depth = 1 - B / A
        if not (0.12 <= depth <= 0.55) or bi - a < P["cup_min"] * 0.3 or i - bi < P["cup_min"] * 0.3:
            continue
        r = bi + int(np.argmax(h[bi:i + 1])); R = h[r]
        if R < A * 0.93 or R > A * 1.03 or r - a < P["cup_min"]:
            continue
        rim = max(A, h[r]) if r < i else A
        hl_ = l[r:i + 1].min(); hdd = 1 - hl_ / R
        if hdd > min(P["handle_dd"], depth / 2) or i - r > P["handle_max"]:
            continue
        tgt = rim + (rim - B); k = _cross_up(c, rim, i, fr)
        if k is not None and C > rim:
            add("cup_handle", f"컵({dt(a)} 림 {A:,.2f} → 바닥 {dt(bi)} {B:,.2f}, 깊이 {depth*100:.0f}%)"
                + (f"·핸들 {i-r}{P['bar']}" if i - r >= 2 else "") + f" 림 {rim:,.2f}을 {ago(i-k)} 돌파 · 측정 목표 {tgt:,.2f}",
                k, rim, stop=max(hl_, rim - 1.5 * atr), tgt=tgt)
        elif i - r >= 2 and rim * 0.95 <= C <= rim:
            add("cup_wait", f"컵앤핸들(바닥 {dt(bi)} {B:,.2f}) 핸들 {i-r}{P['bar']} 형성 — 림 {rim:,.2f}까지 {(rim/C-1)*100:.1f}%",
                None, rim, stop=hl_, tgt=tgt)
        break

    # ── 패턴: 상승 삼각형(평평한 고점 + 높아지는 저점) ───────────────
    hw = [(j, p) for j, p in hs if i - P["tri_n"] <= j < i - 1]
    lw = [(j, p) for j, p in ls if i - P["tri_n"] <= j < i - 1]
    if len(hw) >= 2 and len(lw) >= 2:
        tops = [p for _, p in hw[-3:]]; T = max(tops)
        rising = all(lw[t + 1][1] >= lw[t][1] * 1.01 for t in range(len(lw) - 1))
        if max(tops) / min(tops) <= 1.03 and rising and lw[0][1] <= T * 0.94:
            tgt = T + (T - lw[0][1]); k = _cross_up(c, T, i, fr)
            if k is not None and C > T:
                add("asc_tri", f"상승 삼각형(고점 {len(tops)}회 {T:,.2f} 부근 · 저점 {len(lw)}회 상승) 상단 {ago(i-k)} 돌파 · "
                    f"측정 목표 {tgt:,.2f}", k, T, stop=max(lw[-1][1], T - 1.5 * atr), tgt=tgt)
            elif T * 0.97 <= C <= T:
                add("tri_wait", f"상승 삼각형 상단 {T:,.2f}까지 {(T/C-1)*100:.1f}% — 저점이 높아지며 수렴 중", None, T,
                    stop=lw[-1][1], tgt=tgt)

    # ── 패턴: 상승 깃발형(급등 깃대 → 짧은 하향·횡보 조정 → 위로 이탈) ──
    for e in (i, i - 1, i - 2):
        if e - 3 < 0:
            break
        lo_p = max(0, e - P["flag_max"] - 1)
        if e - 2 <= lo_p:
            continue
        p = lo_p + int(np.argmax(h[lo_p:e - 1]))
        if e - 1 - p < 2:
            continue
        s0 = max(0, p - P["pole_n"]); s = s0 + int(np.argmin(l[s0:p + 1]))
        pole = h[p] / l[s] - 1
        fl = l[p + 1:e].min(); ftop = h[p + 1:e].max()
        if pole >= P["pole_min"] and (h[p] - fl) <= 0.5 * (h[p] - l[s]) and ftop <= h[p] and c[e] > ftop and c[e - 1] <= ftop:
            tgt = ftop + (h[p] - l[s])
            add("bull_flag", f"깃대 {dt(s)}→{dt(p)} +{pole*100:.0f}% 뒤 {e-1-p}{P['bar']} 깃발 조정 상단({ftop:,.2f})을 "
                f"{ago(i-e)} 돌파 · 측정 목표 {tgt:,.2f}", e, ftop, stop=fl, tgt=tgt)
            break

    # ── 패턴: 하락 쐐기(고점·저점 모두 낮아지며 수렴) 상향 이탈 ──────
    hw = [(j, p) for j, p in hs if i - P["wedge_n"] <= j < i - 1]
    lw = [(j, p) for j, p in ls if i - P["wedge_n"] <= j < i - 1]
    if len(hw) >= 2 and len(lw) >= 2:
        (j1, p1), (j2, p2) = hw[0], hw[-1]; (k1, q1), (k2, q2) = lw[0], lw[-1]
        if p2 < p1 and q2 < q1 and j2 > j1 and k2 > k1:
            sh = (p2 - p1) / (j2 - j1); sl = (q2 - q1) / (k2 - k1)
            if sh < sl < 0:
                upper = np.array([p2 + sh * (t - j2) for t in range(n)])
                k = _cross_up(c, upper, i, fr)
                if k is not None and C > upper[i]:
                    add("falling_wedge", f"하락 쐐기(고점 {p1:,.2f}→{p2:,.2f}, 저점 {q1:,.2f}→{q2:,.2f}) 상단선을 {ago(i-k)} 상향 이탈",
                        k, upper[i], stop=q2, tgt=p1)

    # ── 수평 저항선(2회 이상 막힌 자리) — 다른 돌파 레벨과 겹치면 생략 ──
    ph = [(j, p) for j, p in hs if i - P["pat"] <= j <= i - fr - 1]
    best = None
    for j, p in ph:
        t = sum(1 for _, pp in ph if abs(pp / p - 1) <= 0.02)
        if t >= 2:
            k = _cross_up(c, p, i, fr)
            if k is not None and C > p and (best is None or p > best[1]):
                best = (k, p, t)
    if best:
        k, p, t = best
        others = [x["level"] for x in S if x["key"] in ("hi_long", "hi_short", "dbl_bottom", "inv_hs", "box", "cup_handle", "asc_tri", "bull_flag") and x["level"]]
        if not any(abs(p / o_ - 1) < 0.015 for o_ in others):
            add("resist", f"{t}회 막힌 저항대 {p:,.2f}을 {ago(i-k)} 돌파", k, p, stop=p - atr)

    # ── 상승 추세 눌림목 ─────────────────────────────────────────
    if up_trend and C > o[i] and not any(x["key"] == "ma20_reclaim" for x in S):
        sup = [(f"20{u}선", ma20[i], ma20), ("구름 상단", ctop[i], ctop)]
        for j, p in hs:
            if i - P["hi_short"] <= j <= i - 2 * fr and C > p and p >= C * 0.9:
                sup.append((f"돌파한 스윙 고점({dt(j)})", p, None))
        for nm, sv, arr in sup:
            if not np.isfinite(sv):
                continue
            ref = arr if arr is not None else np.full(n, sv)
            span = range(i - 2 * fr, i - 2)
            if all(c[j] > ref[j] for j in span) and h[i - 2 * fr:i - 2].max() >= sv * 1.04 \
                    and l[i - 2:i + 1].min() <= sv * 1.01 and sv < C <= sv * 1.05:
                add("pullback", f"상승 추세(20{u}>60{u}·구름 위)에서 {nm} {sv:,.2f}까지 눌린 뒤 양봉 지지", i, sv, stop=sv - atr)
                break

    # ── 바닥 반전(급락·과매도 후 하락 추세선 돌파) ───────────────────
    dd = l[i - P["look"]:i + 1].min() / h[max(0, i - P["hi_long"]):i + 1].max() - 1
    if dd <= -P["dd"] and np.nanmin(rsi[i - 30 if tf == "d" else i - 15:i + 1]) < 35:
        ph2 = [(j, p) for j, p in hs if j >= i - P["pat"] * 2 // 3]
        if len(ph2) >= 2:
            (j1, p1), (j2, p2) = ph2[-2], ph2[-1]
            if p2 < p1 and j2 - j1 >= P["sep"] // 2:
                slope = (p2 - p1) / (j2 - j1)
                line = np.array([p2 + slope * (t - j2) for t in range(n)])
                k = _cross_up(c, line, i, fr)
                if k is not None and C > line[i] and k > j2:
                    add("bottom_rev", f"고점 대비 {dd*100:.0f}% 하락·RSI 35 아래 과매도 후 하락 추세선(현재 {line[i]:,.2f})을 "
                        f"{ago(i-k)} 돌파", k, line[i], stop=l[i - P['look']:i + 1].min())

    # ── 천장 패턴(감점): 쌍봉 · 헤드앤숄더 넥라인 이탈 ───────────────
    phh = [(j, p) for j, p in hs if j >= i - P["pat"]]
    if len(phh) >= 2:
        (a, H1), (b, H2) = phh[-2], phh[-1]
        if b - a >= P["sep"] and abs(H2 / H1 - 1) <= 0.03:
            T = l[a:b + 1].min()
            if T <= min(H1, H2) * 0.94 and _cross_down(c, T, i, 2 * fr) is not None and C < T:
                add("dbl_top", f"쌍봉({dt(a)} {H1:,.2f} · {dt(b)} {H2:,.2f}) 넥라인 {T:,.2f} 하향 이탈", None, T)
    if len(phh) >= 3:
        (a, Ls), (m, Hd), (b, Rs) = phh[-3], phh[-2], phh[-1]
        if Hd > Ls * 1.03 and Hd > Rs * 1.03 and abs(Rs / Ls - 1) <= 0.06:
            neck = min(l[a:m + 1].min(), l[m:b + 1].min())
            if _cross_down(c, neck, i, 2 * fr) is not None and C < neck:
                add("hs_top", f"헤드앤숄더(머리 {dt(m)} {Hd:,.2f}) 넥라인 {neck:,.2f} 하향 이탈", None, neck)

    # ── 확인·감점 ────────────────────────────────────────────────
    main = sorted([s for s in S if s["key"] not in NON_PATTERN], key=lambda s: -s["pts"])
    bk = next((s["k"] for s in main if s["k"] is not None and s["level"] is not None), None)
    if bk is not None and np.isfinite(va[bk]) and va[bk] > 0 and v[bk] >= 1.5 * va[bk]:
        add("vol", f"돌파 봉({dt(bk)}) 거래량 20{P['bar']} 평균의 {v[bk]/va[bk]:.1f}배")
    ext = C / ma20[i] - 1
    if ext > P["ext"]:
        add("ext", f"20{u}선 대비 +{ext*100:.1f}% — 되돌림 대기 권장")
    if rsi[i] > P["rsi_hot"]:
        add("rsi_hot", f"RSI {rsi[i]:.0f}")
    if np.isfinite(malong[i]) and C < malong[i] and malong[i] < malong[i - P["long_slope"]] \
            and not any(s["key"] in ("bottom_rev", "falling_wedge") for s in S):
        add("longdown", f"{label('longdown', tf).split('·')[0]} — 장기 추세 하락")

    score = round(sum(s["pts"] for s in S), 1)
    above = sorted({round(p, 4) for j, p in hs if j >= i - 2 * P["hi_long"] and p > C * 1.01})[:4]
    below = sorted({round(p, 4) for j, p in ls if j >= i - P["hi_long"] and p < C * 0.99}, reverse=True)[:3]
    lv = {"close": C, "ma5": ma5[i], "ma20": ma20[i], "ma60": ma60[i], "ma_long": malong[i], "conv": conv[i], "base": base[i],
          "cloud_top": ctop[i], "cloud_bot": cbot[i], "bb_up": ub[i], "bb_mid": mb[i], "bb_low": lb[i], "pb": pb[i],
          "bw_pctl": float((bwh < bw[i]).mean() * 100) if len(bwh) else None,
          "atr": atr, "atr_pct": atr / C * 100, "rsi": rsi[i], "swing_hi_above": above, "swing_lo_below": below,
          "hi_short_prev": hsh, "hi_long_prev": hl}
    lv = {k_: (float(v_) if isinstance(v_, (float, np.floating)) and np.isfinite(v_) else v_) for k_, v_ in lv.items()}
    plan = _plan(C, atr, main[0] if main else None, above, float(h[max(0, i - P["hi52"]):i + 1].max())) if tf == "d" else None
    return {"score": score, "sig": [{k_: s[k_] for k_ in ("key", "pts", "txt", "level", "stop", "tgt", "label")}
                                    for s in sorted(S, key=lambda s: -s["pts"])],
            "main": main[0]["label"] if main else None, "levels": lv, "plan": plan,
            "bars_since": None if bk is None else int(i - bk)}


def _plan(C, atr, m, above, hi252=None):
    """일봉 규칙 «초안» 계획 — 판독 에이전트가 주봉·일봉을 보고 조정한다(apply_pick이 최종값을 쓴다)."""
    if m is None:
        return None
    lvl = m["level"] or C
    if m["key"].endswith("_wait"):
        entry = lvl * 1.005
    elif m["key"] in ("pullback", "bb_lower"):
        entry = C
    else:
        entry = C if C <= lvl * 1.04 else lvl * 1.01
    stop = m["stop"] if m["stop"] and m["stop"] < entry * 0.985 else entry - 2.0 * atr
    stop = min(max(stop, entry * 0.85), entry - atr)   # 손절 폭: 최소 1 ATR · 최대 15%
    risk = entry - stop
    cands = sorted({t for t in ([m["tgt"]] if m["tgt"] else []) + list(above) + ([hi252] if hi252 else [])
                    if t and t > entry * 1.03})
    tgt = next((t for t in cands if (t - entry) / risk >= 2.0), cands[-1] if cands else entry + 2.5 * risk)
    return {"entry": float(entry), "stop": float(stop), "target": float(tgt),
            "rr": float((tgt - entry) / (entry - stop)) if entry > stop else 0.0, "basis": m["label"]}


# ══════════════════════════════════════════════════════════════════════════
# ★v65 선정 규칙 — 백테스트(2023-06~2026-08, 학습/검증 분리 · backtest/)로 채택한 것만 쓴다
#   1단계 «차트 망가짐» 필터(주봉 먼저):  종가>200일선 · 50일선>200일선 · 주봉 60주선 아래 하락 아님 · 주봉 구름 위(양운)
#   2단계 순위: 합성 모멘텀 = 백분위(12-1개월 수익) + 백분위(6-1개월 수익) + 백분위(6개월 로그가격 기울기) 의 평균 (시장 안)
#   관찰 목록 = 필터 통과 종목의 순위 상위 WATCH_K · 기본 선정 = 지난 회차 선정 중 아직 10위 안이면 유지 + 나머지는 순위대로
#   진입 = 다음 거래일(눌림·돌파 대기 없음 — 백테스트에서 기다릴수록 손해) · 보유 관리 = config.REBAL_WEEKS 주마다 점검일에 순위 10위 밖 또는 필터 이탈 시 교체(★v66)
#   차트 신호(주봉·일봉 감지기)는 판독·카드의 «맥락»으로 쓰고, 선정·진입 지연에는 쓰지 않는다(효과 미검증).
# ══════════════════════════════════════════════════════════════════════════
WATCH_K = 10        # 관찰 목록(버퍼 경계) — 보유·선정 종목이 이 안에 있으면 유지
EMERGENCY = 0.25    # 비상 손절(진입가 −25%) — 그 이상 좁은 손절은 백테스트에서 수익을 깎았다


def mom_features(df):
    """일봉 → 선정 지표(12-1·6-1개월 수익, 6개월 기울기)와 필터용 이평 상태."""
    c = df["Close"].dropna()
    if len(c) < 260:
        return None
    i = len(c) - 1
    seg = np.log(c.iloc[i - 125:i + 1].values); x = np.arange(len(seg))
    ma50, ma200 = c.rolling(50).mean(), c.rolling(200).mean()
    return {"mom12_1": float(c.iloc[i - 21] / c.iloc[i - 252] - 1), "mom6_1": float(c.iloc[i - 21] / c.iloc[i - 126] - 1),
            "slope126": float(np.polyfit(x, seg, 1)[0] * 252),
            "a200": bool(c.iloc[i] > ma200.iloc[i]), "g50_200": bool(ma50.iloc[i] > ma200.iloc[i]),
            "ma200": float(ma200.iloc[i]), "ma50": float(ma50.iloc[i]), "close": float(c.iloc[i])}


def weekly_flags(wk):
    """★v66 주봉 필터 전용(가벼운 계산) — analyze(주봉)의 cloud_above·longdown과 같은 정의.
       cloud_above: 종가 > 주봉 구름 상단 그리고 양운 / longdown: 종가 < 60주선 그리고 60주선이 8주 전보다 낮음."""
    wk = wk.dropna(subset=["Close"])
    if len(wk) < 80:
        return None
    c = wk["Close"].values.astype(float); i = len(c) - 1
    conv, base, sA, sB = L.ichimoku_raw(wk)
    ca, cb = L.cloud_at_today(sA, sB)
    ca, cb = float(ca.values[i]), float(cb.values[i])
    ma60 = L.sma(wk["Close"], 60).values
    return {"cloud_above": bool(np.isfinite(ca) and np.isfinite(cb) and c[i] > max(ca, cb) and ca > cb),
            "longdown": bool(np.isfinite(ma60[i]) and np.isfinite(ma60[i - 8]) and c[i] < ma60[i] and ma60[i] < ma60[i - 8]),
            "cloud_top": float(max(ca, cb)) if np.isfinite(ca) and np.isfinite(cb) else None}


def passes(f, wf):
    """1단계 필터 — 하나라도 어기면 «차트 망가짐»(관찰 제외). wf = weekly_flags(). 반환 (통과 여부, 항목별 결과)."""
    wf = wf or {}
    chk = {"200일선 위": f["a200"], "50일선>200일선": f["g50_200"],
           "주봉 60주선 하락 아님": not wf.get("longdown", True), "주봉 구름 위": bool(wf.get("cloud_above"))}
    return all(chk.values()), chk


def scan(pool, getdf, exclude=(), k=CAND_K, prev=None, force=None):
    """★v65 1단계 필터(주봉·장기 이평) → 2단계 합성 모멘텀 순위 → 관찰 목록·기본 선정.
       prev = 보유 장부 이름 목록(버퍼 유지용) · force = 순위·필터와 무관하게 출력에 넣을 이름(점검일 사이 보유 유지용).
       반환 dict는 fetch_all·facts·build가 쓴다."""
    rows = []
    for nm, x in pool.items():
        if nm in exclude:
            continue
        try:
            d = getdf(x["ticker"])
            if d is None:
                continue
            f = mom_features(d)
            if not f:
                continue
            wk = to_weekly(d)
            wf = weekly_flags(wk)
        except Exception:
            continue
        if not wf:
            continue
        ok, chk = passes(f, wf)
        rows.append({"name": nm, "ticker": x["ticker"], "_d": d, "_wk": wk, "f": f, "wf": wf, "ok": ok, "chk": chk,
                     "w_partial": wk.attrs.get("partial"), "w_last": wk.index[-1].strftime("%Y-%m-%d")})
    n_scanned = len([n for n in pool if n not in exclude])
    if not rows:
        return {"all": [], "cand": [], "week": [], "default": [], "n_scanned": n_scanned, "n_pass": 0}
    R = pd.DataFrame([{"i": j, **r["f"]} for j, r in enumerate(rows)])
    R["comp"] = (R.mom12_1.rank(pct=True) + R.mom6_1.rank(pct=True) + R.slope126.rank(pct=True)) / 3
    for j, r in enumerate(rows):
        r["comp"] = float(R.comp.iloc[j])
    passed = sorted([r for r in rows if r["ok"]], key=lambda z: -z["comp"])
    for rank_, r in enumerate(passed, 1):
        r["rank"] = rank_
    watch = passed[:max(WATCH_K, k)]
    force = [f_ for f_ in (force or [])]
    watch = watch + [r for r in rows if r["name"] in force and r not in watch]
    prev = [p for p in (prev or [])]
    kept = [r["name"] for r in passed[:WATCH_K] if r["name"] in prev]
    default = kept[:PICK_N] + [r["name"] for r in passed if r["name"] not in kept][:max(0, PICK_N - len(kept))]
    out = []
    for r in watch:
        try:
            r["rw"] = analyze(r["_wk"], "w") or {"score": 0, "sig": [], "main": None, "levels": {}}
        except Exception:
            r["rw"] = {"score": 0, "sig": [], "main": None, "levels": {}}
        try:
            rd = analyze(r["_d"], "d")
        except Exception:
            rd = None
        rd = rd or {"score": 0, "sig": [], "main": None, "levels": {}, "plan": None, "bars_since": None}
        lw = r["rw"]["levels"]; f = r["f"]
        # 관리선 = 필터가 깨지는 가격(200일선·주봉 구름 상단 중 높은 쪽) · 비상 손절 −25%
        guard = max(f["ma200"], r["wf"].get("cloud_top") or 0)
        stop = max(guard, f["close"] * (1 - EMERGENCY)) if guard < f["close"] else f["close"] * (1 - EMERGENCY)
        tgt_c = sorted([t for t in (rd["levels"].get("swing_hi_above") or []) + (lw.get("swing_hi_above") or []) if t > f["close"] * 1.05])
        risk = f["close"] - stop
        # 참고 목표 — 매도는 목표가가 아니라 «순위·필터»로 한다. 차트 저항 중 2R 이상이 없으면 진입가 + 2×위험폭(2R).
        tgt = next((t for t in tgt_c if (t - f["close"]) / risk >= 2.0), None)
        tbasis = "차트 저항" if tgt else "2R(저항 없음)"
        tgt = tgt or f["close"] + 2 * risk
        plan = {"entry": f["close"], "stop": float(stop), "target": float(tgt), "guard": float(guard), "tbasis": tbasis,
                "rr": float((tgt - f["close"]) / risk) if risk > 0 else 0.0, "basis": "다음 거래일 진입 · 관리선/비상 손절"}
        out.append({"name": r["name"], "ticker": r["ticker"], "rank": r.get("rank"), "score": round(r["comp"] * 100, 1),
                    "comp": r["comp"], "mom12_1": f["mom12_1"], "mom6_1": f["mom6_1"], "slope126": f["slope126"],
                    "chk": r["chk"], "default": r["name"] in default, "kept": r["name"] in kept,
                    "wscore": r["rw"]["score"], "dscore": rd["score"], "main_w": r["rw"]["main"], "main_d": rd["main"],
                    "main": (f"모멘텀 {r['rank']}위" if r.get("rank") else "순위 밖(필터 미통과)") + f" · 주봉 «{r['rw']['main'] or '신호 없음'}»",
                    "sig_w": r["rw"]["sig"], "sig_d": rd["sig"], "sig": rd["sig"],
                    "levels_w": lw, "levels": rd["levels"], "plan": plan, "bars_since": rd["bars_since"],
                    "w_partial": r["w_partial"], "w_last": r["w_last"]})
    cand = out[:k] + [o for o in out[k:] if o["default"] or o["name"] in force]   # 기본 선정·보유 유지 종목은 순위와 무관하게 판독 대상
    fail = sorted([r for r in rows if not r["ok"]], key=lambda z: -z["comp"])[:10]
    week = [{"name": r["name"], "ticker": r["ticker"], "comp": round(r["comp"] * 100, 1),
             "fail": [k_ for k_, v_ in r["chk"].items() if not v_]} for r in fail]      # 모멘텀은 높지만 필터 탈락(망가진 차트)
    for r in rows:
        r.pop("_d", None); r.pop("_wk", None)
    return {"all": out, "cand": cand, "week": week, "default": default, "kept": kept,
            "n_scanned": n_scanned, "n_pass": len(passed),
            "rank": [{"name": r["name"], "ticker": r["ticker"], "rank": r["rank"], "score": round(r["comp"] * 100, 1)}
                     for r in passed[:20]]}
