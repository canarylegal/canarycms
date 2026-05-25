"""Build matter description from Admin pre-fix + UK address (matches frontend propertyMatterHelpers)."""

from __future__ import annotations

import random

STREET_NAMES = (
    "High Street",
    "Church Lane",
    "Station Road",
    "Victoria Road",
    "Mill Lane",
    "Park Avenue",
    "Manor Close",
    "Greenway",
    "Oakfield Drive",
    "Kingsway",
)
TOWNS = (
    "Manchester",
    "Leeds",
    "Bristol",
    "Cardiff",
    "Edinburgh",
    "Glasgow",
    "Birmingham",
    "Newcastle upon Tyne",
    "Sheffield",
    "Nottingham",
    "Oxford",
    "Cambridge",
    "Brighton",
    "Bath",
    "York",
)
COUNTIES = (
    "Greater Manchester",
    "West Yorkshire",
    "City of Bristol",
    "South Glamorgan",
    "Midlothian",
    "Lanarkshire",
    "West Midlands",
    "Tyne and Wear",
    "South Yorkshire",
    "Nottinghamshire",
    "Oxfordshire",
    "Cambridgeshire",
    "East Sussex",
    "Somerset",
    "North Yorkshire",
)
POSTCODE_OUTWARD = (
    "M1",
    "LS1",
    "BS1",
    "CF10",
    "EH1",
    "G1",
    "B1",
    "NE1",
    "S1",
    "NG1",
    "OX1",
    "CB1",
    "BN1",
    "BA1",
    "YO1",
)


def random_uk_address_lines() -> list[str]:
    n = random.randint(1, 999)
    street = random.choice(STREET_NAMES)
    town = random.choice(TOWNS)
    county = random.choice(COUNTIES)
    outward = random.choice(POSTCODE_OUTWARD)
    inward = f"{random.randint(1, 9)}{random.choice('ABCDEFGHJKLMNPQRSTUVWXY')}{random.choice('ABCDEFGHJKLMNPQRSTUVWXY')}"
    lines = [
        f"{n} {street}",
        town,
        county,
        f"{outward} {inward}",
        "United Kingdom",
    ]
    if random.random() < 0.35:
        lines.insert(1, random.choice(("Flat 2", "Apartment 4", "Unit 7", "First Floor")))
    return lines


def join_address_lines_for_matter_description(lines: list[str]) -> str:
    parts = [s.strip() for s in lines if (s or "").strip()]
    if not parts:
        return ""
    out = parts[0]
    for i in range(1, len(parts)):
        prev, cur = parts[i - 1], parts[i]
        prev_numeric = prev.isdigit()
        cur_numeric = cur.isdigit()
        sep = " " if (prev_numeric or cur_numeric) else ", "
        out += sep + cur
    return out


def build_matter_description(prefix: str | None, address_lines: list[str] | None = None) -> str:
    """Pre-fix (matter sub-type) + formatted UK address, same rules as the web UI."""
    pre = (prefix or "").strip()
    lines = address_lines if address_lines is not None else random_uk_address_lines()
    addr = join_address_lines_for_matter_description(lines)
    if pre and addr:
        return f"{pre} {addr}"
    if pre:
        return pre
    return addr
