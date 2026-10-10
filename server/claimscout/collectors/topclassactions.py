"""Top Class Actions' public RSS feed of open settlements.

Each post ends with a details box (Who's Eligible, Proof of Purchase, Claim Form, Claim Form Deadline, ...).
We keep those fields and the administrator's claim link, and always link back to the post.
"""
import re
import xml.etree.ElementTree as ET

import httpx

from ..text import html_to_text, parse_date, states_in

FEED = "https://topclassactions.com/category/lawsuit-settlements/open-lawsuit-settlements/feed/"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
UA = "ClaimScout/0.1 (+https://github.com/TheWiderLensInitiative/claimscout; personal settlement finder)"

_LABELS = {
    "who’s eligible": "eligibility", "who's eligible": "eligibility",
    "potential award": "award", "proof of purchase": "proof",
    "claim form": "claim_form", "claim form deadline": "deadline_text",
    "case name": "case_name", "settlement website": "website",
}


def parse_item(item: ET.Element) -> dict | None:
    body = item.findtext(CONTENT) or ""
    link = (item.findtext("link") or "").strip()
    slug = link.rstrip("/").rsplit("/", 1)[-1] or item.findtext("guid")
    # The box: <h6>Label</h6> ... value ... <h6>Next label</h6>
    parts = re.split(r"<h6[^>]*>(.*?)</h6>", body, flags=re.S)
    fields = {}
    for label, value in zip(parts[1::2], parts[2::2]):
        key = _LABELS.get(html_to_text(label).strip().lower())
        if key and key not in fields:
            fields[key] = value
    if "deadline_text" not in fields and "claim_form" not in fields:
        return None   # a news post, not a settlement with a claim
    claim_url = None
    if cf := fields.get("claim_form"):
        if m := re.search(r'<a\b[^>]*href="(https?://[^"]+)"', cf):
            claim_url = m.group(1)
    website = html_to_text(fields.get("website", "")).split("\n")[0].strip() or None
    if website and not website.startswith("http"):
        website = "https://" + website
    eligibility = html_to_text(fields.get("eligibility", ""))
    proof = html_to_text(fields.get("proof", ""))
    intro = html_to_text(body.split("<h6", 1)[0])
    intro = re.sub(r"^\(Photo Credit:[^)]*\)\s*", "", intro)
    return {
        "id": "tca:" + slug,
        "source": "Top Class Actions",
        "title": re.sub(r"\s+class action settlement$", "", (item.findtext("title") or "").strip(), flags=re.I) or slug,
        "url": link,
        "summary": intro.split("\n")[0][:600],
        "eligibility": eligibility,
        "award": html_to_text(fields.get("award", "")) or None,
        "proof": proof or None,
        "proof_needed": _proof_needed(proof),
        "claim_url": claim_url,
        "website": website,
        "deadline": parse_date(html_to_text(fields.get("deadline_text", ""))),
        "case_name": html_to_text(fields.get("case_name", "")) or None,
        "states": states_in(eligibility),
        "published": item.findtext("pubDate"),
    }


def _proof_needed(proof: str):
    p = proof.strip().lower()
    if not p:
        return None
    if p in {"n/a", "na", "none", "no", "not required"} or p.startswith(("n/a", "no proof", "none")):
        return 0
    return 1


def parse_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    return [s for s in (parse_item(i) for i in root.iter("item")) if s]


async def fetch(pages: int = 3, client: httpx.AsyncClient | None = None) -> list[dict]:
    """Newest settlements first. Each page is ~75 posts; older pages are mostly closed."""
    out = []
    own = client is None
    client = client or httpx.AsyncClient(timeout=60, headers={"User-Agent": UA}, follow_redirects=True)
    try:
        for page in range(1, pages + 1):
            r = await client.get(FEED, params={"paged": page} if page > 1 else None)
            if r.status_code == 404:
                break
            r.raise_for_status()
            out += parse_feed(r.text)
    finally:
        if own:
            await client.aclose()
    return out
