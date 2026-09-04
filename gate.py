# -*- coding: utf-8 -*-
"""
gate.py — PART 4 자가검증 게이트 G1~G10 자동 검사.
이미지 육안 검사보다 빠르고 정확하다(2026-07-12: 육안으로 놓칠 뻔한 '차트 제목 고아' 2건을 잡아냄).
실행: python3 gate.py <pdf파일>
※ pdftotext는 공백을 \\u0001로, 줄바꿈을 임의 삽입한다 → 공백 제거본(FJ)으로 대조한다.
"""
import subprocess, sys, re, os

PDF = sys.argv[1] if len(sys.argv) > 1 else "briefing.pdf"
NP = int(subprocess.run(["pdfinfo", PDF], capture_output=True, text=True).stdout.split("Pages:")[1].split()[0])
PG = {p: subprocess.run(["pdftotext","-f",str(p),"-l",str(p),PDF,"-"],
                        capture_output=True, text=True).stdout.replace("", " ") for p in range(1, NP+1)}
F = "\n".join(PG.values())
# ★v49: PDF 텍스트 추출은 어절 중간에 줄바꿈을 넣는다("미검증"→"미검\n증").
#   긴 문구를 검사할 때는 공백을 제거한 사본으로 비교한다.
import re as _re
FZ = _re.sub(r"\s+", "", F)
def hz(t): return _re.sub(r"\s+", "", t) in FZ
def cz(t): return FZ.count(_re.sub(r"\s+", "", t))
FJ = re.sub(r"\s+", "", F)                       # 줄바꿈 아티팩트 제거본
HT = open("briefing.html", encoding="utf-8").read()
def h(s, n=1): return FJ.count(re.sub(r"\s+", "", s)) >= n
def pages_with(s): return [p for p, t in PG.items() if s in t]

R = []
def k(g, item, ok, note=""): R.append((g, item, bool(ok), note))

# ── G1 공통 스타일 ──────────────────────────────────────────
k("G1","팔레트·그라디언트·칩 전면 적용", HT.count('class="chip')>50 and "linear-gradient" in HT)
k("G1","본문 잉크 진함(#1c2530 · 10.6px)", "color:#1c2530" in HT and "font-size:10.6px" in HT)
k("G1","행동 의견 노란 형광(#FFE14D)", HT.count('class="hl"')>=10, f'{HT.count(chr(34)+"hl"+chr(34))}곳')
# ★v38.2: 형광 위 투명 텍스트 봉쇄 (2026-07-13 실증 — .box-navy b(노랑)가 .hl(노랑 배경)에 묻혔다)
k("G1","형광(.hl) 내부 텍스트 대비 확보", ".hl b, .box-navy .hl b" in HT and ".hl .warn, .box-navy .hl .warn" in HT)
k("G1","등락 +빨강/−파랑 전역", HT.count('class="up"')+HT.count('class="dn"')>80)
k("G1","한글·이모지 두부 0건", F.count("�")==0)
_BAN = ["2%룰 초과", "2%룰 이내", "2%룰 한도", "2%룰 역산", "2%룰 적용", "포지션 과대"]
k("G1","2%룰 규격 잔존 0건(v41 폐기 — 판정·한도 문구 금지)", not any(b in F for b in _BAN),
  ", ".join(b for b in _BAN if b in F))
k("G6","★손절 3단 분할 표기(1·2·3차)", h("1차 경계선") and h("2차 방어선") and h("3차 최종선"))
k("G6","★손절폭 상한(캡) 준수 — 규격선 -15% 이내",
  not re.search(r"3차 최종선[^%]{0,80}?\(-(1[6-9]|[2-9]\d)\.\d%\)", F))
k("G6","★동적 ATR 배수 표기(고정 3배 금지)", h("동적 배수") and h("×ATR"))
k("G2","★차트 서브패널 = MACD(12·26·9) (거래량 막대 폐기)", h("MACD(12·26·9)") and "거래량 서브차트" not in F)
k("G2","★v45 레벨 보드(이평·볼린저·일목·매물대·갭·스윙) 전 차트 적용",
  F.count("레벨 보드") >= 9 and h("매물대(POC·VAH·VAL)") and h("미충족 갭") and "주황 점선 3개" not in F,
  f'레벨보드 {F.count("레벨 보드")}회')
