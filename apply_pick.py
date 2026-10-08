# -*- coding: utf-8 -*-
"""
apply_pick.py — ★v65 차트 판독 결과(chart_pick.json) → data.json 강화 카드 + me_pick.json(서술)

  run_finish.sh 첫 단계(merge_me 전)에 실행한다. 판독 결과가 없거나 규격 위반이면 발행하지 않는다(exit 2).

  chart_pick.json 규격(판독 에이전트 — prompts.md §D):
  {"asof": "data.json의 asof(직전 회차 파일 재사용 차단)",
   "screen_read": "이번 회차 후보 판독 총평(2~4문장)",
   "kr": [{"name","weekly","timing","pattern","why","entry","stop","target","trigger","invalid","risk"} × 3],
          # ★v64 weekly = 주봉 판단(추세·패턴), timing = 일봉 진입 시점
          # ★v65 기본 선정(data.chartscan.default)과 다른 종목을 고르면 "override"(교체 사유: 차트상 망가진 근거) 필수
   "us": [... × 3],
   "rejected": [{"name","why"}]   # 후보였지만 고르지 않은 이유(선택)}
"""
import json, sys
import config as C

N = getattr(C, "ENHANCE_N", 3)
D = json.load(open("data.json", encoding="utf-8"))
try:
    P = json.load(open("chart_pick.json", encoding="utf-8"))
except Exception as e:
    print(f"✖ chart_pick.json 없음/읽기 실패({e}) — 차트 판독 에이전트(prompts.md §D)를 먼저 실행할 것. 발행 중단.")
    sys.exit(2)

err = []
if P.get("asof") != D.get("asof"):
    err.append(f"chart_pick.asof={P.get('asof')} ≠ data.asof={D.get('asof')} — 직전 회차 판독 파일이다")
cand = D.get("enhance_cand") or {}
pool = {"kr": D.get("kr", {}), "us": D.get("us", {})}
CP = {}
import re as _re
def _norm(nm, mk):
    """«이름 (티커)»처럼 티커를 덧붙여 쓴 경우 후보 이름으로 되돌린다(후보 티커와 일치할 때만)."""
    if nm in (cand.get(mk) or []):
        return nm
    m = _re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", str(nm or ""))
    if m and m.group(1) in (cand.get(mk) or []) and pool[mk][m.group(1)]["ticker"].split(".")[0] == m.group(2).split(".")[0]:
        return m.group(1)
    return nm
for mk in ("kr", "us"):
    rows = P.get(mk) or []
    for r in rows:
        r["name"] = _norm(r.get("name"), mk)
    for r in P.get("rejected") or []:
        r["name"] = _norm(r.get("name"), mk) if _norm(r.get("name"), mk) in (cand.get(mk) or []) else r.get("name")
    names = [r.get("name") for r in rows]
    if len(rows) != N:
        err.append(f"[{mk}] 선정 {len(rows)}종 ≠ {N}종")
    if len(set(names)) != len(names):
        err.append(f"[{mk}] 중복 선정 {names}")
    for r in rows:
        nm = r.get("name")
        if nm not in (cand.get(mk) or []):
            err.append(f"[{mk}] {nm} — 판독 후보(차트 점수 상위 {len(cand.get(mk) or [])}종) 밖")
            continue
        x = pool[mk][nm]
        try:
            e, s, t = float(r["entry"]), float(r["stop"]), float(r["target"])
        except Exception:
            err.append(f"[{mk}] {nm} — entry/stop/target 숫자 아님"); continue
        Cl = x["close"]
        if not (s < e < t):
            err.append(f"[{mk}] {nm} — 손절 {s} < 진입 {e} < 목표 {t} 순서 위반")
        if not (Cl * 0.85 <= e <= Cl * 1.10):
            err.append(f"[{mk}] {nm} — 진입 {e}가 종가 {Cl:.2f}의 −15%~+10% 밖")
        if s < e * 0.749:
            err.append(f"[{mk}] {nm} — 손절 폭 {(1 - s / e) * 100:.1f}% > 25%(비상 손절 한도)")
        dflt = ((D.get("chartscan") or {}).get(mk) or {}).get("default") or []
        if nm not in dflt and ((D.get("chartscan") or {}).get(mk) or {}).get("mode") == "유지":
            err.append(f"[{mk}] {nm} — 점검일이 아닌 회차(유지)에는 보유 장부({', '.join(dflt)})를 바꿀 수 없다")
        if nm not in dflt and not str(r.get("override") or "").strip():
            err.append(f"[{mk}] {nm} — 기본 선정({', '.join(dflt)})이 아닌데 «override»(교체 사유) 빈칸")
        for f in ("weekly", "timing", "pattern", "why", "trigger", "invalid"):
            if not str(r.get(f) or "").strip():
                err.append(f"[{mk}] {nm} — «{f}» 빈칸")
        CP[nm] = {"mk": mk, "weekly": r.get("weekly"), "timing": r.get("timing"), "pattern": r.get("pattern"), "why": r.get("why"), "trigger": r.get("trigger"),
                  "invalid": r.get("invalid"), "risk": r.get("risk") or "",
                  "entry": e, "stop": s, "target": t, "rr": (t - e) / (e - s) if e > s else 0.0,
                  "chart_score": (x.get("chart") or {}).get("score"), "main": (x.get("chart") or {}).get("main"),
                  "wscore": (x.get("chart") or {}).get("wscore"), "dscore": (x.get("chart") or {}).get("dscore"),
                  "rank": (x.get("chart") or {}).get("rank"), "default": nm in dflt, "override": r.get("override") or ""}
if not str(P.get("screen_read") or "").strip():
    err.append("screen_read 빈칸")
if err:
    print("✖ chart_pick.json 규격 위반 — 판독 에이전트에게 고쳐 쓰게 할 것(발행 중단):")
    for x in err:
        print("   ·", x)
    sys.exit(2)

D["enhance_kr"] = [r["name"] for r in P["kr"]]
D["enhance_us"] = [r["name"] for r in P["us"]]
D["chartpick"] = {"picks": CP, "rejected": P.get("rejected") or [], "screen_read": P["screen_read"]}
json.dump(D, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

ME = {"screen_read": P["screen_read"], "enhance": {}}
for nm, q in CP.items():
    ME["enhance"][nm] = {
        "select": (f"<b>★v65 선정</b> — 차트 망가짐 필터 통과 · 합성 모멘텀 <b class=\"vg\">{q['rank']}위</b>(합성 {q['chart_score']:g})"
                   + (" · <b>기본 선정</b>" if q["default"] else f" · <b>판독 교체</b>({q['override']})")
                   + f" — 판독: <b>{q['pattern']}</b>(근거는 아래 «차트 판독» 표)."),
        "read": f"<b>진입 트리거</b> — {q['trigger']}<br><b>무효화</b> — {q['invalid']}",
        "risk": q["risk"] or f"무효화 조건: {q['invalid']}",
        # ★v63 판독 표 원문 — research를 거쳐 강조 표기(++ -- == …)가 변환된다
        "pick_why": q["why"], "pick_trigger": q["trigger"], "pick_invalid": q["invalid"],
        "pick_weekly": q["weekly"], "pick_timing": q["timing"], "pick_override": q["override"]}
json.dump(ME, open("me_pick.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"■ apply_pick — 국내 {D['enhance_kr']} · 미국 {D['enhance_us']} → data.json · me_pick.json")
