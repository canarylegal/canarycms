"""Profile real route/serialization SQL on the disposable PostgreSQL fixture."""
import json,os,statistics,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import event,select
from fastapi.testclient import TestClient
from app.db import engine,SessionLocal
from app.models import Case
from app.main import app
from seed_performance_fixture import guard

guard()
client=TestClient(app)
assert client.post('/auth/login',json={'email':os.environ['E2E_STAFF_EMAIL'],'password':os.environ['E2E_STAFF_PASSWORD']}).status_code==200
with SessionLocal() as db: case_id=str(db.scalar(select(Case.id).where(Case.case_number=='900001')))
report={}
for name,path,count in [('matters','/cases',5002),('matter_page','/cases/menu',100),('documents',f'/cases/{case_id}/files',1200)]:
    samples=[];queries=[];sizes=[]
    for iteration in range(6):
        statements=[]
        def query(conn,cursor,statement,parameters,context,many): statements.append(statement.split()[0])
        event.listen(engine,'before_cursor_execute',query)
        start=time.perf_counter()
        try: response=client.get(path)
        finally: event.remove(engine,'before_cursor_execute',query)
        elapsed=(time.perf_counter()-start)*1000
        assert response.status_code==200
        data=response.json()['items'] if name=='matter_page' else response.json()
        assert len(data)==count
        if name=='documents':
            forms=[f['portal_form_submission'] for f in response.json() if 'portal_form_submission' in f]
            assert len(forms)==100
            for item in response.json():
                if 'portal_form_submission' not in item: continue
                number=int(item['original_filename'].split()[-1].split('.')[0])
                form=item['portal_form_submission']
                assert form['contact_name']==f'Synthetic Organisation {number}'
                assert form['template_name']==f'Performance form {number%5}'
                assert form['status']=='completed'
        if iteration: samples.append(elapsed);queries.append(len(statements));sizes.append(len(response.content))
    report[name]={'median_ms':round(statistics.median(samples),2),'max_ms':round(max(samples),2),
                  'queries':max(queries),'response_bytes':max(sizes),'rows':count}
if '--assert-budgets' in sys.argv:
    assert report['documents']['queries']<=30,report
    assert report['matters']['queries']<=20,report
    assert report['matter_page']['queries']<=20,report
    assert report['matter_page']['response_bytes']<150000,report
    assert max(r['max_ms'] for r in report.values())<5000,report
print(json.dumps(report))
