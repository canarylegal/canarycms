"""Bounded page/search latency on the guarded 12,000-document fixture."""
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from app.db import engine, SessionLocal
from app.main import app
from app.models import Case
from seed_performance_fixture import guard

guard()
if '--analyze' in sys.argv:
    with engine.begin() as conn:
        conn.exec_driver_sql('ALTER TABLE file RESET (autovacuum_enabled)')
        conn.exec_driver_sql('ANALYZE file')
with engine.connect() as conn:
    file_column_stats = conn.exec_driver_sql("SELECT count(*) FROM pg_stats WHERE schemaname='public' AND tablename='file'").scalar_one()
if '--cold-statistics' in sys.argv:
    assert file_column_stats == 0, 'Cold-plan regression requires unanalyzed fixture data'
# A pathological baseline query must fail visibly rather than hang the test job.
@event.listens_for(engine, 'begin')
def timeout(conn):
    conn.exec_driver_sql("SET LOCAL statement_timeout = '15s'")

with SessionLocal() as db:
    case_id = str(db.scalar(select(Case.id).where(Case.case_number == '900002')))
base = f'/cases/{case_id}/files'
def client_for(email):
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post('/auth/login', json={'email':email,'password':os.environ['E2E_STAFF_PASSWORD']}).status_code == 200
    return client
client = client_for(os.environ['E2E_STAFF_EMAIL'])
scenarios = {f'sort_{sort}': {'sort':sort} for sort in ['created','description','size','user']}
scenarios.update(search_attachment={'q':'Large document 00001'}, search_broad={'q':'Large document'},
                 search_missing={'q':'not present'}, search_sender={'q':'Synthetic sender'},
                 deep_folder={'folder':'/'.join(['Branch 39']+[f'Level {n:02}' for n in range(1,21)])})
report = {'statistics': {'file_column_stats':file_column_stats}}
for name, params in scenarios.items():
    samples=[]; sizes=[]; counts=[]; statuses=[]
    for _ in range(3):
        statements=[]
        def record(conn,cursor,statement,parameters,context,many):
            if not statement.startswith('SET '): statements.append(statement)
        event.listen(engine, 'before_cursor_execute', record)
        start=time.perf_counter()
        try: response=client.get(base+'/browse', params=params)
        finally: event.remove(engine,'before_cursor_execute',record)
        samples.append((time.perf_counter()-start)*1000)
        statuses.append(response.status_code);sizes.append(len(response.content));counts.append(len(statements))
        if response.status_code != 200: break
        assert len(response.json()['items'])<=100
    report[name]={'median_ms':round(statistics.median(samples),2),'max_ms':round(max(samples),2),
                  'queries':max(counts),'response_bytes':max(sizes),'statuses':statuses}
start=time.perf_counter();folders=client.get(base+'/folder-metadata')
report['folders']={'ms':round((time.perf_counter()-start)*1000,2),'bytes':len(folders.content),'paths':len(folders.json()['paths'])}
def concurrent(index):
    ctx=client_for(f'performance-{index}@example.com')
    samples=[]
    for q in ('Large document 00001','Large document','not present'):
        start=time.perf_counter();r=ctx.get(base+'/browse',params={'q':q})
        samples.append({'ms':round((time.perf_counter()-start)*1000,2),'status':r.status_code})
    ctx.close();return samples
with ThreadPoolExecutor(max_workers=4) as pool:
    concurrent_samples=[s for group in pool.map(concurrent,range(4)) for s in group]
report['concurrent']={'max_ms':max(s['ms'] for s in concurrent_samples),'statuses':[s['status'] for s in concurrent_samples]}
print(json.dumps(report))
if '--assert-budgets' in sys.argv:
    for name in scenarios:
        assert report[name]['statuses']==[200]*3,(name,report[name])
        assert report[name]['max_ms']<1000,(name,report[name])
        assert report[name]['queries']<=30 and report[name]['response_bytes']<150000,(name,report[name])
    assert report['folders']['ms']<1000 and report['folders']['bytes']<250000,report['folders']
    assert all(s['status']==200 and s['ms']<3000 for s in concurrent_samples),report['concurrent']
