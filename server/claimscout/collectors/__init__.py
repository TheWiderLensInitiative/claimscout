"""Settlement sources, and merging the same settlement listed by several of them."""
import re

# Sites that list many settlements: their address doesn't identify one settlement.
_SHARED_HOSTS = ("topclassactions.com", "classaction.org", "openclassactions.com", "google.com", "bit.ly",
                 "epiqglobal.com", "kroll.com", "angeiongroup.com", "jndla.com", "simpluris.com", "gilardi.com",
                 "cptgroup.com", "atticusadmin.com", "veritaglobal.com", "kccllc.net", "ilymgroup.com", "rustconsulting.com",
                 "abdata.com", "analyticsllc.com", "apexclassaction.com", "settlementadministrator.com")
_FILLER = {"settlement", "settlements", "class", "action", "lawsuit", "the", "and", "inc", "llc", "co", "corp",
           "company", "data", "breach", "security", "incident", "privacy", "for", "of", "a", "an", "to", "in",
           "up", "per", "million", "cash", "payment", "payments", "automatic", "claim", "claims"}


def site_key(url: str | None, shared: set | frozenset = frozenset()) -> str | None:
    """The settlement's own website, e.g. 'landsenddatasettlement.com'. On a portal shared by many settlements
    (an administrator's claim forms) the whole path is needed to tell them apart."""
    m = re.match(r"https?://(?:www\.)?([^/?#]+)(/[^?#]*)?", (url or "").strip(), re.I)
    if not m:
        return None
    host, path = m.group(1).lower(), (m.group(2) or "").strip("/").lower()
    if any(host == h or host.endswith("." + h) for h in ("topclassactions.com", "classaction.org", "openclassactions.com")):
        return None
    if host in shared or any(host == h or host.endswith("." + h) for h in _SHARED_HOSTS):
        return f"{host}/{path}" if path else None
    return host


def _keys(s: dict, shared) -> set:
    return {site_key(s.get("claim_url"), shared), site_key(s.get("website"), shared)} - {None}


def name_words(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", re.sub(r"\$[\d.,]+\s*[kmb]?", " ", (title or "").lower().replace("’", "'").replace("'", "")))
    return {w for w in words if w not in _FILLER and not w.isdigit() and len(w) > 1}


def same(a: dict, b: dict, shared=frozenset()) -> bool:
    if _keys(a, shared) & _keys(b, shared):
        return True
    # No shared address: same deadline and nearly the same name ("Lands' End - Data Breach" / "Lands' End Data Breach $8M")
    if a.get("deadline") and a.get("deadline") == b.get("deadline"):
        wa, wb = name_words(a.get("title")), name_words(b.get("title"))
        return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6
    return False


def merge(lists: list[list[dict]]) -> tuple[list[dict], dict]:
    """Earlier lists win (they have the most detail). Returns (kept, {dropped id: kept id}).
    A later listing still fills in what the kept one is missing (claim link, payout, proof, deadline)."""
    # a host that several settlements of one source point to is a shared portal, not one settlement's site
    shared = set()
    for rows in lists:
        seen = {}
        for s in rows:
            for k in _keys(s, ()):
                if seen.setdefault(k, s["id"]) != s["id"]:
                    shared.add(k)
    kept, dropped, by_key, origin = [], {}, {}, {}
    for n, rows in enumerate(lists):
        for s in rows:
            keys = _keys(s, shared)
            match = next((by_key[k] for k in keys if k in by_key and origin[by_key[k]["id"]] != n), None) or \
                next((k for k in kept if origin[k["id"]] != n and s.get("deadline") and same(k, s, shared)), None)
            if match is None:
                origin[s["id"]] = n
                kept.append(s)
                match = s
            elif match is not s:
                dropped[s["id"]] = match["id"]
                for f in ("claim_url", "website", "award", "proof", "deadline", "case_name"):
                    if not match.get(f) and s.get(f):
                        match[f] = s[f]
                if match.get("proof_needed") is None and s.get("proof_needed") is not None:
                    match["proof_needed"] = s["proof_needed"]
                if not match.get("states") and s.get("states"):
                    match["states"] = s["states"]
            for k in _keys(match, shared) | keys:
                if k:
                    by_key.setdefault(k, match)
    return kept, dropped
