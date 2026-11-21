"""Operator-only, read-only financial diagnostics. Findings are never repair instructions.

Caller supplies a repeatable-read snapshot. UUIDs and integer pence are intentionally
used instead of client names, descriptions, bank details or raw audit payloads.
"""
from collections import Counter, defaultdict
from datetime import timezone
import json

from sqlalchemy import select
from app.models import (Case, CaseInvoice, CaseInvoiceLine, CaseInvoiceAllocation,
    InvoiceAllocationReversal, LedgerAccount, LedgerEntry, LedgerOperation,
    InterMatterJournal, AuditEvent, BankStatementImport, BankStatementLine,
    BankReconciliation, ClientAccountReconciliation)
from app.invoice_allocation_integrity import invoice_consistency


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _signed(entry):
    return entry.amount_pence if entry.direction.value == 'credit' else -entry.amount_pence


def validate_financial_data(db):
    """Current-state invariants plus evidence gaps and explicit reconciliation bridges.

    Linear in loaded financial rows, with the existing allocation validator reused
    per invoice. No locks, mutations, reconciliation approvals or balance repairs.
    """
    findings = []
    def finding(severity, code, entity, identity, **evidence):
        findings.append(dict(severity=severity, code=code, entity=entity, id=str(identity), evidence=evidence))
    def load(model):
        return list(db.scalars(select(model).order_by(model.id)))
    invoices = load(CaseInvoice)
    accounts = {a.id:a for a in load(LedgerAccount)}
    cases = {c.id:c for c in load(Case)}
    entries = load(LedgerEntry)
    pairs = defaultdict(list)
    for leg in entries: pairs[leg.pair_id].append(leg)
    allocations = load(CaseInvoiceAllocation)
    reversals = load(InvoiceAllocationReversal)
    reversed_ids = {r.allocation_id for r in reversals}
    invoice_map = {i.id:i for i in invoices}
    allocation_map = {a.id:a for a in allocations}
    lines = defaultdict(list)
    for line in load(CaseInvoiceLine):
        lines[line.invoice_id].append(line)
        if line.invoice_id not in invoice_map:
            finding('error','orphan_invoice_line','invoice_line',line.id)
    linked_pairs = defaultdict(list)
    for inv in invoices:
        for pair in (inv.ledger_pair_id,inv.reversal_pair_id):
            if pair: linked_pairs[pair].append(inv.id)
    coverage = Counter()
    audits = defaultdict(list)
    for action, identity, meta in db.execute(select(AuditEvent.action,AuditEvent.entity_id,AuditEvent.meta_json).where(
            AuditEvent.action.in_(['ledger.post','ledger.approve']),AuditEvent.entity_type=='ledger_pair')):
        try: data=json.loads(meta or '{}')
        except (ValueError,TypeError): data={}
        if action=='ledger.approve' or (isinstance(data,dict) and data.get('is_approved') is True):
            audits[identity].append(action)
    for pair, legs in pairs.items():
        accs=[accounts.get(e.account_id) for e in legs]
        if any(a is None for a in accs):
            finding('error','orphan_ledger_account','ledger_pair',pair); continue
        if (len(legs) not in (1,2) or len({a.case_id for a in accs})!=1
            or len({a.account_type for a in accs})!=len(legs)
            or len({e.amount_pence for e in legs})!=1
            or (len(legs)==2 and len({e.direction for e in legs})!=2)
            or len({(e.is_approved,e.is_anticipated) for e in legs})!=1):
            finding('error','invalid_posting_shape','ledger_pair',pair,leg_count=len(legs))
        if any(e.amount_pence<=0 for e in legs): finding('error','nonpositive_posting','ledger_pair',pair)
        if any(e.is_approved and e.is_anticipated for e in legs):
            finding('error','approved_anticipated_posting','ledger_pair',pair)
        if any(a.case_id not in cases for a in accs): finding('error','orphan_ledger_matter','ledger_pair',pair)
        if any(e.recognised_at and _utc(e.recognised_at)<_utc(e.posted_at) for e in legs):
            finding('error','recognition_before_posting','ledger_pair',pair)
        if any(e.is_approved and not e.is_anticipated for e in legs):
            if all(e.recognised_at for e in legs): coverage['recorded_recognition_pairs']+=1
            elif audits.get(str(pair)):
                coverage['legacy_pairs_with_audit_evidence']+=1
                if 'ledger.approve' in audits[str(pair)]:
                    finding('review','approval_time_recovery_available','ledger_pair',pair,
                            fallback='original_posting_date')
            else:
                coverage['legacy_pairs_without_approval_evidence']+=1
                finding('review','missing_approval_evidence','ledger_pair',pair,
                        fallback='original_posting_date',leg_count=len(legs))
    for pair, owners in linked_pairs.items():
        if len(owners)>1: finding('error','shared_invoice_posting','ledger_pair',pair,invoice_ids=list(map(str,owners)))
    for inv in invoices:
        total=sum(l.amount_pence+l.tax_pence for l in lines[inv.id])
        if total!=inv.total_pence:
            finding('error','invoice_line_total_mismatch','invoice',inv.id,stored_pence=inv.total_pence,lines_pence=total)
        if inv.total_pence<=0: finding('error','nonpositive_invoice_total','invoice',inv.id)
        if inv.case_id not in cases: finding('error','orphan_invoice_matter','invoice',inv.id)
        if inv.status not in ('approved','pending_approval','voided'): finding('error','unknown_invoice_status','invoice',inv.id)
        if (inv.status=='approved' or inv.reversal_pair_id) and not inv.approved_at:
            finding('review','missing_invoice_approval_time','invoice',inv.id)
        if inv.status=='voided' and not inv.voided_at: finding('review','missing_invoice_void_time','invoice',inv.id)
        if inv.approved_at and inv.voided_at and _utc(inv.voided_at)<_utc(inv.approved_at):
            finding('error','invoice_void_before_approval','invoice',inv.id)
        for issue in invoice_consistency(db,inv)['issues']:
            finding('error','allocation_'+issue['code'],'invoice',inv.id,**{k:v for k,v in issue.items() if k!='code'})
        expected=[]
        if inv.status in ('approved','pending_approval') or inv.approved_at:
            expected.append(('charge',inv.ledger_pair_id,'debit',inv.status!='pending_approval'))
        if inv.status=='voided' and inv.approved_at:
            expected.append(('void',inv.reversal_pair_id,'credit',True))
        for kind,pair,direction,approved in expected:
            legs=pairs.get(pair,[])
            valid=len(legs)==1
            if valid:
                leg=legs[0]; account=accounts.get(leg.account_id)
                valid=(account is not None and account.case_id==inv.case_id and account.account_type.value=='office'
                       and leg.direction.value==direction and leg.amount_pence==inv.total_pence
                       and leg.is_approved==approved and not leg.is_anticipated)
            if not valid: finding('error','invoice_posting_mismatch','invoice',inv.id,posting=kind,pair_id=str(pair) if pair else None)
    for allocation in allocations:
        inv=invoice_map.get(allocation.invoice_id)
        if inv is None: finding('error','orphan_allocation_invoice','allocation',allocation.id)
        elif inv.approved_at and _utc(allocation.allocated_at)<_utc(inv.approved_at):
            finding('error','allocation_before_approval','allocation',allocation.id)
        if allocation.amount_pence<=0: finding('error','nonpositive_historical_allocation','allocation',allocation.id)
        if allocation.ledger_pair_id not in pairs: finding('error','missing_allocation_receipt','allocation',allocation.id)
        elif inv and {accounts[e.account_id].case_id for e in pairs[allocation.ledger_pair_id] if e.account_id in accounts}!={inv.case_id}:
            finding('review' if allocation.id in reversed_ids else 'error','historical_cross_matter_allocation','allocation',allocation.id)
    for reversal in reversals:
        original=allocation_map.get(reversal.allocation_id)
        if original is None: finding('error','orphan_allocation_reversal','allocation_reversal',reversal.id)
        elif _utc(reversal.reversed_at)<_utc(original.allocated_at):
            finding('error','reversal_before_allocation','allocation_reversal',reversal.id)
    journals=load(InterMatterJournal)
    transfer_pairs={p for j in journals for p in (j.from_pair_id,j.to_pair_id)}
    for journal in journals:
        for pair,cid,direction in [(journal.from_pair_id,journal.from_case_id,'debit'),(journal.to_pair_id,journal.to_case_id,'credit')]:
            legs=pairs.get(pair,[])
            if not (len(legs)==1 and (a:=accounts.get(legs[0].account_id)) is not None
                and a.case_id==cid and a.account_type.value=='client' and legs[0].direction.value==direction
                and legs[0].amount_pence==journal.amount_pence and legs[0].firm_bank_account_id==journal.firm_bank_account_id
                and legs[0].is_approved and not legs[0].is_anticipated):
                finding('error','transfer_posting_mismatch','transfer',journal.id,pair_id=str(pair))
    operations=load(LedgerOperation)
    reversed_pairs={p for o in operations if o.kind=='reverse_posting' for p in (o.result_id,o.reverses_id)}
    journal_map={j.id:j for j in journals}
    for op in operations:
        if op.kind in ('posting','reverse_posting') and op.result_id not in pairs:
            finding('error','missing_operation_result','ledger_operation',op.id)
        if op.kind in ('transfer','reverse_transfer') and op.result_id not in journal_map:
            finding('error','missing_operation_result','ledger_operation',op.id)
        if op.kind=='reverse_transfer':
            original=journal_map.get(op.reverses_id); reverse=journal_map.get(op.result_id)
            if not original or not reverse or (reverse.from_case_id,reverse.to_case_id,reverse.amount_pence,reverse.firm_bank_account_id)!=(original.to_case_id,original.from_case_id,original.amount_pence,original.firm_bank_account_id):
                finding('error','transfer_reversal_mismatch','ledger_operation',op.id)
        if op.kind=='reverse_posting':
            before=pairs.get(op.reverses_id,[]); after=pairs.get(op.result_id,[])
            def signature(rows):
                return sorted((str(e.account_id),str(e.firm_bank_account_id),_signed(e)) for e in rows)
            inverse=sorted((str(e.account_id),str(e.firm_bank_account_id),-_signed(e)) for e in before)
            if not before or not after or signature(after)!=inverse or any(not e.is_approved or e.is_anticipated for e in after):
                finding('error','posting_reversal_mismatch','ledger_operation',op.id)
    imports={r.id:r for r in load(BankStatementImport)}
    statements=load(BankStatementLine)
    match_counts=Counter(s.matched_pair_id for s in statements if s.matched_pair_id)
    for line in statements:
        imported=imports.get(line.import_id)
        if imported is None or imported.firm_bank_account_id!=line.firm_bank_account_id:
            finding('error','statement_import_mismatch','statement_line',line.id)
        if not line.matched_pair_id: continue
        legs=[e for e in pairs.get(line.matched_pair_id,[]) if accounts.get(e.account_id) and accounts[e.account_id].account_type.value=='client']
        reasons=[]
        if len(legs)!=1: reasons.append('requires_one_client_leg')
        if line.ignored: reasons.append('ignored_line_is_matched')
        if match_counts[line.matched_pair_id]!=1: reasons.append('posting_matched_more_than_once')
        if line.matched_pair_id in transfer_pairs|reversed_pairs: reasons.append('internal_or_reversed_posting')
        if len(legs)==1:
            leg=legs[0]
            if not leg.is_approved or leg.is_anticipated: reasons.append('posting_not_actual_approved')
            if leg.amount_pence<=0: reasons.append('nonpositive_posting')
            if leg.firm_bank_account_id!=line.firm_bank_account_id: reasons.append('bank_account_mismatch')
            if _signed(leg)!=line.amount_pence: reasons.append('signed_amount_mismatch')
        if reasons: finding('error','invalid_bank_match','statement_line',line.id,
                            pair_id=str(line.matched_pair_id),reasons=reasons)
    import_counts=Counter(s.import_id for s in statements)
    for imp in imports.values():
        actual=import_counts[imp.id]
        if actual!=imp.line_count: finding('review','statement_import_count_mismatch','statement_import',imp.id,stored=imp.line_count,actual=actual)
    for rec in load(BankReconciliation):
        expected=rec.statement_balance_pence-rec.ledger_total_pence+rec.unpresented_total_pence-rec.unmatched_statement_total_pence
        if rec.difference_pence!=expected:
            finding('error','saved_bank_reconciliation_arithmetic','bank_reconciliation',rec.id,stored_pence=rec.difference_pence,expected_pence=expected)
    for rec in load(ClientAccountReconciliation):
        expected=rec.bank_statement_balance_pence-rec.ledger_client_total_pence
        if rec.difference_pence!=expected:
            finding('error','saved_client_reconciliation_arithmetic','client_reconciliation',rec.id,stored_pence=rec.difference_pence,expected_pence=expected)
    active=[e for e in entries if e.is_approved and not e.is_anticipated and e.account_id in accounts]
    client_by_case=defaultdict(int)
    client_by_bank=defaultdict(int)
    for leg in active:
        account=accounts[leg.account_id]
        if account.account_type.value=='client':
            client_by_case[account.case_id]+=_signed(leg)
            client_by_bank[(account.case_id,leg.firm_bank_account_id)]+=_signed(leg)
    for cid,amount in client_by_case.items():
        if amount<0: finding('error','negative_client_matter_balance','matter',cid,balance_pence=amount)
    for (cid,bank),amount in client_by_bank.items():
        if amount<0: finding('error','negative_client_bank_balance','matter',cid,bank_id=str(bank) if bank else None,balance_pence=amount)
    client=sum(_signed(e) for e in active if accounts[e.account_id].account_type.value=='client')
    office=sum(_signed(e) for e in active if accounts[e.account_id].account_type.value=='office')
    invoice_office=sum(_signed(e) for e in active if accounts[e.account_id].account_type.value=='office' and e.pair_id in linked_pairs)
    approved_total=sum(i.total_pence for i in invoices if i.status=='approved')
    allocated=sum(a.amount_pence for a in allocations if a.id not in reversed_ids and a.invoice_id in invoice_map and invoice_map[a.invoice_id].status=='approved')
    bridge=dict(client_balance_pence=client,office_balance_pence=office,invoice_linked_office_pence=invoice_office,
        other_office_postings_pence=office-invoice_office,approved_invoice_total_pence=approved_total,
        active_allocations_to_approved_invoices_pence=allocated,outstanding_invoice_pence=approved_total-allocated,
        pending_invoice_total_pence=sum(i.total_pence for i in invoices if i.status=='pending_approval'))
    findings.sort(key=lambda f:(f['severity'],f['code'],f['entity'],f['id'],json.dumps(f['evidence'],sort_keys=True)))
    counts=Counter(f['severity'] for f in findings)
    return dict(schema_version=1,status='errors' if counts['error'] else 'review_required' if counts['review'] else 'clear',
        counts=dict(invoices=len(invoices),ledger_entries=len(entries),ledger_pairs=len(pairs),allocations=len(allocations),statement_lines=len(statements)),
        summary=dict(errors=counts['error'],reviews=counts['review'],by_code=dict(sorted(Counter(f['code'] for f in findings).items()))),
        recognition_coverage=dict(sorted(coverage.items())),reconciliation=bridge,findings=findings,
        limitations=['Current-state diagnostics, not certification of historical completeness.',
          'Saved reconciliation arithmetic is checked without treating later activity as corruption.',
          'Office cash, outstanding invoices and draft billing measure different things; use the reconciliation bridge.',
          'Missing audit evidence requires review, not an invented approval date.'])