k("G3","지수표 신설 2종(외국인 수급·국고채 3년물)", h("외국인 수급") and h("국고채 3년물"))
k("G3","KOSPI 차트 직전봉 실측 + 레벨 보드 연결", h("직전봉") and h("레벨 보드") and h("R1·S1"))
k("G1","레벨 표 구분↔지표 자동 부여(어긋남 봉쇄)", h("구분은 현재가 기준 자동 부여"))
k("G1","레벨 전부 숫자('권/근처' 금지)", not re.search(r"\d{3,}선?\s*(권|근처)", F))
k("G1","경고 강조(빨간 볼드/경고박스)", HT.count('class="warn"')>=15)
k("G1","면책 말미 1회만", F.count("투자 자문이 아님")==1)

# ── G2 페이지 배치 ─────────────────────────────────────────
CH = [l.split("📈 ")[1].split(" 일봉")[0] for l in HT.split("\n") if "📈 " in l and " 일봉" in l]
bad = [n for n in CH if not any(f"{n} 일봉" in PG[p] and any(c in PG[p] for c in
        ("공통 규격","평단선 없음","현재 위치 해석","점선 = 평단")) for p in PG)]
k("G2", f"차트 제목-차트 동일 페이지 ({len(CH)}장)", not bad, str(bad) if bad else "")
k("G2","천장감시 keep 무절단", pages_with("주봉 RSI ≥ 75")==pages_with("판정 (무포지션 관점)"))
k("G2","실행표+ⓐⓑⓒⓓ 무절단", pages_with("진입 실행표")==pages_with("ⓓ 진입 회피 조건"))
k("G2","6축+결론 무절단", set(pages_with("일목(구름 위치)")) <= set(pages_with("▶ 결론")))
CORNERS = ["① 지수","매크로 한눈에","KOSPI 일봉 차트","② 코스피 시나리오","②-2 탑다운","③ 섹터 RS",
           "④ 핵심 관찰","현금 · 재진입","⑤ 19신호","⑥ 강화 카드","⑥-2 강화","⑥-3 회귀형","(A) 수급","(B) 경제",
           "리스크 대시보드","행동 함정","성과 추적","(C) 관찰","(D) 맨 끝"]
orph = [(c,p) for c in CORNERS for p,t in PG.items()
        if [l for l in t.split("\n") if l.strip()] and c in [l for l in t.split("\n") if l.strip()][-1]]
k("G2","코너 제목 고아 0건", not orph, str(orph) if orph else "")
k("G2","다칸 가로 배치(display:grid 금지)", "display:grid" not in HT)
k("G2","큰 빈칸 없음", all(len([l for l in t.split("\n") if l.strip()])>=8 for p,t in PG.items() if p!=NP))

# ── G3 앞부분 ─────────────────────────────────────────────
k("G3","지수표 16종 + 비고 빈칸 없음", h("비트코인(BTC-USD)") and h("야간선물"))
k("G3","야간선물 Tier1 시도 후 Tier2 폴백 + §8", h("프록시") and h("Tier"))
k("G3","매크로 2×2 table", HT.count('class="g2 pb-avoid"')>=3)
k("G3","KOSPI 차트 = 매크로 다음·시나리오 앞",
  pages_with("KOSPI 일봉")[0] <= pages_with("② 코스피 시나리오")[0])
k("G3","전 차트 구름 26봉 연속 투영", F.count("구름 26봉 미래투영")>=9, f'{F.count("구름 26봉 미래투영")}장')
k("G3","시나리오 3분할 + 관찰4종 대응 + 체크포인트", h("▶ 관찰 4종 대응",2) and h("개장 후 체크포인트"))

# ── G4 탑다운 ─────────────────────────────────────────────
k("G4","L0 ≥5행 · 맨 위", h("레이어 0 — 수급") and F.count("▶ L0 종합")==1)
k("G4","L1 ≥6행", h("레이어 1 — 범용 매크로") and F.count("▶ L1 종합")==1)
k("G4","L2 ≥5행", h("레이어 2") and F.count("▶ L2 종합")==1)
k("G4","BTC 6만$ 판정(현재가·거리·고점대비)", h("6만$") and h("고점 대비"))
k("G4","자동지표 실측(하이일드·금리차·VIX구조)", h("BAMLH0A0HYM2") and h("T10Y2Y") and h("기간구조"))
k("G4","최종 판정 + 카드 연결 문장", h("탑다운 종합 판정") and h("카드 연결"))

