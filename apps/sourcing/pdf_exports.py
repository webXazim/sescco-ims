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

# Manpower and Subcontractor reports use the same rendering, bounds and escaping
# as the Vendor reports. The caller supplies a tenant-filtered queryset.
def manpower_company_report_rows(suppliers):
    for supplier in suppliers.iterator(chunk_size=200):
        yield (
            supplier.name,
            ', '.join(part for part in (supplier.city, supplier.region) if part),
            supplier.mobile or supplier.phone,
            supplier.email,
            ', '.join(supplier.tags or []),
            str(supplier.active_trade_count),
        )


def subcontractor_company_report_rows(subcontractors):
    for obj in subcontractors.iterator(chunk_size=200):
        location = ', '.join(part for part in (obj.district, obj.city, obj.region) if part)
        yield (
            obj.display_name or obj.name,
            location or obj.address or '',
            obj.mobile or obj.company_phone,
            obj.email or obj.company_email,
            ', '.join(obj.tags or []),
            str(obj.active_service_type_count),
        )


def workforce_catalog_report_rows(offers):
    for offer in offers.iterator(chunk_size=200):
        trade = offer.trade
        quantity = str(offer.available_quantity) if offer.available_quantity is not None else '-'
        rate = '-'
        if offer.rate is not None:
            rate = f'{offer.currency or "SAR"} {_decimal(offer.rate)} / {offer.get_rate_basis_display()}'
            if offer.rate_valid_until:
                rate += f'\nValid to {_date(offer.rate_valid_until)}'
        if offer.overtime_rate is not None:
            rate += f'\nOT: {offer.currency or "SAR"} {_decimal(offer.overtime_rate)}'
        yield (
            '\n'.join(filter(None, (trade.name, trade.code, trade.category))),
            offer.get_availability_display(),
            quantity,
            rate,
            offer.work_location or '-',
            offer.mobilization_lead_time or '-',
            _date(timezone.localtime(offer.last_verified_at)) if offer.last_verified_at else 'Never',
        )


def subcontractor_catalog_report_rows(offers):
    for offer in offers.iterator(chunk_size=200):
        service = offer.service
        rate = '-'
        if offer.rate is not None:
            rate = f'{offer.currency or "SAR"} {_decimal(offer.rate)} / {offer.get_rate_basis_display()}'
            if offer.rate_valid_until:
                rate += f'\nValid to {_date(offer.rate_valid_until)}'
        yield (
            '\n'.join(filter(None, (service.name, service.code, service.category))),
            offer.scope_description or '-',
            offer.service_location or '-',
            offer.get_availability_display(),
            rate,
            offer.lead_time or '-',
            _date(timezone.localtime(offer.last_verified_at)) if offer.last_verified_at else 'Never',
        )


def render_manpower_directory_pdf(*, suppliers, total, status):
    return _make_pdf(
        title='Manpower Supplier Directory',
        subtitle=f'Sourcing company references  /  Status: {status.title()}',
        headings=('Supplier Name', 'Location', 'Mobile Number', 'Email Address', 'Tag', 'Active Trades'),
        widths=(157, 152, 95, 147, 125, 92),
        rows=manpower_company_report_rows(suppliers), total=total,
        note='Active Trades counts distinct active worker types; it is not a count of Rental Payroll workers.',
    )


def render_subcontractor_directory_pdf(*, subcontractors, total, status):
    return _make_pdf(
        title='Subcontractor Directory',
        subtitle=f'Sourcing company references  /  Status: {status.title()}',
        headings=('Subcontractor Name', 'Location', 'Mobile Number', 'Email Address', 'Tag', 'Active Services'),
        widths=(157, 152, 95, 147, 125, 92),
        rows=subcontractor_company_report_rows(subcontractors), total=total,
        note='Active Services counts distinct active service types, not contractual project commitments.',
    )


def render_workforce_catalog_pdf(*, supplier, offers, total):
    return _make_pdf(
        title=f'Workforce Catalog - {supplier.name}',
        subtitle=f'Supplier code: {supplier.code}  /  Active workforce references only',
        headings=('Trade / Code', 'Availability', 'Available Workers', 'Rate / Basis / OT', 'Work Location', 'Mobilization', 'Last Verified'),
        widths=(149, 86, 77, 138, 114, 112, 92),
        rows=workforce_catalog_report_rows(offers), total=total,
        note='Workforce availability and rates are supplier-reported references, not Payroll counts or approved rates.',
    )


def render_subcontractor_catalog_pdf(*, subcontractor, offers, total):
    return _make_pdf(
        title=f'Service Catalog - {subcontractor.display_name or subcontractor.name}',
        subtitle=f'Subcontractor code: {subcontractor.code}  /  Active service references only',
        headings=('Service / Code', 'Scope', 'Location', 'Availability', 'Reference Rate', 'Lead Time', 'Last Verified'),
        widths=(139, 153, 97, 78, 141, 68, 92),
        rows=subcontractor_catalog_report_rows(offers), total=total,
        note='Service rates and availability are sourcing reference snapshots, not approved contracts or project commitments.',
    )
