"""Company logos for settlements, fetched once by this PC and cached in the data folder.

0. Known brands come from two free "tiny logo" sets: Super Tiny Icons (MIT, full colour) and Simple Icons
   (CC0, drawn in the brand's own colour). Crisp and consistent, but they're mostly tech brands, so:
1. Who is it? The defendant named in the summary ("CVS Pharmacy Inc. agreed to pay ..."), or the AI's company
   name, looked up on Wikidata (free, no key). Only business-like results count, so "CVS" never becomes a plant.
2. Where's the logo? The company's own app icon (apple-touch-icon) from its official website, then the logo
   file on Wikimedia Commons, then a large favicon. Nothing good enough: no logo, and the phone shows initials,
   because a wrong logo is worse than none.

Logos are trademarks of their owners; they're shown only to identify which company a settlement is about.
"""
import asyncio
import io
import json
import re
import time
from urllib.parse import quote, urljoin

import httpx
from PIL import Image

from .db import HOME

DIR = HOME / "logos"
SIZE = 192
UA = {"User-Agent": "ClaimScout/0.1 (+https://github.com/TheWiderLensInitiative/claimscout; settlement finder)"}
WIKIDATA = "https://www.wikidata.org/w/api.php"
_BIZ = re.compile(r"compan|corporat|\bbank|credit union|insur|health|hospital|medical|retail|manufactur|brand|agency|"
                  r"\bchain\b|pharmac|financial|automo|logistic|universit|software|provider|maker|\bfirm\b|store|"
                  r"conglomerate|business|enterprise|operator|\bgroup\b|organization|association|foundation|"
                  r"network|media|publisher|fitness|clothing|appliance|telemedicine|supermarket|insurer|bureau|"
                  r"cooperative|college|school|clinic|dental|airline|restaurant|casino|game|developer|lender|brokerage|"
                  r"utility|laborator|website|service|staffing|trucking|carrier", re.I)


def defendant(summary: str | None) -> str | None:
    """'CVS Pharmacy Inc. agreed to pay ...' -> 'CVS Pharmacy'."""
    m = re.match(r"\s*(.+?)\s+(?:has |have |will )?(?:agreed|agree|reached|will pay|is paying|settled)", summary or "")
    if not m:
        return None
    n = re.sub(r"\s*\([^)]*\)", "", m.group(1))
    n = re.split(r",?\s+and\s+|\s*,\s*(?=[A-Z])", n)[0]
    n = re.sub(r",?\s+(Inc|LLC|L\.L\.C|Corp|Corporation|Co|Company|Ltd|LP|L\.P|N\.A|PLC|Holdings?)\.?(\s.*)?$", "", n)
    n = re.sub(r"^(The|A)\s+", "", n).strip(" ,")
    return n if 1 < len(n) < 60 else None


# --- tiny logo sets -------------------------------------------------------------------------------------------
STI = "https://cdn.jsdelivr.net/gh/edent/SuperTinyIcons/images/svg/{}.svg"
STI_INDEX = "https://data.jsdelivr.com/v1/packages/gh/edent/SuperTinyIcons@master?structure=flat"
SI = "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{}.svg"
SI_INDEX = "https://cdn.jsdelivr.net/npm/simple-icons@latest/_data/simple-icons.json"
_GENERIC = {"access", "calendar", "email", "mail", "lock", "phone", "print", "pdf", "rss", "svg", "json", "markdown",
            "line", "ok", "go", "c", "r", "finder", "linux", "semantic", "opensource", "language"}
_index: dict | None = None


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("&", "and"))


def _si_slug(title: str) -> str:
    t = title.lower().replace("+", "plus").replace(".", "dot").replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", t)