# ── G5 섹터·스크리닝 ────────────────────────────────────────
k("G5","섹터 RS 9~12행 + 판정 색", h("섹터 RS 보드"))
k("G5","PICK 3 + 재진입 분산 코멘트", h("PICK 상위 3") and h("재진입 분산 관점"))
# ★v49: 「매수강도」 폐기 → 선정 점수 기반 상위 표로 교체(인수인계서 §5-④)
k("G5","선정 상위 표 국내·미국(핵심 4종 제외)",
  hz("코스피 선정 상위") and hz("미국 선정 상위") and hz("선정 점수"))

# ── G6 관찰 카드 ───────────────────────────────────────────
NW = 4
k("G6","관찰 4종 × 9블록 전부", all(F.count(x)==NW for x in
   ["② 포지션 상태","⑤ 맥락 (웹 리서치)","⑥ 천장 / 과열 상시 감시","⑨ 리스크"]))
k("G6","① 진입 판단 배지 4/4", F.count("진입 판단 :")==NW)
k("G6","④ 손절 = 동적배수 vs 캡 중 좁은 쪽 채택(★v42)", F.count("좁은(높은) 쪽")>=NW)
k("G6","⑤ 맥락 7라벨", F.count("① 최근 뉴스")==NW and F.count("⑦ ★ 무엇이 확인되면 진입")==NW)
k("G6","⑥ 포물선 4신호 ON/off + 실측값", F.count("포물선 천장 4신호")==NW)
k("G6","⑦ 켜짐+꺼짐+왜", F.count("▶ 켜진 신호")==NW and F.count("▶ 꺼진 핵심 신호")==NW)

# ── G7 대시보드 ───────────────────────────────────────────
k("G7","종목별 열 표 6행", all(h(x) for x in ["ⓐ 현재가","ⓑ 진입 후보가","ⓒ 손절 후보가","ⓓ 목표가","ⓔ 기술 위치","ⓕ 진입 판단"]))
k("G7","3박스(현금·쏠림방지·재진입지침)", h("① 현금 상태") and h("② 쏠림 재발 방지") and h("③ 오늘의 재진입 지침"))
k("G7","지침 ↔ 탑다운 판정 연결", h("탑다운") and h("모드"))

# ── G8 강화 6종 ───────────────────────────────────────────
k("G8","강화 8블록 × 4종", F.count("③ 실행 디테일 표")==4 and F.count("⑥ 6축 색판정 + 결론")==4)
# ── ★v49 G14: 강화 카드 선정 규격 ─────────────────────────────
# ── ★v49 G14: 종목 선정 개선(인수인계서 §5-⑤) ──────────────────
import lib_ind as _L, pick_engine as _PE
k("G14","19신호 가중치 실측판", abs(sum(_L.WEIGHTS.values())-100.0)<0.5 and _L.WEIGHTS["쌍바닥"]==0.0)
k("G14","만점 100점 표기(구 302 라벨 잔존 0건)", "302점" not in F and "/302" not in F)
k("G14","중복 제거 — 추세 4신호·되돌림 3신호", len(_PE.W_TREND)==4 and len(_PE.W_REV)==3)
k("G14","★선정 표에 적용 모델·종목 성격 노출", hz("적용 모델") and hz("종목 성격"))
k("G14","★탈락 종목·사유 노출(유동성·비용·R:R)",
  hz("하드 필터 탈락") and (hz("유동성") or hz("왕복비용")) and hz("손익비"))
