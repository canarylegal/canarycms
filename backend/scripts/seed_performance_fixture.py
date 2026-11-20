"""Synthetic scale fixture; refuses any populated/non-test database."""
import hashlib,json,os,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select,func
from app.db import engine,SessionLocal
from app.models import (User,UserRole,Case,CaseStatus,CaseLockMode,File,FileCategory,Contact,ContactType,
                        PortalFormTemplate,PortalFormSubmission,PortalFormSubmissionStatus)
from app.file_storage import FILES_ROOT

def guard():
    if (os.getenv('CANARY_PERFORMANCE_FIXTURE')!='1' or os.getenv('CANARY_TEST_FIXTURE')!='1'
            or engine.url.database!='canary_core_test'):
        raise RuntimeError('Performance fixtures require a dedicated core-test stack.')

def main():
    guard()
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Case))!=2 or db.scalar(select(func.count()).select_from(User))!=3:
            raise RuntimeError('Refusing to modify a populated database.')
        staff=db.scalar(select(User).where(User.email==os.environ['E2E_STAFF_EMAIL']))
        hot=db.scalar(select(Case).where(Case.case_number=='900001'))
        hot.lock_mode=CaseLockMode.none
        people=[]
        for i in range(200):
            person=User(email=f'performance-{i}@example.com', display_name=f'Synthetic Fee Earner {i:03}', initials=f'P{i:03}',
                        role=UserRole.user,is_active=True,password_hash=staff.password_hash,permission_category_id=staff.permission_category_id)
            db.add(person);people.append(person)
        db.flush()
        for i in range(5000):
            db.add(Case(case_number=f'PERF-{i:05}',title=f'Synthetic property transaction {i:05}',client_name=f'Synthetic Client {i:05}',
                        created_by=staff.id,fee_earner_user_id=people[i%200].id,status=CaseStatus.open,
                        lock_mode=CaseLockMode.none,matter_head_type_id=hot.matter_head_type_id,matter_sub_type_id=hot.matter_sub_type_id))
        templates=[];contacts=[]
        for i in range(5):
            template=PortalFormTemplate(name=f'Performance form {i}',reference=f'PERF-{i}',owner_id=staff.id)
            db.add(template);templates.append(template)
        for i in range(100):
            contact=Contact(type=ContactType.organisation,name=f'Synthetic Organisation {i}',company_name=f'Synthetic Organisation {i}')
            db.add(contact);contacts.append(contact)
        db.flush()
        folder=FILES_ROOT/'performance';folder.mkdir(parents=True,exist_ok=True)
        ids=[uuid.uuid4() for _ in range(1200)]
        for i in range(1200):
            body=(f'Synthetic performance document {i}\n'*40).encode()
            path=folder/f'{i}.txt';path.write_bytes(body)
            row=File(id=ids[i],case_id=hot.id,owner_id=staff.id,category=FileCategory.case_document,
                     storage_path=str(path.relative_to(FILES_ROOT)), original_filename=f'Performance document {i:04}.txt',
                     mime_type='text/plain',size_bytes=len(body),checksum=hashlib.sha256(body).hexdigest(),
                     folder_path='' if i<400 else f'Folder {i%20:02}/Section {i%5}',
                     parent_file_id=ids[i-1] if 200<=i<400 and i%2 else None,is_pinned=i<5)
            db.add(row)
        db.flush()
        for i in range(100):
            db.add(PortalFormSubmission(case_id=hot.id,template_id=templates[i%5].id,contact_id=contacts[i].id,
                    snapshot_file_id=ids[i],sent_by_user_id=staff.id,status=PortalFormSubmissionStatus.completed))
        db.commit()
    print(json.dumps({'matters':5002,'fee_earners':200,'hot_case_documents':1200,'portal_forms':100}))
if __name__=='__main__': main()
