from datetime import datetime, timezone
from unittest.mock import Mock
import uuid

from app.models import Contact, PortalFormTemplate, PortalFormSubmission, PortalFormSubmissionStatus
from app.portal_form_service import form_submission_file_list_item, form_submission_file_list_items


def test_batch_metadata_preserves_single_item_payloads_and_missing_reference_fallbacks():
    contact=Contact(id=uuid.uuid4(),name='  Synthetic Client  ')
    template=PortalFormTemplate(id=uuid.uuid4(),name='Client information')
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    submissions=[PortalFormSubmission(id=uuid.uuid4(),contact_id=contact.id,template_id=template.id,
                 status=status,sent_at=now,completed_at=now if status==PortalFormSubmissionStatus.completed else None)
                 for status in PortalFormSubmissionStatus]
    submissions.append(PortalFormSubmission(id=uuid.uuid4(),contact_id=uuid.uuid4(),template_id=uuid.uuid4(),
                      status=PortalFormSubmissionStatus.pending,sent_at=now))
    db=Mock()
    db.scalars.side_effect=[[contact],[template]]
    db.get.side_effect=lambda model,key: contact if model is Contact and key==contact.id else template if model is PortalFormTemplate and key==template.id else None
    expected={s.id:form_submission_file_list_item(db,s) for s in submissions}
    assert form_submission_file_list_items(db,submissions)==expected
    assert expected[submissions[-1].id]['contact_name']=='Contact'
    assert expected[submissions[-1].id]['template_name']==''


def test_empty_form_list_does_not_issue_queries():
    db=Mock()
    assert form_submission_file_list_items(db,[])=={}
    db.scalars.assert_not_called()
