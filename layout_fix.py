# -*- coding: utf-8 -*-
"""layout_fix.py — ★v62.2 «제목 고아» 자동 교정 (render.py가 사용)

WeasyPrint의 break-after:avoid는 «다음 블록이 통째로 안 들어갈 때» 지켜지지 않아
페이지 끝에 제목(＋짧은 안내 박스)만 남고 표·차트가 다음 장에서 시작하는 일이 생긴다.
여기서는 실제 조판 결과(박스 좌표)를 읽어 그런 제목을 찾아 «제목부터 새 페이지»로 밀고 다시 조판한다.

제목 = .corner(1단) · .sub2/.chead(2단) · caption.corner-cap(→ 그 표 전체, 3단)
판정 = 제목이 페이지 p에서 시작 + 같은 절(같거나 높은 단의 다음 제목 전까지)의 내용이 p+1로 넘어감
       + 페이지 p에서 제목 아래에 실린 분량 < ORPHAN_PX (기본 ≈ 본문 높이의 21%)
"""
import re

HEAD_CLASSES = ("corner", "sub2", "chead")
LEVEL = {"corner": 1, "sub2": 2, "chead": 2}
ORPHAN_PX = 220          # CSS px (A4 본문 높이 ≈ 1047px, 약 21%) — 이보다 적게 실리고 넘어가면 고아
MAX_ROUNDS = 4


def tag_headings(html):
    """제목 요소에 data-hid 부여. 캡션 표·차트 표는 표에 부여."""
    n = [0]

    def nid():
        n[0] += 1
        return f"h{n[0]}"

    def cls_tag(m):
        tag, attrs = m.group(1), m.group(2)
        cm = re.search(r"""class=(["'])([^"']*)\1""", attrs)
        classes = cm.group(2).split() if cm else []
        if any(c in classes for c in HEAD_CLASSES) and "data-hid" not in attrs:
            return f"<{tag} data-hid=\"{nid()}\"{attrs}>"
        return m.group(0)

    html = re.sub(r"<(div)(\s[^>]*)>", cls_tag, html)
    # 캡션이 달린 표 / 차트 제목(.ct)이 든 차트 표 → 표 자체를 제목 단위로
    html = re.sub(r"<table((?:\s[^>]*)?)>(\s*<caption class=\"corner-cap\")",
                  lambda m: f"<table data-hid=\"{nid()}\" data-cap=\"1\"{m.group(1)}>{m.group(2)}", html)
    return html


def _boxes(box):
    if type(box).__name__ == "MarginBox":          # 쪽번호 등 여백 상자는 본문이 아니다
        return
    yield box
    for ch in getattr(box, "children", None) or []:
        yield from _boxes(ch)


def _level(e):
    cl = (e.get("class") or "").split()
    return min([LEVEL[c] for c in cl if c in LEVEL] or [3])


def find_orphans(doc, root):
    from weasyprint.formatting_structure import boxes as B
    parent = {c: p for p in root.iter() for c in p}
    heads = {e.get("data-hid"): e for e in root.iter() if e.get("data-hid")}

    page_elems, page_bottom, head_top = [], [], {}
    for pi, page in enumerate(doc.pages):
        els, bottom = set(), 0.0
        for b in _boxes(page._page_box):
            e = getattr(b, "element", None)
            if e is not None:
                els.add(e)
                hid = e.get("data-hid") if hasattr(e, "get") else None
                if hid and hid not in head_top:
                    head_top[hid] = (pi, b.position_y)
            if isinstance(b, (B.LineBox, B.ReplacedBox)) and b.height:
                bottom = max(bottom, b.position_y + b.margin_height())
        page_elems.append(els)
        page_bottom.append(bottom)

    out = []
    for hid, e in heads.items():
        if hid not in head_top:
            continue
        p, top = head_top[hid]
        if p + 1 >= len(doc.pages) or top < 60:        # 이미 페이지 맨 위
            continue
        if e.get("data-cap"):                            # 캡션 표: 절 = 표 자신
            section = [e]
        else:
            lv = _level(e)
            section, par = [], parent.get(e)
            sibs = list(par) if par is not None else []
            for s in sibs[sibs.index(e) + 1:]:
                if s.get("data-hid") and not s.get("data-cap") and _level(s) <= lv:
                    break
                section.append(s)
        nxt = page_elems[p + 1]
        if not any(d in nxt for s in section for d in s.iter()):
            continue
        if page_bottom[p] - top < ORPHAN_PX:
            out.append((hid, p + 1, round(page_bottom[p] - top), top))
    # 한 페이지에 여럿이면 가장 위의 것 하나만 민다(아래 것은 함께 따라 넘어가므로 다음 회차에 재판정)
    best = {}
    for o in out:
        if o[1] not in best or o[3] < best[o[1]][3]:
            best[o[1]] = o
    return [o[:3] for o in sorted(best.values(), key=lambda o: o[1])]


def render_fixed(html, base_url=None, log=print):
    from weasyprint import HTML
    html = tag_headings(html)
    forced, released = [], set()
    for rnd in range(MAX_ROUNDS + 1):
        css = "".join(f'[data-hid="{h}"]{{break-before:page!important;page-break-before:always!important;}}' for h in forced)
        src = html + f"<style>{css}</style>"      # 맨 뒤 + !important — .pgnew(break-before:auto)보다 우선
        H = HTML(string=src, base_url=base_url)
        doc = H.render()
        orph = find_orphans(doc, H.etree_element) if rnd < MAX_ROUNDS else []
        orph = [o for o in orph if o[0] not in forced and o[0] not in released]   # 이미 민 제목은 다시 밀지 않는다(무한 반복 방지)
        # ★v67 제목을 밀 때, 바로 뒤 형제(캡션 표 등)를 앞 회차에서 이미 밀었다면 그 강제 쪽나눔은 푼다
        #   (안 풀면 «제목만 한 페이지 + 표는 다음 페이지» — 10/9 경제 캘린더 사고)
        if orph:
            _root = H.etree_element
            _par = {c: p for p in _root.iter() for c in p}
            for o in orph:
                _e = next((x for x in _root.iter() if x.get("data-hid") == o[0]), None)
                _p = _par.get(_e) if _e is not None else None
                if _p is None:
                    continue
                _sibs = list(_p)
                _i = _sibs.index(_e)
                if _i + 1 < len(_sibs) and _sibs[_i + 1].get("data-hid") in forced:
                    _h = _sibs[_i + 1].get("data-hid")
                    forced.remove(_h)
                    released.add(_h)
        if not orph:
            log(f"  [layout] 제목 고아 0건 (교정 {len(forced)}건 · 조판 {rnd + 1}회 · {len(doc.pages)}쪽)")
            return doc
        log(f"  [layout] 제목 고아 {len(orph)}건 → 새 페이지로: " +
            ", ".join(f"{h}@p{p}({px}px)" for h, p, px in orph))
        forced += [o[0] for o in orph]
    return doc
