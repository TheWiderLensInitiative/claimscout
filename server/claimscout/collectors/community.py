"""Community settlement lists: plain JSON files anyone can host (a GitHub repo works).

Format: a JSON array (or {"settlements": [...]}) of objects with at least "id", "title" and one of
"claim_url"/"website". Optional: eligibility, award, proof, proof_needed, deadline (YYYY-MM-DD), case_name,
states (["CA"]), summary, url. Ids are prefixed with "c:" so they can't collide with built-in sources.
"""
import re

import httpx

from ..text import parse_date, states_in

ALLOWED = {"title", "url", "summary", "eligibility", "award", "proof", "proof_needed", "claim_url", "website",
           "deadline", "case_name", "states"}


def normalize(raw: dict, source: str) -> dict | None:
    if not isinstance(raw, dict) or not raw.get("id") or not raw.get("title"):
        return None
    s = {k: raw.get(k) for k in ALLOWED}
    for k in ("claim_url", "website", "url"):
        if s[k] and not re.match(r"https?://", str(s[k])):
            s[k] = None   # never store javascript:/file: links that the phone would open
    if not (s["claim_url"] or s["website"]):
        return None
    s["id"] = "c:" + re.sub(r"[^a-z0-9-]+", "-", str(raw["id"]).lower())[:120]
    s["source"] = source
    s["deadline"] = parse_date(str(s["deadline"] or ""))
    s["states"] = [x.upper() for x in s["states"] if isinstance(x, str)][:60] if isinstance(s["states"], list) \
        else states_in(s.get("eligibility") or "")
    if s["proof_needed"] not in (0, 1, None):
        s["proof_needed"] = 1 if s["proof_needed"] else 0
    for k in ALLOWED - {"states", "proof_needed"}:
        if s[k] is not None:
            s[k] = str(s[k])[:4000]
    return s


async def fetch(url: str, client: httpx.AsyncClient | None = None) -> list[dict]:
    own = client is None
    client = client or httpx.AsyncClient(timeout=60, follow_redirects=True)
    try:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    finally:
        if own:
            await client.aclose()
    rows = data.get("settlements", []) if isinstance(data, dict) else data
    host = re.sub(r"^https?://([^/]+).*", r"\1", url)
    return [s for s in (normalize(x, f"Community ({host})") for x in rows or []) if s]