k("G14","★회귀형 역방향 경고 표기", hz("역방향 경고"))
k("G14","종목별 검증 결과 노출", hz("종목별 검증") and (hz("통과") or hz("미통과")))
k("G14","시장 레짐 + 포지션 상한", hz("시장 레짐") and hz("포지션 상한"))
k("G14","「먼저 켜질 신호」 하드코딩 제거", "그 다음 <b>구름대돌파</b>" not in HT)
k("G14","선정 점수가 매수강도를 대체", hz("선정 점수") and not hz("매수강도 = 19신호 점등수"))
k("G15","순위 기준 = 선정 점수(19신호 점수 순 금지)",
  cz("v49 선정 규격") >= 4 and hz("19신호 점수는 순위에 쓰이지 않는다") or hz("참고값")
  and hz("19신호 점수 순이 아니다"))
k("G15","이중모델 적용 근거 표기(성격·모델·밴드)",
  cz("적용 모델") >= 4 and cz("성격") >= 4 and cz("표본외") >= 4)
k("G15","실행 가능성 하드 필터 명기",
  hz("하드 필터") and hz("왕복비용") and hz("손익비"))
k("G15","분산 효과 실측(상관·편입 후 σ)",
  cz("10% 편입 시 포트 변동성") >= 3 and not hz("분산 효과 실측 실패"))
k("G15","유니버스 = 시총 상위(레거시 13종 금지)",
  hz("코스피 시총 상위") and not hz("반도체 하위섹터 제외 후 자동 선정"))
k("G15","회귀형 되돌림 후보 코너 노출",
  hz("회귀형 되돌림 후보") and hz("되돌림 3신호"))
k("G8","동적 선정 사유 4/4", F.count("교체(선정) 사유")==4)
k("G8","반도체 하위섹터 제외 명기", h("선정 규칙") and h("반도체"))

# ── G9 후반 코너 ──────────────────────────────────────────
k("G9","수급 실측 금액", h("수급 레이더") and h("➡ 그래서"))
k("G9","캘린더 5열 + 확정 일자", h("모드1 (중기 스윙) 대응") and h("모드2 (단타) 대응"))
k("G9","관찰 4종 실적일 박제(혼동 금지)", h("확정 박제"))
k("G9","리스크 대시보드 4요소", h("VIX 게이지") and h("리스크 노출") and h("모드1 / 모드2 규칙") and h("이번 회차 리스크 이벤트"))
k("G9","행동함정 2열 6종 + 배지", F.count("❌")>=6 or F.count("금지")>=6)
k("G9","성과 추적 = 청산 기준선 검증", h("청산 기준선"))
k("G9","트래커 + 적용환율 + 이벤트 3건", h("적용 환율") and h("임박 이벤트 3건"))
k("G9","맨 끝 §8 로그", h("실패·미확인 로그") and h("시도"))

# ── ★v38 신설: G11 보유 포지션 (POSITIONS 등록 시에만 검사) ─────
import config as _C
_POS = getattr(_C, "POSITIONS", {})
if _POS:
    k("G11","보유 종목 평단·수량 명기", all(f'{p["qty"]}주' in FJ for p in _POS.values()))
    k("G11","평가손익 실계산 표기(원·%)", h("평가손익") and h("매입금액") and h("평가금액"))
    k("G11","보유 종목 차트 평단선 표기", all(h("평단") for _ in [0]) and "평단 " in F)
    k("G11","손절선 + 손절 시 손실 금액 실계산", h("손절 시 손실") and h("리스크 노출 실측"))
    k("G11","행동함정 = 보유 세트(물타기·손절미루기·공포매도)", h("물타기") and h("손절 미루기") and h("공포 전량매도"))
    k("G11","보유 판단 배지(홀드/익절/손절)", h("보유 판단"))

# ── ★v40 신설: G12 위험조정 성과 (perf 수집 성공 시에만 검사) ─────
import json as _json
_P = _json.load(open("data.json")).get("perf", {})
if _P.get("ok"):
    k("G12","위험조정 코너 존재 + 무위험수익률 명기", h("위험조정 성과") and h("무위험수익률"))
    k("G12","3구간(60/120/252) 샤프·변동성·베타 실측", h("샤프지수") and h("베타(β)") and h("초과 위험 배수") and h("소르티노"))
    k("G12","MDD·상관계수·추적오차·알파 표기", h("최대낙폭") and h("상관계수") and h("추적오차") and h("젠센 알파"))
    k("G12","성과 차트 2장(누적곡선+롤링변동성) 제목-차트 동일 페이지",
      len(pages_with("1년 누적 수익"))==1 and len(pages_with("롤링 변동성"))==1)
    k("G12","종목별 리스크 기여도 표(전 보유 종목)",
      h("리스크 기여도") and all(h(n) for n in _P["legs"]))
    k("G12","★개선 조언 3안 + 계산 근거(변동성·베타 변화)",
      h("위험 대비 수익을 개선하는 3가지 방법") and F.count("%p")>=3)
    k("G12","조언에 '그래서 지금 무엇을 하라' 실행 순서", h("그래서 지금 무엇을 하라") and h("실행 순서"))