async def _tiny_index(c) -> dict:
    """{"sti": {norm name: file}, "si": {norm title: (slug, hex)}}, cached on disk for a week."""
    global _index
    f = DIR / "tiny-index.json"
    if _index is None and f.exists() and time.time() - f.stat().st_mtime < 7 * 86400:
        _index = json.loads(f.read_text())
    if _index is None:
        _index = {"sti": {}, "si": {}}
        try:
            files = (await c.get(STI_INDEX)).json().get("files", [])
            for x in files:
                m = re.fullmatch(r"/images/svg/(.+)\.svg", x["name"])
                if m and m.group(1).lower() not in _GENERIC:
                    _index["sti"][_norm(m.group(1))] = m.group(1)
            data = (await c.get(SI_INDEX)).json()
            for x in data if isinstance(data, list) else data.get("icons", []):
                _index["si"][_norm(x["title"])] = (x.get("slug") or _si_slug(x["title"]), x.get("hex", "000000"))
            DIR.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(_index))
        except (httpx.HTTPError, ValueError, KeyError):
            pass   # offline: skip the tiny sets this time
    return _index


def _svg_png(svg: str) -> bytes | None:
    import resvg_py
    try:
        return _square_png(bytes(resvg_py.svg_to_bytes(svg_string=svg, width=512, height=512)))
    except Exception:
        return None


async def _tiny(c, keys: list[str]) -> bytes | None:
    idx = await _tiny_index(c)
    for k in dict.fromkeys(_norm(k) for k in keys if k):
        if len(k) < 3:
            continue
        try:
            if k in idx["sti"]:
                r = await c.get(STI.format(idx["sti"][k]))
                if r.status_code == 200 and (png := _svg_png(r.text)):
                    return png
            if k in idx["si"]:
                slug, hexc = idx["si"][k]
                r = await c.get(SI.format(slug))
                if r.status_code == 200:   # Simple Icons are one path with no colour: paint it the brand colour
                    if png := _svg_png(r.text.replace("<svg ", f'<svg fill="#{hexc}" ', 1)):
                        return png
        except httpx.HTTPError:
            continue
    return None


def _sld(site: str | None) -> str | None:
    """https://corporate.visa.com/x -> 'visa'."""
    host = re.sub(r"^https?://", "", site or "").split("/")[0]
    parts = host.split(".")
    return parts[-2] if len(parts) >= 2 else None


# --- Wikidata and the company's own site ---------------------------------------------------------------------
def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower().replace("’", "'").replace("'", ""))
            if w not in {"the", "of", "and", "inc", "co", "company", "corp", "group", "usa", "us"}}


class Busy(Exception):
    """Wikidata asked us to slow down; try the rest next refresh."""


_wd_gate = asyncio.Semaphore(1)
_wd_until = 0.0


async def _wikidata(c: httpx.AsyncClient, params: dict) -> dict:
    """One request at a time, a short pause between them, and a 10 minute break when told to slow down."""
    global _wd_until
    if time.time() < _wd_until:
        raise Busy()
    async with _wd_gate:
        r = await c.get(WIKIDATA, params=params)
        await asyncio.sleep(0.5)
    if r.status_code == 429 or "json" not in r.headers.get("content-type", ""):
        _wd_until = time.time() + 600
        raise Busy()
    return r.json()


async def _entity(c: httpx.AsyncClient, name: str) -> str | None:
    """A business whose name actually matches: every word of one name appears in the other."""
    found = await _wikidata(c, {"action": "wbsearchentities", "search": name, "language": "en",
                                "format": "json", "limit": 7, "type": "item"})
    want = _words(name)
    for h in found.get("search", []):
        got = _words(h.get("label", "")) | _words((h.get("match") or {}).get("text", ""))
        named = _words(h.get("label", ""))
        if _BIZ.search(h.get("description", "")) and want and (want <= got or (named and named <= want)):
            return h["id"]
    return None


def _us_first(url: str) -> tuple:
    """Prefer the US/international site: .com/.org/.edu/.gov, no country subdomain or path, shortest."""
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    tld_ok = host.endswith((".com", ".org", ".edu", ".gov", ".net", ".us"))
    return (not tld_ok, url.count("/") > 3, len(url))


