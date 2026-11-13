"""Excel and PDF exports of already-authorized Project Pulse report data.

Keep user-controlled text inert in Excel cells and escaped in ReportLab markup.
No public files or background export jobs are created.
"""
from io import BytesIO
from html import escape
from datetime import date, datetime
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def _safe_excel(value):
    if value is None:
        return '—'
    if isinstance(value, (Decimal, int, float, date, datetime)):
        return value
    s = str(value)
    # Some spreadsheet programs interpret leading formula markers, even with leading
    # whitespace/control characters. Escape before writing untrusted database text.
    if s.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + s
    return s


def _display(value):
    if value is None:
        return '—'
    if isinstance(value, Decimal):
        return f'{value:,.2f}'
    if isinstance(value, (date, datetime)):
        return value.strftime('%d %b %Y')
    return str(value)


def make_xlsx(report, project):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = report.title[:31]
    count = len(report.headers)
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=count)
    cell = sheet.cell(1, 1, f'SESCCO · Project Pulse · {report.title}')
    cell.font = Font(name='Aptos', size=15, bold=True, color='FFFFFF')
    cell.fill = PatternFill('solid', fgColor='183048')
    sheet.row_dimensions[1].height = 27
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=count)
    sheet.cell(2, 1, f'Project: {project.code} · Exported {timezone.localdate().isoformat()} · SAR amounts unless noted')
    sheet.cell(2, 1).font = Font(name='Aptos', size=10, color='475569')
    for col, header in enumerate(report.headers, start=1):
        c = sheet.cell(4, col, header)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='29465D')
        c.alignment = Alignment(wrap_text=True, vertical='center')
    sheet.row_dimensions[4].height = 27
    for idx, row in enumerate(report.rows, start=5):
        for col, value in enumerate(row, start=1):
            cell = sheet.cell(idx, col, _safe_excel(value))
            cell.font = Font(name='Aptos', size=10)
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            if idx % 2 == 0:
                cell.fill = PatternFill('solid', fgColor='F4F7F9')
            if isinstance(value, Decimal):
                cell.number_format = '#,##0.00;[Red](#,##0.00)'
            elif isinstance(value, (date, datetime)):
                cell.number_format = 'yyyy-mm-dd'
    sheet.freeze_panes = 'A5'
    sheet.auto_filter.ref = f'A4:{get_column_letter(count)}{max(4, 4 + len(report.rows))}'
    for col, header in enumerate(report.headers, start=1):
        sheet.column_dimensions[get_column_letter(col)].width = min(38, max(15, len(header) + 4))
    extra = workbook.create_sheet('Summary & Notes')
    extra.append(['Metric', 'Value'])
    for name, value in report.stats:
        extra.append([_safe_excel(name), _safe_excel(value)])
    extra.append([])
    extra.append(['Important notes'])
    for note in report.notes:
        extra.append([_safe_excel(note)])
    extra.column_dimensions['A'].width = 95
    extra.column_dimensions['B'].width = 26
    extra.freeze_panes = 'A2'
    extra['A1'].font = Font(bold=True)
    extra['B1'].font = Font(bold=True)
    buff = BytesIO()
    workbook.save(buff)
    return buff.getvalue()


def make_pdf(report, project):
    buff = BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=landscape(A4),
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    heading = ParagraphStyle('heading', fontName='Helvetica-Bold', fontSize=15,
                             leading=19, textColor=colors.HexColor('#183048'), spaceAfter=8)
    subtitle = ParagraphStyle('sub', fontName='Helvetica', fontSize=9, leading=13, spaceAfter=4)
    content = ParagraphStyle('data', fontName='Helvetica', fontSize=7, leading=9,
                             alignment=TA_LEFT, wordWrap='CJK')
    header = ParagraphStyle('header', parent=content, fontName='Helvetica-Bold',
                            textColor=colors.white, alignment=TA_CENTER)
    note_style = ParagraphStyle('note', parent=subtitle, fontSize=8, leading=11)
    flow = [Paragraph(escape(f'SESCCO · {report.title}'), heading),
            Paragraph(escape(f'Project {project.code} · {project.name} · Generated {timezone.localdate().isoformat()}'), subtitle),
            Spacer(1, 5)]
    for label, value in report.stats:
        flow.append(Paragraph(f'<b>{escape(str(label))}:</b> {escape(_display(value))}', subtitle))
    flow.append(Spacer(1, 6))
    cells = [[Paragraph(escape(str(name)), header) for name in report.headers]]
    for row in report.rows:
        cells.append([Paragraph(escape(_display(value)).replace('\n', '<br/>'), content) for value in row])
    if len(cells) == 1:
        cells.append([Paragraph('No records match these filters.', content)] + [''] * (len(report.headers) - 1))
    width = doc.width / len(report.headers)
    table = LongTable(cells, colWidths=[width] * len(report.headers), repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#29465D')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F4F7F9')]),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.HexColor('#CBD5E1')),
    ]))
    flow.append(table)
    flow.append(Spacer(1, 12))
    for note in report.notes:
        flow.append(Paragraph(escape(note), note_style))

    def footer(canvas, pdf):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#64748B'))
        canvas.drawString(12 * mm, 9 * mm, 'SESCCO · Project Pulse · Restricted report')
        canvas.drawRightString(285 * mm, 9 * mm, f'Page {pdf.page}')
        canvas.restoreState()
    doc.build(flow, onFirstPage=footer, onLaterPages=footer)
    return buff.getvalue()


def report_response(report, project, format_name):
    if format_name == 'xlsx':
        payload = make_xlsx(report, project)
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif format_name == 'pdf':
        payload = make_pdf(report, project)
        content_type = 'application/pdf'
    else:
        raise ValueError('Unsupported export type')
    res = HttpResponse(payload, content_type=content_type)
    res['Content-Disposition'] = f'attachment; filename="pulse_{project.pk}_{report.kind}.{format_name}"'
    res['Cache-Control'] = 'private, no-store'
    res['X-Content-Type-Options'] = 'nosniff'
    return res
