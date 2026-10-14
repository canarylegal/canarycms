"""AcroForm extract/fill for Canary Sign — especially multi-state checkbox groups."""

from __future__ import annotations

import io

import pikepdf
import pytest

from app.canary_sign_pdf import (
    _resolve_button_target,
    _set_button_field_value,
    extract_acroform_fields,
    fill_acroform,
    fill_and_flatten_acroform,
)


def _appearance_xobject(pdf: pikepdf.Pdf, label: str) -> pikepdf.Stream:
    # Minimal empty form XObject used as an on-state appearance.
    return pikepdf.Stream(
        pdf,
        b"q Q",
        {
            "/Type": pikepdf.Name.XObject,
            "/Subtype": pikepdf.Name.Form,
            "/BBox": pikepdf.Array([0, 0, 18, 18]),
            "/Resources": pikepdf.Dictionary({}),
        },
    )


def _build_included_excluded_none_pdf() -> bytes:
    """One page, one field ``checkBox1`` with Included / Excluded / None kids."""
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(400, 400))
    kids = pikepdf.Array()
    states = [
        ("Included", 40),
        ("Excluded", 80),
        ("None", 120),
    ]
    parent = pikepdf.Dictionary(
        {
            "/FT": pikepdf.Name.Btn,
            "/T": "checkBox1",
            "/V": pikepdf.Name.Off,
            "/Kids": kids,
        }
    )
    parent_ref = pdf.make_indirect(parent)

    annots = pikepdf.Array()
    for state, x in states:
        on = _appearance_xobject(pdf, state)
        off = _appearance_xobject(pdf, "Off")
        kid = pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name.Annot,
                "/Subtype": pikepdf.Name.Widget,
                "/Parent": parent_ref,
                "/Rect": pikepdf.Array([x, 200, x + 18, 218]),
                "/AS": pikepdf.Name.Off,
                "/AP": pikepdf.Dictionary(
                    {
                        "/N": pikepdf.Dictionary(
                            {
                                f"/{state}": on,
                                "/Off": off,
                            }
                        )
                    }
                ),
            }
        )
        kid_ref = pdf.make_indirect(kid)
        kids.append(kid_ref)
        annots.append(kid_ref)

    page["/Annots"] = annots
    pdf.Root["/AcroForm"] = pikepdf.Dictionary(
        {
            "/Fields": pikepdf.Array([parent_ref]),
            "/NeedAppearances": True,
        }
    )
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_resolve_button_target_prefers_included_for_true() -> None:
    assert _resolve_button_target(True, ["Included", "Excluded", "None"]) == "Included"
    assert _resolve_button_target(False, ["Included", "Excluded", "None"]) is None
    assert _resolve_button_target("Excluded", ["Included", "Excluded", "None"]) == "Excluded"


def test_extract_expands_button_group_into_radio_widgets() -> None:
    raw = _build_included_excluded_none_pdf()
    fields = extract_acroform_fields(raw)
    group = [f for f in fields if f["name"] == "checkBox1"]
    assert len(group) == 3
    assert {f["export_value"] for f in group} == {"Included", "Excluded", "None"}
    assert all(f["field_type"] == "radio" for f in group)
    assert group[0]["options"] == ["Included", "Excluded", "None"]


def test_fill_sets_included_from_boolean_true() -> None:
    raw = _build_included_excluded_none_pdf()
    filled = fill_acroform(raw, {"checkBox1": True}, flatten=False)
    with pikepdf.open(io.BytesIO(filled)) as pdf:
        field = pdf.Root.AcroForm.Fields[0]
        assert str(field.V) == "/Included"
        ases = [str(k.AS) for k in field.Kids]
        assert ases.count("/Included") == 1
        assert ases.count("/Off") == 2


def test_fill_sets_excluded_from_string() -> None:
    raw = _build_included_excluded_none_pdf()
    filled = fill_acroform(raw, {"checkBox1": "Excluded"}, flatten=False)
    with pikepdf.open(io.BytesIO(filled)) as pdf:
        field = pdf.Root.AcroForm.Fields[0]
        assert str(field.V) == "/Excluded"
        ases = [str(k.AS) for k in field.Kids]
        assert "/Excluded" in ases
        assert ases.count("/Off") == 2


