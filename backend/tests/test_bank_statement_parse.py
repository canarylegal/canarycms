"""Unit tests for bank statement CSV/OFX parsing."""
from __future__ import annotations

from app.bank_recon_service import parse_statement_csv, parse_statement_ofx


def test_parse_statement_csv_amount_column() -> None:
    csv = b"Date,Description,Amount,Reference\n01/03/2026,Client receipt,1500.00,REF1\n02/03/2026,Search fee,-45.50,SRCH\n"
    rows = parse_statement_csv(csv)
    assert len(rows) == 2
    assert rows[0]["amount_pence"] == 150_000
    assert rows[1]["amount_pence"] == -4550
    assert rows[0]["reference"] == "REF1"


def test_parse_statement_csv_credit_debit() -> None:
    csv = b"Date,Narrative,Credit,Debit\n2026-03-01,In,100.00,\n2026-03-02,Out,,25.00\n"
    rows = parse_statement_csv(csv)
    assert rows[0]["amount_pence"] == 10_000
    assert rows[1]["amount_pence"] == -2500


def test_parse_ofx_minimal() -> None:
    ofx = b"""OFXHEADER:100
DATA:OFXSGML
<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKTRANLIST>
<STMTTRN>
<DTPOSTED>20260315
<TRNAMT>250.00
<FITID>1
<NAME>Deposit
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""
    rows = parse_statement_ofx(ofx)
    assert len(rows) == 1
    assert rows[0]["amount_pence"] == 25_000
    assert rows[0]["statement_date"].isoformat() == "2026-03-15"
