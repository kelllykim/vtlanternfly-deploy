"""Virginia Tech program catalog shared by registration UI and validation."""
import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).parent / "data" / "vt_majors.json").read_text())
MAJORS = CATALOG["majors"]
_CANONICAL = {major.casefold(): major for major in MAJORS}


def validate_major(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    canonical = _CANONICAL.get(value.strip().casefold())
    if canonical is None:
        raise ValueError("Choose a major from Virginia Tech’s official program list")
    return canonical
