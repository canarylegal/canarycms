import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, event
from app import historical_corrections as service
from app.models import AuditEvent, BankReconciliation, LedgerEntry, UserRole
from tests.test_bank_integrity import fixture as bank_fixture, PERIOD


def fixture(db=None):
    db, user, _, bank, _, _, line, leg = bank_fixture(db)
    line.matched_pair_id = uuid.uuid4()
    line.matched_at = datetime.now(timezone.utc)
    line.matched_by_user_id = user.id
    db.commit()
    return db, user, bank, line, leg


def apply(db, user, plan, **kw):
    return service.apply_unmatch(db, plan=plan, actor_id=user.id,
        reason=kw.get('reason', 'Reviewed missing historical posting'), approved_hash=kw.get('approved_hash',plan['plan_hash']))


def test_preview_is_select_only_and_deterministic():
    db, _, _, line, _ = fixture()
    sql=[]
    def capture(_conn,_cursor,statement,*_args): sql.append(statement)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        first=service.preview_unmatch(db,line.id)
        assert service.preview_unmatch(db,line.id)==first
        assert first['blockers']==[] and first['ledger_effect']=='none'
        assert not db.dirty and not db.new
        assert all(s.lstrip().upper().startswith('SELECT') for s in sql)
    finally:
        event.remove(db.bind,'before_cursor_execute',capture)
        db.close()


def test_apply_receipt_retry_and_later_change_do_not_repeat_mutation():
    db,user,_,line,_=fixture()
    plan=service.preview_unmatch(db,line.id)
    first=apply(db,user,plan);db.commit()
    assert first['status']=='applied' and line.matched_pair_id is None and line.version==1
    assert apply(db,user,plan)['status']=='already_applied'
    line.ignored=True;line.version+=1;db.commit()
    assert apply(db,user,plan)['status']=='already_applied'
    assert line.ignored and line.version==2
    events=list(db.scalars(select(AuditEvent).where(AuditEvent.action==service.ACTION)))
    assert len(events)==1
    meta=json.loads(events[0].meta_json)
    assert meta['before']['matched_pair_id']==plan['before']['matched_pair_id']
    assert meta['after']['matched_pair_id'] is None and meta['reason']
    db.close()


@pytest.mark.parametrize('damage',['amount','version','description','restored_posting','closed_period','tamper','wrong_hash'])
def test_stale_or_changed_evidence_cannot_be_applied(damage):
    db,user,bank,line,leg=fixture()
    plan=service.preview_unmatch(db,line.id)
    if damage=='amount':line.amount_pence+=1
    elif damage=='version':line.version+=1
    elif damage=='description':line.description='Changed source evidence'
    elif damage=='restored_posting':leg.pair_id=line.matched_pair_id
    elif damage=='closed_period':
        db.add(BankReconciliation(firm_bank_account_id=bank.id,period_end_date=PERIOD,
            statement_balance_pence=0,status='approved',prepared_by_user_id=user.id))
    elif damage=='tamper':plan['after']['ignored']=True
    db.commit();original=line.matched_pair_id
    with pytest.raises(HTTPException) as error:
        apply(db,user,plan,approved_hash='incorrect' if damage=='wrong_hash' else plan['plan_hash'])
    assert error.value.status_code==409
    db.rollback();assert line.matched_pair_id==original
    db.close()


@pytest.mark.parametrize('state',['inactive','non_admin','reason'])
def test_apply_requires_active_admin_and_review_reason(state):
    db,user,_,line,_=fixture();plan=service.preview_unmatch(db,line.id)
    if state=='inactive':user.is_active=False
    if state=='non_admin':user.role=UserRole.user
    db.commit()
    with pytest.raises(HTTPException):apply(db,user,plan,reason='' if state=='reason' else 'Reviewed correction')
    db.rollback();assert line.matched_pair_id
    db.close()


def test_audit_failure_rolls_back_entire_correction_and_allows_retry():
    db,user,_,line,_=fixture();plan=service.preview_unmatch(db,line.id)
    with patch.object(service,'log_event',side_effect=RuntimeError('Injected audit failure')):
        with pytest.raises(RuntimeError):apply(db,user,plan)
        db.rollback()
    assert line.matched_pair_id and line.version==0
    assert db.scalar(select(func.count()).select_from(AuditEvent))==0
    assert apply(db,user,plan)['status']=='applied';db.commit();db.close()


def test_existing_posting_is_blocked_even_with_fresh_preview():
    db,user,_,line,leg=fixture();line.matched_pair_id=leg.pair_id;db.commit()
    plan=service.preview_unmatch(db,line.id)
    assert 'posting_exists_requires_separate_review' in plan['blockers']
    with pytest.raises(HTTPException):apply(db,user,plan)
    db.rollback();db.close()


def test_investigation_preserves_evidence_without_inventing_dates():
    db,_,_,line,leg=fixture();leg.recognised_at=None;db.commit()
    db.add(AuditEvent(action='legacy.import',entity_id=str(uuid.uuid4()),meta_json=json.dumps({'pairs':[str(leg.pair_id)]})));db.commit()
    before=service.investigate_history(db)
    assert before==service.investigate_history(db)
    assert before['approval_evidence'][0]['legs'][0]['recognised_at'] is None
    assert before['approval_evidence'][0]['metadata_reference_events'][0]['action']=='legacy.import'
    assert before['bank_matches'][0]['preview']['line_id']==str(line.id)
    assert 'Synthetic statement' not in json.dumps(before)
    assert not db.dirty and not db.new
    db.close()


def test_cli_commit_failure_has_no_success_output(capsys,tmp_path):
    from scripts import historical_financial_review as cli
    from unittest.mock import MagicMock
    session=MagicMock();session.get_bind.return_value.dialect.name='postgresql'
    session.commit.side_effect=RuntimeError('commit failed')
    manager=MagicMock();manager.__enter__.return_value=session
    plan=tmp_path/'plan.json';plan.write_text('{}')
    with patch.object(cli,'SessionLocal',return_value=manager),patch.object(cli,'apply_unmatch',return_value={'status':'applied'}):
        assert cli.main(['apply-unmatch','--plan',str(plan),'--actor-id',str(uuid.uuid4()),
                         '--reason','Reviewed correction','--approve-plan-hash','hash'])==3
    output=capsys.readouterr();assert not output.out and 'failed' in output.err
