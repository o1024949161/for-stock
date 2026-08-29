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

from weasyprint import HTML
import time

out = sys.argv[1] if len(sys.argv) > 1 else "briefing.pdf"
t = time.time()
HTML(filename="briefing.html").write_pdf(out)
print(f"→ PDF 렌더 완료: {out}  ({time.time()-t:.1f}s)")
