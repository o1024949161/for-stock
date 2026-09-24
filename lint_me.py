# -*- coding: utf-8 -*-
"""
lint_me.py — ★v62 빌드 «전» 분석 칸 검사 (G: 게이트 재실행 사이클 제거)

게이트(gate.py)는 PDF를 다 만든 뒤에야 빈 칸·앵커 누락을 잡는다 → 고치고 다시 build·render(약 40초)를 반복했다.
여기서 research.json만 보고 1초 안에 같은 조건을 먼저 잡는다. 게이트를 대체하지 않는다(게이트는 그대로 최종 관문).

검사
  ① [ME] 빈칸 0건        — prefill이 남긴 빈 문자열이 전부 채워졌나(선택 칸 제외)
  ② G18 필수 앵커        — watch 6칸·목표선 / 캘린더 m1·m2 / 시나리오 상·하방 가격 / 탑다운 e / verdict.action
  ③ 자리표시자·참조 해석  — {{경로}}·«=경로»가 data.json·research.json에서 풀리는가
  ④ 강조 기호 짝         — ++ -- !! ^^ == ** 가 홀수로 남아 깨진 문장이 되지 않았나
  ⑤ 게이트 문구 선검사    — 서술이 채워야 하는 필수 문구(실행 순서·물타기·손절 미루기·공포 전량매도·6만$)
  ⑥ 판단 일관성(경고)     — 카드 배지와 규칙 판정이 다르면 근거(why)에 이유가 있나
exit 0 통과 / 1 탈락
"""
import json, re, sys

R = json.load(open("research.json", encoding="utf-8"))
D = json.load(open("data.json", encoding="utf-8"))
import config as C

OPTIONAL = {"perf_prev", "tracker_events", "shrink", "risk.modes", "risk.events", "stress.read",
            "news", "dashboard.rule2_note", "dashboard.risk_note", "log8", "exits", "enhance"}
errs, warns = [], []


def txt(x):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(x or ""))).strip()


def has_num(s):
    return bool(re.search(r"\d", str(s)) or "{{" in str(s))


# ① 빈칸
def walk(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, f"{p}.{k}" if p else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{p}[{i}]")
    elif o == "":
        if not any(p == op or p.startswith(op + ".") or p.startswith(op + "[") or f".{op}" in p for op in OPTIONAL):
            errs.append(f"빈칸: {p}")
walk(R)

# ② G18
for nm, c in (R.get("watch") or {}).items():
    for f in ("why", "action", "read", "danger", "trigger", "avoid"):
        if not txt(c.get(f)):
            errs.append(f"G18 watch/{nm}/{f} 비어 있음")
    if not (has_num(c.get("trigger")) or has_num(c.get("avoid"))):
        errs.append(f"G18 watch/{nm} 진입·경계 가격 앵커 없음(trigger/avoid에 숫자나 {{{{...}}}})")
for i, e in enumerate(R.get("calendar") or []):
    for f in ("when", "what", "m1", "m2"):
        if not txt(e.get(f)):
            errs.append(f"G18 calendar[{i}]/{f} 비어 있음")
if len(R.get("calendar") or []) < 4:
    errs.append("캘린더 4건 미만")
sc = R.get("scenario") or {}
for f in ("up", "dn"):
    if not has_num(sc.get(f)):
        errs.append(f"G18 scenario/{f} 가격 레벨 없음")
for lv in ("L0", "L1", "L2"):
    rows = (R.get("topdown") or {}).get(lv) or []
    need = {"L0": 5, "L1": 6, "L2": 5}[lv]
    if len(rows) < need:
        errs.append(f"topdown/{lv} {len(rows)}행 < {need}행")
    for i, r in enumerate(rows):
        if not txt(r.get("e")) or r.get("c") not in ("g", "y", "r", "gr", "x"):
            errs.append(f"topdown/{lv}[{i}] e 비었거나 c 색코드 오류({r.get('c')})")
if not txt(((R.get("topdown") or {}).get("verdict") or {}).get("action")):
    errs.append("G18 topdown/verdict/action 비어 있음")
if len(R.get("traps") or []) < 6:
    errs.append("traps 6종 미만")
if len(R.get("headline") or []) < 5:
    errs.append("headline 5줄 미만")

# ③ 자리표시자·참조
def pick(path):
    cur = D
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur
blob = json.dumps(R, ensure_ascii=False)
for m in re.finditer(r"\{\{(?!@)(pct:)?([A-Za-z0-9_가-힣.() &/]+?)(?:\|([A-Za-z0-9_가-힣.() &/]+?))?(?::[^}]+)?\}\}", blob):
    for g in (m.group(2), m.group(3)):
        if g and pick(g) is None:
            errs.append(f"자리표시자 해석 불가: {m.group(0)}")
for m in re.finditer(r'"(=[A-Za-z0-9_가-힣.\[\]]+)"', blob):
    path = m.group(1)[1:]
    cur = R
    try:
        for p in path.split("."):
            mm = re.match(r"(.+?)\[(\d+)\]$", p)
            cur = cur[mm.group(1)][int(mm.group(2))] if mm else cur[p]
    except Exception:
        errs.append(f"참조 해석 불가: {m.group(1)}")
for m in re.finditer(r"\{\{@(\w+)\}\}", blob):
    if m.group(1) not in ("stops", "events", "verdict"):
        errs.append(f"알 수 없는 토큰 {{{{@{m.group(1)}}}}}")

# ④ 강조 기호 짝
def strings(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from strings(v, f"{p}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from strings(v, f"{p}[{i}]")
    elif isinstance(o, str):
        yield p, o
for p, s in strings(R):
    for mk in ("++", "!!", "^^", "==", "**"):
        if s.count(mk) % 2:
            warns.append(f"강조 기호 {mk} 짝 안 맞음: {p}")

# ⑤ 게이트 문구
if not re.search(r"실행\s*순서", txt(R.get("perf_advice"))):
    errs.append("perf_advice에 «실행 순서» 문구 필요(G12)")
tr = " ".join(txt(t.get("name")) + " " + txt(t.get("why")) for t in (R.get("traps") or []))
if getattr(C, "POSITIONS", {}):
    for w in ("물타기", "손절 미루기", "공포 전량매도"):
        if w not in tr:
            errs.append(f"traps에 «{w}» 필요(G11 보유 세트)")

# ⑥ 판단 일관성(경고)
try:
    import build_plus as BP
    BS = json.load(open("brief_state.json", encoding="utf-8")) if __import__("os").path.exists("brief_state.json") else {}
    stk = (D.get("extra") or {}).get("stocks") or {}
    for n, code, tk, cur in C.WATCH:
        x = D["kr"].get(n) or D["us"].get(n) or D.get("holdings", {}).get(n)
        w = (R.get("watch") or {}).get(n) or {}
        if not x or not w:
            continue
        _, rule, _, _ = BP.hmatrix(n, x, n in C.POSITIONS, stk.get(n), BS, D["asof"])
        b = w.get("badge", "")
        if rule.split("(")[0] not in b and b.split("(")[0] not in rule:
            warns.append(f"{n}: 배지 «{b}» ≠ 규칙 판정 «{rule}» — why에 이유가 있는지 확인")
except Exception as e:
    warns.append(f"판단 일관성 검사 생략: {e}")

for w in warns:
    print("  ⚠", w)
if errs:
    print(f"✖ lint_me 탈락 {len(errs)}건:")
    for e in errs[:40]:
        print("   ·", e)
    sys.exit(1)
print(f"✔ lint_me 통과 (경고 {len(warns)}건)")