def test_fill_and_flatten_removes_widgets() -> None:
    raw = _build_included_excluded_none_pdf()
    flat = fill_and_flatten_acroform(raw, {"checkBox1": "Included"})
    with pikepdf.open(io.BytesIO(flat)) as pdf:
        # Flatten should drop interactive widgets; tolerate AcroForm remnant.
        page = pdf.pages[0]
        annots = page.get("/Annots")
        if annots is not None:
            for a in annots:
                subtype = str(a.get("/Subtype", ""))
                assert not subtype.endswith("Widget")


def _build_text_fields_pdf() -> bytes:
    """Tall multiline address, comb postcode, and short single-line comment."""
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(600, 800))
    annots = pikepdf.Array()
    fields = pikepdf.Array()

    def add_text(name: str, rect: list[float], *, ff: int, max_len: int | None = None, da: str = "/Helv 11 Tf 0 g"):
        d = {
            "/Type": pikepdf.Name.Annot,
            "/Subtype": pikepdf.Name.Widget,
            "/FT": pikepdf.Name.Tx,
            "/T": name,
            "/Rect": pikepdf.Array(rect),
            "/Ff": ff,
            "/DA": da,
            "/V": "",
        }
        if max_len is not None:
            d["/MaxLen"] = max_len
        ref = pdf.make_indirect(pikepdf.Dictionary(d))
        annots.append(ref)
        fields.append(ref)

    # Multiline (bit 13) + tall box
    add_text("propertyAddress", [50, 600, 400, 720], ff=4096)
    # Comb (bit 25) + MaxLen 8
    add_text("propertyPostcode", [50, 560, 200, 582], ff=1 << 24, max_len=8)
    # Narrow single-line comment
    add_text("comments1", [50, 520, 200, 542], ff=0, da="/Helv 9.5 Tf 0 g")

    page["/Annots"] = annots
    pdf.Root["/AcroForm"] = pikepdf.Dictionary(
        {
            "/Fields": fields,
            "/NeedAppearances": True,
            "/DR": pikepdf.Dictionary(
                {
                    "/Font": pikepdf.Dictionary(
                        {
                            "/Helv": pikepdf.Dictionary(
                                {
                                    "/Type": pikepdf.Name.Font,
                                    "/Subtype": pikepdf.Name.Type1,
                                    "/BaseFont": pikepdf.Name.Helvetica,
                                }
                            )
                        }
                    )
                }
            ),
        }
    )
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_extract_marks_tall_and_ff_multiline() -> None:
    raw = _build_text_fields_pdf()
    fields = {f["name"]: f for f in extract_acroform_fields(raw)}
    assert fields["propertyAddress"]["multiline"] is True
    assert fields["propertyPostcode"]["multiline"] is False
    assert fields["comments1"]["multiline"] is False


def test_fill_multiline_address_wraps_in_appearance() -> None:
    raw = _build_text_fields_pdf()
    addr = "12 High Street\nSomewhere Village\nNear Town"
    filled = fill_acroform(
        raw,
        {
            "propertyAddress": addr,
            "propertyPostcode": "AB12 3CD",
            "comments1": "This is a rather long comment that tends to clip in the field",
        },
        flatten=False,
    )
    with pikepdf.open(io.BytesIO(filled)) as pdf:
        by_name = {str(f.get("/T") or ""): f for f in pdf.Root.AcroForm.Fields}
        addr_ap = bytes(by_name["propertyAddress"].AP.N.read_bytes())
        assert b"High Street" in addr_ap
        assert b"Somewhere Village" in addr_ap
        # Must not keep literal \\n inside a single Tj string.
        assert b"High Street\\nSomewhere" not in addr_ap
        assert addr_ap.count(b"Tj") >= 2

        pc_ap = bytes(by_name["propertyPostcode"].AP.N.read_bytes())
        # Comb: one Tj per character (space included).
        assert pc_ap.count(b"Tj") >= 7

        comment_ap = bytes(by_name["comments1"].AP.N.read_bytes())
        # Font should have been shrunk below the original 9.5pt.
        assert b"9.5 Tf" not in comment_ap
        assert b"Tf" in comment_ap