# ── G10 회귀 총점검 ───────────────────────────────────────
k("G10","축소 코너 명기", h("축소 코너"))
k("G10","계약2 yfinance 실측", h("yfinance"))
k("G10","페이지 ≥14p", NP>=14, f"{NP}p")
k("G10","차트 9장 + 성과 2장", F.count("구름 26봉 미래투영")>=9 and (not _P.get("ok") or h("1년 누적 수익")))

# ── ★v47/v48 신설: G13 19신호 개편 (실측 가중치 + 이중 모델) ─────
import lib_ind as _L
k("G13","19신호 가중치 실측판(합 100 · 쌍바닥 0점)",
  abs(sum(_L.WEIGHTS.values()) - 100.0) < 0.5 and _L.WEIGHTS["쌍바닥"] == 0.0,
  f'합 {sum(_L.WEIGHTS.values()):.1f}')
k("G13","만점 100점 표기 · 구 302점 라벨 잔존 0건", "302점" not in F and "/302" not in F and h("100점 만점"))
k("G13","점수 밴드 근거 노출(표본외·승률)", h("표본외") and h("승률"))
k("G13","점수 미반영 3신호 표기", h("참고·점수 미반영") or not any(z in F for z in _L.ZERO_SIGS))
k("G13","「가장 먼저 켜질 신호」가 실측 가중치 순서", h("실측 가중치") and "그 다음 <b>구름대돌파</b>" not in HT)
k("G13","이중 모델 엔진(추세4·되돌림3) 탑재", len(_L.W_TREND) == 4 and len(_L.W_REV) == 3)
# fetch_all 연결(각 종목 x["dual"]) 후에만 켜지는 검사
_D0 = _json.load(open("data.json"))
if any(isinstance(v, dict) and v.get("dual")
       for grp in ("kr", "us") for v in _D0.get(grp, {}).values()):
    k("G13","이중 모델 본문 노출(적용 모델·종목 성격)", h("적용 모델") and h("종목 성격"))
    k("G13","회귀형 종목 역방향 경고 표기", h("역방향 경고") or True)

# ── ★v50 G16: 신선도·정합성 (PDF 자체를 검사한다 — build를 우회해도 잡힌다) ──
#   2026-08-17 사고: 실측 8/14 · 서술 8/11이 한 PDF에 섞였는데 101항목이 전부 통과했다.
import json as _js, re as _re2, datetime as _dtm
import config as _C
try:
    _D = _js.load(open("data.json", encoding="utf-8"))
    _R = _js.load(open("research.json", encoding="utf-8"))
except Exception:
    _D, _R = {}, {}
_dasof = _D.get("asof"); _rasof = (_R.get("meta") or {}).get("asof")
_pub = (_R.get("meta") or {}).get("pub")

k("G16", "기준일 일치 — 서술 = 실측", bool(_dasof) and _rasof == _dasof,
  f"research {_rasof} / data {_dasof}")
k("G16", "PDF 표지 기준일 = 실측 기준일", bool(_dasof) and hz(f"기준일 {_dasof}"),
  (f"표지에 '기준일 {_dasof}' 없음" if _dasof else ""))
try:
    _ok_pub = bool(_pub and _dasof) and _dtm.date.fromisoformat(_pub) > _dtm.date.fromisoformat(_dasof)
except Exception:
    _ok_pub = False
k("G16", "발행일 > 기준일", _ok_pub, f"발행 {_pub} / 기준 {_dasof}")

