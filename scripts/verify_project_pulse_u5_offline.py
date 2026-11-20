"""Standalone parser + source consistency checks for environments without Django.
This uses the production functions extracted verbatim using AST. The only shim
is the Django slugify utility (ASCII category checks), plus Django's exception class.
"""
from pathlib import Path
import ast, hashlib, io, re, zipfile, unicodedata, json, sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from openpyxl import Workbook
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'apps/project_pulse/import_services.py'
source=p.read_text()
tree=ast.parse(source)
selected=['_text','_is_empty','_validate_text_cell','_decimal','_completion','parse_workbook']
sub=ast.Module(body=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in selected+['WorkImportError']],type_ignores=[])
ns={'hashlib':hashlib,'io':io,'re':re,'zipfile':zipfile,'date':date,'datetime':datetime,'Decimal':Decimal,'InvalidOperation':InvalidOperation,'Path':Path, 'MAX_UPLOAD_BYTES':8*1024*1024,'MAX_SHEET_ROWS':15000, 'MAX_WORKS':2500,'MAX_UNCOMPRESSED_BYTES':50*1024*1024,'_HEADER_ALIASES':({'sn','s/n','serial no','serial number'},{'description','work','works'},{'unit','uom'},{'quantity','qty'},{'% completion','completion %','completion','progress %','% progress'})}
def slugify(v, allow_unicode=False):
    x=unicodedata.normalize('NFKC' if allow_unicode else 'NFKD',str(v)).lower()
    x=re.sub(r'[^\w\s-]','',x)
    return re.sub(r'[-\s]+','-',x).strip('-_')
ns['slugify']=slugify
exec(compile(ast.fix_missing_locations(sub), str(p), 'exec'),ns)
parse=ns['parse_workbook']; Err=ns['WorkImportError']

class Upload(io.BytesIO):
    def __init__(self, contents, name='works.xlsx'):
        super().__init__(contents); self.name=name

def workbook(*sections, other=False):
    w=Workbook(); sh=w.active; sh.title='Works'
    for name, rows in sections:
        sh.append([name]);sh.append(['SN','Description','Unit','Quantity','% Completion'])
        for x in rows:sh.append(list(x))
    if other:w.create_sheet('extra')
    b=io.BytesIO();w.save(b);return Upload(b.getvalue())

results=[]
def check(name,fn):
    try:
        fn(); results.append((name,'PASS',''))
    except Exception as e:
        results.append((name,'FAIL',repr(e)))

def errors_for(upload):
    return ns['parse_workbook'](upload)['errors']

def expect_error(u,substr):
    e=errors_for(u)
    assert any(substr.lower() in z.lower() for z in e),e

def case_input():
    u=workbook(('Transformer',[(1,'Install', 'EA',2,None),(2,'AVC','EA',4,'35'),(3,'Test','LS',1,'100%')]),('Cable',[(1,'Lay','LM',120,None)]))
    p=parse(u)
    assert p['count']==4 and len(p['categories'])==2 and not p['errors'],p
    assert [r['progress'] for c in p['categories'] for r in c['works']]==[0,35,100,0]
    assert [r['blank_percent'] for c in p['categories'] for r in c['works']]==[True,False,False,True]
check('Grouped categories, valid rows and blank = 0',case_input)

def case_format():
    w=Workbook();s=w.active;s.append(['Cable']);s.append(['SN','Description','Unit','Quantity','% Completion']);s.append([1,'Cables','LM',100,0.25]);s['E3'].number_format='0%';b=io.BytesIO();w.save(b)
    p=parse(Upload(b.getvalue()))
    assert not p['errors'] and p['categories'][0]['works'][0]['progress']==25
check('Excel fractional percentage scaled exactly once',case_format)
check('Duplicate serial numbers reject case-insensitively',lambda:expect_error(workbook(('A',[('ABC','Work1','EA',1,0),('abc','Work2','EA',1,0)])),'duplicate SN'))
check('Slug-colliding categories rejected',lambda:expect_error(workbook(('Civil & Steel',[(1,'One','EA',1,0)]),('Civil Steel',[(1,'Two','EA',1,0)])),'conflicts'))
def assert_repeated():
    p=parse(workbook(('Cable Works',[(1,'First','EA',1,0)]),('cable works',[(2,'Next','EA',1,0)])))
    assert len(p['categories'])==1 and p['count']==2 and not p['errors'],p
check('Repeated normalized category headings allowed',lambda:assert_repeated())
def expect_raise(u, phrase):
    try:parse(u)
    except Err as exc:assert phrase.lower() in str(exc).lower(),str(exc);return
    raise AssertionError('expected import error')
check('More than one worksheet rejected',lambda:expect_raise(workbook(('A',[(1,'A','EA',1,0)]),other=True),'exactly one worksheet'))
check('Negative completion rejected',lambda:expect_error(workbook(('A',[(1,'Work','EA',1,-1)])),'between 0 and 100'))
check('Over-100 completion rejected',lambda:expect_error(workbook(('A',[(1,'Work','EA',1,101)])),'between 0 and 100'))
check('Fractional whole-number progress rejected',lambda:expect_error(workbook(('A',[(1,'Work','EA',1,35.2)])),'whole percentage'))
check('Non-numeric completion rejected',lambda:expect_error(workbook(('A',[(1,'Work','EA',1,'unknown')])),'must be numeric'))
check('Negative quantity rejected',lambda:expect_error(workbook(('A',[(1,'Work','EA',-5,0)])),'nonnegative'))
check('Duplicate category codes do not merge silently',lambda:expect_error(workbook(('Mechanical & HVAC',[(1,'Work','EA',1,0)]),('Mechanical HVAC',[(2,'Next','EA',2,0)])),'conflicts'))
check('Only .xlsx accepted',lambda:expect_raise(Upload(b'notanxlsx',name='works.csv'),'Upload an .xlsx'))
def extra_col():
    w=Workbook();s=w.active;s.append(['A']);s.append(['SN','Description','Unit','Quantity','% Completion']);s.append([1,'Work','EA',1,0,'UNEXPECTED']);b=io.BytesIO();w.save(b)
    expect_error(Upload(b.getvalue()),'extra data after column E')
