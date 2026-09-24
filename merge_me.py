# -*- coding: utf-8 -*-
"""
merge_me.py — ★v62 분석 칸(me_*.json) → research.json 병합 (A: 병렬 작성의 마지막 조립)

  python3 merge_me.py me_verdict.json me_market.json me_cards.json me_plan.json
  · dict는 재귀 병합(.update 방식 — 키를 통째로 날리지 않는다: 2026-08 KeyError 사고 규약)
  · list는 통째로 교체(캘린더·함정·헤드라인·탑다운 행 등은 작성자가 전체를 쓴다)
  · 존재하지 않는 최상위 키는 경고만 하고 넣는다(오타 탐지)
"""
import json, sys

R = json.load(open("research.json", encoding="utf-8"))
KNOWN = set(R.keys())


def merge(dst, src, path=""):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            merge(dst[k], v, f"{path}.{k}")
        else:
            dst[k] = v


n = 0
for f in sys.argv[1:]:
    try:
        part = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        print(f"  ✖ {f} 읽기 실패: {e}")
        sys.exit(2)
    unk = [k for k in part if k not in KNOWN and not k.startswith("_")]
    if unk:
        print(f"  ⚠ {f}: research에 없는 최상위 키 {unk} — 오타인지 확인")
    merge(R, {k: v for k, v in part.items() if not k.startswith("_")})
    n += 1
json.dump(R, open("research.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"■ merge_me — {n}개 파일 병합 → research.json")