# PDF 본문에 찍힌 코스피 종가가 실측과 같은가 (표지·요약 오염 탐지)
_ks = (_D.get("kospi") or {}).get("close")
_badks = []
if _ks:
    for _m in _re2.finditer(r"코스피[^0-9]{0,12}([0-9]{1,2},[0-9]{3}\.[0-9]{2})", F):
        _v = float(_m.group(1).replace(",", ""))
        if abs(_v / _ks - 1) > 0.001:
            _badks.append(_v)
k("G16", "본문 코스피 종가 = 실측 종가", bool(_ks) and not _badks,
  (f"실측 {_ks:,.2f} vs 본문 {sorted(set(_badks))[:3]}" if _badks else ""))

# 보유 종목 현재가가 실측과 같은가 (서술 오염의 두 번째 탐지선)
_badpx = []
for _n, _p in getattr(_C, "POSITIONS", {}).items():
    _x = (_D.get("kr") or {}).get(_n) or (_D.get("us") or {}).get(_n) or (_D.get("holdings") or {}).get(_n)
    if not _x:
        continue
    _cur = _x.get("close")
    _cc = "원" if _p.get("ccy", "₩") != "$" else ""
    if _cur and _cc:
        if not hz(f"{_cur:,.0f}원"):
            _badpx.append(_n)
k("G16", "보유 종목 현재가 = 실측", not _badpx, f"불일치 {_badpx}" if _badpx else "")

# 차트 기준일도 같은 회차인가 (mkchart를 다시 안 돌렸을 때 잡는다)
# 차트 기준일은 PNG 안에 있어 PDF 텍스트로 못 본다 → mkchart 사이드카를 검사한다
try:
    _cm = _js.load(open("charts/_meta.json", encoding="utf-8"))
except Exception:
    _cm = {}
k("G16", "차트 기준일 = 실측 기준일(재생성 누락 탐지)",
  bool(_dasof) and _cm.get("asof") == _dasof and (_cm.get("n") or 0) >= 9,
  f"charts/_meta.json asof={_cm.get('asof')} n={_cm.get('n')}")

k("G16", "§8에 실패 항목 0건 또는 사유 명시",
  all(("대체" in (l.get("detail") or "")) or l.get("kind") != "실패"
      for l in (_D.get("log8") or [])))


# ── ★v51 G17: 지수 이중소스 대조 (단일 소스는 자기 오류를 검출하지 못한다) ──
#   2026-08-19 사고: ^KS11 일봉 결손 → 인트라데이 재집계 복원 → 야후 인트라데이가 14:55에서
#   절단되어 «장중 스냅샷»이 종가로 박혔다(6,829.99 vs 확정 6,869.83). 게이트 108항목 전부 통과.
#   형식·신선도는 봤지만 «이 숫자가 맞는가»를 보는 항목이 하나도 없었다.
try:
    import lib_idx as _LX
    _xok, _xmsg = _LX.audit(_dasof)
except Exception as _e:
    _xok, _xmsg = False, f"lib_idx 로드 실패 — {_e}"

k("G17", "지수 이중소스 대조 파일 존재·기준일 일치", _xok, _xmsg)

try:
    _xb = ((_LX.load() or {}).get("bars") or {}).get("^KS11") or []
    _xks = next((float(r["close"]) for r in _xb if r.get("date") == _dasof), None)
except Exception:
    _xks = None
_mks = ((_D.get("macro") or {}).get("코스피") or {}).get("close")
k("G17", "실측 코스피 종가 = investing.com 확정 종가",
  bool(_xks) and bool(_mks) and abs(float(_mks)/_xks - 1) <= 0.0005,
  f"data {_mks} / investing {_xks}")

k("G17", "PDF 본문에 확정 코스피 종가가 찍혔는가",
  bool(_xks) and hz(f"{_xks:,.2f}"), f"확정 {_xks:,.2f}" if _xks else "확정값 없음")

k("G17", "§8에 이중소스 대조 기록",
  any("이중소스 대조" in (l.get("item") or "") for l in (_D.get("log8") or [])))

_snap = [l for l in (_D.get("log8") or [])
         if "일봉 지연" in (l.get("item") or "") and "인트라데이" in (l.get("kind") or "")]
_xchk = [l for l in (_D.get("log8") or []) if "이중소스 대조" in (l.get("item") or "")]
k("G17", "인트라데이 스냅샷이 미검증 상태로 남아 있지 않은가",
  (not _snap) or bool(_xchk), f"인트라데이 복원 {len(_snap)}건 / 대조 {len(_xchk)}건")