async def _claims(c, qid) -> tuple[str | None, str | None]:
    """(official website, Commons logo file) of a Wikidata item."""
    cl = (await _wikidata(c, {"action": "wbgetclaims", "entity": qid, "format": "json"})).get("claims", {})
    def values(prop):
        return [v for s in cl.get(prop, []) if isinstance(v := s.get("mainsnak", {}).get("datavalue", {}).get("value"), str)]
    sites = sorted(values("P856"), key=_us_first)
    logos = values("P154")
    return (sites[0] if sites else None), (logos[0] if logos else None)


def _square_png(data: bytes, min_side=64) -> bytes | None:
    """Any image -> SIZE x SIZE PNG on white, logo centred with a margin. None if it's too small or not an image."""
    try:
        im = Image.open(io.BytesIO(data))
        if getattr(im, "n_frames", 1) > 1 or im.format == "ICO":
            im = max((im.copy() for _ in [0]), key=lambda x: x.size[0])   # ICO: Pillow opens the largest size
        im = im.convert("RGBA")
    except Exception:
        return None
    if min(im.size) < min_side:
        return None
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    inner = int(SIZE * (0.78 if abs(w - h) < max(w, h) * 0.15 else 0.86))
    k = inner / max(w, h)
    im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
    out = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))
    out.alpha_composite(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2))
    buf = io.BytesIO()
    out.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


async def _get_image(c, url, min_side=64) -> bytes | None:
    try:
        r = await c.get(url)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith(("image/", "application/octet")):
            return _square_png(r.content, min_side)
    except httpx.HTTPError:
        pass
    return None


async def _site_icon(c, site: str) -> bytes | None:
    """The site's own apple-touch-icon (a square brand icon, usually 180px), found the way a phone would."""
    for path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
        if png := await _get_image(c, urljoin(site, path), 120):
            return png
    try:
        r = await c.get(site)
        html = r.text[:400_000] if r.status_code == 200 else ""
    except httpx.HTTPError:
        html = ""
    links = re.findall(r"<link\b[^>]*>", html, re.I)
    cands = []
    for tag in links:
        rel = (re.search(r'rel=["\']([^"\']+)', tag, re.I) or [None, ""])[1].lower()
        href = (re.search(r'href=["\']([^"\']+)', tag, re.I) or [None, None])[1]
        if not href or "icon" not in rel or href.endswith(".svg"):
            continue
        size = int((re.search(r'sizes=["\'](\d+)', tag) or [0, 0])[1] or 0)
        cands.append((2 if "apple" in rel else 1, size, urljoin(str(r.url) if html else site, href)))
    for _, _, url in sorted(cands, reverse=True):
        if png := await _get_image(c, url, 96):
            return png
    return None


def _foreign(site: str) -> bool:
    return bool(re.search(r"\.(?!us/)[a-z]{2}/", re.sub(r"^https?://", "", site).split("/")[0] + "/"))


# Price-fixing cases are named after the product, not a company: no logo for "Turkey" or "Pork".
_PRODUCTS = {"turkey", "pork", "beef", "chicken", "broiler", "broilers", "salmon", "eggs", "egg", "milk", "dairy",
             "tuna", "peanuts", "potatoes", "sugar", "cheese", "drywall", "lumber", "opioids", "insulin", "generic"}


