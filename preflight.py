# -*- coding: utf-8 -*-
"""preflight.py — 통합 사전검증 도구 (정본 v54 · 2026-08-25)

구 setup.md(환경 bash) + apply_v51.py(부트스트랩) + preflight.py(키 검증) + pretext.py(텍스트 린트)
네 개를 하나로 합쳤다. 파이프라인 로직(fetch_all/mkchart/build/render/gate)은 손대지 않는다.

  python3 preflight.py setup [기준일]  # ① 작업폴더 재구성 · 의존성 · 폰트 · 야후 어댑터 자동로드
                                  #    삭제 전 회차 파일을 /root/w_backup/<시각>/에 자동 백업(★v56)
                                  #    기준일을 주면 data.json/charts의 asof가 «전부» 일치할 때만 보존(★v55 resume)
  python3 preflight.py research   # ② research.json 키 구조 전수 검증 + off_why 자동 보충
  python3 preflight.py text       # ③ 렌더 前 텍스트 린트 (gate.py 리터럴 대조)

exit 0 = 통과 / 2 = 키 누락 / 3 = 본문 문구 누락 / 1 = 환경 실패
"""
import glob
import html as _html
import json
import os
import re
import shutil
import subprocess
import sys

W = "/root/w"
SRC = "/mnt/project"
TEMPLATE = "research.json.template"   # setup이 원본 research.json을 여기에 보관한다


# ════════════════════════════════════════════════════════════
# ① setup — 환경 재구성
# ════════════════════════════════════════════════════════════
def _stage():
    """/mnt/project → 작업폴더. claude_ 접두어를 떼고 공백을 언더스코어로."""
    if not os.path.isdir(SRC):
        print(f"  ⚠ {SRC} 없음 — 스테이징을 건너뛴다(이미 복사돼 있다고 가정)")
        return 0
    os.makedirs(os.path.join(W, "charts"), exist_ok=True)
    n = 0
    for p in sorted(glob.glob(os.path.join(SRC, "*"))):
        if not os.path.isfile(p):
            continue
        b = os.path.basename(p)
        if b.startswith("claude_"):
            b = b[len("claude_"):]
        b = b.replace(" ", "_")
        dst = os.path.join(W, b)
        # claude_X 와 X 가 둘 다 있으면(중복) 같은 곳에 두 번 쓰인다 — 동일 파일이므로 무해
        shutil.copy2(p, dst)
        n += 1
    # research.json 원본을 템플릿으로 보관 (research 모드가 이것과 대조한다)
    r = os.path.join(W, "research.json")
    if os.path.isfile(r):
        shutil.copy2(r, os.path.join(W, TEMPLATE))
    print(f"  · 스테이징 {n}개 (claude_ 접두어 제거)")
    return n


def _deps():
    subprocess.run("pip install yfinance weasyprint --break-system-packages -q",
                   shell=True, capture_output=True)
    subprocess.run("apt-get install -y fonts-nanum >/dev/null 2>&1; fc-cache -f >/dev/null 2>&1",
                   shell=True, capture_output=True)
    ok = True
    for mod in ("yfinance", "weasyprint"):
        try:
            m = __import__(mod)
            print(f"  ✔ {mod} {getattr(m, '__version__', '?')}")
        except Exception as e:
            print(f"  ✗ {mod} — {e}")
            ok = False
    font = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    print(f"  {'✔' if os.path.exists(font) else '✗'} NanumGothic")
    for t in ("pdftotext", "pdfinfo"):
        print(f"  {'✔' if shutil.which(t) else '✗'} {t}")
    return ok and os.path.exists(font)


def _adapter():
    """yf_adapter.py를 .pth로 자동 로드시킨다(파이프라인 파일 무수정)."""
    if not os.path.isfile(os.path.join(W, "yf_adapter.py")):
        print("  ✗ yf_adapter.py 없음 — 야후 우회 불가")
        return False
    import site
    sp = site.getsitepackages()[0]
    with open(os.path.join(sp, "zz_yfadapter.pth"), "w") as f:
        f.write(f'import sys; sys.path.insert(0, "{W}"); import yf_adapter\n')
    out = subprocess.run(
        [sys.executable, "-c",
         "import yfinance as yf; print(yf.Ticker.history.__qualname__)"],
        capture_output=True, text=True).stdout
    ok = "_install" in out
    print(f"  {'✔' if ok else '✗'} 야후 v8 어댑터 자동로드 ({out.strip().splitlines()[-1] if out.strip() else 'n/a'})")
    return ok


