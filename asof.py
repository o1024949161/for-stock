# -*- coding: utf-8 -*-
"""asof.py — 기준일(D)·간밤 US 절단일 결정기 (★v62)

「장전/마감 브리핑」이 언제 트리거되든 KR 세션 날짜 D를 결정적으로 뽑는다.
  · 장전 → D = 곧 열릴 KR 세션일      · 마감 → D = 방금 닫힌 KR 세션일
  · 자정 넘겨 새벽에 물음 → 15:30 경과 여부로 판정해 어제 세션으로 되돌린다.

★v62 변경
  ① 2026 음력·대체공휴일·선거일·연말휴장을 내장(설·추석 포함). 이전엔 «뉴스로 확인»하던 수작업.
  ② «마감»은 네이버 금융 코스피 최종 체결일(localTradedAt)로 한 번 더 확인한다 —
     내장 목록이 틀려도(임시공휴일 등) 실제 마지막 거래일로 자동 교정. 네트워크 실패 시 목록만 쓴다.
  ③ uscut — 간밤 US 절단일. KR 휴장일 저녁에도 «이미 끝난 최신 미국 세션»이 잡히게 한다.
     (KST 06:00 이후면 오늘, 이전이면 어제 → 그 날짜 «미만»의 US 봉만 사용)

CLI:  python3 asof.py 마감 | 장전 | uscut   → YYYY-MM-DD
"""
import sys, json, urllib.request
import datetime as dt

try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo("Asia/Seoul")
except Exception:
    _KST = dt.timezone(dt.timedelta(hours=9))

# KRX 휴장일(2026) — 주말은 자동. 대체공휴일·선거일·연말휴장 포함.
KR_HOLIDAYS = {
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18",   # 신정 · 설 연휴
    "2026-03-02",                                            # 삼일절 대체
    "2026-05-01", "2026-05-05", "2026-05-25",                # 근로자의날 · 어린이날 · 부처님오신날 대체
    "2026-06-03",                                            # 전국동시지방선거
    "2026-08-17",                                            # 광복절 대체
    "2026-09-24", "2026-09-25",                              # 추석 연휴(평일분)
    "2026-10-05", "2026-10-09",                              # 개천절 대체 · 한글날
    "2026-12-25", "2026-12-31",                              # 성탄절 · 연말휴장
}
KR_CLOSE = dt.time(15, 30)


def is_trading(d):
    return d.weekday() < 5 and d.isoformat() not in KR_HOLIDAYS


def prev_trading(d):
    d -= dt.timedelta(days=1)
    while not is_trading(d):
        d -= dt.timedelta(days=1)
    return d


def next_trading(d):
    d += dt.timedelta(days=1)
    while not is_trading(d):
        d += dt.timedelta(days=1)
    return d


def naver_last_session():
    """네이버 금융 코스피 최종 체결일(YYYY-MM-DD). 장중이거나 실패하면 None."""
    try:
        req = urllib.request.Request("https://m.stock.naver.com/api/index/KOSPI/basic",
                                     headers={"User-Agent": "Mozilla/5.0"})
        j = json.load(urllib.request.urlopen(req, timeout=8))
        if j.get("marketStatus") != "CLOSE":
            return None
        return j["localTradedAt"][:10]
    except Exception:
        return None


def resolve(mode, now=None, verify=True):
    now = now or dt.datetime.now(_KST)
    d, t = now.date(), now.time()
    if mode == "마감":
        out = d if (is_trading(d) and t >= KR_CLOSE) else prev_trading(d)
        if verify:
            nv = naver_last_session()
            if nv and nv < out.isoformat():   # 목록에 없던 임시휴장 → 실제 마지막 거래일로 교정
                return nv
        return out.isoformat()
    if mode == "장전":
        return (d if (is_trading(d) and t < KR_CLOSE) else next_trading(d)).isoformat()
    raise ValueError("mode must be '마감' or '장전'")


def us_cut(now=None):
    now = now or dt.datetime.now(_KST)
    return (now.date() if now.hour >= 6 else now.date() - dt.timedelta(days=1)).isoformat()


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "마감"
    print(us_cut() if m == "uscut" else resolve(m))
