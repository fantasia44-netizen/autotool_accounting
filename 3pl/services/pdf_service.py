"""정산서 PDF 생성 서비스.

reportlab 기반. 한글 폰트는 시스템 폰트(맑은고딕/나눔고딕) 자동 탐색.
"""
import io
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── 한글 폰트 경로 자동 탐색 ──

_FONT_SEARCH_PATHS = [
    # Windows
    r'C:\Windows\Fonts\malgun.ttf',       # 맑은 고딕
    r'C:\Windows\Fonts\NanumGothic.ttf',  # 나눔고딕
    # macOS
    '/Library/Fonts/AppleGothic.ttf',
    '/System/Library/Fonts/AppleSDGothicNeo.ttc',
    # Linux
    '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
    '/usr/share/fonts/nanum/NanumGothic.ttf',
]

_FONT_BOLD_SEARCH_PATHS = [
    r'C:\Windows\Fonts\malgunbd.ttf',
    r'C:\Windows\Fonts\NanumGothicBold.ttf',
    '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf',
]


def _find_font():
    """사용 가능한 한글 폰트 경로 반환."""
    for path in _FONT_SEARCH_PATHS:
        if os.path.exists(path):
            return path
    return None


def _find_font_bold():
    """사용 가능한 한글 Bold 폰트 경로 반환."""
    for path in _FONT_BOLD_SEARCH_PATHS:
        if os.path.exists(path):
            return path
    return None