check('Unsupported extra columns reject data',lambda:extra_col())
def formula():
    w=Workbook();s=w.active;s.append(['A']);s.append(['SN','Description','Unit','Quantity','% Completion']);s.append([1,'Work','EA',1,0]);s['E3']='=25+25';b=io.BytesIO();w.save(b)
    expect_error(Upload(b.getvalue()),'formulas are not accepted')
check('Formula completion rejected',lambda:formula())

def real_boq():
    p=Path(sys.argv[1])
    x=parse(Upload(p.read_bytes(),name=p.name))
    assert x['count']==151 and len(x['categories'])==9 and not x['errors'],(x['count'],len(x['categories']),x['errors'])
if len(sys.argv) > 1:
    check('Actual prepared BOQ: 151 works, 9 categories, zero errors',real_boq)

def zip_and_compile():
    import compileall
    assert compileall.compile_dir(str(ROOT),quiet=2,force=True)
check('Full Python source syntax',zip_and_compile)

def migration_and_urls():
    migs=[p.name for p in (ROOT/'apps/project_pulse/migrations').glob('*.py')]
    assert '0008_work_import_foundation.py' in migs and '0009_work_import_preview.py' in migs
    routes=(ROOT/'apps/project_pulse/urls.py').read_text()
    for r in ['work_progress','works_import_upload','works_import_preview','works_import_apply','scheduled_works']:
        assert f'name="{r}"' in routes,r
check('Project Pulse migrations and legacy route aliases', migration_and_urls)



def rollup_checks():
    from decimal import ROUND_HALF_UP
    from types import SimpleNamespace
    src=(ROOT/'apps/project_pulse/progress_services.py').read_text()
    tree=ast.parse(src)
    wanted=['_percent','calculate_progress','status_for_percentage']
    sub=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted],type_ignores=[])
    cats_rows=[{'id':11,'project_id':42}, {'id':12,'project_id':42},
               {'id':13,'project_id':42}] # category 13 is empty; excluded from average
    tasks_rows=[
        {'category_id':11,'status':'not_started','progress_percent':0,'due_date':None},
        {'category_id':11,'status':'in_progress','progress_percent':35,'due_date':None},
        {'category_id':11,'status':'completed','progress_percent':100,'due_date':None},
        {'category_id':12,'status':'in_progress','progress_percent':60,'due_date':None},
        {'category_id':12,'status':'not_started','progress_percent':0,'due_date':None},
        {'category_id':11,'status':'cancelled','progress_percent':75,'due_date':None},
    ]
    class Rows:
        def __init__(self,rows):self.rows=rows
        def values(self,*fields):return [{k:r[k] for k in fields} for r in self.rows]
        def exclude(self,**kw):return Rows([r for r in self.rows if any(r.get(k)!=v for k,v in kw.items())])
    class Cats:
        def filter(self,**kw):return Rows([c for c in cats_rows if c['project_id'] in kw['project_id__in']])
    class Tasks:
        def filter(self,**kw):return Rows([r for r in tasks_rows if r['category_id'] in kw['category_id__in']])
    class Status: CANCELLED='cancelled';COMPLETED='completed';IN_PROGRESS='in_progress';NOT_STARTED='not_started'
    scope={'Decimal':Decimal,'ROUND_HALF_UP':ROUND_HALF_UP,'_ZERO':Decimal('0'),'_TENTH':Decimal('0.1'),'PulseWorkCategory':SimpleNamespace(objects=Cats()),
           'PulseTask':SimpleNamespace(objects=Tasks(),Status=Status),'timezone':SimpleNamespace(localdate=lambda:date(2026,11,20))}
    exec(compile(ast.fix_missing_locations(sub),'progress_services.py','exec'),scope)
    summaries,categories=scope['calculate_progress']([42],today=date(2026,11,20))
    assert categories[11]['percent']==Decimal('45.0'),categories
    assert categories[12]['percent']==Decimal('30.0'),categories
    assert categories[13]['percent']==Decimal('0.0'),categories
    assert summaries[42]['percent']==Decimal('37.5'),summaries
    assert summaries[42]['task_count']==5 and summaries[42]['completed_count']==1,summaries
    assert summaries[42]['measured_categories']==2,summaries
    assert [scope['status_for_percentage'](x) for x in [0,35,100]]==[
        'not_started','in_progress','completed'
    ]
check('Production rollup: 45%, 30% => project 37.5% (ignore empty/cancelled)',rollup_checks)

p=ROOT/'PROJECT_PULSE_U5_OFFLINE_RESULTS.json';p.write_text(json.dumps({'total':len(results),'passed':sum(s=='PASS' for _,s,_ in results),'failed':sum(s=='FAIL' for _,s,_ in results),'checks':[{'name':n,'status':s,'detail':d} for n,s,d in results]},indent=2))
for n,s,d in results:print(('PASS' if s=='PASS' else 'FAIL'),n, d)
print('TOTAL',len(results),'PASS',sum(s=='PASS' for _,s,_ in results),'FAIL',sum(s=='FAIL' for _,s,_ in results))
raise SystemExit(1 if any(s=='FAIL' for _,s,_ in results) else 0)
