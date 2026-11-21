import uuid
from datetime import datetime, timezone
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Case, File, FileCategory, User
from app.document_pages import document_page, folder_metadata

@pytest.mark.parametrize('cursor', ['bad', 'W10=', 'e30=', 'bnVsbA=='])
def test_invalid_document_cursor(cursor):
    with pytest.raises(HTTPException) as exc: document_page(Mock(), uuid.uuid4(), cursor=cursor)
    assert exc.value.status_code == 400

@pytest.fixture
def documents(db):
    owner=db.scalar(select(User)); case=db.scalar(select(Case))
    folder='page-test-'+uuid.uuid4().hex
    def add(name, parent=None, **values):
        defaults=dict(id=uuid.uuid4(),case_id=case.id,owner_id=owner.id,category=FileCategory.case_document,
            storage_path='unused-test-path',original_filename=name,mime_type='text/plain',size_bytes=10,
            created_at=datetime(2026,1,1,tzinfo=timezone.utc),folder_path=folder,parent_file_id=parent)
        defaults.update(values);row=File(**defaults);db.add(row);db.flush();return row
    parent=add('Message.eml',is_pinned=True,source_mail_date=datetime(2020,1,1,tzinfo=timezone.utc))
    children=[add(f'Attachment {i:03}.txt',parent.id) for i in range(105)]
    ordinary=[add('same.txt') for _ in range(4)]
    marker=add('.folder',category=FileCategory.system,folder_path=folder+'/Empty')
    secret=add('hidden.txt',oo_compose_pending=True)
    return case.id,folder,parent,children,ordinary,add

def walk(db,case_id,**kwargs):
    rows=[];pins=[];cursor=None
    for _ in range(500):
        page,pinned,cursor=document_page(db,case_id,limit=17,cursor=cursor,**kwargs)
        assert len(page)<=17
        rows.extend(row[0] for row in page);pins.extend(pinned)
        if not cursor: return rows,pins
    pytest.fail('cursor did not terminate')

def test_group_spanning_pages_stays_contiguous_for_all_sorts(db,documents):
    case_id,folder,parent,children,ordinary,_=documents
    for sort in ('description','size','created','user'):
        for direction in ('asc','desc'):
            rows,pins=walk(db,case_id,folder=folder,sort=sort,direction=direction)
            assert len(rows)==len({row.id for row in rows})==110
            assert rows[0].id==parent.id
            assert {r.id for r in rows[1:106]}=={r.id for r in children}
            assert pins==[True]*106+[False]*4
            assert {r.id for r in rows[106:]}=={r.id for r in ordinary}

def test_child_search_expands_group_and_retains_empty_folder_counts(db,documents):
    case_id,folder,parent,children,ordinary,add=documents
    child=add('Literal %_ match.txt',parent.id,folder_path=folder+'/Elsewhere')
    rows,_=walk(db,case_id,folder=folder,q='Literal %_ match')
    assert {r.id for r in rows}=={parent.id,*[r.id for r in children]}
    assert walk(db,case_id,folder=folder,q='Literal XXX match')[0]==[]
    metadata=folder_metadata(db,case_id)
    assert folder+'/Empty' in metadata['paths']
    assert metadata['summaries'][folder]=='5 items, 1 subfolder'
    assert metadata['summaries'][folder+'/Empty']=='0 items, 0 subfolders'
    assert walk(db,case_id,folder=folder+'/Empty')[0]==[]

def test_boundary_deletion_insert_and_cursor_scope(db,documents):
    case_id,folder,parent,children,ordinary,add=documents
    first,_,cursor=document_page(db,case_id,folder=folder,sort='description',direction='asc',limit=10)
    boundary=first[-1][0];db.delete(boundary);db.flush()
    # New earlier root must not shift the continuation or duplicate existing IDs.
    add('A new parent.txt',is_pinned=True)
    rest=[]
    while cursor:
        page,_,cursor=document_page(db,case_id,folder=folder,sort='description',direction='asc',cursor=cursor,limit=10)
        rest.extend(r[0] for r in page)
    expected={parent.id,*[r.id for r in children],*[r.id for r in ordinary]}
    assert {r[0].id for r in first}|{r.id for r in rest}==expected
    assert len(first)+len(rest)==len(expected)
    _,_,cursor=document_page(db,case_id,folder=folder,limit=1)
    for params in ({'folder':folder+'/Other'}, {'folder':folder,'q':'different'}, {'folder':folder,'sort':'size'}):
        with pytest.raises(HTTPException): document_page(db,case_id,cursor=cursor,**params)
