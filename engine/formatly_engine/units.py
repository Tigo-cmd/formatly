"""Length units.

Word stores lengths in twips (1/20 pt) and EMUs (1/914400 in). Rulebooks use
human units ("1in", "2.54cm", "12pt"). Everything inside the engine is in
twips.
"""

from __future__ import annotations

import re

TWIPS_PER_INCH = 1440
TWIPS_PER_PT = 20
TWIPS_PER_CM = TWIPS_PER_INCH / 2.54
EMU_PER_TWIP = 635

_LENGTH = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(in|inch|inches|cm|mm|pt|twip|twips)?\s*$", re.I)


def parse_length(value: str | int | float) -> int:
    """Parse "1in", "2.54cm", "25mm", "72pt" into twips. Bare numbers are points."""
    if isinstance(value, (int, float)):
        return round(value * TWIPS_PER_PT)
    m = _LENGTH.match(value)
    if not m:
        raise ValueError(f"not a length: {value!r} (use e.g. '1in', '2.54cm', '12pt')")
    n = float(m.group(1))
    unit = (m.group(2) or "pt").lower()
    if unit.startswith("in"):
        return round(n * TWIPS_PER_INCH)
    if unit == "cm":
        return round(n * TWIPS_PER_CM)
    if unit == "mm":
        return round(n * TWIPS_PER_CM / 10)
    if unit.startswith("twip"):
        return round(n)
    return round(n * TWIPS_PER_PT)


def emu_to_twips(emu: int | None) -> int | None:
    return None if emu is None else round(emu / EMU_PER_TWIP)


def twips_to_emu(twips: int) -> int:
    return twips * EMU_PER_TWIP


def fmt_length(twips: int | None) -> str:
    """Show a length the way people talk about it: inches and centimetres."""
    if twips is None:
        return "not set"
    inches = twips / TWIPS_PER_INCH
    cm = twips / TWIPS_PER_CM
    return f"{inches:.2f} in ({cm:.2f} cm)"


def fmt_pt(twips: int | None) -> str:
    if twips is None:
        return "not set"
    pt = twips / TWIPS_PER_PT
    return f"{pt:g} pt"
