"""ClassAction.org's public settlements page (https://www.classaction.org/settlements).

One page lists every open settlement as a card: name, payout range, deadline, "Proof Required?", a one-line
summary and the official settlement website. We keep those and link back to the card.
"""
import re

import httpx

from ..text import html_to_text, parse_date, states_in
from .topclassactions import UA

PAGE = "https://www.classaction.org/settlements"


def _field(card: str, label: str) -> str | None:
    m = re.search(label + r"</span>\s*<span[^>]*>(.*?)</span>", card, re.S)
    v = html_to_text(m.group(1)).strip() if m else ""
    return None if v.lower() in ("", "n/a", "varies", "tbd") else v


def parse_card(card: str) -> dict | None:
    slug = re.search(r'<div id="([^"]+)" data-name="([^"]*)"', card)
    link = re.search(r'class="js-settlement-link[^"]*"[^>]*href="(https?://[^"]+)"', card) or \
        re.search(r'href="(https?://[^"]+)"[^>]*class="js-settlement-link', card)
    if not slug or not link:
        return None
    name = html_to_text(slug.group(2)).strip()
    title = re.search(r'class="js-settlement-link[^>]*>([^<]+)</a>', card)
    deadline_text = _field(card, "Deadline") or ""
    deadline = None
    if m := re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})$", deadline_text):
        mo, d, y = (int(x) for x in m.groups())
        deadline = f"{y + 2000 if y < 100 else y:04d}-{mo:02d}-{d:02d}"
    proof = _field(card, r"Proof <br>Required\?")
    summary = re.search(r'<p class="f6[^"]*">(.*?)</p>', card, re.S)
    summary = html_to_text(summary.group(1)).strip() if summary else ""
    return {
        "id": "cao:" + slug.group(1),
        "source": "ClassAction.org",
        "title": re.sub(r"\s+class action settlement$", "", html_to_text(title.group(1)).strip() if title else name,
                        flags=re.I) or name,
        "url": f"{PAGE}#{slug.group(1)}",
        "summary": summary[:600],
        "eligibility": summary,
        "award": _field(card, r"Settlement<br>\s*Payout"),
        "proof": proof,
        "proof_needed": {"no": 0, "yes": 1}.get((proof or "").lower()),
        "claim_url": link.group(1),
        "website": link.group(1),
        "deadline": deadline or parse_date(deadline_text),
        "case_name": None,
        "states": states_in(summary),
        "published": None,
    }


def parse_page(html: str) -> list[dict]:
    cards = re.split(r'(?=<div id="[^"]+" data-name=)', html)[1:]
    return [s for s in (parse_card(c) for c in cards) if s]


async def fetch(client: httpx.AsyncClient | None = None) -> list[dict]:
    own = client is None
    client = client or httpx.AsyncClient(timeout=60, headers={"User-Agent": UA}, follow_redirects=True)
    try:
        r = await client.get(PAGE)
        r.raise_for_status()
        return parse_page(r.text)
    finally:
        if own:
            await client.aclose()
