"""Unit tests for Law Society TA6/TA7/TA10 AcroForm prefill mapping."""

from __future__ import annotations

from app.ta_protocol_pdf_merge import (
    acroform_values_for_ta_reference,
    join_seller_names,
    seller_names_from_merge_fields,
    split_address_and_postcode,
)


def test_join_seller_names() -> None:
    assert join_seller_names([]) == ""
    assert join_seller_names(["Ada Lovelace"]) == "Ada Lovelace"
    assert join_seller_names(["Ada Lovelace", "Charles Babbage"]) == "Ada Lovelace and Charles Babbage"
    assert (
        join_seller_names(["Ada", "Charles", "Michael"])
        == "Ada, Charles and Michael"
    )


def test_split_address_and_postcode() -> None:
    addr, pc = split_address_and_postcode("12 High Street\nAnytown\nAB1 2CD")
    assert addr == "12 High Street\nAnytown"
    assert pc == "AB1 2CD"

    addr2, pc2 = split_address_and_postcode("", "12 High Street, Anytown, AB12CD")
    assert "High Street" in addr2
    assert pc2 == "AB1 2CD"


def test_ta6_mapping_includes_sellers_property_and_solicitors() -> None:
    fields = {
        "[PRIMARY_CLIENT_NAME]": "Ada Lovelace",
        "[TITLE_2]": "Mr",
        "[FIRST_NAME_2]": "Charles",
        "[LAST_NAME_2]": "Babbage",
        "[PROPERTY_ADDRESS_BLOCK]": "1 Binary Lane\nCambridge\nCB1 1AA",
        "[PROPERTY_ADDRESS]": "1 Binary Lane, Cambridge, CB1 1AA",
        "[FIRM_TRADING_NAME]": "Example Firm LLP",
        "[FIRM_ADDRESS_BLOCK]": "10 Legal Street\nLondon\nEC1A 1BB",
        "[FIRM_POSTCODE]": "EC1A 1BB",
        "[FEE_EARNER]": "Sam Solicitor",
        "[CASE_REF]": "000001",
    }
    values = acroform_values_for_ta_reference("TA6", fields, fee_earner_email="sam@example.com")
    assert values["Full name of the sellers 1"] == "Ada Lovelace and Mr Charles Babbage"
    assert values["Address"] == "1 Binary Lane\nCambridge"
    assert values["Postcode 1"] == "CB1 1AA"
    assert values["Name of the seller's solicitor's firm"] == "Example Firm LLP"
    assert values["Seller's solicitor address"] == "10 Legal Street\nLondon"
    assert values["Seller's solicitor address postcode 1"] == "EC1A 1BB"
    assert values["Seller's solicitor contact name"] == "Sam Solicitor"
    assert values["Seller's solicitor email"] == "sam@example.com"
    assert values["Seller's solicitor reference number"] == "000001"
    assert values["Role - seller"] is True


def test_ta7_and_ta10_mapping() -> None:
    fields = {
        "[PRIMARY_CLIENT_NAME]": "Ada Lovelace",
        "[PROPERTY_ADDRESS_BLOCK]": "1 Binary Lane\nCambridge\nCB1 1AA",
        "[PROPERTY_ADDRESS]": "1 Binary Lane, Cambridge, CB1 1AA",
        "[FIRM_TRADING_NAME]": "Example Firm LLP",
        "[FIRM_ADDRESS_BLOCK]": "10 Legal Street\nLondon\nEC1A 1BB",
        "[FIRM_POSTCODE]": "EC1A 1BB",
        "[CASE_REF]": "000001",
    }
    ta7 = acroform_values_for_ta_reference("TA7", fields)
    assert ta7["Full name(s) of the seller(s)"] == "Ada Lovelace"
    assert "Name of the seller's solicitor's firm" not in ta7

    ta10 = acroform_values_for_ta_reference("TA10", fields, fee_earner_email="sam@example.com")
    assert ta10["sellerFullName"] == "Ada Lovelace"
    assert ta10["firmName"] == "Example Firm LLP"
    assert ta10["matterReference"] == "000001"
    assert ta10["mailFirmorPA"] == "sam@example.com"


def test_seller_names_from_merge_fields_primary_only() -> None:
    assert seller_names_from_merge_fields({"[PRIMARY_CLIENT_NAME]": "Ada"}) == "Ada"
