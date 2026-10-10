"""OpenClassActions.com's open settlements directory (https://openclassactions.com/settlements.php).

The directory row has the name, a one-line payout summary, proof badge, deadline, category and the states it is
limited to. The official claim link is only on each settlement's own page, so we read that page once per new
settlement and reuse the link afterwards. Automatic payments (nothing to file), Canadian cases and securities
cases (brokerage records, not consumers) are left out.
"""
import asyncio
import re

import httpx

from ..text import html_to_text, states_in
from .topclassactions import UA

PAGE = "https://openclassactions.com/settlements.php"
SKIP_CATEGORIES = {"securities"}


def _attr(row: str, name: str) -> str:
    m = re.search(name + r'="([^"]*)"', row)
    return html_to_text(m.group(1)).strip() if m else ""


def parse_row(row: str) -> dict | None:
    href = re.search(r'href="(https://(?:www\.)?openclassactions\.com/[^"]+)"', row)
    name = re.search(r'class="dir-name"[^>]*>(.*?)</span>', row, re.S)
    if not href or not name:
        return None
    title = html_to_text(name.group(1)).strip()
    details = re.search(r'class="dir-details"[^>]*>(.*?)</span>', row, re.S)
    details = html_to_text(details.group(1)).strip() if details else ""
    proof, category, region = _attr(row, "data-proof"), _attr(row, "data-category"), _attr(row, "data-region")
    if proof == "automatic" or category.lower() in SKIP_CATEGORIES or \
            re.search(r"\bCA-[A-Z]{2}\b", region) or re.search(r"\b(Canada|Canadian|CAD|Quebec|Ontario|British Columbia)\b", title):
        return None
    badge = re.search(r'class="badge[^"]*">([^<]*)', row)
    slug = href.group(1).rstrip("/").rsplit("/", 1)[-1].removesuffix(".php")
    return {
        "id": "oca:" + slug,
        "source": "OpenClassActions",
        "title": re.sub(r"\s+class action settlement$", "", title, flags=re.I),
        "url": href.group(1),
        "summary": details[:600],
        "eligibility": details,
        "award": details if "$" in details else None,
        "proof": html_to_text(badge.group(1)).strip() if badge else None,
        "proof_needed": {"none": 0, "required": 1}.get(proof),
        "claim_url": None,
        "website": None,
        "deadline": _attr(row, "data-deadline") or None,
        "case_name": None,
        "states": sorted(set(re.findall(r"\bUS-([A-Z]{2})\b", region))) or states_in(details),
        "published": _attr(row, "data-added") or None,
    }


def parse_page(html: str) -> list[dict]:
    return [s for s in (parse_row(r) for r in re.findall(r'<a class="dir-row".*?</a>', html, re.S)) if s]


def claim_link(html: str) -> str | None:
    """The page's "File Claim" button, else its official website link, without the tracking tag."""
    for pat in (r'href="(https?://[^"]+)"[^>]*>\s*File Claim', r'Official (?:settlement )?website[^<]*<a[^>]*href="(https?://[^"]+)"',
                r'href="(https?://[^"]+)"[^>]*>\s*Official Website'):
        if m := re.search(pat, html, re.I):
            url = re.sub(r"[?&]utm_source=openclassactions\.com$", "", m.group(1).replace("&amp;", "&"))
            if "openclassactions.com" not in url:
                return url
    return None


async def fetch(known: dict | None = None, client: httpx.AsyncClient | None = None) -> list[dict]:
    """known: {id: claim_url} already stored, so each settlement page is read only once."""
    known = known or {}
    own = client is None
    client = client or httpx.AsyncClient(timeout=60, headers={"User-Agent": UA}, follow_redirects=True)
    gate = asyncio.Semaphore(4)

    async def link(s):
        if known.get(s["id"]):
            s["claim_url"] = known[s["id"]]
            return
        async with gate:
            try:
                r = await client.get(s["url"])
                if r.status_code == 200:
                    s["claim_url"] = claim_link(r.text)
            except httpx.HTTPError:
                pass   # try again next refresh

    try:
        r = await client.get(PAGE)
        r.raise_for_status()
        rows = parse_page(r.text)
        await asyncio.gather(*(link(s) for s in rows))
        for s in rows:
            s["website"] = s["claim_url"]
        return rows
    finally:
        if own:
            await client.aclose()
