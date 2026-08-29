# -*- coding: utf-8 -*-
"""style.py — 2-0-1 색상·가시성 팔레트 (고정). 손대지 않는다."""
CSS = """
<meta charset="utf-8">
<style>
@page { size: A4; margin: 12mm 10mm; @bottom-right { content: counter(page) " / " counter(pages);
  font-family:'NanumGothic'; font-size:7pt; color:#8A939C; } }
* { box-sizing:border-box; }
body { font-family:'NanumGothic',sans-serif; color:#1c2530; font-size:10.6px; line-height:1.5; margin:0; }
h1,h2,h3 { margin:0; }
.up { color:#e8453c; font-weight:bold; }   /* 상승 = 빨강 (한국식) */
.dn { color:#2f6fed; font-weight:bold; }   /* 하락 = 파랑 */
.hl { background:#FFE14D; padding:1px 3px; font-weight:bold; color:#1c2530; }
.warn { color:#C0392B; font-weight:bold; }

/* ── 페이지 배치 (2-0-3) : WeasyPrint 기준. div가 아니라 table로 원자화한다 ── */
.pb-avoid,.keep { page-break-inside:avoid; break-inside:avoid; }
.corner,.sub2,.ct,.chead { break-after:avoid; page-break-after:avoid; }
table.chartwrap,table.chartwrap tr,table.chartwrap td { break-inside:avoid; page-break-inside:avoid; }
.keep table,.keep table tr { break-inside:avoid; page-break-inside:avoid; }
.g2,.g2 tr,.traptbl,.traptbl tr,.trapblk,.box-navy,.concl { break-inside:avoid; page-break-inside:avoid; }
thead { display:table-header-group; }
tr { break-inside:avoid; page-break-inside:avoid; }

.banner { background:linear-gradient(90deg,#12325B,#245DA3); color:#fff; padding:14px 16px; border-radius:7px; margin-bottom:9px; }
.banner h1 { font-size:20px; letter-spacing:-.4px; }
.banner .sub { font-size:10.5px; opacity:.95; margin-top:4px; }
.banner .pill { display:inline-block; background:rgba(255,255,255,.18); border:1px solid rgba(255,255,255,.35);
  border-radius:11px; padding:1.5px 8px; font-size:9.6px; margin-right:5px; }

.corner { font-size:14px; font-weight:bold; color:#12325B; border-left:5px solid #245DA3;
  padding:3px 0 3px 8px; margin:13px 0 6px 0; }
/* 코너 제목을 표에 붙일 때는 caption 사용 — 표와 절대 분리되지 않는다(고아 봉쇄) */
caption.corner-cap { caption-side:top; text-align:left; font-size:14px; font-weight:bold; color:#12325B;
  border-left:5px solid #245DA3; padding:3px 0 5px 8px; margin:13px 0 6px 0; break-after:avoid; }
.sub2 { font-size:11.6px; font-weight:bold; color:#245DA3; margin:8px 0 4px 0; }

.chip { display:inline-block; color:#fff; border-radius:9px; padding:1.5px 8px; font-size:9.6px; font-weight:bold; margin-bottom:3px; }
.c-navy{background:#16243F;} .c-purple{background:#6A3FB5;} .c-blue{background:#245DA3;}
.c-teal{background:#00897B;} .c-red{background:#C0392B;} .c-amber{background:#E08A00;}
.c-gray{background:#5A6570;} .c-green{background:#1E8449;}

table { border-collapse:collapse; width:100%; font-size:9.9px; }
th { background:#E9F0FB; color:#12325B; font-weight:bold; padding:4px 5px; border:1px solid #C9D8EC; text-align:center; }
td { padding:4px 5px; border:1px solid #DCE5F0; vertical-align:middle; }
tbody tr:nth-child(even) td { background:#F8FAFD; }
.tc{text-align:center;} .tr{text-align:right;} .tl{text-align:left;}

.box { border-left:4px solid #999; background:#F7F9FC; padding:7px 9px; margin:6px 0; border-radius:0 4px 4px 0; }
.box-g{border-left-color:#1E8449;background:#F1FAF3;} .box-b{border-left-color:#245DA3;background:#F0F5FF;}
.box-a{border-left-color:#E08A00;background:#FFF9EE;} .box-r{border-left-color:#C0392B;background:#FDF2F1;}
.box-navy { background:#16243F; color:#fff; padding:9px 11px; border-radius:5px; margin:6px 0; border-left:4px solid #FFE14D; }
.box-navy b { color:#FFE14D; }
/* ★v38.2 대비 결함 봉쇄 — 2026-07-13 실증:
   .box-navy b(노랑) 이 .hl(노랑 배경) 안에 들어가면 노랑 위 노랑 = 완전 투명이 됐다.
   형광(.hl) 내부는 항상 어두운 잉크로 강제 복원한다. gate.py G1이 이 규칙의 존재를 검사한다. */
.hl, .box-navy .hl { color:#1c2530; }
.hl b, .box-navy .hl b, .hl strong, .box-navy .hl strong { color:#1c2530; }
.hl .warn, .box-navy .hl .warn, .hl b.warn, .box-navy .hl b.warn { color:#A32217; }
.hl .vg, .box-navy .hl .vg { color:#0B6B36; }
.hl .vr, .box-navy .hl .vr { color:#A32217; }
.hl .up, .box-navy .hl .up { color:#C0281F; }
.hl .dn, .box-navy .hl .dn { color:#1F4FB8; }
.sogo { font-weight:bold; color:#12325B; }

/* 신호등 — 색은 동그라미와 숫자에만 (셀 배경 통짜 채색 금지) */
.d { font-size:13px; font-weight:bold; line-height:1; }
.dg{color:#1E8449;} .dy{color:#E0A800;} .dr{color:#C0392B;} .dgr{color:#9AA5B1;}
.vg{color:#1E8449;font-weight:bold;} .vy{color:#B8860B;font-weight:bold;}
.vr{color:#C0392B;font-weight:bold;} .vgr{color:#8A939C;font-weight:bold;}

.card { border:1px solid #C9D8EC; border-radius:6px; margin:9px 0 12px 0; overflow:hidden; }
.chead { background:linear-gradient(90deg,#12325B,#245DA3); color:#fff; padding:7px 11px; }
.chead.en { background:linear-gradient(90deg,#186A3B,#28A745); }
.chead .nm { font-size:13.5px; font-weight:bold; }
.chead .tk { font-size:9.6px; opacity:.85; margin-left:5px; }
.chead .rt { float:right; text-align:right; }
.pillw { display:inline-block; background:rgba(255,255,255,.2); border:1px solid rgba(255,255,255,.4);
  border-radius:10px; padding:1.5px 8px; font-size:10px; font-weight:bold; margin-left:4px; }
.bad-hot { background:#FF7043; border-color:#FF7043; }
.bad-hi { background:#FFD54A; border-color:#FFD54A; color:#3a2c00; }
.cbody { padding:8px 10px; } .blk { margin:7px 0; }

.ax { width:16.66%; border:1px solid #DCE5F0; padding:5px 3px; text-align:center; vertical-align:top; background:#FCFDFF; }
.ax .an { font-size:8.8px; color:#5A6570; }
.ax .av { font-size:12px; font-weight:bold; margin:2px 0; }
.ax .ad { font-size:8.2px; color:#6B7680; line-height:1.25; }
.concl { background:#0E2E5A; color:#fff; padding:7px 10px; border-radius:4px; font-size:10.4px; margin-top:5px; }
.concl b { color:#FFE14D; }

.on { display:inline-block; background:#C0392B; color:#fff; border-radius:8px; padding:.5px 6px; font-size:8.8px; font-weight:bold; }
.off { display:inline-block; background:#E4E8ED; color:#6B7680; border-radius:8px; padding:.5px 6px; font-size:8.8px; font-weight:bold; }

table.chartwrap { width:100%; border-collapse:collapse; margin:7px 0; }
table.chartwrap td { border:none !important; padding:0 !important; background:transparent !important; }
.ct { font-weight:bold; color:#6A3FB5; font-size:10.6px; margin-bottom:3px; }
.chartwrap img { width:100%; border:1px solid #DCE5F0; border-radius:4px; }
.cap { font-size:9.2px; color:#5A6570; margin-top:3px; }

.g2 { width:100%; border-collapse:separate; border-spacing:6px; }
.g2 td { width:50%; vertical-align:top; padding:8px 10px; border-radius:5px; border:1px solid #DCE5F0; border-left-width:5px; }
.g2 .t { font-weight:bold; font-size:11px; margin-bottom:3px; }

.trapblk { border:2.5px solid #C0392B; border-radius:7px; padding:9px; margin:7px 0; background:#FFFCFC; }
.traptbl { width:100%; border-collapse:separate; border-spacing:5px; }
.traptbl td { width:50%; vertical-align:top; background:#fff; border:1px solid #F0C6C0; border-radius:5px; padding:7px 8px; }
.nobadge { display:inline-block; background:#C0392B; color:#fff; border-radius:3px; padding:.5px 5px; font-size:8.6px; font-weight:bold; }
.todaybadge { display:inline-block; background:#FF7043; color:#fff; border-radius:3px; padding:.5px 5px; font-size:8.6px; font-weight:bold; }

/* ── ★v44(2026-08-13 사용자 피드백): 페이지 시작 규칙 ──────────────
   "종목 분석이 종목명만 찍고 다음 페이지로 넘어가 조잡하다."
   원인: 카드 헤더(.chead)와 본문(.cbody)이 페이지 경계에서 갈라졌기 때문.
   → ①새 코너·새 종목 카드는 반드시 새 페이지에서 시작(.pgnew)
     ②카드 헤더는 본문과 절대 분리되지 않는다(break-after:avoid) */
.pgnew { break-before:page; page-break-before:always; }
/* ★v45: 코너 끝의 짧은 각주·박스가 혼자 다음 페이지로 넘어가 빈 페이지를 만들던 문제 */
.stick { break-before:avoid; page-break-before:avoid; }
.chead { break-after:avoid; page-break-after:avoid; }
.card > .chead + .cbody { break-before:avoid; page-break-before:avoid; }
.foot { font-size:9px; color:#6B7680; border-top:1px solid #DCE5F0; margin-top:12px; padding-top:6px; }
</style>
"""
