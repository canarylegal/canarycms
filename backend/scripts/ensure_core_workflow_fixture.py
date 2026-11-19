#!/usr/bin/env python3
"""Seed ONLY a dedicated, disposable *_core_test PostgreSQL database."""
from __future__ import annotations
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, func
from app.db import SessionLocal, engine
from app.models import Case, CaseLockMode, CaseStatus, User, UserRole, UserPermissionCategory
from app.models import MatterHeadType, MatterSubType, MatterSubTypeMenu
from app.security import hash_password


def main():
    if os.getenv('CANARY_TEST_FIXTURE') != '1' or not (engine.url.database or '').endswith('_core_test'):
        raise RuntimeError('Refusing to seed: require CANARY_TEST_FIXTURE=1 and a dedicated *_core_test database.')
    credentials = [
        ('E2E_STAFF', 'Workflow Fee Earner', 'WFE', False),
        ('E2E_APPROVER', 'Workflow Approver', 'WAP', True),
        ('E2E_DENIED', 'Workflow Restricted User', 'WRU', False),
    ]
    with SessionLocal() as db:
        expected = {os.environ[prefix + '_EMAIL'] for prefix, *_ in credentials}
        existing = set(db.scalars(select(User.email)))
        if existing:
            if existing == expected and db.scalar(select(func.count()).select_from(Case)) == 2:
                print('Core workflow fixture already present.')
                return
            raise RuntimeError('Refusing to modify a populated database; recreate the disposable test stack.')
        staff_category = UserPermissionCategory(name='Core test poster', perm_fee_earner=True,
                                               perm_post_anticipated=True)
        db.add(staff_category); db.flush()
        users = []
        for prefix, name, initials, admin in credentials:
            email = os.environ[prefix + '_EMAIL']
            if not email.endswith('@example.com'):
                raise RuntimeError('Fixture accounts must use example.com.')
            user = User(email=email, password_hash=hash_password(os.environ[prefix + '_PASSWORD']),
                        display_name=name, initials=initials, role=UserRole.admin if admin else UserRole.user,
                        permission_category_id=staff_category.id, is_active=True)
            db.add(user); db.flush(); users.append(user)
        staff, approver, _ = users
        head = MatterHeadType(name='CI workflow matters')
        db.add(head); db.flush()
        subtype = MatterSubType(head_type_id=head.id, name='CI workflow subtype')
        db.add(subtype); db.flush()
        db.add(MatterSubTypeMenu(sub_type_id=subtype.id, name='Tasks'))
        for number, title, owner in [('900001', 'CI Core Workflows', staff), ('900002', 'CI Restricted Matter', approver)]:
            db.add(Case(case_number=number, title=title, client_name='Synthetic test client',
                        fee_earner_user_id=owner.id, created_by=owner.id, status=CaseStatus.open,
                        matter_head_type_id=head.id, matter_sub_type_id=subtype.id,
                        lock_mode=CaseLockMode.allow_list))
        db.commit()
    print('Created synthetic staff, approver, restricted user and two test matters.')


if __name__ == '__main__':
    main()
