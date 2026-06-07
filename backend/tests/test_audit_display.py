from app.audit_display import extract_case_id, format_audit_summary, parse_audit_meta


def test_parse_audit_meta_invalid_json() -> None:
    assert parse_audit_meta("{not json") == {"_raw": "{not json"}


def test_extract_case_id_from_meta() -> None:
    assert (
        extract_case_id(
            entity_type="file",
            entity_id="f1",
            meta={"case_id": "abc-123"},
        )
        == "abc-123"
    )


def test_extract_case_id_from_entity() -> None:
    assert (
        extract_case_id(
            entity_type="case",
            entity_id="case-1",
            meta=None,
        )
        == "case-1"
    )


def test_format_file_rename_summary() -> None:
    summary = format_audit_summary(
        action="case.file.rename",
        entity_type="file",
        entity_id="f1",
        meta={"old_filename": "Old.docx", "new_filename": "New.docx"},
    )
    assert summary == 'Renamed file "Old.docx" to "New.docx"'


def test_format_file_delete_summary() -> None:
    summary = format_audit_summary(
        action="case.file.delete",
        entity_type="file",
        entity_id="f1",
        meta={"filename": "Letter.pdf"},
    )
    assert summary == 'Deleted file "Letter.pdf"'


def test_format_file_rename_legacy_meta() -> None:
    summary = format_audit_summary(
        action="case.file.rename",
        entity_type="file",
        entity_id="f1",
        meta={"filename": "OnlyNew.docx"},
    )
    assert summary == 'Renamed file to "OnlyNew.docx"'