async def _guess_site(c, name: str) -> str | None:
    """'Teleflora' -> https://www.teleflora.com, but only if that page's title names the company."""
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower().replace("’", "").replace("'", ""))
             if w not in {"the", "inc", "llc", "co", "corp"}]
    if not words or len(words) > 4 or len("".join(words)) < 5 or \
            {"university", "college", "school", "schools", "county", "city", "state", "hospital", "department"} & set(words):
        return None   # institutions rarely live at name.com, and someone else often does
    for site in (f"https://www.{''.join(words)}.com", f"https://www.{'-'.join(words)}.com"):
        try:
            r = await c.get(site, timeout=8)
        except httpx.HTTPError:
            continue
        head = r.text[:60_000].lower() if r.status_code == 200 else ""
        names = re.findall(r"<title[^>]*>(.*?)</title>", head, re.S) + \
            re.findall(r"og:site_name[\"'][^>]*content=[\"']([^\"']+)", head)
        title = " ".join(" ".join(names).split())
        flat = re.sub(r"[^a-z0-9]", "", title)
        if flat and all(w in flat for w in words) and "domain" not in title and "for sale" not in title:
            return str(r.url).split("?")[0]
        if len(words) == 1:
            break
    return None


async def find(c: httpx.AsyncClient, names: list[str], domain: str | None = None) -> tuple[bytes | None, str | None]:
    """(png, website) for the first name that resolves to a company with a usable logo.
    Raises Busy when nothing was found but Wikidata couldn't be asked (so it's worth trying again later)."""
    sites, commons = [], None
    names = [n for n in names if n and not (_words(n) and _words(n) <= _PRODUCTS | {"prices", "price", "fixing", "pharmaceuticals", "drugs"})]
    if domain:
        sites.append("https://" + re.sub(r"^https?://|/.*$", "", domain))
    if png := await _tiny(c, names + [_sld(x) for x in sites]):
        return png, sites[0] if sites else None
    busy = False
    for n in names:
        if not n:
            continue
        try:
            qid = await _entity(c, n)
            if qid:
                site, commons = await _claims(c, qid)
                if site and _foreign(site):
                    site, commons = None, None   # Lincoln University (NZ) is not Lincoln University (Missouri)
                if site:
                    sites.append(site)
                break
        except Busy:
            busy = True
            break
    if not sites and not busy:
        for n in names[-1:]:   # the label: the company as the settlement names it
            if site := await _guess_site(c, n):
                sites.append(site)
    if sites and (png := await _tiny(c, [_sld(x) for x in sites])):
        return png, sites[0] if sites else None
    for site in dict.fromkeys(sites):
        if _foreign(site):
            continue   # a foreign site (whirlpool.co.jp) often has a different local brand
        if png := await _site_icon(c, site):
            return png, site
    if commons:
        url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(commons)}?width=512"
        if png := await _get_image(c, url, 64):
            return png, sites[0] if sites else None
    if busy:
        raise Busy()
    return None, sites[0] if sites else None


async def resolve(db, limit=200, log=print) -> int:
    """Find logos for settlements that haven't been tried yet. Returns how many got one."""
    rows = db.q("""SELECT id, title, summary, label, company, domain FROM settlements WHERE logo IS NULL
                   AND (deadline IS NULL OR deadline >= date('now')) LIMIT ?""", (limit,))
    if not rows:
        return 0
    DIR.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(4)
    found = 0
    async with httpx.AsyncClient(timeout=15, headers=UA, follow_redirects=True) as c:
        async def one(s):
            nonlocal found
            async with sem:
                try:
                    png, site = await find(c, [s["company"], defendant(s["summary"]), s["label"]], s["domain"])
                except Busy:
                    return   # left untried; the next refresh asks again
                except Exception as e:   # one company's broken site must not stop the rest
                    log(f"logo {s['id']}: {e}")
                    png, site = None, None
                name = ""
                if png:
                    key = re.sub(r"[^a-z0-9]+", "-", (site or s["id"]).lower()).strip("-")[:80] + ".png"
                    (DIR / key).write_bytes(png)
                    name, found = key, found + 1
                db.x("UPDATE settlements SET logo=?, domain=COALESCE(domain, ?) WHERE id=?",
                     (name, re.sub(r"^https?://(www\.)?|/.*$", "", site) if site else None, s["id"]))
        await asyncio.gather(*(one(s) for s in rows))
    return found
