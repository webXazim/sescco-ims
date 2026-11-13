#!/usr/bin/env python3
"""U10 source & export regression checks, runnable without Django/DB.

This does NOT replace `manage.py check`, migration checks, Django test suite,
PostgreSQL tests, browser tests, or deployment testing.
Run from anywhere: python scripts/project_pulse_u10_offline_checks.py
Requires the project's openpyxl and reportlab runtime dependencies for exports.
"""
import ast
import io
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def verify_python():
    files = list(ROOT.rglob('*.py'))
    for file in files:
        ast.parse(file.read_text(encoding='utf-8-sig'), filename=str(file))
    assert len(files) > 650, 'Unexpectedly small project tree'
    return len(files)


def verify_routes():
    from_file = ROOT / 'apps/project_pulse/urls.py'
    src = from_file.read_text()
    destinations = set(re.findall(r'views\.(\w+)\s*,\s*name\s*=', src))
    names = set(re.findall(r'name\s*=\s*[\'\"](\w+)[\'\"]', src))
    view_tree = ast.parse((ROOT/'apps/project_pulse/views.py').read_text())
    functions = {node.name for node in view_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert destinations and destinations <= functions, f'Undefined views: {destinations-functions}'
    templates = ROOT/'templates/project_pulse'
    for file in templates.rglob('*.html'):
        for match in re.findall(r"\{%\s*url\s+['\"]project_pulse:([a-zA-Z_0-9]+)['\"]", file.read_text()):
            assert match in names, f'Unknown route in {file.name}: {match}'
    return len(names)


def verify_permissions():
    t = ast.parse((ROOT/'apps/accounts/access_catalog.py').read_text())
    enum = next(n for n in t.body if isinstance(n, ast.ClassDef) and n.name == 'AccessPermission')
    codes = {
        n.value.value for n in enum.body
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
    }
    latest = ast.parse((ROOT/'apps/accounts/migrations/0025_project_pulse_u09_report_authority.py').read_text())
    vals = next(n.value for n in latest.body if isinstance(n, ast.Assign)
                and any(isinstance(x, ast.Name) and x.id == 'ALL_PERMISSIONS' for x in n.targets))
    migrated = set(ast.literal_eval(vals))
    assert codes == migrated, f'Catalog/migration mismatch: {sorted(codes ^ migrated)}'
    assert len([x for x in codes if x.startswith('pulse.')]) == 27
    assert (ROOT/'VERSION').read_text().strip() == '1.0.127'
    return len(codes)


def verify_privacy_and_finance_guards():
    # These assertions protect previous U10 bug fixes when running without ORM.
    view = (ROOT/'apps/project_pulse/views.py').read_text()
    assert 'if can_view_projects else []' in view
    assert 'can_view_progress = can_view_projects and all(' in view
    home = (ROOT/'templates/project_pulse/home.html').read_text()
    assert '{% if pulse_can_view_projects %}<section class="pulse-panel">' in home
    budget = (ROOT/'apps/project_pulse/budget_services.py').read_text()
    assert 'balance_on_approved_budgets' in budget
    assert 'unbudgeted_approved_cost' in budget
    assert 'unbudgeted_actual_total == ZERO' in budget
    reports = (ROOT/'apps/project_pulse/report_services.py').read_text()
    assert 'selected_budget - budgeted_actual' in reports
    assert 'Unbudgeted approved expenses (selected) SAR' in reports
    storage = (ROOT/'apps/project_pulse/private_storage.py').read_text()
    assert 'base_url=None' in storage and 'def url(self, name)' in storage
    assert (ROOT/'apps/project_pulse/tests/test_release_hardening.py').exists()


def verify_exports():
    # Compile actual export functions into a no-Django namespace; real openpyxl
    # and ReportLab do the work, not mock spreadsheet/PDF generators.
    from html import escape
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    tree = ast.parse((ROOT/'apps/project_pulse/report_exports.py').read_text())
    keep = {'_safe_excel', '_display', 'make_xlsx', 'make_pdf'}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in keep]
    assert {x.name for x in functions} == keep
    globals_ = dict(BytesIO=io.BytesIO, escape=escape, Decimal=Decimal, date=date,
                    datetime=datetime, Workbook=Workbook, Alignment=Alignment, Font=Font,
                    PatternFill=PatternFill, get_column_letter=get_column_letter,
                    timezone=SimpleNamespace(localdate=date.today), colors=colors,
                    TA_CENTER=TA_CENTER, TA_LEFT=TA_LEFT, A4=A4, landscape=landscape,
                    ParagraphStyle=ParagraphStyle, mm=mm, LongTable=LongTable,
                    Paragraph=Paragraph, SimpleDocTemplate=SimpleDocTemplate,
                    Spacer=Spacer, TableStyle=TableStyle)
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<actual report_exports functions>', 'exec'), globals_)
    report = SimpleNamespace(title='Expense analysis',
        headers=('Date', 'Category', 'Expense', 'Amount SAR'),
        rows=[(date(2026, 11, 13), 'Material', '=SUM(A1:A99)', Decimal('12.34'))]
             + [(date(2026, 11, 13), 'Equipment', 'Excavator #'+str(i), Decimal('125.50')) for i in range(115)],
        stats=[('Approved SAR', Decimal('14444.84'))],
        notes=['Sensitive figures, authorized export only.'])
    project = SimpleNamespace(code='U10-SMOKE', name='Project Pulse QA')
    xlsx = globals_['make_xlsx'](report, project)
    workbook = load_workbook(io.BytesIO(xlsx), data_only=False)
    assert workbook.active['C5'].data_type == 's'
    assert workbook.active['C5'].value == "'=SUM(A1:A99)"
    assert workbook.active['D5'].data_type == 'n'
    assert abs(workbook.active['D5'].value - 12.34) < 0.00001
    assert workbook.active.max_row == 4 + len(report.rows)
    assert abs(workbook['Summary & Notes']['B2'].value - 14444.84) < 0.00001
    pdf = globals_['make_pdf'](report, project)
    assert pdf.startswith(b'%PDF-') and pdf.rstrip().endswith(b'%%EOF')
    assert len(pdf) > 4000
    # PyMuPDF is optional (not a production dependency); when available also
    # verify that the final report row survives across PDF page boundaries.
    try:
        import fitz
    except ImportError:
        pass
    else:
        document = fitz.open(stream=pdf, filetype='pdf')
        assert document.page_count >= 2, 'Expected a multi-page PDF smoke export'
        text = '\n'.join(page.get_text() for page in document)
        assert 'Excavator #114' in text, 'Final report row was dropped'
        document.close()
    return len(report.rows), len(pdf), len(xlsx)


def main():
    checks = [
        ('Python AST', verify_python), ('Routes/templates', verify_routes),
        ('Access catalog / migration', verify_permissions),
        ('Security & finance guards', verify_privacy_and_finance_guards),
        ('Real XLSX/PDF generation', verify_exports),
    ]
    for label, fn in checks:
        try:
            value = fn()
            print(f'PASS {label}: {value if value is not None else "OK"}')
        except Exception as exc:
            print(f'FAIL {label}: {exc}', file=sys.stderr)
            raise
    print('All U10 offline checks passed. Django/PostgreSQL tests are still required.')


if __name__ == '__main__':
    main()
