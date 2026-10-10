"""Small text helpers: HTML to text, dates, US states."""
import datetime as dt
import html
import re

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}
_BY_NAME = {v.lower(): k for k, v in STATES.items()}
# "Washington" alone is usually the state, but not in "Washington, D.C."; longest names first so
# "West Virginia" isn't read as "Virginia".
_STATE_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(n) for n in STATES.values()), key=len, reverse=True)) + r")\b")

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def html_to_text(s: str) -> str:
    s = re.sub(r"<(script|style)\b.*?</\1>", "", s or "", flags=re.S | re.I)
    s = re.sub(r"<(br|/p|/li|/h\d|/div|/tr)\b[^>]*>", "\n", s, flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = s.replace("\xa0", " ")
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", s)).strip()


def parse_date(s: str):
    """'11/25/2026', 'Nov. 25, 2026', 'November 25, 2026', '2026-11-25' -> '2026-11-25' (or None)."""
    s = (s or "").strip()
    if m := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s):
        y, mo, d = map(int, m.groups())
    elif m := re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", s):
        mo, d, y = map(int, m.groups())
        y += 2000 if y < 100 else 0
    elif m := re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", s):
        mo = MONTHS.get(m.group(1)[:3].lower())
        if not mo:
            return None
        d, y = int(m.group(2)), int(m.group(3))
    else:
        return None
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def all_dates(s: str):
    pat = r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|[A-Z][a-z]{2,8}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{4}-\d{2}-\d{2})\b"
    return [d for d in (parse_date(x) for x in re.findall(pat, s or "")) if d]


def states_in(text: str):
    """States a class is limited to, read from eligibility text ('Illinois residents who ...').

    Only counts a state when the text ties people to it (residents, lived, in <state>), so 'a California
    company' doesn't limit a nationwide class. Returns [] for nationwide/unknown.
    """
    t = re.sub(r"Washington,?\s+D\.?C\.?", "District of Columbia", text or "")
    found = []
    for m in _STATE_RE.finditer(t):
        name = m.group(1)
        before, after = t[max(0, m.start() - 40):m.start()].lower(), t[m.end():m.end() + 25].lower()
        if re.search(r"\b(residents?|citizens?|consumers|persons|people|individuals|customers|purchasers|insureds|policyholders|homeowners|drivers|students|employees|workers|patients|subscribers|users)\b", after) \
                or re.search(r"\b(in|of|resided in|lived in|reside in|live in|located in|residing in)\s+(the state of\s+)?$", before):
            code = _BY_NAME[name.lower()]
            if code not in found:
                found.append(code)
    return found


def max_amount(award: str | None) -> float | None:
    """The most one person could get: 'Up to $5,000' -> 5000, 'Estimated $25 to $95' -> 95, '$1.2K' -> 1200.
    Settlement totals ('$20M fund') are ignored; None when no per-person dollar figure is given."""
    best = None
    for num, unit in re.findall(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|m|million|b|billion)?\b", award or "", re.I):
        v = float(num.replace(",", ""))
        unit = (unit or "").lower()
        if unit in ("m", "million", "b", "billion"):
            continue
        if unit in ("k", "thousand"):
            v *= 1000
        if v <= 100_000:
            best = max(best or 0, v)
    return best
