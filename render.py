# -*- coding: utf-8 -*-
"""
render.py — briefing.html → PDF.
★ 렌더 엔진 = WeasyPrint (wkhtmltopdf 금지).
   wkhtmltopdf(구형 QtWebKit)는 큰 div의 break-inside:avoid를 무시해
   '차트 제목 고아'·'천장감시 표 절단'이 재발한다(2026-07-12 실증).
★ fontTools가 나눔폰트 OS/2 unicodeRange bit>122를 거부하는 버그 → 아래 패치로 우회.
실행: python3 render.py [출력파일명]
"""
import sys
from fontTools.ttLib.tables import O_S_2f_2 as _os2
_orig = _os2.table_O_S_2f_2.setUnicodeRanges
_os2.table_O_S_2f_2.setUnicodeRanges = lambda self, bits: _orig(self, {b for b in bits if 0 <= b <= 122})

import time
import layout_fix   # ★v62.2 제목 고아 자동 교정(조판 결과를 읽어 제목만 남은 페이지를 없앤다)

out = sys.argv[1] if len(sys.argv) > 1 else "briefing.pdf"
t = time.time()
try:
    doc = layout_fix.render_fixed(open("briefing.html", encoding="utf-8").read(), base_url=".")
    doc.write_pdf(out)
except Exception as e:                      # 교정기가 실패해도 발행은 막지 않는다(기존 방식으로 렌더)
    print(f"  [layout] 교정 실패 → 기본 렌더: {type(e).__name__}: {e}")
    from weasyprint import HTML
    HTML(filename="briefing.html").write_pdf(out)
print(f"→ PDF 렌더 완료: {out}  ({time.time()-t:.1f}s)")