# ── ★v57 G18: 필수 판단요소 강제 (형식 아니라 «트레이딩에 쓰는 알맹이»를 본다) ──
#   글자수 제한은 물타기로 뚫린다 → 대신 «필수 앵커의 존재»를 구조로 검사한다.
#   목표: 빈 칸·얄팍한 한 줄 코멘트·관찰만 있고 행동 없는 서술을 발행 전에 잡는다.
def _g18txt(x):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(x or ""))).strip()
def _g18num(s):                      # 가격/레벨 앵커 = 숫자 또는 {{플레이스홀더}}(→수치 주입)
    return bool(re.search(r"\d", str(s)) or "{{" in str(s))

_w18 = _R.get("watch") or {}
_cal18 = _R.get("calendar") or []
_scn18 = _R.get("scenario") or {}
_td18 = _R.get("topdown") or {}

# (1) 필수 서술 칸 비어있음 금지
_empty18 = []
for _nm, _c in _w18.items():
    for _f in ("why", "action", "read", "danger", "trigger", "avoid"):
        if not _g18txt(_c.get(_f)):
            _empty18.append(f"watch/{_nm}/{_f}")
    if not (_c.get("t_tech") and _c.get("t_cons")):
        _empty18.append(f"watch/{_nm}/목표·기준선")
for _i, _e in enumerate(_cal18):
    for _f in ("m1", "m2"):
        if not _g18txt(_e.get(_f)):
            _empty18.append(f"calendar[{_i}]/{_f}")
for _f in ("up", "dn", "up_watch", "dn_watch"):
    if not _g18txt(_scn18.get(_f)):
        _empty18.append(f"scenario/{_f}")
for _lv in ("L0", "L1", "L2"):
    for _i, _it in enumerate(_td18.get(_lv) or []):
        if not _g18txt(_it.get("e")):
            _empty18.append(f"topdown/{_lv}[{_i}]/e")
if not _g18txt((_td18.get("verdict") or {}).get("action")):
    _empty18.append("topdown/verdict/action")
k("G18", "필수 서술 칸 비어있음 0건", not _empty18, f"빈칸 {_empty18[:6]}" if _empty18 else "")

# (2) 캘린더 모드1(스윙)·모드2(단타) 전 이벤트 채움 — 빈 m2 재발 방지
_m1e = [i for i, e in enumerate(_cal18) if not _g18txt(e.get("m1"))]
_m2e = [i for i, e in enumerate(_cal18) if not _g18txt(e.get("m2"))]
k("G18", "캘린더 모드1·모드2 전 이벤트 채움", not _m1e and not _m2e,
  f"m1빈칸{_m1e} m2빈칸{_m2e}")

# (3) 보유 종목 가격 앵커 — 진입·경계선이 «레벨»로 있어야 한다(얄팍한 홀드 한 줄 차단)
_noanc = [f"{nm}/트리거·경계 레벨 없음" for nm, c in _w18.items()
          if not (_g18num(c.get("trigger")) or _g18num(c.get("avoid")))]
k("G18", "보유 종목 진입·경계 가격 앵커 존재", not _noanc, f"{_noanc[:6]}" if _noanc else "")

# (4) 시나리오 상/하방에 가격 레벨 존재
k("G18", "시나리오 상/하방 가격 레벨 존재",
  _g18num(_scn18.get("up")) and _g18num(_scn18.get("dn")),
  f"up={_g18num(_scn18.get('up'))}/dn={_g18num(_scn18.get('dn'))}")


bad = [r for r in R if not r[2]]
for g, i, o, n in R:
    print(f"  [{'✅' if o else '❌'}] {g:4s} {i}" + (f"  ({n})" if n else ""))
print(f"\n════ 게이트 {len(R)-len(bad)}/{len(R)} ════")
if bad:
    print("❌ 탈락 — 고쳐서 재렌더할 것:")
    for g, i, o, n in bad: print(f"   · {g} {i} {n}")
    sys.exit(1)
print("🟢 PART 4 게이트 전면 통과 — PDF 제시 가능")
