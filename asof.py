# -*- coding: utf-8 -*-
"""asof.py — 기준일(D) 결정기 (★v57)

「장전/마감 브리핑」이 언제 트리거되든 KR 세션 날짜 D를 결정적으로 뽑는다.
D만 맞으면 yf_adapter._asof_trim이 KR=D 확정봉 / 비KR=D 미만(간밤)으로 자동 분리한다.

세 경우(+자정 넘긴 새벽)를 전부 커버:
  · 장전 (미장 마감 후·한국장 개장 전, 보통 아침) → D = 곧 열릴 KR 세션일
  · 마감 (한국장 마감 후·미장 개장 전, 저녁)      → D = 방금 닫힌 KR 세션일
  · 마감 (미국장 «중»에 물음)                     → D = 방금 닫힌 KR 세션일(동일). 형성 중 US는 트림이 잘라 간밤으로.
  · 자정 넘겨 새벽에 물음                          → 15:30 경과 여부로 판정해 어제 세션으로 되돌린다.

KR 거래일 = 평일 − KRX 휴장일. 음력 휴장일(설·추석)은 매년 바뀌므로 넣지 않는다 —
대신 «마감»은 절차상 마감시황 뉴스의 날짜로 최종 확인한다(그게 정본). 주말·확정 고정휴장만 내장.
CLI:  python3 asof.py 마감   /   python3 asof.py 장전   → YYYY-MM-DD 출력
"""
import sys
import datetime as dt

try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo("Asia/Seoul")
except Exception:
    _KST = dt.timezone(dt.timedelta(hours=9))

# 확정 고정일 휴장(2026, 평일에 걸리는 것만 유효). 음력·대체공휴일은 뉴스로 확인.
KR_HOLIDAYS = {
    "2026-01-01", "2026-03-01", "2026-05-05", "2026-06-06",
    "2026-08-15", "2026-10-03", "2026-10-09", "2026-12-25",
}
KR_CLOSE = dt.time(15, 30)   # KRX 정규장 마감


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


def resolve(mode, now=None):
    """mode: '마감' 또는 '장전'. now: KST tz-aware datetime(없으면 현재)."""
    now = now or dt.datetime.now(_KST)
    d, t = now.date(), now.time()
    if mode == "마감":
        # 방금 닫힌 KR 세션 = 15:30이 지난 가장 최근 거래일
        if is_trading(d) and t >= KR_CLOSE:
            return d.isoformat()
        return prev_trading(d).isoformat()
    elif mode == "장전":
        # 곧 열릴 KR 세션 = 오늘(거래일이고 아직 마감 전)이거나 다음 거래일
        if is_trading(d) and t < KR_CLOSE:
            return d.isoformat()
        return next_trading(d).isoformat()
    raise ValueError("mode must be '마감' or '장전'")


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "마감"
    print(resolve(m))