def generate_invoice_pdf(client, year_month, summary, invoice=None, operator_name=''):
    """정산서 PDF BytesIO 생성.

    Args:
        client: dict — 고객사 정보 (name, business_no, contact_name 등)
        year_month: str — 'YYYY-MM'
        summary: dict — get_monthly_summary() 결과 (total, by_category, items)
        invoice: dict|None — 정산서 정보 (status, confirmed_at 등)
        operator_name: str — 운영사명

    Returns:
        io.BytesIO — PDF 바이너리
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # 한글 폰트 등록
    font_path = _find_font()
    font_bold_path = _find_font_bold()
    if font_path:
        pdfmetrics.registerFont(TTFont('KoreanFont', font_path))
        font_name = 'KoreanFont'
    else:
        font_name = 'Helvetica'
        logger.warning('한글 폰트를 찾을 수 없습니다. 기본 폰트 사용.')

    if font_bold_path:
        pdfmetrics.registerFont(TTFont('KoreanFontBold', font_bold_path))
        font_bold = 'KoreanFontBold'
    else:
        font_bold = font_name

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # 카테고리 한글 라벨
    cat_labels = {
        'inbound': '입고비', 'outbound': '출고비', 'storage': '보관비',
        'courier': '택배비', 'material': '부자재비', 'return': '반품비',
        'vas': '부가서비스', 'custom': '기타',
    }

    y = height - 30 * mm

    # ── 헤더 ──
    c.setFont(font_bold, 18)
    c.drawString(25 * mm, y, '정 산 서')
    y -= 8 * mm

    c.setFont(font_name, 9)
    c.setFillColor(colors.grey)
    status_text = '확정' if (invoice and invoice.get('status') == 'confirmed') else '미확정'
    c.drawString(25 * mm, y, f'상태: {status_text}')
    c.drawRightString(width - 25 * mm, y, f'발행일: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}')
    c.setFillColor(colors.black)
    y -= 12 * mm

    # ── 고객사 / 운영사 정보 ──
    c.setFont(font_bold, 10)
    c.drawString(25 * mm, y, '공급자 (운영사)')
    c.drawString(width / 2 + 5 * mm, y, '공급받는자 (고객사)')
    y -= 6 * mm

    c.setFont(font_name, 9)
    c.drawString(25 * mm, y, f'상호: {operator_name or "PackFlow"}')
    c.drawString(width / 2 + 5 * mm, y, f'상호: {client.get("name", "")}')
    y -= 5 * mm
    c.drawString(width / 2 + 5 * mm, y, f'사업자번호: {client.get("business_no", "-")}')
    y -= 5 * mm
    c.drawString(width / 2 + 5 * mm, y, f'담당자: {client.get("contact_name", "-")}')
    y -= 10 * mm

    # ── 정산 기간 ──
    c.setFont(font_bold, 11)
    c.drawString(25 * mm, y, f'정산 기간: {year_month}')
    y -= 10 * mm

    # ── 카테고리별 요약 테이블 ──
    c.setFont(font_bold, 9)
    _draw_row(c, 25 * mm, y, ['카테고리', '금액'], [80 * mm, 50 * mm], font_bold, 9,
              bg=colors.Color(0.93, 0.95, 0.98))
    y -= 6 * mm

    c.setFont(font_name, 9)
    by_cat = summary.get('by_category', {})
    for cat_key, cat_amount in by_cat.items():
        _draw_row(c, 25 * mm, y,
                  [cat_labels.get(cat_key, cat_key), f'{cat_amount:,.0f}원'],
                  [80 * mm, 50 * mm], font_name, 9)
        y -= 6 * mm

    # 합계
    c.setFont(font_bold, 10)
    _draw_row(c, 25 * mm, y,
              ['합  계', f'{summary.get("total", 0):,.0f}원'],
              [80 * mm, 50 * mm], font_bold, 10,
              bg=colors.Color(0.85, 0.92, 1.0))
    y -= 12 * mm

    # ── 상세 내역 테이블 ──
    c.setFont(font_bold, 10)
    c.drawString(25 * mm, y, '상세 내역')
    y -= 8 * mm

    col_widths = [30 * mm, 35 * mm, 18 * mm, 25 * mm, 28 * mm, 25 * mm]
    headers = ['카테고리', '항목', '수량', '단가', '금액', '일자']
    c.setFont(font_bold, 8)
    _draw_row(c, 25 * mm, y, headers, col_widths, font_bold, 8,
              bg=colors.Color(0.93, 0.95, 0.98))
    y -= 5.5 * mm

    c.setFont(font_name, 8)
    items = summary.get('items', [])
    for item in items:
        if y < 25 * mm:
            c.showPage()
            y = height - 25 * mm
            c.setFont(font_name, 8)

        row = [
            cat_labels.get(item.get('category', ''), item.get('category', '')),
            item.get('fee_name', ''),
            str(item.get('quantity', 0)),
            f'{float(item.get("unit_price", 0)):,.0f}',
            f'{float(item.get("total_amount", 0)):,.0f}',
            (item.get('created_at', '')[:10] if item.get('created_at') else ''),
        ]
        _draw_row(c, 25 * mm, y, row, col_widths, font_name, 8)
        y -= 5.5 * mm

    # ── 하단 안내 ──
    y -= 10 * mm
    if y < 30 * mm:
        c.showPage()
        y = height - 30 * mm

    c.setFont(font_name, 8)
    c.setFillColor(colors.grey)
    c.drawString(25 * mm, y, '본 정산서는 PackFlow 시스템에서 자동 생성되었습니다.')
    c.setFillColor(colors.black)

    c.save()
    buf.seek(0)
    return buf


def _draw_row(c, x, y, cells, col_widths, font_name, font_size, bg=None):
    """테이블 행 그리기 헬퍼."""
    from reportlab.lib import colors

    row_height = font_size * 0.4 + 3  # mm 근사

    if bg:
        from reportlab.lib.units import mm
        total_width = sum(col_widths)
        c.setFillColor(bg)
        c.rect(x, y - 1.5 * mm, total_width, 5 * mm, fill=1, stroke=0)
        c.setFillColor(colors.black)

    c.setFont(font_name, font_size)
    cx = x
    for i, cell in enumerate(cells):
        c.drawString(cx + 1, y, str(cell))
        cx += col_widths[i]
