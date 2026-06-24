"""Tests for letter salutation resolution."""

from __future__ import annotations

from types import SimpleNamespace

from app.letter_salutation import (
    join_informal_first_names,
    primary_client_letter_dear_line,
    resolve_letter_dear_line,
    resolve_letter_sign_off,
)


def _person(**kwargs: object) -> SimpleNamespace:
    base = {
        "type": SimpleNamespace(value="person"),
        "matter_contact_type": "client",
        "first_name": "Sarah",
        "last_name": "Smith",
        "title": "Mrs",
        "name": "Mrs Sarah Smith",
        "letter_salutation": None,
        "letter_salutation_custom": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _org(**kwargs: object) -> SimpleNamespace:
    base = {
        "type": SimpleNamespace(value="organisation"),
        "matter_contact_type": "lawyers",
        "trading_name": "Ashbourne and Finch",
        "company_name": "Ashbourne and Finch Ltd",
        "name": "Ashbourne and Finch",
        "letter_salutation": None,
        "letter_salutation_custom": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_join_informal_first_names_two() -> None:
    contacts = [_person(first_name="Sarah"), _person(first_name="John")]
    assert join_informal_first_names(contacts) == "Sarah and John"


def test_join_informal_first_names_three() -> None:
    contacts = [
        _person(first_name="Sarah"),
        _person(first_name="John"),
        _person(first_name="Leslie"),
    ]
    assert join_informal_first_names(contacts) == "Sarah, John and Leslie"


def test_client_person_informal_default() -> None:
    assert resolve_letter_dear_line(_person()) == "Dear Sarah,"


def test_client_person_formal() -> None:
    contact = _person(letter_salutation="dear_first_name_formal")
    assert resolve_letter_dear_line(contact) == "Dear Mrs Smith,"


def test_non_client_person_sir_madam_default() -> None:
    contact = _person(matter_contact_type="lawyers")
    assert resolve_letter_dear_line(contact) == "Dear Sir / Madam,"


def test_organisation_sirs() -> None:
    contact = _org(letter_salutation="dear_sirs")
    assert resolve_letter_dear_line(contact) == "Dear Sirs,"


def test_organisation_firm_name() -> None:
    contact = _org(letter_salutation="dear_firm_name")
    assert resolve_letter_dear_line(contact) == "Dear Ashbourne and Finch,"


def test_custom_salutation() -> None:
    contact = _person(letter_salutation="custom", letter_salutation_custom="Colin and family")
    assert resolve_letter_dear_line(contact) == "Dear Colin and family,"


def test_primary_client_merge_all_informal() -> None:
    clients = [_person(first_name="Sarah"), _person(first_name="John")]
    assert primary_client_letter_dear_line(clients) == "Dear Sarah and John,"


def test_merge_all_clients_fills_contact_letter_dear() -> None:
    from types import SimpleNamespace

    from app.docx_util import build_merge_fields

    case = SimpleNamespace(title="Sale", case_number="123")
    clients = [_person(first_name="Sarah"), _person(first_name="John")]
    fields = build_merge_fields(
        case,
        merge_all_clients=True,
        ordered_client_contacts=clients,
    )
    assert fields["[CONTACT_LETTER_DEAR]"] == "Dear Sarah and John,"
    assert fields["[PRIMARY_CLIENT_LETTER_DEAR]"] == "Dear Sarah and John,"
    assert fields["[CONTACT_LETTER_SIGN_OFF]"] == "Yours sincerely,"


def test_non_client_person_sir_or_madam() -> None:
    contact = _person(matter_contact_type="lawyers", letter_salutation="dear_sir_or_madam")
    assert resolve_letter_dear_line(contact) == "Dear Sir or Madam,"


def test_sign_off_faithfully_for_sir_madam() -> None:
    contact = _person(matter_contact_type="lawyers")
    assert resolve_letter_sign_off(contact) == "Yours faithfully,"


def test_sign_off_faithfully_for_sir_or_madam() -> None:
    contact = _person(matter_contact_type="lawyers", letter_salutation="dear_sir_or_madam")
    assert resolve_letter_sign_off(contact) == "Yours faithfully,"


def test_sign_off_faithfully_for_sirs() -> None:
    contact = _org(letter_salutation="dear_sirs")
    assert resolve_letter_sign_off(contact) == "Yours faithfully,"


def test_sign_off_sincerely_for_client() -> None:
    assert resolve_letter_sign_off(_person()) == "Yours sincerely,"


def test_sign_off_sincerely_for_firm_name() -> None:
    contact = _org(letter_salutation="dear_firm_name")
    assert resolve_letter_sign_off(contact) == "Yours sincerely,"


def test_sign_off_sincerely_for_custom() -> None:
    contact = _person(letter_salutation="custom", letter_salutation_custom="Colin")
    assert resolve_letter_sign_off(contact) == "Yours sincerely,"
