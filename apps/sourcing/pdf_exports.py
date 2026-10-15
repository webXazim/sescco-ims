"""Read-only, paginated PDF reports for Vendor Sourcing.

Reports never mutate Sourcing or operational data. Callers must provide tenant-
scoped querysets and enforce Sourcing export + Vendor view authority.
"""
from __future__ import annotations

from html import escape as html_escape
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

MAX_PDF_ROWS = 10000
PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
INK = colors.HexColor('#152b42')
MUTED = colors.HexColor('#586d82')
LINE = colors.HexColor('#dce5ee')
HEADER_BG = colors.HexColor('#eff4f9')
STRIPE = colors.HexColor('#f8fafc')


def _text(value, *, limit=300):
    """Escape supplier-controlled text before using ReportLab's Paragraph markup."""
    if value is None or value == '':
        return '-'
    return html_escape(' '.join(str(value).split())[:limit], quote=False)


def _date(value):
    return value.strftime('%d %b %Y') if value else '-'


def _decimal(value):
    if value is None:
        return '-'
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else str(value)


def company_report_rows(vendors):
    """Return six requested fields in the Directory's filtered/sorted order."""
    for vendor in vendors.iterator(chunk_size=200):
        location = ', '.join(part for part in (vendor.district, vendor.city, vendor.region) if part)
        if not location:
            location = vendor.address or ''
        yield (
            vendor.display_name or vendor.name,
            location,
            vendor.mobile or vendor.company_phone,
            vendor.email or vendor.company_email,
            ', '.join(vendor.tags or []),
            str(vendor.active_material_count),
        )


def catalog_report_rows(offers):
    """Active supply offers from one vendor only, with quotation metadata."""
    for offer in offers.iterator(chunk_size=200):
        material = offer.material
        description = '\n'.join(filter(None, (offer.specification, offer.brand, offer.model)))
        material_text = '\n'.join(filter(None, (material.name, material.code, material.category)))
        quantity = '-'
        if offer.available_quantity is not None:
            quantity = f'{_decimal(offer.available_quantity)} {offer.unit or material.default_unit}'.strip()
        rate = '-'
        if offer.rate is not None:
            rate = f'{offer.currency or "SAR"} {_decimal(offer.rate)}'
            if offer.rate_valid_until:
                rate += f'\nValid to {_date(offer.rate_valid_until)}'
        yield (
            material_text,
            description or '-',
            offer.get_availability_display(),
            quantity,
            rate,
            offer.lead_time or '-',
            _date(timezone.localtime(offer.last_verified_at)) if offer.last_verified_at else 'Never',
        )


def _cell(value, style):
    # Explicit line breaks are authored by this service, not raw model markup.
    return Paragraph('<br/>'.join(_text(bit, limit=360) for bit in str(value).split('\n')), style)


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(13 * mm, 17 * mm, PAGE_WIDTH - 13 * mm, 17 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont('Helvetica', 7.7)
    canvas.drawString(13 * mm, 12.8 * mm, 'SESCCO MS  /  Sourcing Directory  /  Reference only - verify with provider')
    canvas.drawRightString(PAGE_WIDTH - 13 * mm, 12.8 * mm, f'Page {doc.page}')
    canvas.restoreState()


def _make_pdf(*, title, subtitle, headings, widths, rows, total, note):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        leftMargin=13 * mm, rightMargin=13 * mm,
        topMargin=16 * mm, bottomMargin=23 * mm,
        title=title, author='SESCCO MS', subject='Read-only Sourcing reference export',
        pageCompression=1,
    )
    title_style = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=17, leading=22, textColor=INK)
    sub_style = ParagraphStyle('sub', fontName='Helvetica', fontSize=9, leading=13, textColor=MUTED)
    heading_style = ParagraphStyle('heading', fontName='Helvetica-Bold', fontSize=8.2, leading=11, textColor=INK)
    body_style = ParagraphStyle('body', fontName='Helvetica', fontSize=8.1, leading=11.5, textColor=INK, splitLongWords=True, spaceAfter=0)

    stamp = timezone.localtime(timezone.now()).strftime('%d %b %Y, %H:%M')
    story = [Paragraph(_text(title), title_style), Spacer(1, 4 * mm)]
    story.append(Paragraph(_text(subtitle), sub_style))
    story.append(Paragraph(f'{total:,} records  |  Generated {stamp}', sub_style))
    story.append(Spacer(1, 5 * mm))

    data = [[Paragraph(_text(header), heading_style) for header in headings]]
    data.extend([_cell(value, body_style) for value in row] for row in rows)
    if len(data) == 1:
        story.append(Paragraph('No matching records.', body_style))
    else:
        table = LongTable(data, colWidths=widths, repeatRows=1, hAlign='LEFT', splitByRow=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, 0), 0.8, LINE),
            ('LINEBELOW', (0, 1), (-1, -1), 0.25, LINE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, STRIPE]),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_text(note, limit=600), sub_style))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def render_vendor_directory_pdf(*, vendors, total, status):
    return _make_pdf(
        title='Vendor Directory',
        subtitle=f'Sourcing company references  /  Status: {status.title()}',
        headings=('Vendor Name', 'Location', 'Mobile Number', 'Email Address', 'Tag', 'Active Materials'),
        widths=(157, 152, 95, 147, 125, 92),
        rows=company_report_rows(vendors), total=total,
        note='Active Materials counts distinct active material references, not separate quotations.',
    )


def render_vendor_catalog_pdf(*, vendor, offers, total):
    return _make_pdf(
        title=f'Supply Catalog - {vendor.display_name or vendor.name}',
        subtitle=f'Vendor code: {vendor.code}  /  Active supply items only',
        headings=('Material / Code', 'Specification / Brand / Model', 'Availability', 'Quantity / Unit', 'Reference Rate', 'Lead Time', 'Last Verified'),
        widths=(151, 157, 87, 88, 123, 70, 92),
        rows=catalog_report_rows(offers), total=total,
        note='Reference prices, quantities and lead times are last-known supplier statements, not stock balances or purchase commitments.',
    )
