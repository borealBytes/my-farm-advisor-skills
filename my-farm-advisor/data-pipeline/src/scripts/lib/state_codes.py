"""US state FIPS codes shared by boundary ingest and farm orchestration."""

from __future__ import annotations

# FIPS -> (USPS abbreviation, state name)
US_STATE_FIPS: dict[str, tuple[str, str]] = {
    "01": ("AL", "Alabama"),
    "02": ("AK", "Alaska"),
    "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"),
    "06": ("CA", "California"),
    "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"),
    "10": ("DE", "Delaware"),
    "11": ("DC", "District of Columbia"),
    "12": ("FL", "Florida"),
    "13": ("GA", "Georgia"),
    "15": ("HI", "Hawaii"),
    "16": ("ID", "Idaho"),
    "17": ("IL", "Illinois"),
    "18": ("IN", "Indiana"),
    "19": ("IA", "Iowa"),
    "20": ("KS", "Kansas"),
    "21": ("KY", "Kentucky"),
    "22": ("LA", "Louisiana"),
    "23": ("ME", "Maine"),
    "24": ("MD", "Maryland"),
    "25": ("MA", "Massachusetts"),
    "26": ("MI", "Michigan"),
    "27": ("MN", "Minnesota"),
    "28": ("MS", "Mississippi"),
    "29": ("MO", "Missouri"),
    "30": ("MT", "Montana"),
    "31": ("NE", "Nebraska"),
    "32": ("NV", "Nevada"),
    "33": ("NH", "New Hampshire"),
    "34": ("NJ", "New Jersey"),
    "35": ("NM", "New Mexico"),
    "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"),
    "38": ("ND", "North Dakota"),
    "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"),
    "41": ("OR", "Oregon"),
    "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"),
    "45": ("SC", "South Carolina"),
    "46": ("SD", "South Dakota"),
    "47": ("TN", "Tennessee"),
    "48": ("TX", "Texas"),
    "49": ("UT", "Utah"),
    "50": ("VT", "Vermont"),
    "51": ("VA", "Virginia"),
    "53": ("WA", "Washington"),
    "54": ("WV", "West Virginia"),
    "55": ("WI", "Wisconsin"),
    "56": ("WY", "Wyoming"),
}

STATE_ABBR_TO_FIPS: dict[str, str] = {
    abbr: fips for fips, (abbr, _name) in US_STATE_FIPS.items()
}
STATE_NAME_TO_FIPS: dict[str, str] = {
    name.casefold(): fips for fips, (_abbr, name) in US_STATE_FIPS.items()
}


def state_fips(state: object | None) -> str:
    """Resolve ``IL`` / ``Illinois`` (or an existing FIPS code) to ``"17"``.

    Returns an empty string when the value cannot be resolved so callers can
    decide whether to skip the row or fail.
    """

    value = str(state or "").strip()
    if not value:
        return ""
    if value.isdigit() and len(value) <= 2:
        return value.zfill(2)
    return (
        STATE_ABBR_TO_FIPS.get(value.upper())
        or STATE_NAME_TO_FIPS.get(value.casefold())
        or ""
    )
