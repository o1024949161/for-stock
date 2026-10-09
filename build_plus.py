# -*- coding: utf-8 -*-
"""
build_plus.py — ★v62 build.py 보조 모듈

  ① lite_convert  — 경량 강조 표기(D) + «한 번 쓰고 여러 곳에» 참조(C) + 부호 숫자 자동 색
  ② lead_board    — ①-2 선행 신호판(외국인 K200 선물 · EWY · 미 2년물 · 실질금리 · 시장 폭 · 프로그램)
  ③ hmatrix       — 보유/진입 판단 매트릭스(4축 자동)
  ④ exp_move      — (★v67 폐지: 본문에서 호출하지 않는다 · 함수만 보존)
  ⑤ scorecard     — 판단 채점표
  ⑥ glossary      — 해설 부록(처음 보는 지표·기법 읽는 법)
  ⑦ state_update  — brief_state.json(채점·기준가·컨센서스 이력) 갱신

강조 표기 되돌리기: config.MARKUP = "html" 또는 환경변수 BRIEF_MARKUP=html → 변환을 끄고 v61처럼 HTML을 직접 쓴다.
(두 방식은 공존한다 — lite 모드에서도 HTML 태그는 그대로 통과한다.)
"""
import re, json, datetime as dt

# ════════════════════════════════════════════════════════════
# ① 경량 강조 + 참조 + 자동 색
# ════════════════════════════════════════════════════════════
_MARK = [
    (re.compile(r"\+\+(?=\S)(.+?)(?<=\S)\+\+"), r"<b class='vg'>\1</b>"),     # ++호재++  초록 볼드
    (re.compile(r"--(?=\S)(.+?)(?<=\S)--"), r"<b class='vr'>\1</b>"),         # --악재--  빨강 볼드
    (re.compile(r"!!(?=\S)(.+?)(?<=\S)!!"), r"<b class='warn'>\1</b>"),       # !!경고!!  경고 볼드
    (re.compile(r"\^\^(?=\S)(.+?)(?<=\S)\^\^"), r"<b class='vy'>\1</b>"),     # ^^중립^^  노랑 볼드
    (re.compile(r"==(?=\S)(.+?)(?<=\S)=="), r"<span class='hl'>\1</span>"),    # ==행동== 노란 형광
    (re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*"), r"<b>\1</b>"),                # **강조** 볼드
]
_NUM = re.compile(r"(?<![\w.,/:])([+\-−])(\d[\d,]*(?:\.\d+)?)(%p|%|bp|억원|억|조원|조|만원|원|p|배|계약)?(?![\w])")
_COLOR_CLS = re.compile(r"class=['\"][^'\"]*\b(up|dn|vg|vr|vy|warn|hl|dg|dr|dy)\b")
_VOID = {"br", "img", "hr", "wbr"}


def _autocolor(s):
    out, stack = [], []
    for part in re.split(r"(<[^>]+>)", s):
        if part.startswith("<"):
            m = re.match(r"<\s*(/)?\s*([a-zA-Z0-9]+)", part)
            if m:
                tag = m.group(2).lower()
                if m.group(1):
                    if stack:
                        stack.pop()
                elif tag not in _VOID and not part.endswith("/>"):
                    stack.append(bool(_COLOR_CLS.search(part)))
            out.append(part)
            continue
        if any(stack):
            out.append(part)
            continue
        def rep(mm):
            sgn = mm.group(1)
            cls = "up" if sgn == "+" else "dn"
            return f"<span class='{cls}'>{mm.group(0)}</span>"
        out.append(_NUM.sub(rep, part))
    return "".join(out)


def _lite_str(s):
    for rx, to in _MARK:
        s = rx.sub(to, s)
    return _autocolor(s)


def _get_path(R, path):
    cur = R
    for p in re.split(r"\.", path):
        m = re.match(r"(.+?)\[(\d+)\]$", p)
        if m:
            cur = cur[m.group(1)][int(m.group(2))]
        else:
            cur = cur[p]
    return cur


def lite_convert(R, tokens=None, mode="lite", miss=None):
    """① "=path.to.field" 참조 해석  ② {{@token}} 치환  ③ lite면 강조 변환·자동 색."""
    tokens = tokens or {}
    miss = miss if miss is not None else []

    def ref(v, depth=0):
        if isinstance(v, str) and v.startswith("=") and " " not in v.strip() and len(v) > 2 and depth < 3:
            try:
                return ref(_get_path(R, v[1:].strip()), depth + 1)
            except Exception:
                miss.append(v)
                return v
        return v

    def walk(o):
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        if isinstance(o, str):
            o = ref(o)
            if not isinstance(o, str):
                return walk(o)
            for k, v in tokens.items():
                o = o.replace("{{@" + k + "}}", v)
            return _lite_str(o) if mode == "lite" else o
        return o
    return walk(R)


# ════════════════════════════════════════════════════════════
# 공용
# ════════════════════════════════════════════════════════════
def _sig(c):
    return f'<span class="d d{c}">●</span>'


def _pc(v, d=2, unit="%"):
    if v is None:
        return "—"
    cls = "up" if v > 0 else ("dn" if v < 0 else "")
    return f'<span class="{cls}">{v:+,.{d}f}{unit}</span>'


def _eok(v):
    if v is None:
        return "—"
    a = abs(v)
    s = f"{a/1e4:,.2f}조" if a >= 1e4 else f"{a:,.0f}억"
    cls = "up" if v > 0 else ("dn" if v < 0 else "")
    return f'<span class="{cls}"><b>{"+" if v > 0 else ("−" if v < 0 else "")}{s}</b></span>'


# ════════════════════════════════════════════════════════════
# ② 선행 신호판
# ════════════════════════════════════════════════════════════
LEAD_HELP = (
    "<b>📖 이 판이 왜 필요한가</b> — 아래 지표들은 «오늘 코스피가 어땠나»가 아니라 <b>«다음 장이 어느 쪽으로 기울어 있나»</b>를 "
    "먼저 보여주는 것들이다. 각 줄의 <b>의미</b> 칸이 «이 숫자가 오르면/내리면 주식에 무슨 뜻인가»이고, "
    "<b>신호</b> 색은 규칙으로 자동 판정한다(초록=주식에 우호 · 노랑=중립 · 빨강=부담). "
    "자세한 원리는 맨 뒤 <b>📘 해설 부록</b>에 있다.")


def lead_rows(D):
    ex = D.get("extra") or {}
    fu = ex.get("futures") or {}
    fl = (ex.get("flows") or {}).get("KOSPI") or {}
    ewy = ex.get("ewy") or {}
    rt = ex.get("rates") or {}
    pg = (ex.get("program") or {}).get("KOSPI") or {}
    adr = D.get("adr") or {}
    bus = D.get("breadth_us") or {}
    combo = ex.get("foreign_combo") or {}
    rows = []
    if fu:
        c = "g" if (fu["frn"] > 0 and fu.get("frn_5d", 0) > 0) else ("r" if (fu["frn"] < 0 and fu.get("frn_5d", 0) < 0) else "y")
        stk = fu.get("frn_streak", 0)
        rows.append(("외국인 K200 선물", f'{_eok(fu["frn"])} <span style="font-size:8.6px;">(≈{fu.get("contracts") or 0:+,}계약)</span>',
                     f'5일 합 {_eok(fu.get("frn_5d"))} · {"연속 순매수" if stk > 0 else "연속 순매도"} {abs(stk)}일', c,
                     "외국인이 선물로 «지수 방향»에 베팅한 크기. 현물보다 빨리 움직여 다음 날 방향을 먼저 보여준다.",
                     "순매수가 며칠 이어지면 지수 상방 쪽. 현물 매도+선물 매수는 «엇갈림»(차익·헤지)이라 단정 금지."))
    if combo:
        lab = combo["label"]
        c = "g" if "동반 매수" in lab else ("r" if "동반 매도" in lab else "y")
        rows.append(("외국인 현·선물 조합", f"<b>{lab}</b>",
                     f'현물 {_eok(combo.get("spot"))} / 선물 {_eok(combo.get("fut"))}', c,
                     "현물(주식)과 선물을 같이 사면 «진짜 매수», 같이 팔면 «진짜 매도»로 읽는다.",
                     "동반 매수=가장 강한 우호 신호 · 동반 매도=가장 강한 경고 · 엇갈림=관망."))
    if ewy:
        r = ewy.get("resid") or 0
        c = "g" if r >= 1 else ("r" if r <= -1 else "y")
        rows.append(("EWY(미국 상장 한국 ETF)", f'${ewy["close"]:,.2f} {_pc(ewy["chg"])}',
                     f'한국장 이후 새 정보분 <b>{_pc(r)}</b><br><span style="font-size:8.2px;">{ewy.get("note","")}</span>', c,
                     "한국장이 닫힌 뒤 뉴욕에서 거래되는 «한국 주식 바구니». 한국장 마감 이후 나온 뉴스가 여기에 먼저 반영된다.",
                     "새 정보분 ±1% 이상이면 다음 개장 갭 방향의 강한 힌트(원화 환율 효과 제거 후)."))
    if rt.get("us2y"):
        v = rt["us2y"]; ch = v.get("chg_bp") or 0
        c = "g" if ch <= -5 else ("r" if ch >= 5 else "y")
        rows.append(("미 국채 2년물", f'<b>{v["val"]:.3f}%</b> <span style="font-size:8.4px;">({v["date"]})</span>',
                     f'하루 {_pc(ch,1,"bp")} · 5일 {_pc(v.get("chg5_bp"),1,"bp")}', c,
                     "연준이 앞으로 금리를 어떻게 할지에 대한 시장의 «예상». 10년물보다 정책 기대에 민감하다.",
                     "급등(+5bp↑)=금리 인상·고금리 유지 우려 → 성장주 부담. 급락=완화 기대 → 성장주 우호."))
    if rt.get("real10") or rt.get("real10_est"):
        re_ = rt.get("real10_est") or {}
        rv = rt.get("real10") or {}
        ch = re_.get("chg_bp") if re_ else rv.get("chg_bp")
        lvl = re_.get("val") if re_ else rv.get("val")
        c = "g" if (ch is not None and ch <= -5) else ("r" if (ch is not None and ch >= 5) or (lvl or 0) >= 2.5 else "y")
        rows.append(("미 10년 실질금리", (f'<b>{re_["val"]:.2f}%</b> <span style="font-size:8.4px;">(당일 추정 {re_["date"]})</span><br>' if re_ else "")
                     + (f'<span style="font-size:8.4px;">TIPS 실측 {rv["val"]:.2f}% ({rv["date"]})</span>' if rv else ""),
                     f'하루 {_pc(ch,1,"bp")}' + (f' · 20일 {_pc(rv.get("chg20_bp"),1,"bp")}' if rv else ""), c,
                     "물가를 뺀 «진짜» 금리. 미래 이익을 오늘 가치로 깎는 할인율이라, 오르면 성장주(구글 등) 밸류에이션이 눌린다.",
                     "2.5% 이상이면 역사적 고수준(부담). 하루 +5bp 이상 급등은 성장주에 즉각 악재."))
    if rt.get("bei10"):
        v = rt["bei10"]
        rows.append(("미 10년 기대인플레(BEI)", f'<b>{v["val"]:.2f}%</b> <span style="font-size:8.4px;">({v["date"]})</span>',
                     f'하루 {_pc(v.get("chg_bp"),1,"bp")}', "y",
                     "시장이 예상하는 향후 10년 평균 물가. 명목금리 = 실질금리 + 기대인플레.",
                     "명목금리 상승이 «물가 기대» 때문인지 «실질금리» 때문인지 가른다 — 실질 쪽이면 더 위험."))
    if adr:
        a20 = adr.get("above20")
        c = "g" if (a20 or 0) >= 60 else ("r" if (a20 or 0) < 40 else "y")
        whole = f'전체 코스피 상승 {int(pg["up"])} / 하락 {int(pg["dn"])}종(ADR {pg["adr"]:.2f})<br>' if pg.get("up") else ""
        rows.append(("시장 폭 — 국장", whole + f'시총 상위 {adr["n"]}종 중 <b>20일선 위 {a20}%</b> · 60일선 위 {adr.get("above60")}%',
                     f'20일선 위 비율 5일 전 {adr.get("above20_5d")}% → 20일 전 {adr.get("above20_20d")}% · 신고가 {adr.get("nh")} / 신저가 {adr.get("nl")}', c,
                     "지수가 올라도 «몇 종목만» 오르는지, «대부분»이 오르는지. 소수 대형주만 끄는 상승은 오래 못 간다.",
                     "20일선 위 60%↑=건강한 상승 · 40%↓=좁은 장(지수 착시). 지수↑인데 비율↓이면 경고(다이버전스)."))
    if bus:
        a20 = bus.get("above20")
        c = "g" if (a20 or 0) >= 60 else ("r" if (a20 or 0) < 40 else "y")
        rows.append(("시장 폭 — 미장", f'시총 상위 {bus["n"]}종 중 <b>20일선 위 {a20}%</b> · 60일선 위 {bus.get("above60")}%',
                     f'5일 전 {bus.get("above20_5d")}% · 20일 전 {bus.get("above20_20d")}% · 신고가 {bus.get("nh")} / 신저가 {bus.get("nl")}', c,
                     "미국 대형주 전반의 참여도. 구글 같은 개별 보유 종목이 «시장 따라» 움직이는지 판단하는 바탕.",
                     "국장과 같은 기준으로 읽는다."))
    if pg.get("nonarb") is not None:
        v = pg["nonarb"]
        c = "g" if v > 0 else ("r" if v < -3000 else "y")
        rows.append(("프로그램 비차익(코스피)", _eok(v), f'차익 {_eok(pg.get("arb"))} · 합계 {_eok(pg.get("prog"))}', c,
                     "기관·외국인이 바구니(여러 종목)로 한꺼번에 사고파는 물량. 대형주 방향을 좌우한다.",
                     "−3천억 이하 대량 매도면 대형주 하방 압력. 지속되면 외국인 이탈 신호."))
    return rows


def lead_board_html(D, R):
    rows = lead_rows(D)
    if not rows:
        return '<div class="box box-b">선행 신호판 산출 불가 — §8 참조.</div>'
    h = ['<table class="pb-avoid"><caption class="corner-cap">①-2 선행 신호판 — 외국인 선물 · EWY · 미 2년물 · 실질금리 · 시장 폭</caption>'
         '<thead><tr><th style="width:14%">지표</th><th style="width:20%">오늘 값 (실측)</th><th style="width:17%">변화 · 추세</th>'
         '<th style="width:5%">신호</th><th style="width:24%">무엇을 뜻하나</th><th>읽는 법(임계)</th></tr></thead><tbody>']
    for k, v, chg, c, mean, how in rows:
        h.append(f'<tr><td class="tl"><b>{k}</b></td><td class="tl">{v}</td><td class="tl" style="font-size:9px;">{chg}</td>'
                 f'<td class="tc">{_sig(c)}</td><td class="tl" style="font-size:9px;">{mean}</td>'
                 f'<td class="tl" style="font-size:9px;">{how}</td></tr>')
    h.append('</tbody></table>')
    ng = sum(1 for r in rows if r[3] == "g"); nr = sum(1 for r in rows if r[3] == "r")
    h.append(f'<div class="box box-a pb-avoid" style="font-size:9.4px;">{LEAD_HELP} '
             f'<b>오늘 집계: 초록 {ng} · 빨강 {nr} · 노랑 {len(rows)-ng-nr}</b>.</div>')
    if R.get("lead_sogo"):
        h.append(f'<div class="box box-b" style="font-size:9.6px;">➡ <b>다음 장 판단</b> — {R["lead_sogo"]}</div>')
    return "\n".join(h)


# ════════════════════════════════════════════════════════════
# ③ 판단 매트릭스
# ════════════════════════════════════════════════════════════
def revision(bs, name, today_target, asof=None):
    """brief_state 컨센서스 이력으로 목표가 변화율(약 4주)을 계산. 이력 없으면 None."""
    hist_ = ((bs or {}).get("cons") or {}).get(name) or []
    if not hist_ or not today_target:
        return None, None
    try:
        d_today = dt.date.fromisoformat(asof) if asof else dt.date.today()
        old = [h for h in hist_ if h.get("target_mean")]
        if not old:
            return None, None
        ref = min(old, key=lambda h: abs((d_today - dt.date.fromisoformat(h["date"])).days - 28))
        days = (d_today - dt.date.fromisoformat(ref["date"])).days
        if days < 5:
            return None, None
        return (today_target / ref["target_mean"] - 1) * 100, days
    except Exception:
        return None, None


def hmatrix(name, x, held, st, bs, asof=None):
    """4축(논리·추세·수급·위치) 자동 판정 → 규칙 판정. st = extra.stocks[name] (없어도 됨)."""
    ax = []
    px = x["close"]
    tm = (st or {}).get("target_mean")
    rv, rdays = revision(bs, name, tm, asof)
    if tm:
        up = (tm / px - 1) * 100
        c = "g" if (up >= 10 and (rv is None or rv >= 0)) else ("r" if (up < 0 or (rv is not None and rv <= -5)) else "y")
        v = f"목표가 평균 {tm:,.2f} → 여력 {up:+.1f}%" if tm < 5000 else f"목표가 평균 {tm:,.0f} → 여력 {up:+.1f}%"
        v += f" · 4주 변화 {rv:+.1f}%" if rv is not None else " · 변화 추적 시작"
    else:
        c, v = "y", "컨센서스 없음"
    ax.append(("논리(컨센서스)", c, v, "증권가 평균 목표가까지 여력 + 목표가가 오르는 중인지(리비전)"))
    tr_g = px > x["ma60"] and x["ma20"] > x["ma60"]
    tr_r = px < x["ma60"] and x["ma20"] < x["ma60"]
    c = "g" if tr_g else ("r" if tr_r else "y")
    ax.append(("추세", c, f'60일선 {x["vs_ma60"]:+.1f}% · 20일선 {"위" if x["ma20"] > x["ma60"] else "아래"}(60일선 대비) · 주봉 RSI {x["rsi_w"]:.0f}',
               "종가·20일선이 60일선 위에 있으면 중기 상승 추세"))
    if st and st.get("frn_20d_amt") is not None:
        n20 = (st.get("frn_20d_amt") or 0) + (st.get("inst_20d_amt") or 0)
        n5 = (st.get("frn_5d_amt") or 0) + (st.get("inst_5d_amt") or 0)
        c = "g" if (n20 > 0 and n5 > 0) else ("r" if (n20 < 0 and n5 < 0) else "y")
        v = f"외인+기관 5일 {n5:+,.0f}억 · 20일 {n20:+,.0f}억 · 외국인 {'연속 순매수' if (st.get('frn_streak') or 0) > 0 else '연속 순매도'} {abs(st.get('frn_streak') or 0)}일"
        ax.append(("수급", c, v, "큰손(외국인·기관)이 사고 있나 — 20일·5일 모두 매수면 초록"))
    else:
        u = x.get("ud20")
        c = "g" if (u or 0) >= 1.2 else ("r" if (u or 0) < 0.9 else "y")
        ax.append(("수급(거래량)", c, f"상승일/하락일 거래량 {u:.2f}배(20일)" if u else "—",
                   "미장은 투자자별 집계가 없어 «오른 날 거래가 더 많은가»로 매집 여부를 본다"))
    rsi, pb = x["rsi"], x["pb"]
    c = "r" if (rsi > 80 or pb > 1.1) else ("y" if (rsi > 70 or pb > 1.0 or rsi < 30) else "g")
    av = x.get("avwap_lo")
    ax.append(("위치(과열·지지)", c, f"RSI {rsi:.0f} · %b {pb:.2f}" + (f" · 저점 앵커 VWAP {av:,.2f} ({(px/av-1)*100:+.1f}%)" if av and av < 5000 else (f" · 저점 앵커 VWAP {av:,.0f} ({(px/av-1)*100:+.1f}%)" if av else "")),
               "과열(RSI 80↑·밴드 상단 이탈)이면 빨강. 저점 이후 평균 매입가(VWAP) 위면 매수자 대부분이 이익 중"))
    ng = sum(1 for a in ax if a[1] == "g"); nr = sum(1 for a in ax if a[1] == "r")
    if held:
        rule = ("추가매수 검토" if ng == 4 else "보유" if ng == 3 else "보유(경계)" if ng == 2 and nr <= 1
                else ("청산 검토" if (ax[0][1] == "r" and ax[1][1] == "r") else "일부 매도·축소 검토"))
    else:
        rule = ("진입 검토" if ng == 4 else "조건부 진입(트리거 확인)" if ng == 3 else "관망" if nr <= 1 else "회피")
    return ax, rule, ng, nr


def hmatrix_html(name, x, held, st, bs, badge, asof=None):
    ax, rule, ng, nr = hmatrix(name, x, held, st, bs, asof)
    h = [f'<div class="blk keep"><span class="chip c-blue">⑩ 판단 매트릭스 — 4축 자동 판정</span><table><thead><tr>'
         '<th style="width:16%">축</th><th style="width:6%">신호</th><th style="width:44%">오늘 값</th><th>이 축이 보는 것</th></tr></thead><tbody>']
    for k, c, v, why in ax:
        h.append(f'<tr><td class="tl"><b>{k}</b></td><td class="tc">{_sig(c)}</td><td class="tl">{v}</td>'
                 f'<td class="tl" style="font-size:8.8px;">{why}</td></tr>')
    same = (rule.split("(")[0] in badge) or (badge.split("(")[0] in rule)
    h.append(f'</tbody></table><div class="box box-b" style="font-size:9.4px;"><b>▶ 규칙 판정</b> — 초록 {ng} · 빨강 {nr} → '
             f'<b class="{"vg" if ng >= 3 else ("vr" if nr >= 2 else "vy")}">{rule}</b> · 분석 판단 배지 <b>{badge}</b> '
             + ("(일치)" if same else "<b class='warn'>(불일치 — 위 ①「근거」에 이유가 있어야 한다)</b>")
             + '<br><span style="font-size:8.6px;color:#5A6570;">규칙: '
             + ("보유 — 초록4=추가매수 검토 · 3=보유 · 2=보유(경계) · 논리·추세 동시 빨강=청산 검토 · 그 외=일부 매도·축소 검토"
                if held else "미보유 — 초록4=진입 검토 · 3=조건부 진입 · 빨강1 이하=관망 · 빨강2↑=회피")
             + '. 규칙은 «기준선»이고, 뉴스·이벤트를 반영한 최종 판단은 배지가 한다.</span></div></div>')
    return "\n".join(h), rule


# ════════════════════════════════════════════════════════════
# ④ 이벤트 예상 변동폭
# ════════════════════════════════════════════════════════════
def exp_move_html(items):
    """items: [(name, x, cur, held)]"""
    h = ['<table class="pb-avoid"><caption class="corner-cap">이벤트 예상 변동폭 — 최근 20일 일간 변동성(σ) 기준</caption>'
         '<thead><tr><th style="width:15%">종목</th><th>현재가</th><th>일간 σ</th><th>내일 68% 범위(±1σ)</th>'
         '<th>이벤트 당일 경계(±2σ)</th><th>5거래일 68% 범위</th><th style="width:22%">쓰는 법</th></tr></thead><tbody>']
    for n, x, cur, held in items:
        s = x.get("sig20")
        if not s:
            continue
        p = x["close"]
        fm = (lambda v: f"${v:,.2f}") if cur == "$" else (lambda v: f"{v:,.0f}원")
        lo1, hi1 = p * (1 - s / 100), p * (1 + s / 100)
        lo2, hi2 = p * (1 - 2 * s / 100), p * (1 + 2 * s / 100)
        s5 = s * 5 ** 0.5
        h.append(f'<tr><td class="tl"><b>{n}</b>{" <span class=warn>[보유]</span>" if held else ""}</td><td class="tr">{fm(p)}</td>'
                 f'<td class="tc">±{s:.2f}%</td><td class="tc">{fm(lo1)} ~ {fm(hi1)}</td>'
                 f'<td class="tc"><b class="warn">{fm(lo2)}</b> ~ {fm(hi2)}</td>'
                 f'<td class="tc">±{s5:.1f}% ({fm(p*(1-s5/100))} ~ {fm(p*(1+s5/100))})</td>'
                 f'<td class="tl" style="font-size:8.6px;">±2σ 밖 종가 = «평소 흔들림이 아닌» 사건 반응 → 손절·추가 판단을 그날 다시 한다</td></tr>')
    h.append('</tbody></table>')
    h.append('<div class="box box-a pb-avoid" style="font-size:9.2px;">📖 <b>읽는 법</b> — 최근 20일 동안 하루 평균 얼마나 출렁였는지(σ)로 '
             '«정상 범위»를 미리 그어 둔다. 통계적으로 하루 등락은 약 68%가 ±1σ, 95%가 ±2σ 안에 든다. '
             '<b>CPI·FOMC·실적 같은 이벤트 날에 ±2σ를 넘으면</b> 시장이 그 이벤트를 «예상 밖»으로 받아들였다는 뜻이다 — '
             '그 방향으로 추세가 이어질 확률이 높아 <span class="hl">손절·추가매수 판단을 그날 종가로 다시 한다</span>. '
             '안쪽이면 «소음»이므로 계획대로 유지한다.</div>')
    return "\n".join(h)


# ════════════════════════════════════════════════════════════
# ⑤ 판단 채점표
# ════════════════════════════════════════════════════════════
def scorecard_html(D):
    sc = D.get("scorecard") or {}
    h = ['<div class="sub2">★ 판단 채점표 — 지난 회차의 추천·판단이 실제로 맞았나 (자동 채점)</div>']
    if not (sc.get("picks") or sc.get("watch") or sc.get("kospi")):
        h.append('<div class="box box-a pb-avoid" style="font-size:9.4px;"><b>채점 기록 시작 회차</b> — 이번 회차의 탑다운 판정·카드 배지·'
                 '추천 카드(진입가·손절가·목표가·패턴)를 <b>brief_state.json</b>에 기록했다. 다음 회차부터 '
                 '«추천 후 목표 도달/손절 도달/진행 중»과 수익률, 패턴별 적중률이 이 자리에 자동으로 쌓인다. '
                 '<span class="hl">채점의 목적은 자책이 아니라 «어떤 기준이 실제로 먹히는지» 가려 기준을 고치는 것</span>이다.</div>')
        return "\n".join(h)
    s = sc.get("sum")
    if s:
        h.append(f'<div class="box box-navy pb-avoid"><b>▶ 누적</b> — 추천 {s["n"]}건 · 목표 도달 <b class="vg">{s["hit"]}</b> · '
                 f'손절선 도달 <b class="vr">{s["stop"]}</b> · 진행 중 {s["open"]} · 현재 수익 중 {s["win"]}/{s["n"]} · 평균 {s["avg"]:+.2f}%</div>')
    if sc.get("picks"):
        h.append('<table class="pb-avoid"><thead><tr><th>추천일</th><th>종목</th><th>등급·패턴</th><th>추천 시 종가</th><th>손절</th><th>목표</th>'
                 '<th>현재</th><th>수익률</th><th>결과</th></tr></thead><tbody>')
        for p in sc["picks"][-12:]:
            rc = "vg" if p["res"] == "목표 도달" else ("vr" if p["res"] == "손절선 도달" else "vy")
            h.append(f'<tr><td class="tc">{p["asof"]}</td><td class="tl"><b>{p["name"]}</b></td><td class="tc">{p.get("grade") or "—"}</td>'
                     f'<td class="tr">{p["entry"]:,.2f}</td><td class="tr">{(p["stop"] or 0):,.2f}</td><td class="tr">{(p["target"] or 0):,.2f}</td>'
                     f'<td class="tr">{p["now"]:,.2f}</td><td class="tc">{_pc(p["ret"])}</td>'
                     f'<td class="tc"><b class="{rc}">{p["res"]}</b>{(" " + p["when"]) if p.get("when") else ""}</td></tr>')
        h.append('</tbody></table>')
    if sc.get("watch"):
        h.append('<table class="pb-avoid"><thead><tr><th>판단일</th><th>종목</th><th>배지</th><th>규칙 판정</th><th>그때</th><th>지금</th><th>이후 수익률</th></tr></thead><tbody>')
        for w in sc["watch"][-8:]:
            h.append(f'<tr><td class="tc">{w["asof"]}</td><td class="tl"><b>{w["name"]}</b></td><td class="tc">{w.get("badge") or "—"}</td>'
                     f'<td class="tc">{w.get("rule") or "—"}</td><td class="tr">{w["then"]:,.2f}</td><td class="tr">{w["now"]:,.2f}</td>'
                     f'<td class="tc">{_pc(w["ret"])}</td></tr>')
        h.append('</tbody></table>')
    if sc.get("kospi"):
        h.append('<table class="pb-avoid"><thead><tr><th>판정일</th><th>탑다운 판정</th><th>그때 코스피</th><th>이후 코스피</th></tr></thead><tbody>')
        for k in sc["kospi"][-6:]:
            h.append(f'<tr><td class="tc">{k["asof"]}</td><td class="tl">{k.get("verdict") or "—"}</td>'
                     f'<td class="tr">{k["then"]:,.2f}</td><td class="tc">{_pc(k["ret"])}</td></tr>')
        h.append('</tbody></table>')
    return "\n".join(h)


# ════════════════════════════════════════════════════════════
# ⑥ 해설 부록
# ════════════════════════════════════════════════════════════
GLOSSARY = [
    ("A. 선행 지표 (다음 장 방향을 먼저 보여주는 것)", [
        ("외국인 코스피200 선물 순매수",
         "선물은 «코스피200 지수를 미래 가격에 사고파는 계약»이다(1계약 = 지수×25만원, 지금 약 2.8억원). 외국인은 한국 주식을 "
         "대량으로 사기 전에 선물로 먼저 방향을 잡는 경우가 많아, <b>선물 순매수가 며칠 이어지면 현물(주식) 매수가 뒤따르는</b> 경향이 있다. "
         "단위는 <b>억원</b>이고 괄호 안은 계약 수 환산. <b>현물 매도 + 선물 매수</b>는 «주식은 팔되 지수 하락엔 대비» 같은 차익·헤지일 수 있어 "
         "단정하지 않고, <b>현·선물 동반 매수/매도</b>일 때만 강한 신호로 읽는다."),
        ("EWY (iShares MSCI South Korea ETF)",
         "뉴욕에 상장된 «한국 대형주 바구니» ETF다. 한국장이 15:30에 닫힌 뒤에도 밤새 뉴욕에서 거래되므로 <b>한국장 마감 이후에 나온 뉴스가 "
         "EWY 가격에 먼저 반영</b>된다. 달러로 거래되므로 원/달러 변화를 빼야 한다: <b>새 정보분 = EWY 등락 − (같은 날 코스피 등락 − 원/달러 등락)</b>. "
         "이 값이 +1% 이상이면 다음 날 코스피 갭 상승, −1% 이하면 갭 하락 가능성이 크다. 한국 휴장일엔 EWY 등락 전체가 다음 개장 갭 힌트다."),
        ("미 국채 2년물",
         "2년 뒤 만기 미국 국채의 금리. 앞으로 2년간 연준 기준금리의 «시장 평균 예상»에 가장 가깝다. <b>급등 = «금리 더 올린다/오래 높게 유지한다»</b>는 "
         "베팅이 늘었다는 뜻 → 성장주·반도체에 부담. 급락은 금리 인하 기대. 10년물은 경기·재정 요인이 섞여서, 정책 기대는 2년물이 더 깨끗하다."),
        ("미 10년 실질금리 · 기대인플레(BEI)",
         "명목금리(우리가 보는 10년물)는 <b>실질금리 + 기대인플레</b>로 쪼개진다. 실질금리는 물가를 뺀 «진짜 돈의 값»으로, 먼 미래 이익을 "
         "오늘 가치로 할인하는 비율이다. 그래서 <b>실질금리가 오르면 이익이 먼 미래에 몰린 성장주(구글 같은 빅테크)의 적정 가치가 깎인다</b>. "
         "TIPS(물가연동국채) 실측은 하루 늦게 게시되므로, 당일 값은 «10년물 − BEI»로 추정해 함께 적는다(두 값의 차이는 0.01%p 수준으로 검증)."),
        ("시장 폭(Breadth)",
         "«얼마나 많은 종목이 같이 오르나». ① <b>ADR</b> = 오른 종목 수 ÷ 내린 종목 수(1 이상이면 오른 종목이 더 많다) "
         "② <b>20일선·60일선 위 비율</b> = 단기·중기 상승 추세에 있는 종목 비중 ③ <b>52주 신고가·신저가 수</b>. "
         "지수가 올라도 비율이 떨어지면 «소수 대형주만 끄는 좁은 장» → 되돌림 위험이 크다(다이버전스). 60%↑면 건강, 40%↓면 취약."),
        ("프로그램 비차익",
         "여러 종목을 바구니로 한 번에 사고파는 기관·외국인 주문 중 선물과 무관한 것. 대형주 방향을 직접 움직인다. "
         "수천억 단위 순매도가 며칠 이어지면 외국인 자금 이탈의 조기 신호."),
    ]),
    ("B. 종목을 고르는 기법", [
        ("RS 백분위 (상대강도)",
         "같은 시장 150종 안에서 «최근 1년 수익률»이 몇 등인가를 1~99로 매긴 것(최근 3개월에 가중 0.4). "
         "<b>80 이상 = 상위 20% 주도주</b>. 오르는 종목이 계속 오르는 «모멘텀» 효과는 학계에서 가장 오래 검증된 현상 중 하나다. "
         "<b>RS 선행 신고가</b>는 주가는 아직 고점 아래인데 «지수 대비 상대 성과»가 먼저 1년 최고치를 찍은 경우 — 주가 신고가의 선행 신호로 쓴다."),
        ("추정치·목표가 변화 (리비전)",
         "증권사 평균 목표가·이익 추정치가 <b>지금 올라가고 있는가</b>. 주가는 «이익 수준»보다 «이익 전망의 변화»에 더 크게 반응한다. "
         "회차마다 컨센서스를 기록해 약 4주 전 대비 변화율을 계산한다(기록이 쌓이기 전 회차는 «추적 시작»)."),
        ("앵커드 VWAP (저점 기준 평균 매입가)",
         "최근 120일 중 <b>가장 낮았던 날부터 오늘까지 거래된 가격의 거래량 가중 평균</b>. 그 저점 이후 산 사람들의 평균 단가다. "
         "현재가가 이 선 위면 «저점 이후 매수자 대부분이 이익» → 매물 압력이 약하고 지지선 역할, 아래면 반대. 이동평균보다 «실제 매입가»에 가깝다."),
        ("판단 매트릭스 (4축)",
         "보유·관찰 종목을 ① 논리(목표가 여력·리비전) ② 추세(60일선 위·20일선>60일선) ③ 수급(외국인+기관 5·20일) ④ 위치(과열·앵커드 VWAP) "
         "4축으로 자동 채점해 «규칙 판정»을 낸다. 사람(분석)의 배지와 다르면 그 이유가 근거에 적혀 있어야 한다 — 감(感)이 규칙을 이긴 이유를 남기는 장치."),
        ("판단 채점표",
         "지난 회차 추천 카드가 목표가에 먼저 닿았는지, 손절선에 먼저 닿았는지를 실제 일봉 고가·저가로 채점한다. "
         "쌓이면 «차트 패턴별 실제 적중률», «규칙 판정 vs 분석 배지 중 누가 더 맞았나»를 숫자로 볼 수 있다."),
    ]),
    ("C. 강화 카드 선정 기준 — 백테스트로 채택한 규칙 (★v65)", [
        ("선정 경로", "<b>① 후보 풀</b> 코스피 시총 상위 150 · 미장 상위 150 → <b>② 차트 망가짐 필터(주봉 먼저)</b> → <b>③ 합성 모멘텀 순위</b> → "
         "<b>④ 기본 선정</b>(지난 회차 선정이 10위 안이면 유지 + 순위대로 3종) → <b>⑤ 차트 판독</b>(주봉→일봉, 명백히 망가진 경우만 교체)."),
        ("② 차트 망가짐 필터", "종가가 200일선 위 · 50일선이 200일선 위(정배열) · 주봉 60주선 아래로 떨어지며 60주선도 하락하는 상태가 아님 · 주봉 구름 위(양운). "
         "백테스트에서 이 조건을 어긴 종목은 이후 60일 동안 유니버스 평균보다 1~3%p 뒤처졌다(두 시장·두 기간 모두). «망가진 차트를 거른다»는 생각이 데이터로 확인된 부분."),
        ("③ 합성 모멘텀", "12-1개월 수익(최근 1개월 제외 1년 수익) · 6-1개월 수익 · 6개월 로그가격 추세 기울기를 시장 안에서 백분위로 바꿔 평균. "
         "최근 1개월을 빼는 이유는 직전 한 달 급등분이 되돌림되는 경향이 있어서다. 순위 1~3위가 4~10위보다 뚜렷이 좋았다."),
        ("진입 시점", "다음 거래일에 진입한다. 20일선·전환선·기준선 눌림 대기, 20일 고점 돌파 확인, 과열 시 보류는 모두 즉시 진입보다 성적이 나빴다 — "
         "강한 종목은 기다리는 사이 달아난다. 차트 지표는 «어디가 지지선인가»를 보는 맥락으로 쓴다."),
        ("보유 관리·손절(★v66)", "점검일(config.REBAL_WEEKS 주마다)에만 교체한다 — 보유 종목이 순위 10위 안이고 필터를 통과하면 유지(버퍼), 빈자리는 순위대로. "
         "점검일 사이에는 비상 손절(진입가 −25%)만 반영한다. 브리핑은 «보유 장부»(진입가·진입일·마지막 점검일)를 brief_state에 기록해 회차마다 이어받는다. "
         "20일선·50일선 이탈 청산, −2.5 ATR 손절은 흔들림에 털려 수익을 크게 깎았다."),
        ("가동 조건(★v66)", "점검일에 지수(코스피·S&P500)가 200일선 위일 때만 그 시장 전략을 가동하고, 아래면 매수를 멈추고 보유분을 현금으로 돌린다. "
         "10년 백테스트(2018~2026)에서 가동 조건이 없을 때 국장 2018~19 횡보·하락 구간에 연 −47%·최대 낙폭 −61%였고, 조건을 넣자 −2%·−7%로 줄었다. "
         "국·미 50:50 최대 낙폭은 −53% → −28%. 대신 강한 반등 초입 일부를 놓쳐 전체 수익은 조금 줄었다."),
        ("자금 배분", "국장 3종·미장 3종에 같은 금액(50:50), 종목당 같은 비중. 두 시장 포트의 상관이 낮아(0.2~0.4) 섞으면 수익은 비슷하고 낙폭이 줄었다. "
         "종목 수를 1~2개로 줄이면 결과가 들쭉날쭉했고, 5~10개로 늘리면 수익이 줄었다."),
        ("한계", "검증 기간 2023-06~2026-08(84개 시점). 유니버스가 «현재» 시총 상위라 생존 편향이 있다 — 그 시점 거래대금 상위로 제한해도 결론은 같았지만 수치는 줄었다. "
         "모멘텀 상위 종목은 개별로 60일 −20~−30%가 나는 경우가 10%쯤 있다. 과거 성적이며 미래 수익을 보장하지 않는다. "
         "판독 에이전트의 교체 판단은 백테스트하지 못했으므로 채점표로 따로 추적한다."),
    ]),
    ("D. 손절·변동성 용어", [
        ("ATR (Average True Range)",
         "하루 평균 «실제 변동폭»(전일 종가와의 갭까지 포함한 고가−저가)의 14일 평균. <b>ATR 5%</b>면 그 종목은 하루 5% 정도 흔드는 게 «평소»다. "
         "손절을 ATR보다 좁게 잡으면 평범한 흔들림에 털린다."),
        ("동적 ATR 배수 · 손절 3단", "손절 최종선 = 앵커(보유 이익 구간은 최근 고점, 손실 구간은 평단, 신규는 진입가) − k×ATR. "
         "ATR이 작으면 k=3.0, 크면 1.5까지 줄이고, 어떤 경우에도 −15%를 넘지 않는다(캡). 1·2·3차 선에서 1/3씩 줄여 «한 번에 다 파는» 실수를 막는다."),
        ("표본외 · 종목별 검증", "«표본외»는 모델을 만들 때 쓰지 않은 기간으로 다시 시험한 성적(과최적화 방지). "
         "«종목별 검증»은 그 종목 과거에서 고점수 구간이 저점수 구간보다 실제로 나았는지 — ✕면 그 종목엔 점수를 근거로 쓰지 않는다."),
    ]),
]


def glossary_html():
    h = ['<div class="corner pgnew">📘 해설 부록 — 처음 보는 지표·기법 읽는 법</div>',
         '<div class="box box-a pb-avoid" style="font-size:9.6px;">이 부록은 매 회차 같은 내용이다(회차 서술이 아니라 «사전»). '
         '본문에서 모르는 용어가 나오면 여기서 찾는다. 각 항목은 <b>무엇인가 → 왜 주가에 영향을 주나 → 어떻게 읽나</b> 순서다.</div>']
    for sec, items in GLOSSARY:
        h.append(f'<div class="sub2">{sec}</div><table class="pb-avoid"><thead><tr><th style="width:20%">용어</th><th>설명</th></tr></thead><tbody>')
        for k, v in items:
            h.append(f'<tr><td class="tl"><b>{k}</b></td><td class="tl" style="font-size:9.4px;line-height:1.55;">{v}</td></tr>')
        h.append('</tbody></table>')
    return "\n".join(h)


# ════════════════════════════════════════════════════════════
# ⑦ brief_state.json 갱신
# ════════════════════════════════════════════════════════════
def state_update(bs, rnd, exits, cons):
    bs = dict(bs or {})
    bs["version"] = 1
    rs = [r for r in bs.get("rounds", []) if r.get("asof") != rnd["asof"]]
    rs.append(rnd)
    bs["rounds"] = rs[-40:]
    bs["exits"] = exits or bs.get("exits", {})
    ch = bs.get("cons", {})
    for n, c in (cons or {}).items():
        lst = [h for h in ch.get(n, []) if h.get("date") != c["date"]]
        lst.append(c)
        ch[n] = lst[-30:]
    bs["cons"] = ch
    return bs