def _resume_ok(asof):
    """★v55 — 세션이 중간에 끊겼을 때만, «같은 기준일»의 수집물을 보존한다.
    §1의 «작업폴더 무조건 삭제»는 2026-08-17 사고(낡은 스냅샷 위 작업) 때문에 옳다.
    그래서 보존 조건을 asof 일치로 못박는다 — 하나라도 어긋나면 전면 삭제로 되돌아간다."""
    if not asof:
        return False
    try:
        d = json.load(open(os.path.join(W, "data.json"), encoding="utf-8"))
        m = json.load(open(os.path.join(W, "charts", "_meta.json"), encoding="utf-8"))
    except Exception:
        return False
    ok = d.get("asof") == asof and m.get("asof") == asof and (m.get("n") or 0) >= 9
    print(f"  {'✔' if ok else '✗'} resume 조건 — data.asof={d.get('asof')} / charts.asof={m.get('asof')} / 목표={asof}")
    return ok


BACKUP = "/root/w_backup"          # ★v56 — 작업폴더 «바깥». setup이 지우지 못하는 자리다.


def _snapshot():
    """★v56 — 삭제 전에 회차 파일을 작업폴더 바깥으로 복사한다.
    2026-08-30 사고: 코드 개정 직후 첫 setup은 «구버전»이 실행된다(파이썬이 이미 메모리에
    올린 코드가 자기 자신을 새 파일로 덮고 종료하기 때문). 그래서 resume이 걸리지 않고
    data.json·research.json이 통째로 날아갔다. 코드를 고칠 때마다 재발하는 구조적 사고라
    «보존 로직»이 아니라 «백업 로직»으로 막는다 — 보존은 실패할 수 있어도 백업은 남는다."""
    import datetime as _dt
    src = [f for f in ("research.json", "index_xcheck.json", "data.json") 
           if os.path.isfile(os.path.join(W, f))]
    if not src:
        return
    dst = os.path.join(BACKUP, _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(dst, exist_ok=True)
    for f in src:
        shutil.copy2(os.path.join(W, f), os.path.join(dst, f))
    print(f"  · ★v56 회차 파일 백업 {len(src)}개 → {dst}")


def cmd_setup(asof=None):
    print("■ preflight setup — 환경 재구성")
    _snapshot()
    keep = {"charts", ".yfcache"}
    if asof and _resume_ok(asof):
        keep |= {"data.json", "state_%s.json" % asof}
        print("  · ★v55 resume — 같은 기준일 수집물 보존(fetch_all·mkchart 재실행 불필요)")
    elif asof:
        print("  · ★v55 resume 불가 — 전면 삭제 후 처음부터(기준일 불일치는 2026-08-17 사고 재발 조건이다)")
    if os.path.isdir(W):
        for p in glob.glob(os.path.join(W, "*")):
            if os.path.basename(p) in keep:
                continue
            (shutil.rmtree if os.path.isdir(p) else os.remove)(p)
    os.makedirs(W, exist_ok=True)
    _stage()
    ok = _deps() & _adapter()
    print("  →", "환경 준비 완료" if ok else "환경 결함 — 위 ✗ 항목을 해결할 것")
    return 0 if ok else 1


# ════════════════════════════════════════════════════════════
# ② research — 키 구조 검증 + off_why 자동 보충
# ════════════════════════════════════════════════════════════
def cmd_research():
    print("■ preflight research — research.json 키 구조 검증")
    new = json.load(open("research.json", encoding="utf-8"))
    data = json.load(open("data.json", encoding="utf-8"))

    tpl = TEMPLATE if os.path.isfile(TEMPLATE) else None
    if tpl is None and os.path.isfile(os.path.join(SRC, "research.json")):
        tpl = os.path.join(SRC, "research.json")
    if tpl is None:
        print("  ⚠ 템플릿(research.json.template) 없음 — 키 대조를 건너뛴다")
        old = None
    else:
        old = json.load(open(tpl, encoding="utf-8"))

    filled = 0
    for name, w in new.get("watch", {}).items():
        x = (data.get("kr") or {}).get(name) or (data.get("us") or {}).get(name)
        if not x:
            continue
        ow = w.setdefault("off_why", {})
        for k, on in (x.get("on") or {}).items():
            if not on and k not in ow:
                ow[k] = (x.get("det") or {}).get(k, "조건 미충족")
                filled += 1

    miss = []

    def walk(o, n, p=""):
        if p.endswith("/off_why"):
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if not isinstance(n, dict) or k not in n:
                    miss.append(p + "/" + str(k))
                    continue
                walk(v, n[k], p + "/" + str(k))
        elif isinstance(o, list) and o and isinstance(o[0], dict):
            if isinstance(n, list) and n:
                for i, e in enumerate(n):
                    walk(o[0], e, f"{p}[{i}]")
            else:
                miss.append(p + " (list shape)")

    if old is not None:
        walk(old, new)
    for name, w in new.get("watch", {}).items():
        x = (data.get("kr") or {}).get(name) or (data.get("us") or {}).get(name)
        if not x:
            continue
        for k, on in (x.get("on") or {}).items():
            if not on and k not in w.get("off_why", {}):
                miss.append(f"/watch/{name}/off_why/{k}")

    json.dump(new, open("research.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"  · off_why 자동 보충 {filled}건")
    if miss:
        print("  ✖ 누락 키:", miss[:20])
        return 2
    print("  ✔ 키 구조 전수 일치 — 조립 진행 가능")
    return 0


# ════════════════════════════════════════════════════════════
# ③ text — 렌더 前 텍스트 린트
# ════════════════════════════════════════════════════════════
# gate.py 안에서 «PDF 본문»이 아니라 HTML/CSS 구조를 보는 검사에 쓰이는 문자열
SKIP = {
    "linear-gradient", "color:#1c2530", "font-size:10.6px",
    ".hl b, .box-navy .hl b", ".hl .warn, .box-navy .hl .warn",
}


def gate_literals(path="gate.py"):
    """gate.py를 파싱해 «본문에 있어야 하는» 리터럴을 뽑는다.
    게이트 규격을 복제하지 않는다 — gate.py가 바뀌면 자동으로 따라간다."""
    src = open(path, encoding="utf-8").read()
    out, banned = [], set()
    for m in re.finditer(r'(not\s+)?\b(?:h|hz)\(\s*"([^"]{2,60})"', src):
        neg, s = m.group(1), m.group(2)
        if s in SKIP:
            continue
        if neg:                      # not h("…") = 있으면 탈락하는 «금지 문구»
            banned.add(s)
            continue
        out.append(s)
    seen, uniq = set(), []
    for s in out:
        if s in banned or s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return uniq


def cmd_text():
    print("■ preflight text — 렌더 前 텍스트 린트")
    lits = gate_literals()
    raw = open("briefing.html", encoding="utf-8").read()
    raw = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.S | re.I)
    flat = re.sub(r"\s+", "", _html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    missing = [s for s in lits if re.sub(r"\s+", "", s) not in flat]

    print(f"  · gate.py에서 리터럴 {len(lits)}건 추출")
    if not missing:
        print("  ✔ 전부 본문에 존재 — 렌더 진행 가능")
        return 0
    print(f"  ✖ 본문 누락 {len(missing)}건 — 렌더 전에 research.json을 고칠 것:")
    for s in missing:
        print(f"     · {s!r}")
    print("  ※ 차트 PNG 안에만 있는 문구는 본문 캡션에도 한 번 써 준다.")
    return 3


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"setup": cmd_setup, "research": cmd_research, "text": cmd_text}.get(mode)
    if not fn:
        print(__doc__)
        sys.exit(1)
    if mode == "setup":                       # ★v55: setup만 기준일 인자를 받는다
        sys.exit(fn(sys.argv[2] if len(sys.argv) > 2 else None))
    sys.exit(fn())
