"""Create minimal Word (.docx) files for case compose flows."""

from __future__ import annotations

from ._text import (
    _s_str,
    _initial_letter,
)

from .merge_fields import (
    PRECEDENT_CODES,
    IMAGE_PRECEDENT_CODES,
    _ADDITIONAL_CLIENT_NAME_CODES,
    _LAWYER_ROW_NAME_CODES,
    _empty_precedent_field_map,
    build_merge_fields,
    property_merge_fields,
    _core_name_company_for_contact,
    _org_and_address_block,
)

from .ooxml_merge import (
    validate_docx_package_bytes,
    is_invalid_ooxml_merge_exception,
    _MergeTextSegment,
    _parse_modifier_letters,
    _replace_merge_tokens_to_segments,
    _replace_merge_tokens_in_ooxml_text,
    _segments_plain_text,
    replace_word_mergefields_in_docx_bytes,
    merge_precedent_codes,
    fee_earner_signature_image_path,
    SIGNATURE_SCALE_DEFAULT,
    SIGNATURE_WIDTH_INCHES_AT_DEFAULT_SCALE,
    signature_width_inches_from_scale,
    fee_earner_signature_for_merge,
    inject_merge_code_images,
)

from .letterhead import (
    precedent_is_standalone_letter,
    splice_precedent_into_blank_letter,
    extract_letterhead_body_masthead_elements,
    extract_letterhead_body_masthead_elements_for_document,
    reapply_letterhead_layout_package_bytes,
    apply_digital_letterhead_headers_footers,
)

from .quote_table import (
    PRECEDENT_BODY_MARKER,
    QUOTE_FEE_TABLE_MARKER,
    QUOTE_TABLE_MARKERS,
    QUOTE_MERGE_SLOT_COUNT,
    INVOICE_MERGE_SLOT_COUNT,
    COMPLETION_MERGE_SLOT_COUNT,
    insert_xlsx_grid_table_at_marker,
    format_gbp_pence,
    insert_quote_fee_table_at_marker,
    strip_precedent_body_marker,
    _docx_set_table_width_pct,
    apply_quote_table_presentation,
    strip_empty_quote_table_rows,
    write_quote_template_docx,
    write_quote_template_docx_bytes,
)

from .invoice_docx import (
    invoice_line_merge_fields,
    strip_empty_invoice_table_rows,
    write_invoice_docx,
)

from .completion import (
    finance_item_completion_rows,
    completion_line_merge_fields,
    strip_empty_completion_table_rows,
    write_completion_statement_docx,
)

from .proofing import (
    ensure_docx_proofing_language_en_gb_bytes,
    normalize_onlyoffice_persisted_docx_bytes,
    finalize_stored_docx_bytes,
    write_blank_docx,
    write_blank_email_precedent_docx,
    write_quote_email_precedent_docx,
    extract_plain_text_from_docx_bytes,
    write_client_account_reconcile_report_docx,
)

__all__ = [
    '_s_str',
    '_initial_letter',
    'PRECEDENT_CODES',
    'IMAGE_PRECEDENT_CODES',
    '_ADDITIONAL_CLIENT_NAME_CODES',
    '_LAWYER_ROW_NAME_CODES',
    '_empty_precedent_field_map',
    'build_merge_fields',
    'property_merge_fields',
    '_core_name_company_for_contact',
    '_org_and_address_block',
    'validate_docx_package_bytes',
    'is_invalid_ooxml_merge_exception',
    '_MergeTextSegment',
    '_parse_modifier_letters',
    '_replace_merge_tokens_to_segments',
    '_replace_merge_tokens_in_ooxml_text',
    '_segments_plain_text',
    'replace_word_mergefields_in_docx_bytes',
    'merge_precedent_codes',
    'fee_earner_signature_image_path',
    'SIGNATURE_SCALE_DEFAULT',
    'SIGNATURE_WIDTH_INCHES_AT_DEFAULT_SCALE',
    'signature_width_inches_from_scale',
    'fee_earner_signature_for_merge',
    'inject_merge_code_images',
    'precedent_is_standalone_letter',
    'splice_precedent_into_blank_letter',
    'extract_letterhead_body_masthead_elements',
    'extract_letterhead_body_masthead_elements_for_document',
    'reapply_letterhead_layout_package_bytes',
    'apply_digital_letterhead_headers_footers',
    'PRECEDENT_BODY_MARKER',
    'QUOTE_FEE_TABLE_MARKER',
    'QUOTE_TABLE_MARKERS',
    'QUOTE_MERGE_SLOT_COUNT',
    'INVOICE_MERGE_SLOT_COUNT',
    'COMPLETION_MERGE_SLOT_COUNT',
    'insert_xlsx_grid_table_at_marker',
    'format_gbp_pence',
    'insert_quote_fee_table_at_marker',
    'strip_precedent_body_marker',
    '_docx_set_table_width_pct',
    'apply_quote_table_presentation',
    'strip_empty_quote_table_rows',
    'write_quote_template_docx',
    'write_quote_template_docx_bytes',
    'invoice_line_merge_fields',
    'strip_empty_invoice_table_rows',
    'write_invoice_docx',
    'finance_item_completion_rows',
    'completion_line_merge_fields',
    'strip_empty_completion_table_rows',
    'write_completion_statement_docx',
    'ensure_docx_proofing_language_en_gb_bytes',
    'normalize_onlyoffice_persisted_docx_bytes',
    'finalize_stored_docx_bytes',
    'write_blank_docx',
    'write_blank_email_precedent_docx',
    'write_quote_email_precedent_docx',
    'extract_plain_text_from_docx_bytes',
    'write_client_account_reconcile_report_docx',
]
